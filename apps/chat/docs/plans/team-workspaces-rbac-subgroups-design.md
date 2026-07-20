# Team Workspaces — RBAC via Sub-groups ("Groups") Design

**Date:** 2026-06-22
**Status:** Design approved (brainstorming). Next: implementation plan (writing-plans).
**Builds on:** the shipped Team Workspaces feature (`nufi-v0.0.9`). See `team-workspaces-shared-rag.md`, `team-workspaces-decisions.md`, `team-workspaces-phase3-findings.md`.

## Goal

Add fine-grained, intra-team access control so that **different groups of members within a team can access different shared resources**. Today, sharing a resource (knowledge file, agent, or prompt) with a team makes it visible to **every** member. We introduce named **sub-groups ("Groups")** inside a team; resources can be shared with the whole team (as today) **or** with specific sub-groups, and a member only sees resources granted to the team or to a sub-group they belong to.

Motivating scenario: a company team where Engineering accesses engineering docs, Legal accesses legal docs, etc.

## Requirements (settled during brainstorming)

1. **Model = sub-groups / departments.** Persistent, named groups inside a team; members are assigned to them; resources are shared to them. (Not per-document member lists; not clearance tiers.)
2. **Scope = all shared resource types**: knowledge files, agents, and prompts can each be scoped to a sub-group.
3. **Management = owner/admin only.** The team owner and team admins create sub-groups, manage their membership, and choose share targets. No per-sub-group "manager" role in v1.
4. **Access semantics = additive union, no deny.** A member's accessible set is the union of team-wide grants and the grants of every sub-group they belong to. There are no negative/deny rules. The model stays monotonic and matches ACL semantics.
5. **No per-sub-group roles in v1.** Sub-group membership is a binary access dimension ("in" / "not in"). Team-level roles (owner/admin/member) are unchanged and govern management.
6. **UI term = "Groups"** (sub-groups shown inside a team).

## Architecture — Approach A1: sub-groups ARE `Group` documents

A sub-group is a regular `Group` document, reusing the entire Group + ACL + RAG machinery the team feature already ships. Sharing to a sub-group is the **same** `grantPermission(...)` call used for team sharing, with a different `principalId`. The crucial property: `findAccessibleResources({ userId, role })` already resolves a user's **full** principal set (the user + every group they belong to + their role), so granting a file to a sub-group requires **no change** to the file-access / RAG hot path.

Rejected alternatives: A2 (a dedicated sub-group model + label-based filtering) reinvents groups and forces custom filtering inside the RAG hot path; A3 (per-resource member ACL, no named groups) does not scale and contradicts requirement #1.

## 1. Data model

A sub-group reuses `packages/data-schemas/src/schema/group.ts` (`groupSchema`) with minimal additions:

