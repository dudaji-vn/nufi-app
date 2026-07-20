# Team Workspaces — Self-Service Collaboration & Shared Knowledge (RAG)

## 1. Objective

Let an end user create a **team**, invite other members, and share resources within
that team — agents, prompt groups, and most importantly a **shared RAG knowledge base**
(uploaded files / documents the whole team can query). The goal is a self-service
collaboration layer that requires no admin involvement for day-to-day team management.

## 2. Current platform state

We have already built the permission and grouping foundation that this feature stands on.
What is in place today:

| Capability | Status | Where |
|---|---|---|
| Group entity with membership (`memberIds`, local/Entra source, tenant-aware) | **Done** | `packages/data-schemas/src/schema/group.ts`, `methods/userGroup.ts` |
| ACL permission engine — grant / check / effective permissions | **Done** | `api/server/services/PermissionService.js`, `schema/aclEntry.ts` |
| First-class **GROUP** principal in the ACL (share any resource with a group) | **Done** | `packages/data-provider/src/accessPermissions.ts` (`PrincipalType.GROUP`) |
| Resource sharing for Agents, Prompt Groups, MCP servers, Skills (user / group / public) | **Done** | `api/server/routes/accessPermissions.js`, `controllers/PermissionsController.js` |
| Permission bits VIEW / EDIT / DELETE / SHARE + named access roles (viewer/editor/owner) | **Done** | `accessPermissions.ts`, `schema/accessRole.ts` |
| People-picker + sharing UI components | **Done** | `client/src/components/Sharing/*`, `client/src/hooks/Sharing/*` |
| RBAC (system roles ADMIN/USER + per-feature interface permissions) | **Done** | `schema/role.ts`, `packages/data-provider/src/permissions.ts` |

**Key consequence:** because the ACL engine already treats a group as a principal, *granting
a resource to a team is already solved* — it is one `grantPermission({ principalType: GROUP, principalId: <teamGroupId> })`
call. We do **not** need to build a new sharing engine. The remaining work is the self-service
layer on top, plus closing the one resource gap below (files).

## 3. What the current system does **not** yet support (the gap)

1. **Self-service team creation.** Group create/update/delete and membership changes are
   admin-only today (`api/server/routes/admin/groups.js`, gated by `SystemCapabilities.MANAGE_GROUPS`).
   A regular user cannot create a team.
2. **Invitations.** There is no invite/accept flow. Membership is a direct admin assignment;
   there is no consent step, no email invite, no pending-invite concept.
3. **Team ownership & roles.** A group has a flat `memberIds` list with no owner and no
   per-member role (owner / admin / member).
4. **Direct file (RAG) sharing.** Uploaded files are per-user (`schema/file.ts`, required
   `user` field) and the ACL has **no** `ResourceType.FILE`. A file can only be shared
   *indirectly* by attaching it to a shared agent (`api/server/services/Files/permissions.js:hasAccessToFilesViaAgent`).
   There is no way to share a knowledge base with a team directly.
5. **End-user team UI.** No surface for a user to create/manage a team or its shared knowledge.

The plan below builds exactly these five missing pieces.

## 4. Design approach

**A team is a Group.** We extend the existing `Group` model (with `source: 'local'`) to carry
ownership and per-member roles, rather than introducing a parallel `Team` entity. This means
sharing-to-a-team reuses the ACL `GROUP` principal with zero new plumbing, and teams inherit
tenant isolation and the existing people-picker.

**Shared RAG = files granted to the team's group.** We add `ResourceType.FILE` to the ACL and
register files as an ACL-governed resource. A team's knowledge base is then simply the set of
files with a `GROUP` ACL grant to that team. RAG retrieval is extended so a member's accessible
file set is `owned ∪ team-shared ∪ agent-inherited`.

**Self-service, role-gated.** New user-facing endpoints (not behind admin capabilities) let a
user create a team and manage it, authorized by their **role within that team** rather than a
global admin capability.

```
User ──creates──► Team (= local Group + ownerId + member roles)
       │
       ├─ invites member ──► TeamInvite (token, email, role, pending) ──► accept ──► addUserToGroup
       │
       └─ adds knowledge ──► File + ACL grant {GROUP: teamGroupId, perm: FILE_VIEWER}
                                    │
                                    └─► every member's RAG queries include these file_ids
```

## 5. Phased implementation plan

