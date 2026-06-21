# Team Workspaces — Phase 0: Data Model (Spec)

> Detailed implementation spec for **Phase 0** of the master plan
> [`team-workspaces-shared-rag.md`](./team-workspaces-shared-rag.md). Phase 0 models team
> ownership, member roles, and invitations — entirely inside the `@librechat/data-schemas`
> package, with unit tests on a real in-memory MongoDB. No API routes, no UI, no FILE ACL
> (those are later phases).

## 1. Scope & boundaries

**In scope (all in `packages/data-schemas`):**

1. Extend the `Group` schema/types with team ownership, per-member roles, and a `kind`
   discriminator — **without changing existing fields** so admin/Entra paths keep working.
2. New `TeamInvite` schema + model + types + methods (invite lifecycle).
3. New team-membership-with-roles methods on `userGroup.ts`, keeping `memberIds` in sync with
   the new `members[]` array through a single atomic mutation per operation.
4. Wire the new model/methods/types/schema into the four barrel files.
5. Unit tests (TDD) covering the invite lifecycle, role helpers, and `memberIds` ↔ `members`
   consistency.

**Explicitly out of scope (later phases):**

- `api/server/routes/teams.js` and any `/api` endpoints or controllers (Phase 1–2).
- Email sending for invites (Phase 2).
- `ResourceType.FILE` / FILE access roles / shared-RAG retrieval (Phase 3).
- Frontend (Phase 5), interface permission `TEAMS` and config limits (Phase 6).

## 2. Locked decisions

- **Single owner per team.** `ownerId` is the source of truth for ownership.
  - Invariant: a team always has **exactly one** member with `role === 'owner'`, and
    `ownerId === that member.userId`.
  - Owner-only operations (enforced at the API layer in later phases, but the data methods
    make them expressible): delete team, transfer ownership.
  - Admins manage members/knowledge/settings; members are read/use only.
  - Changing the owner requires an explicit `transferOwnership` — you cannot demote or remove
    the sole owner directly (last-owner protection).
- **A team is a `Group`** with `kind: 'team'`, `source: 'local'`. Admin/Entra groups keep the
  default `kind: 'group'` and are untouched.
- **`memberIds` remains the ACL membership source.** The ACL principal resolution path
  (`getUserPrincipals → getUserGroups → findGroupsByMemberId`) reads `memberIds`, which stores
  `idOnTheSource` strings (for a local user with no external id, this is `userId.toString()`).
  Every team-membership mutation must update `memberIds` with the **same** value the existing
  `addUserToGroup` would (`user.idOnTheSource || userId.toString()`), so ACL checks keep working.
- **Invites carry `role: 'admin' | 'member'` only.** Ownership is never granted by invite; it
  moves only via `transferOwnership`.
- **Method/file conventions follow the `auditLog` feature** (most recent addition to this fork):
  `schema/X.ts` (default export `Schema<IX>`), `models/X.ts` (`createXModel` factory),
  `types/X.ts` (`IX extends Document`), `methods/X.ts` (`createXMethods` factory +
  `export type XMethods = ReturnType<...>`).

## 3. Schema & type changes

### 3.1 `Group` — `schema/group.ts` (extend, do not modify existing fields)

Add:

| Field | Definition | Notes |
|---|---|---|
| `kind` | `{ type: String, enum: ['group','team'], default: 'group', index: true }` | Distinguishes self-service teams from admin/Entra groups |
| `ownerId` | `{ type: Schema.Types.ObjectId, ref: 'User', index: true }` | Optional (existing groups have none). Always points to a member with `role: 'owner'` |
| `members` | array of `groupMemberSchema` subdocuments, `{ _id: false }` | Source of truth for per-member role |
| `joinPolicy` | `{ type: String, enum: ['invite'], default: 'invite' }` | Room for `request`/`open` later |

`groupMemberSchema` (subdocument, `_id: false`):

```
userId:   { type: Schema.Types.ObjectId, ref: 'User', required: true }
role:     { type: String, enum: ['owner','admin','member'], default: 'member', required: true }
joinedAt: { type: Date, default: Date.now }
```

Additional indexes:

```
groupSchema.index({ 'members.userId': 1 });
groupSchema.index({ ownerId: 1, kind: 1 });
```

### 3.2 `Group` types — `types/group.ts`

```ts
export type TeamRole = 'owner' | 'admin' | 'member';
export type GroupKind = 'group' | 'team';

export interface IGroupMember {
  userId: Types.ObjectId;
  role: TeamRole;
  joinedAt: Date;
}
```

Extend `IGroup` with: `kind?: GroupKind;`, `ownerId?: Types.ObjectId;`,
`members?: IGroupMember[];`, `joinPolicy?: 'invite';`.

### 3.3 `TeamInvite` — new `schema/teamInvite.ts`, `models/teamInvite.ts`, `types/teamInvite.ts`