- `kind`: extend the existing enum `['group','team']` → `['group','team','team_subgroup']`.
- `parentTeamId: ObjectId` — references the parent team Group. Present only on sub-groups. Add index `{ parentTeamId: 1 }` for listing a team's sub-groups.
- Reused as-is: `name`, `description?`, `memberIds: [String]`, `members: [{ userId, role, joinedAt }]`, `tenantId` (inherited from the parent team), `ownerId` (set to the parent team's owner).

**Invariants:**
- A sub-group's members must be a **subset** of the parent team's members. Adding a user to a sub-group requires that user already be a team member; the handler rejects otherwise.
- A user may belong to **multiple** sub-groups → access is the union.
- `members[].role` on a sub-group is not meaningful in v1 (membership is binary); store `'member'` for consistency. Team-level roles remain on the parent team Group.
- Preserve the existing `memberIds` ↔ `members` dual-write invariant (`memberIds` is the ACL source of truth); apply `applyTenantIsolation` in any new model factory, per `reference_data_schemas_tenant_isolation`.

New/extended methods in `packages/data-schemas/src/methods/userGroup.ts` (or a sibling): `createSubgroup`, `getTeamSubgroups({ parentTeamId })`, `updateSubgroup`, `deleteSubgroup`, `addSubgroupMember`, `removeSubgroupMember`, `getUserSubgroups({ userId, parentTeamId })`, `getSubgroupsForTeam`. Reuse existing add/remove member helpers where possible.

## 2. Access / ACL resolution

- **Sharing to a sub-group** = `grantPermission({ principalType: PrincipalType.GROUP, principalId: subGroupId, resourceType: FILE | AGENT | PROMPTGROUP, accessRoleId: *_VIEWER, grantedBy: caller })` — identical to team sharing, different `principalId`.
- **Files / RAG: no hot-path change.** `findAccessibleResources({ userId, role, resourceType: FILE, requiredPermissions: VIEW })` already unions all of the caller's group principals. `getTeamSharedFileIds` and `filterFilesByAgentAccess` (`api/server/services/Files/permissions.js`) work unchanged: a member only retrieves files granted to a sub-group they belong to.
- **Agents / prompts: extend the list resolution.** The team agents/prompts listing in `packages/api/src/teams/*` currently enumerates resources granted to the team principal. Extend it to union resources granted to the team **or** to any sub-group the caller belongs to. (Owner/admin views should additionally surface *all* sub-group grants for management — see UI.)
- **Union, no deny.** More group memberships → more access. No subtractive rules.

## 3. API (extend `api/server/routes/teams.js` + `packages/api/src/teams/*`)

Sub-group CRUD + membership (owner/admin; guarded by the existing `requireJwtAuth, checkBan, configMiddleware` + team-role authz used by the other team-management routes):
- `POST /api/teams/:id/subgroups` `{ name, description? }` → create.
- `GET /api/teams/:id/subgroups` → list (with member counts).
- `GET /api/teams/:id/subgroups/:sgId` → detail (members).
- `PATCH /api/teams/:id/subgroups/:sgId` `{ name?, description? }` → rename/edit.
- `DELETE /api/teams/:id/subgroups/:sgId` → delete sub-group + revoke all its grants.
- `POST /api/teams/:id/subgroups/:sgId/members` `{ userId }` → add (must already be a team member).
- `DELETE /api/teams/:id/subgroups/:sgId/members/:userId` → remove.

Targeted sharing — **reuse the existing share endpoints**, add an optional target:
- Share: `POST /:id/knowledge | /:id/agents | /:id/prompts` accepts optional `targetSubgroupId`. Absent → grant to the whole team (current behavior). Present (and a valid sub-group of this team) → grant to that sub-group.
- List: `GET /:id/knowledge | /:id/agents | /:id/prompts` returns each grant annotated with its **target** (whole team vs which sub-group) — derivable from the ACL entry's `principalId`. The result is **caller-scoped**: a regular member sees only resources granted to the team or to a sub-group they belong to (the same accessible set the RAG layer resolves); owner/admin see **all** grants with their targets (for management). This makes the knowledge LIST caller-aware — a behavior change from today's "list all team files" — using the same union resolution as `getTeamSharedFileIds`.
- Unshare: `DELETE /:id/knowledge/:fileId | /:id/agents/:agentId | /:id/prompts/:promptGroupId` accepts optional `targetSubgroupId` query → revoke the grant for that specific target (a resource may be shared to several sub-groups).

Validation: `targetSubgroupId` must reference a sub-group whose `parentTeamId` equals `:id`, else 400/404.

## 4. UI (in the team detail page; `client/src/components/Teams/*`)

- **New "Groups" tab** alongside Members / Invites / Knowledge / Shared. Lists the team's sub-groups (name, member count); owner/admin can create, rename, delete, and open a sub-group to manage its members (a picker over the team's existing members). Localize en only (`com_ui_*`).
- **"Share with" target selector** in the Add-file / Add-agent / Add-prompt pickers (Knowledge + Shared tabs): a dropdown defaulting to **Whole team**, plus each sub-group. Selecting a sub-group sets `targetSubgroupId`.
- **Target badge + per-target unshare** on each shared resource row: show "Whole team" or the sub-group name; the unshare action targets that specific grant.
- **Member experience is unchanged** except for visibility: members only see resources they can access. Sub-group structure/management is owner/admin-only.
- New data-provider hooks under `client/src/data-provider/Teams/` (queries: `useTeamSubgroupsQuery`, `useTeamSubgroupQuery`; mutations: create/update/delete subgroup, add/remove subgroup member). Reuse react-query v4 3-arg form and the established invalidation discipline. Extend the share mutations to pass `targetSubgroupId`.