Phases are ordered so each is independently shippable and testable. File paths are concrete;
unless noted, backend work is in the `dudaji-vn/nufichat` fork (`develop` branch), and the
`@librechat/data-schemas` package must be rebuilt (`npm run build` in `packages/data-schemas`)
after schema/method changes.

### Phase 0 — Data model

**Goal:** model team ownership, roles, and invites.

- Extend `packages/data-schemas/src/schema/group.ts`:
  - `ownerId: { type: ObjectId, ref: 'User', index: true }`
  - `members: [{ userId: ObjectId, role: 'owner'|'admin'|'member', joinedAt: Date }]`
    (keep `memberIds` in sync on every write so existing ACL/Entra paths keep working).
  - `kind: { type: String, enum: ['group','team'], default: 'group', index: true }`
    to distinguish self-service teams from admin/Entra groups.
  - `joinPolicy: { type: String, enum: ['invite'], default: 'invite' }` (room for `request`/`open` later).
- New schema `packages/data-schemas/src/schema/teamInvite.ts`: `groupId` (ref Group),
  `email`, `invitedUserId` (nullable), `role`, `token` (unique), `status`
  (`pending|accepted|declined|expired|revoked`), `invitedBy`, `expiresAt`, `tenantId`,
  timestamps. Indexes on `token`, `(email, status)`, `(groupId, status)`.
- Register the model in `packages/data-schemas/src/models/index.ts`
  (`TeamInvite: createTeamInviteModel(mongoose)`) and add `IGroup`/`ITeamInvite` type updates
  in `packages/data-schemas/src/types/`.
- Methods:
  - Extend `methods/userGroup.ts` with `setMemberRole`, `getTeamRole(userId, groupId)`,
    `transferOwnership`, and team-filtered `getUserTeams`.
  - New `methods/teamInvite.ts`: `createInvite`, `findInviteByToken`, `listPendingInvitesForUser`,
    `listInvitesForTeam`, `acceptInvite`, `declineInvite`, `revokeInvite`, `expireStaleInvites`.

**Acceptance:** schema builds; unit tests for invite lifecycle and role helpers pass; `memberIds`
stays consistent with `members` on add/remove.

### Phase 1 — Self-service Team API

**Goal:** users create and manage teams without admin rights.

- New route `api/server/routes/teams.js`, mounted in `api/server/routes/index.js`. Guarded by
  `requireJwtAuth` + `checkBan` (NOT an admin capability). Endpoints:
  - `POST /api/teams` — create team; creator becomes `owner` (reuses `db.createGroup`, sets
    `kind:'team'`, `ownerId`, adds creator to `members`).
  - `GET /api/teams` — teams the current user belongs to (`getUserTeams`).
  - `GET /api/teams/:id` — details + members + roles (member-only).
  - `PATCH /api/teams/:id` — name/description/avatar (owner/admin).
  - `DELETE /api/teams/:id` — owner only; cascades: remove the group's ACL grants
    (`removeAllPermissions` for principal = group), delete invites, delete group.
  - `GET /api/teams/:id/members`, `DELETE /api/teams/:id/members/:userId` (owner/admin, or self-leave),
    `PATCH /api/teams/:id/members/:userId` (change role, owner/admin).
- New middleware `api/server/middleware/teams/requireTeamRole.js` — resolves caller's role in the
  team and enforces a minimum (`owner` > `admin` > `member`). Last-owner protection (cannot
  leave/demote the only owner).
- Controller `api/server/controllers/TeamsController.js` wrapping the data methods.

**Acceptance:** a non-admin user can create a team, see it listed, rename it, add/remove members
(once invited), leave it, and delete a team they own; role checks enforced; integration tests green.

### Phase 2 — Invitations

**Goal:** consented membership via invite → accept.

- Endpoints (on `teams.js`):
  - `POST /api/teams/:id/invites` — owner/admin invites by email with a role; creates `TeamInvite`
    + token; sends email via the existing mailer (`api/server/utils` / `sendEmail`) with a deep
    link `/${appUrl}/teams/invite/:token`.
  - `GET /api/teams/invites` — pending invites for the current user (match by `invitedUserId` or
    verified email).
  - `POST /api/teams/invites/:token/accept` — validates token + expiry, `addUserToGroup`, sets
    role, marks `accepted`.
  - `POST /api/teams/invites/:token/decline`.
  - `DELETE /api/teams/:id/invites/:inviteId` — revoke (owner/admin).
