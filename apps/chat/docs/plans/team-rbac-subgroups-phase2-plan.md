# Team RBAC Sub-groups — Phase 2 (Targeted Sharing + Caller-scoped Lists + Union) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Let owner/admin share knowledge files, agents, and prompts with a specific sub-group (not just the whole team), and make the list endpoints caller-scoped (a member sees only team-wide + their sub-groups' resources) with each grant annotated by its target.

**Architecture:** Sharing to a sub-group is the existing `grantPermission(GROUP, principalId, …)` with `principalId = targetSubgroupId` instead of the team id. Access resolution for FILES/RAG already unions all of a caller's groups (Phase 1 confirmed) — so the USE path needs no change; only the management LIST views need an explicit union across the caller's principals (team + their sub-groups).

**Tech Stack:** TypeScript (`packages/data-schemas`, `packages/api`, `packages/data-provider`), Jest + `mongodb-memory-server`. Phase 1 (sub-group model + CRUD/membership API) is merged on `fork/main`.

## Global Constraints

- Reuse `grantPermission`/`revokePermission`/`findEntriesByPrincipal` (the ACL) — sharing to a sub-group differs only by `principalId`. Do not add a parallel sharing system.
- `targetSubgroupId` is **optional** on every share/unshare/list flow: absent → the whole team (today's behavior, back-compat); present → it MUST be validated as a sub-group whose `parentTeamId` equals the route's team `:id` (else 400/404). Never grant to an arbitrary group id.
- **Union, no deny.** A caller's accessible set = grants to the team ∪ grants to each sub-group they belong to. Owner/admin LIST views show ALL grants (team + every sub-group) annotated by target, for management.
- **Entra ids:** `memberIds` stores `idOnTheSource || _id`. Any "sub-groups this user is in" query MUST resolve the id first (mirror `addSubgroupMember`/`resolveMemberIdValue`). This includes fixing `getUserSubgroups` (Phase 1 left it raw with a footgun comment).
- Owner/admin only for share/unshare + the management list view; a member may call the list and receive only their accessible set. Reuse `resolveTeamAccess`.
- TypeScript, no `any`, no `Record<string,unknown>`. Real-mongo tests. The FILE/RAG hot path (`getTeamSharedFileIds`, `filterFilesByAgentAccess`) is NOT modified — only confirmed by test.

---

### Task 1: data-schemas — fix `getUserSubgroups` Entra id + add `getUserTeamPrincipals`; confirm RAG union

**Files:**
- Modify: `packages/data-schemas/src/methods/userGroup.ts` (`getUserSubgroups` ~line 1160; add `getUserTeamPrincipals`; export it in the returned object)
- Test: `packages/data-schemas/src/methods/userGroup.subgroup.spec.ts` (extend)

**Interfaces:**
- Produces:
```ts
getUserSubgroups(params: { userId: string; parentTeamId: string | Types.ObjectId }): Promise<IGroup[]>; // FIX: resolve id
// New — the principal-id set a user has WITHIN a team (for list-union queries):
getUserTeamPrincipals(params: { userId: string; teamId: string | Types.ObjectId }): Promise<string[]>;
//   returns [teamId, ...subGroupIds] as strings: the team (if the user is a member) plus every sub-group of that team the user belongs to.
```

- [ ] **Step 1: Write failing tests.** (a) An Entra-style member (team `memberIds` holds an `idOnTheSource` GUID; pass that user's raw `_id`) is returned by `getUserSubgroups` — currently returns `[]`. (b) `getUserTeamPrincipals` returns `[teamId, sgAId]` for a user in sub-group A of the team, and `[teamId]` for a team member in no sub-group, and `[]` for a non-member.
- [ ] **Step 2: Run, confirm FAIL:** `cd packages/data-schemas && npx jest userGroup.subgroup`
- [ ] **Step 3: Implement.** In `getUserSubgroups`, resolve the id (mirror `addSubgroupMember`: `const resolvedId = await resolveMemberIdValue(new Types.ObjectId(userId))`) and query `memberIds: resolvedId`. Add `getUserTeamPrincipals`:
```ts
async function getUserTeamPrincipals({ userId, teamId }) {
  const resolvedId = await resolveMemberIdValue(new Types.ObjectId(userId));
  const [team, subs] = await Promise.all([
    Group.findOne({ _id: teamId, kind: 'team', memberIds: resolvedId }).select('_id').lean<IGroup | null>(),
    Group.find({ parentTeamId: teamId, kind: 'team_subgroup', memberIds: resolvedId }).select('_id').lean<IGroup[]>(),
  ]);
  const ids: string[] = [];
  if (team) ids.push(team._id.toString());
  for (const s of subs) ids.push(s._id.toString());
  return ids;
}
```
Remove the now-stale FOOTGUN comment on `getUserSubgroups` (the bug is fixed).
- [ ] **Step 4: Run tests → PASS.** Also `npx jest userGroup.spec userGroup.team.spec` (no regressions).
- [ ] **Step 5: Confirm the RAG union already works (existing behavior, no code change).** Add a test in `api/server/services/Files/__tests__/permissions.spec.js` (or wherever `getTeamSharedFileIds` is tested; create if absent) that grants a FILE to a sub-group, makes a user a member of that sub-group, and asserts `getTeamSharedFileIds(userId, role)` includes that file's `file_id` — and a non-member does NOT get it. (This proves Phase-1's "no hot-path change" claim end-to-end.)
- [ ] **Step 6: Build + commit.**
```bash
cd packages/data-schemas && npm run build && cd ../..
git add packages/data-schemas/src/methods/userGroup.ts packages/data-schemas/src/methods/userGroup.subgroup.spec.ts api/server/services/Files/__tests__/permissions.spec.js
git commit -m "feat(data-schemas): resolve Entra id in getUserSubgroups + getUserTeamPrincipals; confirm RAG sub-group union"
```

---

### Task 2: Sub-group share/unshare targeting (knowledge + agents + prompts)

**Files:**
- Create: `packages/api/src/teams/target.ts` (a small shared validator `resolveShareTarget`)
- Modify: `packages/api/src/teams/knowledge.ts` (`add` ~line 69, `remove` ~line 167), `packages/api/src/teams/resources.ts` (`share` ~line 106, `revoke` ~line 150)
- Test: `packages/api/src/teams/knowledge.spec.ts`, `packages/api/src/teams/resources.spec.ts` (extend)

**Interfaces:**
- Consumes: `db.getSubgroupById` (Phase 1). Produces:
```ts
// target.ts
export async function resolveShareTarget(
  deps: { getSubgroupById: (id: string) => Promise<IGroup | null> },
  teamId: string,
  targetSubgroupId?: string,
): Promise<{ ok: true; principalId: string } | { ok: false; status: 400 | 404 }>;
//   no targetSubgroupId → { ok:true, principalId: teamId }
//   valid sub-group of this team → { ok:true, principalId: targetSubgroupId }
//   missing/invalid/cross-team → { ok:false, status: 404 }
```

- [ ] **Step 1: Write failing tests.** In `knowledge.spec.ts`/`resources.spec.ts`: sharing with `targetSubgroupId` of a real sub-group grants to the SUB-GROUP principal (assert the `grantPermission` call's `principalId === subgroupId`, and `findEntriesByPrincipal(GROUP, subgroupId, …)` returns it); sharing with an invalid/cross-team `targetSubgroupId` → 404; sharing without it still grants to the team (unchanged); unshare with `targetSubgroupId` revokes from the sub-group, not the team.
- [ ] **Step 2: Run, confirm FAIL:** `cd packages/api && npx jest knowledge resources`
- [ ] **Step 3: Implement.** Add `resolveShareTarget` (target.ts). In `knowledge.add` + `resources.share`, read `targetSubgroupId` from `req.body` (share) — after the existing owner/admin authz — call `resolveShareTarget(deps, teamId, targetSubgroupId)`; on `!ok` return its status; else use the returned `principalId` in `grantPermission({ principalId, … })` instead of the raw team `id`. In `knowledge.remove` + `resources.revoke`, read `targetSubgroupId` from `req.query`, resolve the same way, and `revokePermission(GROUP, principalId, …)`. Wire `getSubgroupById` into the handler deps (it's on `db`). Keep the no-target path byte-for-byte equivalent to today.
- [ ] **Step 4: Run tests → PASS.** `npx jest teams` (no regressions). Build `cd packages/api && npm run build`.
- [ ] **Step 5: Commit.**
```bash
git add packages/api/src/teams/target.ts packages/api/src/teams/knowledge.ts packages/api/src/teams/resources.ts packages/api/src/teams/knowledge.spec.ts packages/api/src/teams/resources.spec.ts
git commit -m "feat(api): share/unshare knowledge+agents+prompts to a sub-group (validated targetSubgroupId)"
```

---

### Task 3: Caller-scoped list + target annotation + union (knowledge + agents + prompts)

**Files:**
- Modify: `packages/api/src/teams/knowledge.ts` (`list` ~line 130), `packages/api/src/teams/resources.ts` (`list` ~line 173)
- Test: `packages/api/src/teams/knowledge.spec.ts`, `packages/api/src/teams/resources.spec.ts` (extend — the core access matrix)

**Interfaces:**
- Consumes: `db.getUserTeamPrincipals` (Task 1), `db.getTeamSubgroups` + `db.getTeamRole`/`resolveTeamAccess` (Phase 1), `findEntriesByPrincipal`. Each returned resource gains a `target: { type: 'team' } | { type: 'subgroup'; id: string; name: string }` field.

- [ ] **Step 1: Write failing tests — the access matrix.** Setup: team with members owner, m1 (in sub-group A), m2 (in sub-group B); a file F-team shared team-wide, F-A shared to A, F-B shared to B. Assert: `list` as m1 → [F-team, F-A] (not F-B); as m2 → [F-team, F-B]; as owner/admin → [F-team, F-A, F-B] each annotated with its target ('team'/'A'/'B'). Repeat the shape for agents + prompts (one each is enough). Assert the `target` annotation is correct.
- [ ] **Step 2: Run, confirm FAIL:** `cd packages/api && npx jest knowledge resources`
- [ ] **Step 3: Implement.** In each `list` handler, after authz: determine the caller's principals — if owner/admin, principals = `[teamId, ...(await getTeamSubgroups(teamId)).map(s => s._id)]` (management view: all); else principals = `await getUserTeamPrincipals({ userId: callerId, teamId })` (their accessible set). Query `findEntriesByPrincipal(GROUP, principal, resourceType)` for each principal (or extend the dep to accept many), build a sub-group id→name map (from `getTeamSubgroups`), resolve resources, and annotate each with `target` (principalId === teamId → `{type:'team'}` else `{type:'subgroup', id, name}`). **De-dup rule (decided): one row per ACL grant** — i.e. per (resource × visible target principal). A resource granted to both the team and sub-group A appears as two rows (target 'team' and target 'A'); the UI groups by resource. No collapsing logic needed. Keep response back-compat: existing fields unchanged, `target` added.
- [ ] **Step 4: Run tests → PASS.** `npx jest teams`. Build.
- [ ] **Step 5: Commit.**
```bash
git add packages/api/src/teams/knowledge.ts packages/api/src/teams/resources.ts packages/api/src/teams/knowledge.spec.ts packages/api/src/teams/resources.spec.ts
git commit -m "feat(api): caller-scoped team resource lists with sub-group target annotation (union)"
```

---

### Task 4: data-provider surface for sub-groups + targeted sharing (enables Phase 3 UI)

**Files:**
- Modify: `packages/data-provider/src/api-endpoints.ts`, `packages/data-provider/src/data-service.ts`, `packages/data-provider/src/keys.ts`, the team types module (where `TSubgroup` lives) + `types/queries.ts`
- Test: none new (type/surface only; verified by `tsc` + the Phase-3 hooks)

**Interfaces:**
- Produces: endpoint builders + data-service fns for the Phase-1 sub-group routes (`listSubgroups`, `getSubgroup`, `createSubgroup`, `updateSubgroup`, `deleteSubgroup`, `addSubgroupMember`, `removeSubgroupMember`) using `encodeURIComponent` on every dynamic segment; and a `targetSubgroupId?` param threaded into the existing `addTeamKnowledge`/`shareTeamAgent`/`shareTeamPrompt` (+ the unshare/`remove`) service fns + query string. Query/Mutation keys for sub-groups. Response types: `TSubgroupListResponse = { subgroups: TSubgroup[] }`, `TSubgroupDetailResponse = TSubgroupDetail`, and extend the knowledge/agent/prompt list item types with the `target` field from Task 3.

- [ ] **Step 1:** Add the endpoint builders (mirror the existing `teams`/`teamKnowledge` endpoint patterns in `api-endpoints.ts`), the data-service functions (mirror existing team service fns), the keys, and the types. Thread `targetSubgroupId?` through the share/unshare service fns (body for share, query for unshare) and the `target` field into the list response item types.
- [ ] **Step 2: Build + commit.**
```bash
npm run build:data-provider
git add packages/data-provider/src/api-endpoints.ts packages/data-provider/src/data-service.ts packages/data-provider/src/keys.ts packages/data-provider/src/types.ts packages/data-provider/src/types/queries.ts
git commit -m "feat(data-provider): sub-group endpoints/service/types + targetSubgroupId on share services"
```

---

## Self-Review (run after writing; fix inline)

- **Spec coverage (P2 scope):** targeted share → T2; caller-scoped list + target annotation + agents/prompts union → T3; the `getUserSubgroups` Entra carry-over → T1; data-provider surface for P3 → T4. The RAG "no hot-path change" claim is confirmed by a test in T1. ✓
- **Out of P2 scope:** frontend (P3); cascade on team/user delete + limits (P4). The Phase-1 flaky route-test cleanup race (M-NEW-1) — note in the ledger; if it recurs while running P2 suites, stabilize the cleanup, else defer to P4.
- **Type consistency:** `getUserTeamPrincipals` (T1) is consumed in T3's list union; `resolveShareTarget` (T2) returns `principalId` used by the grant/revoke calls; the `target` field shape (T3) matches the data-provider list types (T4). `db.getSubgroupById` returns null for non-sub-groups (Phase 1 kind-filter) so `resolveShareTarget` cross-team check is `sg?.parentTeamId?.toString() === teamId`.
- **Back-compat:** every no-`targetSubgroupId` path must remain byte-equivalent to today (grant to team, list all team resources for the existing callers) — verified by keeping/passing the existing knowledge/resources tests unchanged.

## Definition of done (Phase 2)

`packages/data-schemas`, `packages/api`, `packages/data-provider` build clean; all new + existing team specs green; owner/admin can share each resource type with a sub-group, members see only their accessible (team + their sub-groups) resources with correct target annotations, and a real-mongo test proves a sub-group-shared file reaches `getTeamSharedFileIds` for members only. Then local FF-merge to `fork/main` (release still deferred to after P3). The Entra-id carry-over is fixed; the data-provider surface is ready for the Phase-3 UI.
