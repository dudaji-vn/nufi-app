# Team RBAC Sub-groups — Phase 1 (Data model + Sub-group CRUD/Membership API) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the backend foundation for intra-team sub-groups ("Groups"): the data model and the owner/admin CRUD + membership API, so later phases can target shares at sub-groups.

**Architecture:** A sub-group is a regular `Group` document (`kind:'team_subgroup'`, `parentTeamId`). It reuses the existing Group schema, the `createUserGroupMethods` factory, the `createTeamsHandlers`-style handler factory + `resolveTeamAccess` authz, and the `teams.js` route. No ACL/RAG changes in P1 (sharing to sub-groups is P2).

**Tech Stack:** TypeScript (`packages/data-schemas`, `packages/api`, `packages/data-provider`), Mongoose, Express (thin JS wrapper in `/api`), Jest + `mongodb-memory-server`.

## Global Constraints

- New backend logic is **TypeScript** in `packages/data-schemas` (models/methods) and `packages/api` (handlers); `/api` holds only a thin JS route wrapper (CLAUDE.md D1).
- A sub-group IS a `Group` (`kind:'team_subgroup'`, `parentTeamId`) — do **not** create a new collection/model.
- Preserve the `memberIds` ↔ `members` dual-write invariant: `memberIds: string[]` is the ACL source of truth; `members: [{userId, role, joinedAt}]` mirrors it. Member id stored is `idOnTheSource || userId.toString()` (match existing `addTeamMember`).
- **Invariant:** a sub-group's members must be a subset of the parent team's `memberIds`. Reject adding a non-team-member.
- Sub-group membership is **binary** (no per-sub-group roles in v1); store `members[].role = 'member'`.
- **Owner/admin only** for every sub-group endpoint — reuse `resolveTeamAccess(id, callerId, 'admin')`.
- Apply `applyTenantIsolation` in any model factory touched; sub-groups inherit the parent team's `tenantId`. See `reference_data_schemas_tenant_isolation`.
- No `any`; explicit types; reuse existing types (`IGroup`, `TeamRole`, `TTeamMember`) rather than duplicating.
- Tests use real `mongodb-memory-server` (not mocked DB), per the project testing philosophy.
- Union access, no deny; no nesting (flat sub-groups under a team).

---

### Task 1: Group schema — sub-group fields

**Files:**
- Modify: `packages/data-schemas/src/schema/group.ts` (the `kind` enum ~line 69-72; add `parentTeamId`; add an index near line 100-102)
- Test: `packages/data-schemas/src/schema/group.spec.ts` (create if absent)

**Interfaces:**
- Produces: `IGroup.kind` now includes `'team_subgroup'`; `IGroup.parentTeamId?: Types.ObjectId`. Later tasks read `parentTeamId` to scope sub-groups to a team.

- [ ] **Step 1: Write the failing test** (`group.spec.ts`) — a real-mongo test that persists a sub-group:
```ts
it('persists a sub-group with kind team_subgroup and parentTeamId', async () => {
  const Group = mongoose.model('Group');
  const parentTeamId = new mongoose.Types.ObjectId();
  const sg = await Group.create({
    name: 'Engineering', kind: 'team_subgroup', parentTeamId,
    ownerId: new mongoose.Types.ObjectId(), memberIds: [], members: [],
  });
  const found = await Group.findById(sg._id).lean();
  expect(found?.kind).toBe('team_subgroup');
  expect(found?.parentTeamId?.toString()).toBe(parentTeamId.toString());
});
```
- [ ] **Step 2: Run it, confirm it FAILS** (`kind` rejects `'team_subgroup'`, or `parentTeamId` is stripped by strict mode): `cd packages/data-schemas && npx jest group.spec`
- [ ] **Step 3: Implement** — in `group.ts`: extend the enum and add the field + index:
```ts
// kind field:
kind: { type: String, enum: ['group', 'team', 'team_subgroup'], default: 'group' },
// add alongside the other fields:
parentTeamId: { type: Schema.Types.ObjectId, ref: 'Group', index: true },
```
(Mirror the existing `ownerId` ObjectId definition. The strict-mode lesson from Phase 6 applies: a field not in the schema is silently dropped.)
- [ ] **Step 4: Run the test, confirm PASS**
- [ ] **Step 5: Build + commit**
```bash
npm run build:data-schemas 2>/dev/null || (cd packages/data-schemas && npm run build)
git add packages/data-schemas/src/schema/group.ts packages/data-schemas/src/schema/group.spec.ts
git commit -m "feat(data-schemas): sub-group fields on Group (kind, parentTeamId)"
```