```ts
export type TeamInviteStatus = 'pending' | 'accepted' | 'declined' | 'expired' | 'revoked';
export type TeamInviteRole = 'admin' | 'member';

export interface ITeamInvite extends Document {
  _id: Types.ObjectId;
  groupId: Types.ObjectId;          // ref Group
  email: string;                    // stored lowercased
  invitedUserId?: Types.ObjectId;   // nullable — resolved if the email maps to a user
  role: TeamInviteRole;
  token: string;                    // unique, high-entropy (crypto.randomBytes(32).hex)
  status: TeamInviteStatus;         // default 'pending'
  invitedBy: Types.ObjectId;        // ref User
  expiresAt: Date;
  tenantId?: string;
  createdAt?: Date;
  updatedAt?: Date;
}
```

Schema fields mirror the type. Indexes:

```
teamInviteSchema.index({ token: 1 }, { unique: true });
teamInviteSchema.index({ email: 1, status: 1 });
teamInviteSchema.index({ groupId: 1, status: 1 });
teamInviteSchema.index({ invitedUserId: 1, status: 1 });
teamInviteSchema.index({ expiresAt: 1 });
```

`models/teamInvite.ts`: `createTeamInviteModel(mongoose)` using the
`mongoose.models.TeamInvite || mongoose.model('TeamInvite', teamInviteSchema)` guard.

## 4. Methods

### 4.1 `userGroup.ts` — new team-membership methods

All mutations are **atomic single-document updates** (Mongoose `findOneAndUpdate`); no
multi-document transactions are required because every change targets one `Group` document.
Each method that adds a member computes `memberIdValue = user.idOnTheSource || userId.toString()`
(a single `User.findById(userId, 'idOnTheSource')` lookup) before writing.

- `createTeam({ name, description?, avatar?, ownerId, tenantId? }, session?) → IGroup`
  Creates a `Group` with `kind: 'team'`, `ownerId`, `members: [{ userId: ownerId, role:
  'owner', joinedAt: now }]`, and `memberIds: [ownerMemberIdValue]`. Establishes the invariant
  at creation.
- `addTeamMember({ groupId, userId, role = 'member' }, session?) → IGroup | null`
  Rejects `role: 'owner'` (throws). Guards against duplicates with the query filter
  `{ _id: groupId, 'members.userId': { $ne: userId } }`, applying
  `$push: { members: { userId, role, joinedAt: now } }` and
  `$addToSet: { memberIds: memberIdValue }`. Returns the updated group, or `null` when the
  filter does not match — i.e. the user is already a member **or** the group does not exist
  (the no-op case). The API layer (Phase 1) verifies team existence before calling, so within
  Phase 0 a `null` is treated as "already a member".
- `removeTeamMember({ groupId, userId }, session?) → IGroup | null`
  Rejects removing the current owner (throw — must transfer first). Applies
  `$pull: { members: { userId } }` and `$pull: { memberIds: memberIdValue }`.
- `setMemberRole({ groupId, userId, role }, session?) → IGroup | null`
  Only `'admin' | 'member'`. Rejects `'owner'` (use `transferOwnership`) and rejects demoting
  the current owner. Uses `arrayFilters` (`$set: { 'members.$[e].role': role }`,
  `arrayFilters: [{ 'e.userId': userId }]`).
- `getTeamRole({ groupId, userId }, session?) → TeamRole | null`
  Reads the `members` subdocument for `userId`.
- `transferOwnership({ groupId, fromUserId, toUserId }, session?) → IGroup | null`
  First reads the group to validate preconditions — `fromUserId` is the current `ownerId` and
  `toUserId` is an existing member — and **throws** if either fails. Then performs a single
  atomic update: `$set: { ownerId: toUserId, 'members.$[old].role': 'admin',
  'members.$[new].role': 'owner' }` with `arrayFilters: [{ 'old.userId': fromUserId }, {
  'new.userId': toUserId }]`. (Transferring to the current owner is a no-op success.)
- `getUserTeams({ userId }, session?) → IGroup[]`
  `find({ kind: 'team', 'members.userId': userId })`.

Existing methods (`addUserToGroup`, `removeUserFromGroup`, `syncUserEntraGroups`, etc.) are
**not modified**; team groups are mutated only through the new methods above.

### 4.2 `methods/teamInvite.ts` — `createTeamInviteMethods(mongoose)`

- `createInvite({ groupId, email, role, invitedBy, invitedUserId?, tenantId?, ttlMs? }) → ITeamInvite`
  Lowercases `email`; generates `token = crypto.randomBytes(32).toString('hex')`; sets
  `expiresAt = new Date(Date.now() + (ttlMs ?? 7 days))`, `status: 'pending'`.
- `findInviteByToken(token) → ITeamInvite | null`
- `listPendingInvitesForUser({ userId?, email? }) → ITeamInvite[]`
  `status: 'pending'`, `expiresAt > now`, matching `invitedUserId === userId` OR
  `email === lowercased email`.
- `listInvitesForTeam({ groupId, status? }) → ITeamInvite[]`
- `acceptInvite({ token, userId }) → ITeamInvite | null`
  Atomic `findOneAndUpdate({ token, status: 'pending', expiresAt: { $gt: now } }, { $set: {
  status: 'accepted', invitedUserId: userId } }, { new: true })`. Returns `null` if already
  used/expired (double-accept safe). **Does not** add membership — the Phase 2 endpoint composes
  `acceptInvite` + `addTeamMember` so the data method stays single-purpose.
