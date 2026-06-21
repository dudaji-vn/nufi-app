# Team Workspaces — Phase 1: Self-Service Team API (Spec)

Phase 1 of the master plan. A regular (non-admin) user can create and manage a team without admin
rights. Backend logic is **TypeScript in `packages/api`** with a **thin JS route** in `/api`
([decision D1](./team-workspaces-decisions.md)). Builds on the Phase-0 data methods.

## 1. Architecture (mirrors `admin/groups`)

```
packages/api/src/teams/handlers.ts   createTeamsHandlers(deps) -> { create, list, get, update,
                                       remove, listMembers, removeMember, changeMemberRole,
                                       transferOwnership }  (Express handlers) + role helpers
packages/api/src/teams/index.ts      re-export
packages/api/src/teams/handlers.spec.ts  unit tests (pure jest, mocked deps)
packages/api/src/index.ts            + export * from './teams'
api/server/routes/teams.js           thin JS: require('@librechat/api'), inject db.*, apply
                                       requireJwtAuth + checkBan, map routes -> handlers
api/server/routes/index.js           + const teams = require('./teams')
api/server/index.js                  + app.use('/api/teams', routes.teams)  (before /api 404)
api/server/routes/__tests__/teams.spec.js  supertest integration (real in-memory Mongo)
packages/data-schemas .../teamInvite.ts  + deleteInvitesByGroup({groupId}) for delete-cascade
```

`req.user.id` (string) is the caller. `requireJwtAuth` runs `tenantContextMiddleware` internally,
so data-schemas tenant isolation is active in-request. No admin capability is used.

## 2. Dependencies injected into `createTeamsHandlers`

From `db = require('~/models')`: `createTeam`, `getUserTeams`, `getTeamRole`, `findGroupById`,
`updateGroupById`, `deleteGroup`, `removeTeamMember`, `setMemberRole`, `transferOwnership`,
`deleteInvitesByGroup` (new), `findUsers` (to enrich member listings with name/email/avatar).
Declare them in a `TeamsHandlersDeps` interface (typed with data-schemas signatures; no `any`).

## 3. Authorization helper (TS, D3)

```ts
type TeamRole = 'owner' | 'admin' | 'member';
const RANK = { owner: 3, admin: 2, member: 1 } as const;
// resolveRole(deps, groupId, userId): Promise<TeamRole | null>  — wraps getTeamRole
// hasMinRole(role: TeamRole | null, min: TeamRole): boolean      — RANK[role] >= RANK[min]
```
Each handler resolves the caller's role and returns 403 if below the required minimum (or 404 if
the team doesn't exist / isn't `kind:'team'`). A non-member resolving `null` → 403 (or 404 to avoid
leaking existence — use **404** for "not found OR not a member" on `GET/PATCH/DELETE /:id` to avoid
disclosing team existence to outsiders; 403 only when the caller IS a member but lacks the rank).

## 4. Endpoints

All under `/api/teams`, after `requireJwtAuth, checkBan`. `caller = req.user.id`. Responses JSON.

| Method/Path | Min role | Behavior | Success |
|---|---|---|---|
| `POST /` | (any auth) | validate `name` non-empty; `createTeam({name, description?, avatar?, ownerId: caller, tenantId: req.user.tenantId})` | 201 team |
| `GET /` | (any auth) | `getUserTeams({userId: caller})` | 200 team[] |
| `GET /:id` | member | `findGroupById`; 404 if missing/not team/caller not a member; enrich members via `findUsers` | 200 team+members |
| `PATCH /:id` | admin | validate body (name/description/avatar); `updateGroupById(id, patch)` (only `kind:'team'`) | 200 team |
| `DELETE /:id` | owner | `deleteInvitesByGroup({groupId:id})` then `deleteGroup(id)` | 200 `{success:true}` |
| `GET /:id/members` | member | members from group + `findUsers` enrichment ({userId,role,joinedAt,name,email,avatar}) | 200 member[] |
| `DELETE /:id/members/:userId` | admin **or self** | self-leave allowed for any member (caller===:userId); else admin+. `removeTeamMember({groupId,userId})` | 200 `{success:true}` |
| `PATCH /:id/members/:userId` | admin | body `{role:'admin'\|'member'}`; `setMemberRole({groupId,userId,role})` | 200 team |
| `POST /:id/transfer` | owner | body `{newOwnerId}` (must be a member); `transferOwnership({groupId,fromUserId:caller,toUserId:newOwnerId})` | 200 team |

## 5. Validation & error mapping

- Validate ObjectId for `:id`, `:userId`, `newOwnerId` (`isValidObjectIdString` from data-schemas) → 400.
- `name` required, non-empty trimmed on create; PATCH body must contain ≥1 updatable field.
- `role` ∈ {`admin`,`member`} on member PATCH → 400 otherwise.
- Data-layer guard throws (e.g. "Cannot remove the team owner; transfer ownership first",
  "fromUserId is not the current owner", "toUserId is not a member") → map to **409 Conflict**
  with the thrown `message`.
- Mongoose `ValidationError` → 400 `{error: message}`. Anything else → `logger.error(...)` + 500
  `{error: 'Failed to <action>'}`. Mirror `admin/groups.ts` error style exactly.

## 6. Tests

**Unit (`packages/api/src/teams/handlers.spec.ts`, pure jest, mocked deps):** each handler — happy
path + authz (member/admin/owner gates, self-leave, non-member 404), validation failures, and
data-layer-throw → 409 mapping. Assert the right `db.*` dep is called with the right args.

**Integration (`api/server/routes/__tests__/teams.spec.js`, supertest + mongodb-memory-server +
real `createMethods`/`createModels`, middleware mocked to inject `req.user`):** full lifecycle —
create → appears in `GET /` → owner-only delete forbidden for non-owner → transfer → leave →
delete cascade also removes the team's invites (seed a `TeamInvite`, delete team, assert gone). At
least one negative authz case per protected route.

## 7. Acceptance

A non-admin user can create a team, see it listed, view/rename it, list members, change a member's
role, remove a member / leave, transfer ownership, and delete a team they own; role checks enforced
(403/404); delete cascades to the team's invites; `@librechat/api` and `@librechat/data-schemas`
build clean; unit + integration tests green. Local FF-merge to `fork/main`.

## 8. Out of scope (later phases)

Invitations & email (Phase 2 — direct member *add* lives there), FILE-ACL/shared-RAG (Phase 3),
agent/prompt team-sharing (Phase 4), interface-permission `TEAMS` + config limits (Phase 6),
frontend (Phase 5). By-principal ACL cleanup on delete is deferred to Phase 3/4 (D5).