## 5. Migration / back-compat

- **Zero data migration.** Existing teams have no sub-groups and behave exactly as today (all shares team-wide).
- Existing ACL grants remain on the team principal → all members still see them.
- `targetSubgroupId` is optional everywhere → existing clients and flows are unaffected.

## 6. Cascade / cleanup

- **Delete sub-group** → `deleteAclEntries({ principalId: sgId })` (revoke all grants made to it) + delete the Group doc.
- **Remove a member from the team** → also remove them from every sub-group of that team.
- **Delete a team** → delete all its sub-groups and their grants (extend the existing team-delete cascade + the Phase-6 sole-owner delete path in `UserController.js`).
- **Delete a user** → existing `removeUserFromAllGroups` + team cascade already cover group membership; extend the team cascade so sub-group membership/ownership is cleaned consistently.

## 7. Limits (optional)

Add `maxSubgroupsPerTeam?` to the existing `teams` config block (`packages/data-provider/src/config.ts`), enforced in the sub-group `create` handler via the existing `configMiddleware` pattern (unset = unlimited). May be deferred past v1.

## 8. Testing strategy (TDD; real `mongodb-memory-server` for the data/access paths)

- **Model:** sub-group CRUD; the members-⊆-team invariant (reject adding a non-team-member); `getUserSubgroups` union.
- **Handlers / authz:** owner/admin-only for sub-group CRUD, membership, and targeted shares; a regular member is denied (403).
- **Access (core, real mongo):** a file granted to sub-group A is returned by `getTeamSharedFileIds` for a member of A; a team member **not** in A does **not** get it; a team-wide grant is returned for everyone. Same union behavior for agents/prompts listing.
- **Cascade:** deleting a sub-group revokes its grants; removing a member from the team removes them from sub-groups; deleting a team removes its sub-groups + grants; deleting a user cleans up.
- Frontend: query/mutation hooks (loading/success/error), the Groups tab, and the share-target selector.

## Phasing (for the implementation plan)

- **P1 — Data model + sub-group CRUD/membership.** Schema (`kind`, `parentTeamId`), methods, the 7 endpoints, authz, invariant + authz tests.
- **P2 — Targeted sharing + agents/prompts union.** `targetSubgroupId` on share/unshare, list-with-target annotation, the agents/prompts list union, access tests (the core matrix above).
- **P3 — Frontend.** Groups tab + member management UI; "Share with" selector + target badges + per-target unshare; data-provider hooks; localization.
- **P4 — Cascade + cleanup + (optional) limits + docs.** All cascade paths, optional `maxSubgroupsPerTeam`, update `docs/team-workspaces.md`.

Each phase is independently testable and ships on its own (mirroring the team-workspaces phase discipline: spec → TDD-via-subagents → review → local FF-merge to `fork/main`, with releases per `feedback_release_flow`).

## Out of scope (v1)

- Per-sub-group roles / sub-group "managers" (centralized owner/admin management only).
- Nested sub-groups (flat, one level under the team).
- Deny / negative permissions (union only).
- EDIT/SHARE-level grants to sub-groups (v1 grants VIEW, matching current team knowledge sharing).
- Self-service join / join policies for sub-groups.

## Open questions / future

- Optional EDIT access for sub-groups (let a sub-group co-edit a resource) — deferred; current team sharing is VIEW-only.
- Sub-group managers (delegated administration) — the natural next RBAC step if orgs grow.