- `declineInvite({ token }) → ITeamInvite | null` — atomic `pending → declined`.
- `revokeInvite({ inviteId }) → ITeamInvite | null` — atomic `pending → revoked`.
- `expireStaleInvites() → number` — `updateMany({ status: 'pending', expiresAt: { $lte: now }
  }, { $set: { status: 'expired' } })`; returns the modified count.

`export type TeamInviteMethods = ReturnType<typeof createTeamInviteMethods>;`

## 5. Wiring (barrel files)

- `models/index.ts`: import `createTeamInviteModel`; add `TeamInvite: createTeamInviteModel(mongoose)`.
- `methods/index.ts`: import `createTeamInviteMethods` + `TeamInviteMethods`; add to the
  `AllMethods` intersection; spread `...createTeamInviteMethods(mongoose)` in `createMethods`;
  re-export `TeamInviteMethods`. (New `userGroup` methods need no extra wiring — they ride on the
  existing `createUserGroupMethods` spread.)
- `schema/index.ts`: `export { default as teamInviteSchema } from './teamInvite';`
- `types/index.ts`: `export * from './teamInvite';`

## 6. Tests (TDD — write first, watch fail, then implement)

Use the existing harness pattern (`MongoMemoryServer`, register models, call the factory) seen in
`userGroup.roles.spec.ts`.

**`methods/userGroup.team.spec.ts`:**

- `createTeam` establishes the invariant (one owner, `ownerId` matches, owner in `members`,
  `memberIds` seeded with the owner's `idOnTheSource`/id).
- `addTeamMember` updates **both** `members` and `memberIds`; rejects duplicate adds (no-op);
  rejects `role: 'owner'`; stores the correct `memberIds` value for users with and without
  `idOnTheSource`.
- `removeTeamMember` pulls from **both** arrays; refuses to remove the owner.
- `setMemberRole` flips admin↔member; refuses `'owner'`; refuses demoting the owner.
- `getTeamRole` returns the correct role or `null`.
- `transferOwnership` swaps roles and `ownerId` atomically; old owner becomes admin; rejects when
  `fromUserId` is not the current owner or `toUserId` is not a member.
- `getUserTeams` returns only `kind: 'team'` groups the user is a member of.
- **Consistency:** after any add/remove/transfer, the set of `memberIds` equals the set of
  `members[].userId` mapped through `idOnTheSource || _id`.

**`methods/teamInvite.spec.ts`:**

- `createInvite` lowercases email, sets `pending`, unique high-entropy token, future `expiresAt`;
  honors a custom `ttlMs`.
- `findInviteByToken` round-trips.
- `listPendingInvitesForUser` matches by `invitedUserId` or `email`; excludes expired/non-pending.
- `listInvitesForTeam` filters by `groupId` (and optional `status`).
- `acceptInvite` transitions `pending → accepted`, stamps `invitedUserId`; a second accept returns
  `null`; an expired invite returns `null`.
- `declineInvite` / `revokeInvite` transition only from `pending`.
- `expireStaleInvites` flips only past-due pending invites and returns the count.

## 7. Acceptance criteria

- `npm run build` in `packages/data-schemas` succeeds (rollup), producing updated `dist`.
- New specs pass: `npx jest userGroup.team teamInvite`.
- Full package test suite stays green: `npm run test:ci`.
- `memberIds` is provably consistent with `members` after add/remove/transfer (covered by the
  consistency test).

## 8. Phase-0-specific risks & mitigations

| Risk | Mitigation |
|---|---|
| `memberIds` (idOnTheSource strings) drifting from `members` (ObjectIds) | One atomic mutation per op updates both with the same `idOnTheSource \|\| userId.toString()` value; dedicated consistency test |
| Existing admin/Entra group paths regressing | Existing fields/methods untouched; new fields are additive with safe defaults (`kind: 'group'`) |
| Race on invite accept (double-accept) | `acceptInvite` is a single atomic `findOneAndUpdate` guarded on `status: 'pending'` + `expiresAt` |
| Ownerless team / removing the last owner | `removeTeamMember`/`setMemberRole` refuse to touch the owner; ownership moves only via `transferOwnership` |
| `crypto`/`Date` usage in a "pure" package | Node's `crypto` and `Date` are available at runtime in `data-schemas`; only the Workflow scripting sandbox forbids them |

## 9. Git / release

- Branch: `feat/team-workspaces-phase0` (off `fork/main`, which holds the latest code incl. the
  audit-log reference pattern; `develop` is currently behind by 6 commits).
- Bump `@librechat/data-schemas` `0.0.51 → 0.0.52` and rebuild `dist` so `/api` consumes the new
  methods. (Done at the end of the phase.)
- PR target to be confirmed with the maintainer at merge time (per the NUFI release flow,
  feature → `develop`; but `develop` is stale relative to `fork/main`).
