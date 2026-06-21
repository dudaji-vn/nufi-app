# Team Workspaces — Autonomous Decisions Log

Decisions made by Claude during the autonomous Phases 1–7 run (user AFK, explicitly
authorized to decide). Each entry: the decision, the rationale, and how to revisit.
Phase 0 was reviewed and approved by the user before this run.

## Standing guardrails (apply to every phase)

- **No outward/irreversible actions** without the user: no `git push`, no PRs, no real email
  sends (mailer is wired but exercised only via spies/mocks in tests), no deleting/overwriting
  pre-existing data or code, nothing outside the Team Workspaces scope, no change to the
  release/tag flow.
- **Per phase:** spec (decisions recorded here) → task plan → subagent TDD execution with a
  per-task spec+quality review → final whole-branch review → **local fast-forward merge into
  `fork/main`** (not pushed) → delete the phase branch. Same rigor as Phase 0.
- **Branch per phase:** `feat/team-workspaces-phaseN`, off the current `fork/main`.

## D1 — Backend lives in TypeScript (`packages/api`), `/api` is a thin JS wrapper

The master plan names `api/server/routes/teams.js` (JS). **CLAUDE.md outranks the plan**: "All
new backend code must be TypeScript in `/packages/api`" and "Keep `/api` changes to the absolute
minimum (thin JS wrappers)". The repo already does this for the sibling feature: a thin
`api/server/routes/admin/groups.js` route delegates to `packages/api/src/admin/groups.ts`.

**Decision:** mirror that split for teams — real logic (service + controller-ish handlers) in
TypeScript under `packages/api/src/teams/`, with a thin `api/server/routes/teams.js` that mounts
and delegates. Data access continues through the `@librechat/data-schemas` methods built in
Phase 0 (already exposed to `/api` via `api/models/index.js`). *Revisit only if the existing
admin/groups split turns out not to be the real pattern (exploration will confirm).*

## D2 — Phase ordering

Backend core first (the plan says Phases 0–3 deliver the core value): **1 → 2 → 3 → 4 → 6 → 7**,
then **5 (frontend) last**. Frontend is large and benefits from the user's visual review (argent/
playwright), so it is deferred to the end of the run and may be left for a session with the user
present. If context runs low, stop at a clean phase boundary and report status via the ledger.

## Phase 1 decisions

### D3 — Team-role authorization is a TS helper inside handlers, not a JS Express middleware
The plan suggested `api/server/middleware/teams/requireTeamRole.js`. That would put authz business
logic in untyped JS. Instead, each TS handler resolves the caller's role via the injected
`getTeamRole` and asserts a minimum with a small pure helper (`assertMinRole`, ordering
owner>admin>member). Keeps authz in testable TS, no JS middleware with logic. The JS route only
applies `requireJwtAuth, checkBan`.

### D4 — Teams TS module layout
`packages/api/src/teams/handlers.ts` exports `createTeamsHandlers(deps)` (factory returning Express
handlers) + the role helpers; `packages/api/src/teams/index.ts` re-exports; unit tests in
`packages/api/src/teams/handlers.spec.ts` (pure jest, mocked deps). Mirrors `admin/groups.ts` +
`admin/index.ts`. `src/index.ts` re-exports `./teams`. Built into `@librechat/api`.

### D5 — Phase 1 delete-cascade scope (YAGNI on by-principal ACL)
`DELETE /api/teams/:id` cascade = delete the group's `TeamInvite`s + delete the `Group`. ACL grants
where the team is the **principal** cannot exist until team-sharing (Phase 3/4), so the
by-principal ACL cleanup (and a `deleteAclEntriesByPrincipal` method) is deferred to those phases
and added to this cascade then. Phase 1 adds one small data-schemas method `deleteInvitesByGroup`
(deleteMany by groupId) for the invite cleanup.

### D6 — Phase 1 endpoint set (incl. transfer-ownership)
`POST /api/teams` · `GET /api/teams` · `GET /api/teams/:id` · `PATCH /api/teams/:id` ·
`DELETE /api/teams/:id` · `GET /api/teams/:id/members` · `DELETE /api/teams/:id/members/:userId`
(remove or self-leave) · `PATCH /api/teams/:id/members/:userId` (admin↔member) ·
`POST /api/teams/:id/transfer` (owner-only, `{newOwnerId}` → `transferOwnership`). Direct member
*add* is intentionally absent — members join via invite accept (Phase 2). `transferOwnership` real
signature is `{ groupId, fromUserId, toUserId }`.

## Phase 2 decisions

### D7 — Invite handlers are a separate TS module
`packages/api/src/teams/invites.ts` exports `createTeamInviteHandlers(deps)` (6 handlers) + unit
tests `invites.spec.ts`, rather than bloating the already-large `handlers.ts`. Re-exported via
`teams/index.ts`.

### D8 — Email send is an injected, optional, config-gated dependency
The JS route wraps the existing mailer: `sendInviteEmail(payload)` built in `api/server/routes/teams.js`
using `sendEmail` (`~/server/utils`) + the existing `inviteUser.handlebars` template + link
`${DOMAIN_CLIENT}/teams/invite/${token}`, and ONLY when `checkEmailConfig()` (from `@librechat/api`)
is true (else a no-op). The TS handler takes `sendInviteEmail?` as an OPTIONAL dep and calls it
after `createInvite` — so invite creation never hard-fails when email is unconfigured, and unit
tests need no mailer. Email is sent with `throwError:false` so a transient SMTP error doesn't fail
the request. **No real email is sent during this autonomous run** (tests use a spy; runtime depends
on deploy env config).
- **Token exposure:** the create response and the invitee's own `GET /api/teams/invites` include the
  `token` (the creator/invitee legitimately hold it); the team-scoped `GET /api/teams/:id/invites`
  (owner/admin view) EXCLUDES `token` (admins revoke by `inviteId`, not token).

### D9 — Accept/decline are bound to the caller (anti-token-theft)
`accept`/`decline` validate that the invite's `email === req.user.email` OR
`invitedUserId === req.user.id`; otherwise 403. A stolen token alone cannot be redeemed.

### D10 — `revokeInvite` gains an optional `groupId` guard
Phase-0 `revokeInvite({inviteId})` → `revokeInvite({inviteId, groupId?})` (filter also matches
`groupId` when provided), so a team admin can only revoke invites belonging to THEIR team. Small
data-schemas change + test (Phase 2 T1).

### D11 — Route ordering: `/invites` before `/:id`
On the teams router, `GET /api/teams/invites`, `POST /api/teams/invites/:token/accept|decline` MUST
be registered BEFORE the `/:id` routes, else Express matches `:id = 'invites'`. The `/:id/invites`
routes (create/list/revoke) are unaffected (distinct prefix).

### D12 — Accept composition order (robust, non-transactional)
`accept` = (1) `findInviteByToken` + validate pending/unexpired/caller-bound → 404/403/410;
(2) `addTeamMember({groupId, userId:caller, role})` (idempotent — existing member → null is fine);
(3) `acceptInvite({token, userId:caller})` (atomic pending→accepted; a racing null still leaves the
user a member — the desired end state). No cross-document transaction needed.

### D13 — No scheduled expiry sweep
No cron lib exists. `listPendingInvitesForUser`/`acceptInvite` already filter `expiresAt > now`, so
expired invites are excluded at query time. Skip a scheduled sweep; an optional one-shot
`runAsSystem(db.expireStaleInvites)` at boot can be added in Phase 6/7 if status-accuracy matters.

<!-- Subsequent phase decisions appended below. -->