- Background sweep (cron or lazy-on-read) to `expireStaleInvites`.

**Acceptance:** invited user receives an email, sees a pending invite, accepts, and becomes a
member with the assigned role; expired/revoked tokens are rejected.

### Phase 3 — Shared RAG / Team Knowledge (headline feature)

**Goal:** a file/knowledge base can be shared directly with a team and queried by every member.

- **Extend the ACL to files:**
  - Add `FILE = 'file'` to `ResourceType` and `FILE_VIEWER/EDITOR/OWNER` to `AccessRoleIds` in
    `packages/data-provider/src/accessPermissions.ts`; extend `accessRoleToPermBits`. Seed the
    new access roles (role-seed path used for the existing `agent_viewer` etc.).
  - Register files in the resource registry used by `canAccessResource`/the permissions routes so
    `/api/permissions/file/:resourceId` works, with a model resolver `getFileByObjectId`.
- **Team knowledge endpoints** (on `teams.js`):
  - `POST /api/teams/:id/knowledge` — attach an existing/uploaded file to the team:
    `grantPermission({ principalType: GROUP, principalId: teamGroupId, resourceType: FILE, resourceId: fileId, accessRoleId: FILE_VIEWER })` (owner/admin).
  - `GET /api/teams/:id/knowledge` — list files shared with the team.
  - `DELETE /api/teams/:id/knowledge/:fileId` — revoke the grant (owner/admin).
- **Extend file access checks** in `api/server/services/Files/permissions.js`:
  - Add `hasAccessToFile`/`filterFilesByTeamAccess` that, in addition to the existing
    agent-inheritance path, consults `checkPermission({ resourceType: FILE })` for direct/group
    grants. The user's effective accessible-file set becomes `owned ∪ team-shared ∪ agent-inherited`.
- **RAG retrieval scoping:** in the chat/agent run path that passes `file_ids` to `rag_api`,
  union in the team-shared file ids for the requesting user so vector search returns the team's
  documents. (Trace the current `file_ids` resolution in the agent/file service and extend it; no
  change to `rag_api` itself — it already queries by file_id.)

**Acceptance:** owner attaches a document to a team; another member, in a fresh conversation,
asks a question and the answer cites the shared document; a non-member cannot retrieve it; revoke
removes access immediately.

### Phase 4 — Team-scoped resource sharing (agents & prompts)

**Goal:** make "share with my team" a one-click action for agents and prompt groups.

- This reuses the existing generic permissions endpoint
  (`PUT /api/permissions/:resourceType/:resourceId`) with `principalType: GROUP` = the team's
  group id. Backend work is minimal; the effort is surfacing teams in the share UI (Phase 5).
- Optional convenience endpoint `POST /api/teams/:id/agents/:agentId` / `.../prompts/:promptGroupId`
  that wraps `grantPermission` for the team group, for a cleaner UX.

**Acceptance:** sharing an agent/prompt with a team makes it visible and usable to all current
members; removing a member revokes their access on next check.

### Phase 5 — Frontend (end-user UI)

**Goal:** a Teams surface; reuse existing Sharing components everywhere possible.

- New section under `client/src/routes` + `client/src/components/Teams/*`:
  - Teams list, create-team dialog, team detail (members + roles), pending-invites inbox,
    invite-by-email dialog, accept/decline screen for `/teams/invite/:token`.
  - **Team Knowledge** panel: upload/attach files to the team, list shared knowledge, remove.
- Reuse `client/src/components/Sharing/*` (PeoplePicker, `AccessRolesPicker`, `PrincipalAvatar`,
  `PublicSharingToggle`) for member management and for the resource-share dialogs.
- Surface teams in the existing agent/prompt **Share** dialog (group principals are already
  supported by the people-picker — add a "My teams" affordance).
- React-query hooks `client/src/data-provider/Teams/*` and request/response types in
  `packages/data-provider`.

**Acceptance:** a user completes the whole flow in the UI — create team, invite by email, accept,
attach a document, share an agent with the team — with no API client.

### Phase 6 — Permissions, guardrails, tenant-awareness

- New interface permission `TEAMS` (`USE`, `CREATE`) in `schema/role.ts` +
  `packages/data-provider/src/permissions.ts`, so admins can gate who may create teams; default
  on for `USER`.