---

### Task 2: Sub-group methods (CRUD + membership + invariant)

**Files:**
- Modify: `packages/data-schemas/src/methods/userGroup.ts` (add functions inside `createUserGroupMethods`; export them in the returned object ~line 1016-1040)
- Test: `packages/data-schemas/src/methods/userGroup.subgroup.spec.ts` (new)

**Interfaces:**
- Consumes: existing `createGroup`, `getTeamById` (or `Group` model directly), the `memberIds`/`members` dual-write done by `addTeamMember` (line 836) — mirror it.
- Produces (add to the returned methods object so they reach `db.*`):
```ts
createSubgroup(params: {
  parentTeamId: string | Types.ObjectId; name: string; description?: string;
  ownerId: string | Types.ObjectId; tenantId?: string; session?: ClientSession;
}): Promise<IGroup>;
getTeamSubgroups(parentTeamId: string | Types.ObjectId): Promise<IGroup[]>;
getSubgroupById(subgroupId: string | Types.ObjectId): Promise<IGroup | null>;
updateSubgroup(subgroupId: string | Types.ObjectId, updates: { name?: string; description?: string }): Promise<IGroup | null>;
deleteSubgroup(subgroupId: string | Types.ObjectId, session?: ClientSession): Promise<void>;
addSubgroupMember(params: { subgroupId: string | Types.ObjectId; userId: string; session?: ClientSession }): Promise<IGroup>;
removeSubgroupMember(params: { subgroupId: string | Types.ObjectId; userId: string; session?: ClientSession }): Promise<IGroup>;
getUserSubgroups(params: { userId: string; parentTeamId: string | Types.ObjectId }): Promise<IGroup[]>;
```

