# Team RBAC Sub-groups — Phase 4 (Cascade + Limits + Multi-target picker + Docs) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax. T1/T2 are backend TDD; T3 is frontend (build + `tsc` + controller visual-verify against the running app :3080/:3081); T4 is docs.

**Goal:** Finish the feature: cascade sub-group cleanup on team-delete / member-removal / user-delete; an optional `maxSubgroupsPerTeam` limit; make the share picker target-aware (so a resource can be shared with more than one target); and document it.

**Architecture:** Cascade is **orchestration of the existing Phase-1 `db` methods** (`getTeamSubgroups`, `deleteSubgroup`, `deleteAclEntries`, `removeSubgroupMember`) at the handler / `UserController` level — no new persistence model. The limit mirrors the existing `teams.*` config checks. The picker fix filters candidates by the *selected* "Share with" target instead of by resource id.

**Tech Stack:** TypeScript (`packages/api`, `packages/data-provider`), JS (`/api` controllers + thin route), React (`client`), Jest + `mongodb-memory-server`. Phases 1-3 are merged on `fork/main`.

## Global Constraints

- Reuse existing `db` methods for cascade — `getTeamSubgroups(teamId)`, `deleteSubgroup(sgId)` (deletes the Group), `deleteAclEntries({ principalId })` (revoke a principal's grants), `removeSubgroupMember({ subgroupId, userId })` (atomic, Entra-id-resolving). Do NOT add a new model.
- Cascade must be **idempotent + isolated**: a failure cleaning one sub-group must not abort the rest (wrap per-sub-group cleanup so one error is logged + skipped, mirroring the per-team isolation already in `UserController.js`'s team loop).
- `maxSubgroupsPerTeam` is OPTIONAL (unset = unlimited); enforced ONLY in the sub-group `create` handler, mirroring the existing `maxTeamsPerUser`/`maxKnowledgeFilesPerTeam` checks (→ 403 when over).
- The picker fix must keep single-target behavior identical and stay back-compat for teams with no sub-groups. No `any`. Real-mongo tests for the cascade.
- Deleting a sub-group already revokes its own grants (Phase 1). This phase adds the team/user/member-level cascade that *reaches* sub-groups.

---

### Task 1: Cascade sub-group cleanup (team-delete, member-removal, user-delete)

**Files:**
- Modify: `packages/api/src/teams/handlers.ts` (`removeHandler` ~line 290 — team delete; `removeMemberHandler` ~line 338 — member removal). Wire `getTeamSubgroups`, `deleteSubgroup`, `deleteAclEntries`, `removeSubgroupMember` into the handlers' deps if not already present.
- Modify: `api/server/controllers/UserController.js` (`deleteUserController` cascade ~lines 341-372)
- Modify: `api/server/routes/teams.js` (pass any newly-needed `db.*` deps to `createTeamsHandlers`)
- Test: `packages/api/src/teams/handlers.spec.ts` (extend), `api/server/controllers/__tests__/` (the user-delete cascade test, extend)

**Interfaces:**
- Consumes: `db.getTeamSubgroups(teamId)`, `db.deleteSubgroup(sgId)`, `db.deleteAclEntries({ principalId })`, `db.removeSubgroupMember({ subgroupId, userId })` (all Phase-1/2).

- [ ] **Step 1: Write failing tests.** (a) `removeHandler` (team delete): a team with 2 sub-groups (each with a granted file) → after delete, both sub-group Groups are gone AND `deleteAclEntries` was called per sub-group principal. (b) `removeMemberHandler`: removing member m1 (who is in sub-group A) from the team → m1 is removed from sub-group A. (c) user-delete cascade: a user who owns a sole-member team with a sub-group → the sub-group is deleted; a user who is a non-owner member in a sub-group → removed from it.
- [ ] **Step 2: Run, confirm FAIL:** `cd packages/api && npx jest handlers` and `cd api && npx jest deleteUser`
- [ ] **Step 3: Implement (orchestration).**
  - `removeHandler` — before `deleteGroup(id)`:
```ts
const subgroups = await getTeamSubgroups(id);
for (const sg of subgroups) {
  try { await deleteAclEntries({ principalId: sg._id }); await deleteSubgroup(sg._id); }
  catch (e) { logger.error('[teams] subgroup cleanup failed', e); }   // isolate
}
```
  - `removeMemberHandler` — after `removeTeamMember(...)`:
```ts
const subgroups = await getTeamSubgroups(id);
for (const sg of subgroups) {
  try { await removeSubgroupMember({ subgroupId: sg._id, userId }); } catch (e) { logger.error(...); }
}
```
  - `UserController.js` `deleteUserController` — in the per-team loop: for the **sole-owner delete** branch (where `deleteGroup(team._id)` is called), first delete the team's sub-groups (`const subs = await db.getTeamSubgroups(team._id); for (const sg of subs) { await db.deleteAclEntries({ principalId: sg._id }); await db.deleteSubgroup(sg._id); }`, each wrapped in try/catch); for the **non-owner / transfer** branches (where the user is removed from the team), also remove them from that team's sub-groups (`for (const sg of subs) { await db.removeSubgroupMember({ subgroupId: sg._id, userId: user.id }); }`). Keep the existing per-team try/catch isolation.
- [ ] **Step 4: Run tests → PASS.** `cd packages/api && npx jest teams` + `cd api && npx jest teams deleteUser` (no regressions). Build `cd packages/api && npm run build`.
- [ ] **Step 5: Commit:** `feat(api): cascade sub-group cleanup on team-delete, member-removal, and user-delete`.

---

### Task 2: `maxSubgroupsPerTeam` config limit

**Files:**
- Modify: `packages/data-provider/src/config.ts` (the `teams` object ~line 1389)
- Modify: `packages/api/src/teams/subgroups.ts` (the `create` handler — add the limit check), `api/server/routes/teams.js` if a new dep is needed
- Test: `packages/api/src/teams/subgroups.spec.ts` (extend)

**Interfaces:**
- Consumes: `req.config?.config?.teams?.maxSubgroupsPerTeam` (the `configMiddleware` already on the teams router), `db.getTeamSubgroups(teamId)`.

- [ ] **Step 1:** Add to the `teams` zod object: `maxSubgroupsPerTeam: z.number().int().positive().optional(),`. Build data-provider.
- [ ] **Step 2: Write a failing test** in `subgroups.spec.ts`: with `maxSubgroupsPerTeam: 1` configured and 1 sub-group existing, creating a 2nd → 403; unset → unlimited.
- [ ] **Step 3: Implement** in the sub-group `create` handler: read the limit from `req.config?.config?.teams?.maxSubgroupsPerTeam`; if defined and `(await getTeamSubgroups(teamId)).length >= limit` → `res.status(403).json({ error: '...' })` (mirror the wording/shape of the existing `maxTeamsPerUser` check). Wire `getTeamSubgroups` into the subgroups handler deps if not present.
- [ ] **Step 4: Run tests → PASS.** Build data-provider + packages/api.
- [ ] **Step 5: Commit:** `feat: optional maxSubgroupsPerTeam config limit`.

---

### Task 3: Make the share picker target-aware (multi-target sharing)

**Files:**
- Modify: `client/src/components/Teams/KnowledgeTab.tsx`, `client/src/components/Teams/SharedTab.tsx`
- Test: none (frontend; controller visually verifies)

**Problem:** the pickers currently filter candidates by resource id (`!sharedIds.has(r.id)`), so once a resource is shared with ANY target it disappears from the picker — you can never share it with a second sub-group (or additionally the whole team). The rows + per-target unshare already support multi-target.

**Interfaces:** the picker already tracks the selected `targetSubgroupId` (Phase 3 T3); the shared list rows carry `item.target` (`{type:'team'} | {type:'subgroup', id, name}`).

- [ ] **Step 1:** Build a set of `${resourceId}-${targetKey}` from the shared list, where `targetKey = item.target.type === 'subgroup' ? item.target.id : 'team'`. In each picker, compute the candidate filter against the CURRENTLY-SELECTED target: `const selectedKey = targetSubgroupId ?? 'team'; const available = all.filter(r => !sharedKeys.has(\`${r.id}-${selectedKey}\`))`. So a resource already shared with sub-group A still appears in the picker when the target is "Whole team" or sub-group B, and disappears only for target A. Recompute `available` when the "Share with" select changes.
- [ ] **Step 2:** `cd client && npx tsc --noEmit 2>&1 | grep components/Teams` — no new errors; `npx eslint --fix` on changed files.
- [ ] **Step 3: Commit:** `feat(client): target-aware share picker (allow sharing a resource with multiple sub-groups)`.
- [ ] **Controller visual-verify:** (needs a shareable resource — if the dev account has none, upload one file first, or verify the filter logic by sharing an agent/prompt with team then with a sub-group and confirming it stays selectable for the second target). Confirm: share file F with "Whole team" → F still selectable in the picker when target = sub-group A → share F with A → two rows (Whole team, A) each with its badge → unshare the A row leaves the team row.

---

### Task 4: Documentation

**Files:**
- Modify: `docs/team-workspaces.md` (add a sub-group RBAC section)

- [ ] **Step 1:** Add a "Sub-groups (RBAC)" section documenting: the model (a sub-group is a `Group` with `kind:'team_subgroup'`, `parentTeamId`; flat; owner/admin-managed; binary membership); the API (the 7 `/api/teams/:id/subgroups*` routes + the `targetSubgroupId` param on the share/unshare/list endpoints + the `target` annotation on list responses); access semantics (union across the caller's groups, no deny; members see only team + their sub-groups' resources; the RAG hot path scopes per-user automatically); the `maxSubgroupsPerTeam` limit; cascade behavior. Match the existing doc's style/structure.
- [ ] **Step 2: Commit:** `docs: document team sub-group RBAC`.

---

## Self-Review (run after writing; fix inline)

- **Spec coverage (P4 scope):** cascade (team/member/user) → T1; limit → T2; the deferred P3 #2 multi-target picker → T3; docs → T4. ✓
- **Cascade completeness:** the three entry points that can orphan a sub-group membership/grant are team-delete (T1 removeHandler), member-removal (T1 removeMemberHandler), and user-delete (T1 UserController). Deleting a sub-group itself already revokes its grants (Phase 1). Confirm no 4th path (e.g. transfer-ownership doesn't remove members, so no sub-group impact).
- **Isolation:** every per-sub-group cleanup is wrapped so one failure doesn't abort the cascade (matches the existing per-team try/catch).
- **Limit:** only in `create`, only when configured, mirrors the existing checks.
- **Picker fix:** single-target + no-sub-group behavior unchanged; the key is `${id}-${targetKey}` consistent between the shared-set build and the candidate filter.

## Definition of done (Phase 4)

`packages/api`/`data-provider` build + all team specs green (incl. the new cascade + limit tests); deleting a team/user/member cleans sub-groups + grants (real-mongo verified); `maxSubgroupsPerTeam` enforced when set; the share picker allows multi-target sharing (controller-verified); docs updated. Then local FF-merge to `fork/main`. **The whole sub-group RBAC feature (P1-P4) is then complete and usable end-to-end** — ready to release per `feedback_release_flow` whenever the user chooses.
