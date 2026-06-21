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

<!-- Subsequent phase decisions appended below. -->