- [ ] **Step 1: Write failing tests** (`userGroup.subgroup.spec.ts`) — real mongo, covering the invariant + union:
```ts
// setup: createTeam(...) with ownerId; addTeamMember for users u1, u2 (so team.memberIds = [owner,u1,u2]).
it('createSubgroup stores kind/parentTeamId and inherits tenantId', async () => { /* assert kind, parentTeamId, tenantId */ });
it('addSubgroupMember adds a team member (dual-writes memberIds + members)', async () => {
  const sg = await methods.createSubgroup({ parentTeamId: team._id, name: 'Eng', ownerId });
  const updated = await methods.addSubgroupMember({ subgroupId: sg._id, userId: u1 });
  expect(updated.memberIds).toContain(u1);
  expect(updated.members.find(m => m.userId.toString() === u1)).toBeTruthy();
});
it('addSubgroupMember REJECTS a non-team-member', async () => {
  const sg = await methods.createSubgroup({ parentTeamId: team._id, name: 'Eng', ownerId });
  await expect(methods.addSubgroupMember({ subgroupId: sg._id, userId: 'stranger' }))
    .rejects.toThrow(/not a member of the team/i);
});
it('getUserSubgroups returns only the subgroups the user belongs to', async () => {
  const a = await methods.createSubgroup({ parentTeamId: team._id, name: 'A', ownerId });
  const b = await methods.createSubgroup({ parentTeamId: team._id, name: 'B', ownerId });
  await methods.addSubgroupMember({ subgroupId: a._id, userId: u1 });
  const got = await methods.getUserSubgroups({ userId: u1, parentTeamId: team._id });
  expect(got.map(g => g._id.toString())).toEqual([a._id.toString()]);
});
it('removeSubgroupMember pulls from memberIds and members', async () => { /* ... */ });
it('getTeamSubgroups lists all subgroups of a team', async () => { /* ... */ });
```
- [ ] **Step 2: Run, confirm FAIL** (methods undefined): `cd packages/data-schemas && npx jest userGroup.subgroup`
- [ ] **Step 3: Implement the methods.** Key bodies (reuse `createGroup` + mirror `addTeamMember`'s dual-write):
```ts
async function createSubgroup({ parentTeamId, name, description, ownerId, tenantId, session }) {
  return createGroup({ name, description, kind: 'team_subgroup', parentTeamId, ownerId, tenantId, memberIds: [], members: [] }, session);
}
async function getTeamSubgroups(parentTeamId) {
  return Group.find({ parentTeamId, kind: 'team_subgroup' }).lean();
}
async function addSubgroupMember({ subgroupId, userId, session }) {
  const sg = await Group.findById(subgroupId);                       // need parentTeamId
  if (!sg) throw new Error('Sub-group not found');
  const team = await Group.findById(sg.parentTeamId).lean();
  if (!team || !(team.memberIds ?? []).includes(userId)) {
    throw new Error('User is not a member of the team');             // the invariant
  }
  if (!sg.memberIds.includes(userId)) {
    sg.memberIds.push(userId);
    sg.members.push({ userId, role: 'member', joinedAt: new Date() });
    await sg.save({ session });
  }
  return sg.toObject();
}
async function getUserSubgroups({ userId, parentTeamId }) {
  return Group.find({ parentTeamId, kind: 'team_subgroup', memberIds: userId }).lean();
}
// removeSubgroupMember: $pull from memberIds and members by userId.
// updateSubgroup: findByIdAndUpdate {name?, description?}, {new:true}.
// deleteSubgroup: await Group.deleteOne({ _id: subgroupId }, { session }).
```
(`Group` is the model already in scope in this factory; `createGroup` already applies tenant isolation — pass `tenantId` through.)
- [ ] **Step 4: Run tests, confirm PASS**
- [ ] **Step 5: Build + commit**
```bash
cd packages/data-schemas && npm run build && cd ../..
git add packages/data-schemas/src/methods/userGroup.ts packages/data-schemas/src/methods/userGroup.subgroup.spec.ts
git commit -m "feat(data-schemas): sub-group CRUD + membership methods (with team-subset invariant)"
```

---

### Task 3: Shared types for sub-groups

**Files:**
- Modify: `packages/data-provider/src/types.ts` (or the team types module where `TTeam`/`TTeamMember` live — grep `TTeamMember` to locate)
- Test: none (type-only; verified by `tsc` in consuming tasks)

**Interfaces:**
- Produces:
```ts
export type TSubgroup = {
  _id: string;
  name: string;
  description?: string;
  parentTeamId: string;
  memberCount: number;        // computed in the list handler
};
export type TSubgroupMember = TTeamMember;   // reuse existing member shape
export type TSubgroupDetail = { subgroup: TSubgroup; members: TSubgroupMember[] };
```
- [ ] **Step 1: Add the types** next to `TTeam`/`TTeamMember`, reusing `TTeamMember`. Do not duplicate the member shape.
- [ ] **Step 2: Build + commit**
```bash
npm run build:data-provider
git add packages/data-provider/src/types.ts
git commit -m "feat(data-provider): sub-group shared types"
```

---

### Task 4: Sub-group handlers (factory + authz + invariant → HTTP)

**Files:**
- Create: `packages/api/src/teams/subgroups.ts`
- Modify: `packages/api/src/teams/index.ts` (export `createSubgroupsHandlers`)
- Test: `packages/api/src/teams/subgroups.spec.ts`

**Interfaces:**
- Consumes: the `db` methods from Task 2 (`createSubgroup`, `getTeamSubgroups`, `getSubgroupById`, `updateSubgroup`, `deleteSubgroup`, `addSubgroupMember`, `removeSubgroupMember`), the `resolveTeamAccess(id, callerId, minRole)` helper pattern from `handlers.ts` (reuse/extract it if exported; else mirror it), and `deleteAclEntries({ principalId })`.
- Produces: `createSubgroupsHandlers(deps): { create, list, get, update, remove, addMember, removeMember }` — Express handlers.

- [ ] **Step 1: Write failing handler tests** (`subgroups.spec.ts`, mirroring `handlers.spec.ts` setup with in-memory mongo + a fake `req/res`):
```ts
it('create: owner can create a sub-group → 201 with {subgroup}', async () => { /* ... */ });
it('create: a plain member is denied → 403', async () => { /* resolveTeamAccess minRole admin */ });
it('addMember: rejects a non-team-member → 400/422', async () => { /* invariant surfaces as HTTP error */ });
it('list: returns the team sub-groups with memberCount', async () => { /* ... */ });
it('remove: deletes the sub-group and revokes its ACL grants', async () => { /* spy deleteAclEntries called with {principalId: sgId} */ });
```
- [ ] **Step 2: Run, confirm FAIL**: `cd packages/api && npx jest subgroups`
- [ ] **Step 3: Implement `createSubgroupsHandlers`.** Skeleton (every handler authorizes first via `resolveTeamAccess`):
```ts
export function createSubgroupsHandlers(deps: SubgroupsHandlersDeps) {
  const { db } = deps;
  async function resolveAdmin(req, res) {            // reuse handlers.ts resolveTeamAccess if exported
    const access = await resolveTeamAccess(db, req.params.id, callerId(req), 'admin');
    if ('error' in access) { res.status(access.status).json({ error: access.error }); return null; }
    return access;                                   // { team, role }
  }
  return {
    async create(req, res) {
      const access = await resolveAdmin(req, res); if (!access) return;
      const { name, description } = req.body;
      if (!name?.trim()) return res.status(400).json({ error: 'name is required' });
      const sg = await db.createSubgroup({ parentTeamId: access.team._id, name: name.trim(), description, ownerId: access.team.ownerId, tenantId: access.team.tenantId });
      return res.status(201).json({ subgroup: toSubgroupDTO(sg, 0) });
    },
    async list(req, res) {
      const access = await resolveAdmin(req, res); if (!access) return;
      const subs = await db.getTeamSubgroups(access.team._id);
      return res.json({ subgroups: subs.map(s => toSubgroupDTO(s, (s.memberIds ?? []).length)) });
    },
    async addMember(req, res) {
      const access = await resolveAdmin(req, res); if (!access) return;
      const sg = await db.getSubgroupById(req.params.sgId);
      if (!sg || sg.parentTeamId?.toString() !== access.team._id.toString()) return res.status(404).json({ error: 'Sub-group not found' });
      try {
        const updated = await db.addSubgroupMember({ subgroupId: sg._id, userId: req.body.userId });
        return res.json({ subgroup: toSubgroupDTO(updated, updated.memberIds.length) });
      } catch (e) { return res.status(400).json({ error: e.message }); }   // invariant → 400
    },
    async remove(req, res) {
      const access = await resolveAdmin(req, res); if (!access) return;
      const sg = await db.getSubgroupById(req.params.sgId);
      if (!sg || sg.parentTeamId?.toString() !== access.team._id.toString()) return res.status(404).json({ error: 'Sub-group not found' });
      await db.deleteAclEntries({ principalId: sg._id });   // revoke any grants (no-op until P2)
      await db.deleteSubgroup(sg._id);
      return res.json({ success: true });
    },
    // get, update, removeMember: same authz + parent-ownership check + db call.
  };
}
```
Every handler must verify the sub-group's `parentTeamId === :id` before acting (prevents cross-team access via a guessed sgId).
- [ ] **Step 4: Run tests, confirm PASS.** Build: `cd packages/api && npm run build`
- [ ] **Step 5: Commit**
```bash
git add packages/api/src/teams/subgroups.ts packages/api/src/teams/index.ts packages/api/src/teams/subgroups.spec.ts
git commit -m "feat(api): sub-group handlers (CRUD + membership, owner/admin authz, team-subset invariant)"
```

---

### Task 5: Route wiring + integration test

**Files:**
- Modify: `api/server/routes/teams.js` (instantiate `subgroupHandlers` from `db`; add 7 routes after the members routes ~line 90)
- Test: `api/server/routes/teams.subgroups.spec.js` (supertest-style integration, mirroring existing teams route tests if present; else a handler-level integration test)

**Interfaces:**
- Consumes: `createSubgroupsHandlers` (Task 4); the `db` object built in `teams.js` from `require('~/models')`.

- [ ] **Step 1: Write a failing integration test** asserting the routes exist + persist + authorize (owner creates a sub-group → 201; member → 403; add a team member to it → 200; non-team-member → 400).
- [ ] **Step 2: Run, confirm FAIL** (routes 404): `cd api && npx jest teams.subgroups`
- [ ] **Step 3: Wire the routes** (thin JS — handlers carry the logic):
```js
const subgroupHandlers = createSubgroupsHandlers({ db });
router.post('/:id/subgroups', subgroupHandlers.create);
router.get('/:id/subgroups', subgroupHandlers.list);
router.get('/:id/subgroups/:sgId', subgroupHandlers.get);
router.patch('/:id/subgroups/:sgId', subgroupHandlers.update);
router.delete('/:id/subgroups/:sgId', subgroupHandlers.remove);
router.post('/:id/subgroups/:sgId/members', subgroupHandlers.addMember);
router.delete('/:id/subgroups/:sgId/members/:userId', subgroupHandlers.removeMember);
```
(These inherit the router-level `requireJwtAuth, checkBan, configMiddleware`.)
- [ ] **Step 4: Run tests, confirm PASS**
- [ ] **Step 5: Commit**
```bash
git add api/server/routes/teams.js api/server/routes/teams.subgroups.spec.js
git commit -m "feat(api): wire sub-group routes on the teams router"
```

---

## Self-Review (run after writing; fix inline)

- **Spec coverage (P1 scope):** schema (`kind`, `parentTeamId`) → Task 1; methods + invariant + union → Task 2; types → Task 3; CRUD/membership endpoints + owner/admin authz → Tasks 4-5. The `getUserSubgroups` union helper (Task 2) is what P2 will use to extend agents/prompts listing. ✓
- **Out of P1 scope (do NOT build here):** targeted sharing / `targetSubgroupId` (P2), frontend (P3), full cascade on team/user delete + limits (P4). `deleteSubgroup`'s own grant-revoke IS in P1 (intrinsic to delete), but no-op until P2 adds grants.
- **Type consistency:** `IGroup.parentTeamId` (Task 1) is read in Tasks 2/4; `TSubgroup`/`TSubgroupMember` (Task 3) reuse `TTeamMember`; method names in Task 2's `Produces` match the `db.*` calls in Task 4. The handler authz reuses `resolveTeamAccess`/`hasMinRole` from `handlers.ts` — if not exported, Task 4 extracts it to a shared `access.ts` helper (already a file in `packages/api/src/teams/`).
- **Invariant placement:** enforced in `addSubgroupMember` (Task 2, data layer) AND surfaced as HTTP 400 in the handler (Task 4) — defense at the source, friendly error at the edge.

## Definition of done (Phase 1)

`packages/data-schemas`, `packages/api` build clean; all new specs green (real mongo); a team owner/admin can create sub-groups and manage their membership over HTTP, with the team-subset invariant and owner/admin authz enforced. No sharing/UI yet. Then: local FF-merge to `fork/main` per the team-workspaces phase rhythm (release deferred until the feature is usable end-to-end, or per `feedback_release_flow`).