- Config limits in `librechat.yaml`: max teams per user, max members per team, max knowledge
  files per team.
- Ensure `tenantId` is set on Group/TeamInvite/ACL writes (models are already tenant-aware).
- Cascades: on user deletion, remove memberships, reassign/transfer owned teams or delete them;
  enforce last-owner protection on leave/demote/delete.

**Acceptance:** team creation respects the interface permission and configured limits; tenant
isolation holds; no orphaned ownerless teams.

### Phase 7 — Tests, migration, rollout

- Unit tests (invite lifecycle, role transitions, FILE ACL checks) and integration tests for all
  endpoints, including negative/authorization cases.
- Migration: seed `FILE` access roles; backfill `ownerId`/`kind` on any pre-existing local groups
  if we promote them to teams (otherwise leave untouched).
- Feature flag (interface permission `TEAMS.USE` + an env/config toggle) to dark-launch and ramp.
- Docs page in `nufi-docs` under `content/docs/<section>/`.

**Acceptance:** CI green; feature flag toggles the surface cleanly on/off; docs published.

## 6. API surface (summary)

```
POST   /api/teams                              create team
GET    /api/teams                              my teams
GET    /api/teams/:id                          team detail
PATCH  /api/teams/:id                          update team
DELETE /api/teams/:id                          delete team (owner)
GET    /api/teams/:id/members                  list members
DELETE /api/teams/:id/members/:userId          remove / leave
PATCH  /api/teams/:id/members/:userId          change role

POST   /api/teams/:id/invites                  invite by email
GET    /api/teams/invites                      my pending invites
POST   /api/teams/invites/:token/accept        accept
POST   /api/teams/invites/:token/decline       decline
DELETE /api/teams/:id/invites/:inviteId        revoke

POST   /api/teams/:id/knowledge                share a file with team
GET    /api/teams/:id/knowledge                list team knowledge
DELETE /api/teams/:id/knowledge/:fileId        revoke file

PUT    /api/permissions/:resourceType/:resourceId   (existing) share agent/prompt with team group
```

## 7. Data model changes (summary)

- `Group` (extended): `ownerId`, `members[{userId, role, joinedAt}]`, `kind`, `joinPolicy`
  (keep `memberIds` synced).
- `TeamInvite` (new): `groupId, email, invitedUserId, role, token, status, invitedBy, expiresAt, tenantId`.
- `ResourceType.FILE` + `FILE_VIEWER/EDITOR/OWNER` access roles in the ACL.

## 8. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Group writes now touched by both admin and self-service paths could drift `memberIds` vs `members` | Centralize membership mutation in one method that updates both atomically (session/transaction) |
| RAG retrieval over-fetching files a user shouldn't see | Single source of truth for "accessible file ids" (`owned ∪ team ∪ agent`) used by both file listing and the rag_api query path; tests for the negative case |
| Entra-synced groups vs self-service teams confusion | `kind` discriminator; team endpoints only operate on `kind:'team'`, admin endpoints unchanged |
| Invite token leakage | Single-use, expiring, high-entropy tokens; bind to email; revoke endpoint |
| Last-owner / orphaned teams | Enforce ≥1 owner; transfer-ownership flow; cascade on user delete |

## 9. Rollout

Ship behind the `TEAMS` interface permission, default-off in production until Phase 3 (shared RAG)
is verified end-to-end. Enable per-tenant, monitor, then default-on. The `@librechat/data-schemas`
package version must be bumped and rebuilt; the admin panel (which installs a published
`@librechat/data-schemas`) only needs an update if it surfaces teams.

## 10. Effort estimate (rough)

| Phase | Scope | Est. |
|---|---|---|
| 0 | Data model + methods | 2–3 d |
| 1 | Self-service team API | 2–3 d |
| 2 | Invitations + email | 2 d |
| 3 | Shared RAG (FILE ACL + retrieval) | 4–5 d |
| 4 | Team-scoped agent/prompt sharing | 1 d |
| 5 | Frontend | 5–6 d |
| 6 | Permissions/guardrails/tenant | 2 d |
| 7 | Tests, migration, docs, rollout | 3 d |
| | **Total** | **~21–25 d (1 engineer)** |

Phases 0–3 deliver the core value (a working shared-RAG team) and can ship first;
4–7 harden and complete the experience.
