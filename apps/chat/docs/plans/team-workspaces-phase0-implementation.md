# Team Workspaces — Phase 0 (Data Model) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add team ownership, per-member roles, and an invitation lifecycle to `@librechat/data-schemas` — as additive schema fields plus new factory methods — without changing any existing admin/Entra group behavior.

**Architecture:** A "team" is a `Group` with `kind: 'team'`, a single `ownerId`, and a `members[{userId, role, joinedAt}]` array. The legacy `memberIds` string array (the ACL membership source) is kept in sync by every team-membership mutation through one atomic single-document update. Invitations live in a new `TeamInvite` collection with a single-purpose method set; membership is added by composing `acceptInvite` + `addTeamMember` (the composition belongs to a later phase).

**Tech Stack:** TypeScript, Mongoose 8.23.1, Jest + `mongodb-memory-server`, Rollup (package build). Spec: [`team-workspaces-phase0-data-model.md`](./team-workspaces-phase0-data-model.md).

## Global Constraints

- **Package:** all work is in `packages/data-schemas`. Run tests from there: `npx jest <pattern>`. Build: `npm run build`.
- **No `any`.** Avoid `unknown` / `Record<string, unknown>`; use `FilterQuery<T>` for Mongo filters.
- **Factory pattern:** new model = `models/X.ts` `createXModel(mongoose)`; new methods = `methods/X.ts` `createXMethods(mongoose)` returning an object literal + `export type XMethods = ReturnType<typeof createXMethods>`.
- **`memberIds` value** for any user is always `user.idOnTheSource || userId.toString()` — identical to the existing `addUserToGroup`.
- **Atomic mutations:** every membership/invite state change is a single `findOneAndUpdate` / `updateMany` (one document), never a read-modify-write across awaits except where a precondition read is explicitly required (`removeTeamMember`, `setMemberRole`, `transferOwnership`).
- **Node crypto import:** `import crypto from 'node:crypto';` then `crypto.randomBytes(32).toString('hex')` (matches `methods/agent.ts`).
- **Invite roles** are `'admin' | 'member'` only. Ownership moves **only** via `transferOwnership`.
- **Owner invariant:** a team always has exactly one member with `role: 'owner'`, and `ownerId === that member.userId`.
- **Tests:** real in-memory MongoDB (`mongodb-memory-server`), real queries — no mocking of Mongoose. Mock only the winston logger (`jest.mock('~/config/winston', ...)`).
- **Branch:** `feat/team-workspaces-phase0`.
- **Commit trailers:** every commit message ends with these two lines:
  ```
  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_0124K78cKsx5zsmH9YWfnqAd
  ```
- **Version bump** `@librechat/data-schemas` `0.0.51 → 0.0.52` and rebuild `dist` in the final task.

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `src/types/group.ts` | Modify | Add `TeamRole`, `GroupKind`, `IGroupMember`; extend `IGroup` |
| `src/schema/group.ts` | Modify | Add `groupMemberSchema` + `kind`/`ownerId`/`members`/`joinPolicy` fields + indexes |
| `src/methods/userGroup.ts` | Modify | Add `resolveMemberIdValue` + 7 team methods to the factory |
| `src/methods/userGroup.team.spec.ts` | Create | Tests for schema defaults + team membership/role/ownership methods |
| `src/types/teamInvite.ts` | Create | `TeamInviteStatus`, `TeamInviteRole`, `ITeamInvite` |
| `src/schema/teamInvite.ts` | Create | `teamInviteSchema` + indexes |
| `src/models/teamInvite.ts` | Create | `createTeamInviteModel` factory |
| `src/methods/teamInvite.ts` | Create | `createTeamInviteMethods` factory (8 methods) |
| `src/methods/teamInvite.spec.ts` | Create | Tests for the invite lifecycle |
| `src/models/index.ts` | Modify | Register `TeamInvite` |
| `src/methods/index.ts` | Modify | Add `TeamInviteMethods` to `AllMethods`, spread + export |
| `src/schema/index.ts` | Modify | Re-export `teamInviteSchema` |
| `src/types/index.ts` | Modify | Re-export `teamInvite` types |
| `package.json` | Modify | Version `0.0.51 → 0.0.52` |

---

## Task 1: Extend the Group schema & types

**Files:**
- Modify: `src/types/group.ts`
- Modify: `src/schema/group.ts`
- Test: `src/methods/userGroup.team.spec.ts` (create)

**Interfaces:**
- Produces: `TeamRole = 'owner'|'admin'|'member'`, `GroupKind = 'group'|'team'`, `IGroupMember { userId: Types.ObjectId; role: TeamRole; joinedAt: Date }`, and an `IGroup` carrying optional `kind`, `ownerId`, `members`, `joinPolicy`. The `Group` Mongoose model now persists those fields (defaults: `kind: 'group'`, `joinPolicy: 'invite'`; `members` unset unless provided).

- [ ] **Step 1: Add types to `src/types/group.ts`**

Add above `IGroup`:

```ts
export type TeamRole = 'owner' | 'admin' | 'member';
export type GroupKind = 'group' | 'team';

export interface IGroupMember {
  userId: Types.ObjectId;
  role: TeamRole;
  joinedAt: Date;
}
```

Add these fields inside the `IGroup` interface (after `tenantId?: string;`):

```ts
  /** 'team' = self-service workspace; 'group' = admin/Entra group (default). */
  kind?: GroupKind;
  /** The single team owner. Always equals a member whose role is 'owner'. */
  ownerId?: Types.ObjectId;
  /** Per-member roles for teams. Source of truth for role; kept in sync with memberIds. */
  members?: IGroupMember[];
  joinPolicy?: 'invite';
```

- [ ] **Step 2: Add the member subdocument + fields to `src/schema/group.ts`**

Replace the import line `import type { IGroup } from '~/types';` with:

```ts
import type { IGroup, IGroupMember } from '~/types';
```

Add this subdocument schema directly above `const groupSchema = ...`:

```ts
const groupMemberSchema = new Schema<IGroupMember>(
  {
    userId: {
      type: Schema.Types.ObjectId,
      ref: 'User',
      required: true,
    },
    role: {
      type: String,
      enum: ['owner', 'admin', 'member'],
      default: 'member',
      required: true,
    },
    joinedAt: {
      type: Date,
      default: Date.now,
    },
  },
  { _id: false },
);
```

Inside `groupSchema`, add these fields after the `tenantId` field (still inside the first object passed to `new Schema`):

```ts
    kind: {
      type: String,
      enum: ['group', 'team'],
      default: 'group',
      index: true,
    },
    ownerId: {
      type: Schema.Types.ObjectId,
      ref: 'User',
      index: true,
    },
    members: {
      type: [groupMemberSchema],
      default: undefined,
    },
    joinPolicy: {
      type: String,
      enum: ['invite'],
      default: 'invite',
    },
```

Add these indexes after the existing `groupSchema.index({ memberIds: 1 });` line:

```ts
groupSchema.index({ 'members.userId': 1 });
groupSchema.index({ ownerId: 1, kind: 1 });
```

- [ ] **Step 3: Write the failing schema test**

Create `src/methods/userGroup.team.spec.ts`:

```ts
import mongoose from 'mongoose';
import { MongoMemoryServer } from 'mongodb-memory-server';
import type * as t from '~/types';
import { createUserGroupMethods } from './userGroup';
import groupSchema from '~/schema/group';
import userSchema from '~/schema/user';

jest.mock('~/config/winston', () => ({
  error: jest.fn(),
  info: jest.fn(),
  debug: jest.fn(),
}));

let mongoServer: MongoMemoryServer;
let Group: mongoose.Model<t.IGroup>;
let User: mongoose.Model<t.IUser>;
let methods: ReturnType<typeof createUserGroupMethods>;

beforeAll(async () => {
  mongoServer = await MongoMemoryServer.create();
  await mongoose.connect(mongoServer.getUri());
  Group = mongoose.models.Group || mongoose.model<t.IGroup>('Group', groupSchema);
  User = mongoose.models.User || mongoose.model<t.IUser>('User', userSchema);
  methods = createUserGroupMethods(mongoose);
});

afterAll(async () => {
  await mongoose.disconnect();
  await mongoServer.stop();
});

beforeEach(async () => {
  await mongoose.connection.dropDatabase();
});

describe('Group team schema', () => {
  test('defaults kind to "group" and leaves members unset for a plain group', async () => {
    const group = await Group.create({ name: 'Plain', source: 'local' });
    expect(group.kind).toBe('group');
    expect(group.joinPolicy).toBe('invite');
    expect(group.members).toBeUndefined();
    expect(group.ownerId).toBeUndefined();
  });

  test('persists a team with members and defaults a member role to "member"', async () => {
    const ownerId = new mongoose.Types.ObjectId();
    const memberId = new mongoose.Types.ObjectId();
    const team = await Group.create({
      name: 'Team A',
      source: 'local',
      kind: 'team',
      ownerId,
      members: [
        { userId: ownerId, role: 'owner', joinedAt: new Date() },
        { userId: memberId },
      ],
    });
    const reloaded = await Group.findById(team._id).lean<t.IGroup>();
    expect(reloaded?.kind).toBe('team');
    expect(reloaded?.ownerId?.toString()).toBe(ownerId.toString());
    expect(reloaded?.members).toHaveLength(2);
    expect(reloaded?.members?.[1].role).toBe('member');
    expect(reloaded?.members?.[1].joinedAt).toBeInstanceOf(Date);
  });
});
```

- [ ] **Step 4: Run the test, expect FAIL**

Run: `cd packages/data-schemas && npx jest userGroup.team`
Expected: FAIL — TypeScript/assertion errors because `kind`, `members`, etc. are not yet on the schema/type (or the test was written before Steps 1–2 are applied; if Steps 1–2 are already applied, this confirms green — in that case run after writing the test only).

> Note: Steps 1–2 and Step 3 both edit toward the same green. Apply types/schema first, then the test should pass on first run. If you prefer strict red→green, comment out the schema fields, see the test fail, then restore.

- [ ] **Step 5: Run the test, expect PASS**

Run: `cd packages/data-schemas && npx jest userGroup.team`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
git add packages/data-schemas/src/types/group.ts packages/data-schemas/src/schema/group.ts packages/data-schemas/src/methods/userGroup.team.spec.ts
git commit   # message: "feat(data-schemas): extend Group schema with team kind/owner/members" + trailers
```

---

## Task 2: Team membership methods (create / add / remove / list)

**Files:**
- Modify: `src/methods/userGroup.ts`
- Test: `src/methods/userGroup.team.spec.ts` (append)

**Interfaces:**
- Consumes: `IGroup`, `IGroupMember`, `TeamRole` from Task 1; existing `findGroupById`.
- Produces (added to the `createUserGroupMethods` return object):
  - `createTeam({ name, description?, avatar?, ownerId, tenantId? }, session?) => Promise<IGroup>`
  - `addTeamMember({ groupId, userId, role? = 'member' }, session?) => Promise<IGroup | null>`
  - `removeTeamMember({ groupId, userId }, session?) => Promise<IGroup | null>`
  - `getUserTeams({ userId }, session?) => Promise<IGroup[]>`
  - private `resolveMemberIdValue(userId, session?) => Promise<string>`

- [ ] **Step 1: Write the failing tests** (append to `src/methods/userGroup.team.spec.ts`)

```ts
describe('team membership methods', () => {
  async function makeUser(idOnTheSource?: string) {
    return User.create({
      name: 'U' + Math.random(),
      email: `u${Math.random()}@test.com`,
      provider: 'local',
      ...(idOnTheSource ? { idOnTheSource } : {}),
    });
  }

  test('createTeam seeds owner member + ownerId + memberIds', async () => {
    const owner = await makeUser();
    const team = await methods.createTeam({ name: 'T', ownerId: owner._id });
    expect(team.kind).toBe('team');
    expect(team.ownerId?.toString()).toBe(owner._id.toString());
    expect(team.members).toHaveLength(1);
    expect(team.members?.[0].role).toBe('owner');
    expect(team.memberIds).toEqual([owner._id.toString()]);
  });

  test('addTeamMember updates members AND memberIds', async () => {
    const owner = await makeUser();
    const member = await makeUser();
    const team = await methods.createTeam({ name: 'T', ownerId: owner._id });
    const updated = await methods.addTeamMember({
      groupId: team._id,
      userId: member._id,
      role: 'admin',
    });
    expect(updated?.members).toHaveLength(2);
    const added = updated?.members?.find((m) => m.userId.toString() === member._id.toString());
    expect(added?.role).toBe('admin');
    expect(updated?.memberIds).toContain(member._id.toString());
  });

  test('addTeamMember uses idOnTheSource for memberIds when present', async () => {
    const owner = await makeUser();
    const entraUser = await makeUser('entra-123');
    const team = await methods.createTeam({ name: 'T', ownerId: owner._id });
    const updated = await methods.addTeamMember({ groupId: team._id, userId: entraUser._id });
    expect(updated?.memberIds).toContain('entra-123');
    expect(updated?.members?.some((m) => m.userId.toString() === entraUser._id.toString())).toBe(true);
  });

  test('addTeamMember is a no-op for an existing member (returns null)', async () => {
    const owner = await makeUser();
    const team = await methods.createTeam({ name: 'T', ownerId: owner._id });
    const result = await methods.addTeamMember({ groupId: team._id, userId: owner._id });
    expect(result).toBeNull();
  });

  test('addTeamMember rejects role "owner"', async () => {
    const owner = await makeUser();
    const member = await makeUser();
    const team = await methods.createTeam({ name: 'T', ownerId: owner._id });
    await expect(
      // @ts-expect-error - owner is not assignable, but guard must also hold at runtime
      methods.addTeamMember({ groupId: team._id, userId: member._id, role: 'owner' }),
    ).rejects.toThrow();
  });

  test('removeTeamMember pulls from members AND memberIds', async () => {
    const owner = await makeUser();
    const member = await makeUser();
    const team = await methods.createTeam({ name: 'T', ownerId: owner._id });
    await methods.addTeamMember({ groupId: team._id, userId: member._id });
    const updated = await methods.removeTeamMember({ groupId: team._id, userId: member._id });
    expect(updated?.members?.some((m) => m.userId.toString() === member._id.toString())).toBe(false);
    expect(updated?.memberIds).not.toContain(member._id.toString());
  });

  test('removeTeamMember refuses to remove the owner', async () => {
    const owner = await makeUser();
    const team = await methods.createTeam({ name: 'T', ownerId: owner._id });
    await expect(
      methods.removeTeamMember({ groupId: team._id, userId: owner._id }),
    ).rejects.toThrow(/owner/i);
  });

  test('getUserTeams returns only team-kind groups the user belongs to', async () => {
    const owner = await makeUser();
    const team = await methods.createTeam({ name: 'T', ownerId: owner._id });
    await Group.create({ name: 'plain', source: 'local', memberIds: [owner._id.toString()] });
    const teams = await methods.getUserTeams({ userId: owner._id });
    expect(teams).toHaveLength(1);
    expect(teams[0]._id.toString()).toBe(team._id.toString());
  });
});
```

- [ ] **Step 2: Run, expect FAIL**

Run: `cd packages/data-schemas && npx jest userGroup.team -t "team membership methods"`
Expected: FAIL — `methods.createTeam is not a function`.

- [ ] **Step 3: Implement the methods in `src/methods/userGroup.ts`**

Update the local-types import line to include `TeamRole`:

```ts
import type { TeamRole, IGroup, IRole, IUser } from '~/types';
```

Add these functions inside `createUserGroupMethods`, just before the final `return {` block:

```ts
  /**
   * Resolve the value stored in Group.memberIds for a user: the user's
   * idOnTheSource if present, else the userId string. Mirrors addUserToGroup
   * so ACL membership resolution stays consistent.
   */
  async function resolveMemberIdValue(
    userId: string | Types.ObjectId,
    session?: ClientSession,
  ): Promise<string> {
    const User = mongoose.models.User as Model<IUser>;
    const query = User.findById(userId, 'idOnTheSource');
    if (session) {
      query.session(session);
    }
    const user = await query.lean<{ idOnTheSource?: string }>();
    return user?.idOnTheSource || userId.toString();
  }

  /**
   * Create a self-service team. The creator becomes the sole owner and the
   * first member; memberIds is seeded so ACL checks work immediately.
   */
  async function createTeam(
    params: {
      name: string;
      description?: string;
      avatar?: string;
      ownerId: string | Types.ObjectId;
      tenantId?: string;
    },
    session?: ClientSession,
  ): Promise<IGroup> {
    const ownerObjectId =
      typeof params.ownerId === 'string' ? new Types.ObjectId(params.ownerId) : params.ownerId;
    const memberIdValue = await resolveMemberIdValue(ownerObjectId, session);
    const Group = mongoose.models.Group as Model<IGroup>;
    const doc: Partial<IGroup> = {
      name: params.name,
      description: params.description,
      avatar: params.avatar,
      source: 'local',
      kind: 'team',
      ownerId: ownerObjectId,
      members: [{ userId: ownerObjectId, role: 'owner', joinedAt: new Date() }],
      memberIds: [memberIdValue],
      joinPolicy: 'invite',
      tenantId: params.tenantId,
    };
    const options = session ? { session } : {};
    return await Group.create([doc], options).then((groups) => groups[0]);
  }

  /**
   * Add a member to a team, updating members and memberIds atomically.
   * Rejects 'owner' (ownership moves only via transferOwnership). No-op if the
   * user is already a member (returns null).
   */
  async function addTeamMember(
    params: {
      groupId: string | Types.ObjectId;
      userId: string | Types.ObjectId;
      role?: 'admin' | 'member';
    },
    session?: ClientSession,
  ): Promise<IGroup | null> {
    const role = params.role ?? 'member';
    if (role !== 'admin' && role !== 'member') {
      throw new Error(`Invalid team member role: ${role}`);
    }
    const userObjectId =
      typeof params.userId === 'string' ? new Types.ObjectId(params.userId) : params.userId;
    const memberIdValue = await resolveMemberIdValue(userObjectId, session);
    const Group = mongoose.models.Group as Model<IGroup>;
    const options = { new: true, ...(session ? { session } : {}) };
    return await Group.findOneAndUpdate(
      { _id: params.groupId, 'members.userId': { $ne: userObjectId } },
      {
        $push: { members: { userId: userObjectId, role, joinedAt: new Date() } },
        $addToSet: { memberIds: memberIdValue },
      },
      options,
    ).lean<IGroup>();
  }

  /**
   * Remove a member from a team, pulling from members and memberIds atomically.
   * Refuses to remove the current owner (transfer ownership first).
   */
  async function removeTeamMember(
    params: { groupId: string | Types.ObjectId; userId: string | Types.ObjectId },
    session?: ClientSession,
  ): Promise<IGroup | null> {
    const userObjectId =
      typeof params.userId === 'string' ? new Types.ObjectId(params.userId) : params.userId;
    const group = await findGroupById(params.groupId, {}, session);
    if (!group) {
      return null;
    }
    if (group.ownerId && group.ownerId.toString() === userObjectId.toString()) {
      throw new Error('Cannot remove the team owner; transfer ownership first');
    }
    const memberIdValue = await resolveMemberIdValue(userObjectId, session);
    const Group = mongoose.models.Group as Model<IGroup>;
    const options = { new: true, ...(session ? { session } : {}) };
    return await Group.findByIdAndUpdate(
      params.groupId,
      { $pull: { members: { userId: userObjectId }, memberIds: memberIdValue } },
      options,
    ).lean<IGroup>();
  }

  /** Get all team-kind groups a user is a member of. */
  async function getUserTeams(
    params: { userId: string | Types.ObjectId },
    session?: ClientSession,
  ): Promise<IGroup[]> {
    const userObjectId =
      typeof params.userId === 'string' ? new Types.ObjectId(params.userId) : params.userId;
    const Group = mongoose.models.Group as Model<IGroup>;
    const query = Group.find({ kind: 'team', 'members.userId': userObjectId });
    if (session) {
      query.session(session);
    }
    return await query.lean<IGroup[]>();
  }
```

Add the four public methods to the returned object (extend the existing `return { ... }`):

```ts
    createTeam,
    addTeamMember,
    removeTeamMember,
    getUserTeams,
```

- [ ] **Step 4: Run, expect PASS**

Run: `cd packages/data-schemas && npx jest userGroup.team`
Expected: PASS (all schema + membership tests).

- [ ] **Step 5: Commit**

```bash
git add packages/data-schemas/src/methods/userGroup.ts packages/data-schemas/src/methods/userGroup.team.spec.ts
git commit   # "feat(data-schemas): team create/add/remove membership with memberIds sync" + trailers
```

---

## Task 3: Team role & ownership methods

**Files:**
- Modify: `src/methods/userGroup.ts`
- Test: `src/methods/userGroup.team.spec.ts` (append)

**Interfaces:**
- Consumes: Task 2 methods + `findGroupById`, `TeamRole`.
- Produces (added to the factory return):
  - `getTeamRole({ groupId, userId }, session?) => Promise<TeamRole | null>`
  - `setMemberRole({ groupId, userId, role: 'admin'|'member' }, session?) => Promise<IGroup | null>`
  - `transferOwnership({ groupId, fromUserId, toUserId }, session?) => Promise<IGroup | null>`

- [ ] **Step 1: Write the failing tests** (append to `src/methods/userGroup.team.spec.ts`)

```ts
describe('team role & ownership methods', () => {
  async function makeUser() {
    return User.create({
      name: 'U' + Math.random(),
      email: `u${Math.random()}@test.com`,
      provider: 'local',
    });
  }

  test('getTeamRole returns the role or null', async () => {
    const owner = await makeUser();
    const member = await makeUser();
    const stranger = await makeUser();
    const team = await methods.createTeam({ name: 'T', ownerId: owner._id });
    await methods.addTeamMember({ groupId: team._id, userId: member._id, role: 'admin' });
    expect(await methods.getTeamRole({ groupId: team._id, userId: owner._id })).toBe('owner');
    expect(await methods.getTeamRole({ groupId: team._id, userId: member._id })).toBe('admin');
    expect(await methods.getTeamRole({ groupId: team._id, userId: stranger._id })).toBeNull();
  });

  test('setMemberRole flips admin<->member but refuses the owner', async () => {
    const owner = await makeUser();
    const member = await makeUser();
    const team = await methods.createTeam({ name: 'T', ownerId: owner._id });
    await methods.addTeamMember({ groupId: team._id, userId: member._id, role: 'member' });
    await methods.setMemberRole({ groupId: team._id, userId: member._id, role: 'admin' });
    expect(await methods.getTeamRole({ groupId: team._id, userId: member._id })).toBe('admin');
    await expect(
      methods.setMemberRole({ groupId: team._id, userId: owner._id, role: 'admin' }),
    ).rejects.toThrow(/owner/i);
  });

  test('transferOwnership swaps roles and ownerId atomically', async () => {
    const owner = await makeUser();
    const member = await makeUser();
    const team = await methods.createTeam({ name: 'T', ownerId: owner._id });
    await methods.addTeamMember({ groupId: team._id, userId: member._id, role: 'admin' });
    const updated = await methods.transferOwnership({
      groupId: team._id,
      fromUserId: owner._id,
      toUserId: member._id,
    });
    expect(updated?.ownerId?.toString()).toBe(member._id.toString());
    expect(await methods.getTeamRole({ groupId: team._id, userId: member._id })).toBe('owner');
    expect(await methods.getTeamRole({ groupId: team._id, userId: owner._id })).toBe('admin');
    const owners = updated?.members?.filter((m) => m.role === 'owner') ?? [];
    expect(owners).toHaveLength(1);
  });

  test('transferOwnership rejects a non-owner source or non-member target', async () => {
    const owner = await makeUser();
    const member = await makeUser();
    const stranger = await makeUser();
    const team = await methods.createTeam({ name: 'T', ownerId: owner._id });
    await methods.addTeamMember({ groupId: team._id, userId: member._id });
    await expect(
      methods.transferOwnership({ groupId: team._id, fromUserId: member._id, toUserId: owner._id }),
    ).rejects.toThrow(/owner/i);
    await expect(
      methods.transferOwnership({ groupId: team._id, fromUserId: owner._id, toUserId: stranger._id }),
    ).rejects.toThrow(/member/i);
  });

  test('memberIds stays consistent with members after a transfer', async () => {
    const owner = await makeUser();
    const member = await makeUser();
    const team = await methods.createTeam({ name: 'T', ownerId: owner._id });
    await methods.addTeamMember({ groupId: team._id, userId: member._id });
    await methods.transferOwnership({ groupId: team._id, fromUserId: owner._id, toUserId: member._id });
    const reloaded = await Group.findById(team._id).lean<t.IGroup>();
    const memberObjectIds = (reloaded?.members ?? []).map((m) => m.userId.toString()).sort();
    const memberIdSet = [...(reloaded?.memberIds ?? [])].sort();
    expect(memberIdSet).toEqual(memberObjectIds);
  });
});
```

- [ ] **Step 2: Run, expect FAIL**

Run: `cd packages/data-schemas && npx jest userGroup.team -t "team role & ownership"`
Expected: FAIL — `methods.getTeamRole is not a function`.

- [ ] **Step 3: Implement in `src/methods/userGroup.ts`**

Add inside `createUserGroupMethods` (after the Task 2 functions, before `return {`):

```ts
  /** Get a user's role within a team, or null if not a member. */
  async function getTeamRole(
    params: { groupId: string | Types.ObjectId; userId: string | Types.ObjectId },
    session?: ClientSession,
  ): Promise<TeamRole | null> {
    const userObjectId =
      typeof params.userId === 'string' ? new Types.ObjectId(params.userId) : params.userId;
    const group = await findGroupById(params.groupId, { members: 1 }, session);
    if (!group || !group.members) {
      return null;
    }
    const member = group.members.find((m) => m.userId.toString() === userObjectId.toString());
    return member ? member.role : null;
  }

  /**
   * Change a member's role between 'admin' and 'member'. Refuses to touch the
   * owner (use transferOwnership) and rejects 'owner' as a target role.
   */
  async function setMemberRole(
    params: {
      groupId: string | Types.ObjectId;
      userId: string | Types.ObjectId;
      role: 'admin' | 'member';
    },
    session?: ClientSession,
  ): Promise<IGroup | null> {
    if (params.role !== 'admin' && params.role !== 'member') {
      throw new Error(`Invalid role for setMemberRole: ${params.role}`);
    }
    const userObjectId =
      typeof params.userId === 'string' ? new Types.ObjectId(params.userId) : params.userId;
    const group = await findGroupById(params.groupId, {}, session);
    if (!group) {
      return null;
    }
    if (group.ownerId && group.ownerId.toString() === userObjectId.toString()) {
      throw new Error('Cannot change the owner role; use transferOwnership');
    }
    const Group = mongoose.models.Group as Model<IGroup>;
    const options = {
      new: true,
      arrayFilters: [{ 'elem.userId': userObjectId }],
      ...(session ? { session } : {}),
    };
    return await Group.findByIdAndUpdate(
      params.groupId,
      { $set: { 'members.$[elem].role': params.role } },
      options,
    ).lean<IGroup>();
  }

  /**
   * Transfer team ownership: the current owner is demoted to 'admin' and the
   * target is promoted to 'owner', with ownerId updated — one atomic update.
   */
  async function transferOwnership(
    params: {
      groupId: string | Types.ObjectId;
      fromUserId: string | Types.ObjectId;
      toUserId: string | Types.ObjectId;
    },
    session?: ClientSession,
  ): Promise<IGroup | null> {
    const fromObjectId =
      typeof params.fromUserId === 'string'
        ? new Types.ObjectId(params.fromUserId)
        : params.fromUserId;
    const toObjectId =
      typeof params.toUserId === 'string' ? new Types.ObjectId(params.toUserId) : params.toUserId;
    const group = await findGroupById(params.groupId, {}, session);
    if (!group) {
      return null;
    }
    if (!group.ownerId || group.ownerId.toString() !== fromObjectId.toString()) {
      throw new Error('fromUserId is not the current owner');
    }
    if (fromObjectId.toString() === toObjectId.toString()) {
      return group;
    }
    const isMember = (group.members ?? []).some(
      (m) => m.userId.toString() === toObjectId.toString(),
    );
    if (!isMember) {
      throw new Error('toUserId is not a member of the team');
    }
    const Group = mongoose.models.Group as Model<IGroup>;
    const options = {
      new: true,
      arrayFilters: [{ 'old.userId': fromObjectId }, { 'new.userId': toObjectId }],
      ...(session ? { session } : {}),
    };
    return await Group.findByIdAndUpdate(
      params.groupId,
      {
        $set: {
          ownerId: toObjectId,
          'members.$[old].role': 'admin',
          'members.$[new].role': 'owner',
        },
      },
      options,
    ).lean<IGroup>();
  }
```

Add to the returned object:

```ts
    getTeamRole,
    setMemberRole,
    transferOwnership,
```

- [ ] **Step 4: Run, expect PASS**

Run: `cd packages/data-schemas && npx jest userGroup.team`
Expected: PASS (all describe blocks).

- [ ] **Step 5: Commit**

```bash
git add packages/data-schemas/src/methods/userGroup.ts packages/data-schemas/src/methods/userGroup.team.spec.ts
git commit   # "feat(data-schemas): team role & ownership transfer methods" + trailers
```

---

## Task 4: TeamInvite schema, model & types

**Files:**
- Create: `src/types/teamInvite.ts`
- Create: `src/schema/teamInvite.ts`
- Create: `src/models/teamInvite.ts`
- Test: `src/methods/teamInvite.spec.ts` (create)

**Interfaces:**
- Produces: `TeamInviteStatus`, `TeamInviteRole = 'admin'|'member'`, `ITeamInvite` (with `groupId`, `email`, `invitedUserId?`, `role`, `token`, `status`, `invitedBy`, `expiresAt`, `tenantId?`); `createTeamInviteModel(mongoose) => Model<ITeamInvite>`; a `TeamInvite` collection with a unique `token` index and `email` stored lowercased.

- [ ] **Step 1: Create `src/types/teamInvite.ts`**

```ts
import type { Document, Types } from 'mongoose';

export type TeamInviteStatus = 'pending' | 'accepted' | 'declined' | 'expired' | 'revoked';
export type TeamInviteRole = 'admin' | 'member';

/** A pending/historical invitation for a user to join a team. */
export interface ITeamInvite extends Document {
  _id: Types.ObjectId;
  /** The team (Group with kind 'team') being joined. */
  groupId: Types.ObjectId;
  /** Invitee email, stored lowercased. */
  email: string;
  /** Resolved invitee user id, when the email maps to an existing account. */
  invitedUserId?: Types.ObjectId;
  role: TeamInviteRole;
  /** Single-use, high-entropy token (unique). */
  token: string;
  status: TeamInviteStatus;
  invitedBy: Types.ObjectId;
  expiresAt: Date;
  tenantId?: string;
  createdAt?: Date;
  updatedAt?: Date;
}
```

- [ ] **Step 2: Create `src/schema/teamInvite.ts`**

```ts
import { Schema } from 'mongoose';
import type { ITeamInvite } from '~/types';

const teamInviteSchema = new Schema<ITeamInvite>(
  {
    groupId: {
      type: Schema.Types.ObjectId,
      ref: 'Group',
      required: true,
    },
    email: {
      type: String,
      required: true,
      lowercase: true,
    },
    invitedUserId: {
      type: Schema.Types.ObjectId,
      ref: 'User',
    },
    role: {
      type: String,
      enum: ['admin', 'member'],
      default: 'member',
      required: true,
    },
    token: {
      type: String,
      required: true,
    },
    status: {
      type: String,
      enum: ['pending', 'accepted', 'declined', 'expired', 'revoked'],
      default: 'pending',
    },
    invitedBy: {
      type: Schema.Types.ObjectId,
      ref: 'User',
      required: true,
    },
    expiresAt: {
      type: Date,
      required: true,
    },
    tenantId: {
      type: String,
      index: true,
    },
  },
  { timestamps: true },
);

teamInviteSchema.index({ token: 1 }, { unique: true });
teamInviteSchema.index({ email: 1, status: 1 });
teamInviteSchema.index({ groupId: 1, status: 1 });
teamInviteSchema.index({ invitedUserId: 1, status: 1 });
teamInviteSchema.index({ status: 1, expiresAt: 1 });

export default teamInviteSchema;
```

- [ ] **Step 3: Create `src/models/teamInvite.ts`**

```ts
import type { Model } from 'mongoose';
import type { ITeamInvite } from '~/types';
import teamInviteSchema from '~/schema/teamInvite';

export function createTeamInviteModel(mongoose: typeof import('mongoose')) {
  return (
    (mongoose.models.TeamInvite as Model<ITeamInvite>) ||
    mongoose.model<ITeamInvite>('TeamInvite', teamInviteSchema)
  );
}
```

- [ ] **Step 4: Write the failing test** — create `src/methods/teamInvite.spec.ts`:

```ts
import mongoose from 'mongoose';
import { MongoMemoryServer } from 'mongodb-memory-server';
import type * as t from '~/types';
import { createTeamInviteModel } from '~/models/teamInvite';

jest.mock('~/config/winston', () => ({
  error: jest.fn(),
  info: jest.fn(),
  debug: jest.fn(),
}));

let mongoServer: MongoMemoryServer;
let TeamInvite: mongoose.Model<t.ITeamInvite>;

beforeAll(async () => {
  mongoServer = await MongoMemoryServer.create();
  await mongoose.connect(mongoServer.getUri());
  TeamInvite = createTeamInviteModel(mongoose);
});

afterAll(async () => {
  await mongoose.disconnect();
  await mongoServer.stop();
});

beforeEach(async () => {
  await mongoose.connection.dropDatabase();
});

describe('TeamInvite model', () => {
  test('lowercases email and defaults status to pending', async () => {
    const invite = await TeamInvite.create({
      groupId: new mongoose.Types.ObjectId(),
      email: 'Mixed.Case@Example.COM',
      role: 'member',
      token: 'tok-1',
      invitedBy: new mongoose.Types.ObjectId(),
      expiresAt: new Date(Date.now() + 1000),
    });
    expect(invite.email).toBe('mixed.case@example.com');
    expect(invite.status).toBe('pending');
  });

  test('enforces a unique token', async () => {
    const base = {
      groupId: new mongoose.Types.ObjectId(),
      email: 'a@test.com',
      role: 'member' as const,
      invitedBy: new mongoose.Types.ObjectId(),
      expiresAt: new Date(Date.now() + 1000),
    };
    await TeamInvite.create({ ...base, token: 'dup' });
    await TeamInvite.init();
    await expect(TeamInvite.create({ ...base, token: 'dup' })).rejects.toThrow();
  });
});
```

- [ ] **Step 5: Run, expect FAIL then PASS**

Run: `cd packages/data-schemas && npx jest teamInvite`
Expected: with Steps 1–3 applied, PASS (2 tests). If you wrote the test before creating the files, expect a module-resolution FAIL first, then PASS after Steps 1–3.

> The unique-token test calls `TeamInvite.init()` to ensure indexes are built before asserting the duplicate-key error.

- [ ] **Step 6: Commit**

```bash
git add packages/data-schemas/src/types/teamInvite.ts packages/data-schemas/src/schema/teamInvite.ts packages/data-schemas/src/models/teamInvite.ts packages/data-schemas/src/methods/teamInvite.spec.ts
git commit   # "feat(data-schemas): TeamInvite schema, model & types" + trailers
```

---

## Task 5: TeamInvite methods (invite lifecycle)

**Files:**
- Create: `src/methods/teamInvite.ts`
- Test: `src/methods/teamInvite.spec.ts` (append)

**Interfaces:**
- Consumes: `ITeamInvite`, `TeamInviteRole`, `TeamInviteStatus` from Task 4.
- Produces `createTeamInviteMethods(mongoose)` returning:
  - `createInvite({ groupId, email, role, invitedBy, invitedUserId?, tenantId?, ttlMs? }) => Promise<ITeamInvite>`
  - `findInviteByToken(token) => Promise<ITeamInvite | null>`
  - `listPendingInvitesForUser({ userId?, email? }) => Promise<ITeamInvite[]>`
  - `listInvitesForTeam({ groupId, status? }) => Promise<ITeamInvite[]>`
  - `acceptInvite({ token, userId }) => Promise<ITeamInvite | null>`
  - `declineInvite({ token }) => Promise<ITeamInvite | null>`
  - `revokeInvite({ inviteId }) => Promise<ITeamInvite | null>`
  - `expireStaleInvites() => Promise<number>`
  - `export type TeamInviteMethods = ReturnType<typeof createTeamInviteMethods>`

- [ ] **Step 1: Write the failing tests** (append to `src/methods/teamInvite.spec.ts`)

Add the factory import at the top of the file (below the existing imports):

```ts
import { createTeamInviteMethods } from './teamInvite';
```

Add a `methods` handle and the suite:

```ts
let inviteMethods: ReturnType<typeof createTeamInviteMethods>;

beforeAll(() => {
  inviteMethods = createTeamInviteMethods(mongoose);
});

describe('TeamInvite methods', () => {
  const groupId = () => new mongoose.Types.ObjectId();
  const userId = () => new mongoose.Types.ObjectId();

  test('createInvite lowercases email, sets pending + future expiry + token', async () => {
    const invite = await inviteMethods.createInvite({
      groupId: groupId(),
      email: 'INVITE@Test.com',
      role: 'member',
      invitedBy: userId(),
    });
    expect(invite.email).toBe('invite@test.com');
    expect(invite.status).toBe('pending');
    expect(invite.token).toHaveLength(64);
    expect(invite.expiresAt.getTime()).toBeGreaterThan(Date.now());
  });

  test('createInvite honors a custom ttlMs', async () => {
    const invite = await inviteMethods.createInvite({
      groupId: groupId(),
      email: 'x@test.com',
      role: 'member',
      invitedBy: userId(),
      ttlMs: 1000,
    });
    expect(invite.expiresAt.getTime()).toBeLessThan(Date.now() + 5000);
  });

  test('listPendingInvitesForUser matches by userId or email and excludes expired', async () => {
    const uid = userId();
    const gid = groupId();
    await inviteMethods.createInvite({ groupId: gid, email: 'by-email@test.com', role: 'member', invitedBy: userId() });
    await inviteMethods.createInvite({ groupId: gid, email: 'z@test.com', role: 'admin', invitedBy: userId(), invitedUserId: uid });
    const expired = await inviteMethods.createInvite({ groupId: gid, email: 'old@test.com', role: 'member', invitedBy: userId(), invitedUserId: uid, ttlMs: 1 });
    await new Promise((r) => setTimeout(r, 5));

    const byEmail = await inviteMethods.listPendingInvitesForUser({ email: 'BY-EMAIL@test.com' });
    expect(byEmail).toHaveLength(1);

    const byUser = await inviteMethods.listPendingInvitesForUser({ userId: uid });
    expect(byUser.map((i) => i.token)).not.toContain(expired.token);
    expect(byUser.length).toBeGreaterThanOrEqual(1);
  });

  test('listInvitesForTeam filters by groupId and optional status', async () => {
    const gid = groupId();
    await inviteMethods.createInvite({ groupId: gid, email: 'a@test.com', role: 'member', invitedBy: userId() });
    await inviteMethods.createInvite({ groupId: groupId(), email: 'b@test.com', role: 'member', invitedBy: userId() });
    const all = await inviteMethods.listInvitesForTeam({ groupId: gid });
    expect(all).toHaveLength(1);
    const pending = await inviteMethods.listInvitesForTeam({ groupId: gid, status: 'pending' });
    expect(pending).toHaveLength(1);
  });

  test('acceptInvite transitions pending->accepted once; double-accept returns null', async () => {
    const invite = await inviteMethods.createInvite({ groupId: groupId(), email: 'a@test.com', role: 'member', invitedBy: userId() });
    const uid = userId();
    const accepted = await inviteMethods.acceptInvite({ token: invite.token, userId: uid });
    expect(accepted?.status).toBe('accepted');
    expect(accepted?.invitedUserId?.toString()).toBe(uid.toString());
    const again = await inviteMethods.acceptInvite({ token: invite.token, userId: uid });
    expect(again).toBeNull();
  });

  test('acceptInvite rejects an expired invite (returns null)', async () => {
    const invite = await inviteMethods.createInvite({ groupId: groupId(), email: 'a@test.com', role: 'member', invitedBy: userId(), ttlMs: 1 });
    await new Promise((r) => setTimeout(r, 5));
    const result = await inviteMethods.acceptInvite({ token: invite.token, userId: userId() });
    expect(result).toBeNull();
  });

  test('declineInvite and revokeInvite transition only from pending', async () => {
    const a = await inviteMethods.createInvite({ groupId: groupId(), email: 'a@test.com', role: 'member', invitedBy: userId() });
    expect((await inviteMethods.declineInvite({ token: a.token }))?.status).toBe('declined');
    expect(await inviteMethods.declineInvite({ token: a.token })).toBeNull();

    const b = await inviteMethods.createInvite({ groupId: groupId(), email: 'b@test.com', role: 'member', invitedBy: userId() });
    expect((await inviteMethods.revokeInvite({ inviteId: b._id }))?.status).toBe('revoked');
  });

  test('expireStaleInvites flips only past-due pending invites and returns the count', async () => {
    await inviteMethods.createInvite({ groupId: groupId(), email: 'fresh@test.com', role: 'member', invitedBy: userId() });
    await inviteMethods.createInvite({ groupId: groupId(), email: 'stale@test.com', role: 'member', invitedBy: userId(), ttlMs: 1 });
    await new Promise((r) => setTimeout(r, 5));
    const count = await inviteMethods.expireStaleInvites();
    expect(count).toBe(1);
  });
});
```

- [ ] **Step 2: Run, expect FAIL**

Run: `cd packages/data-schemas && npx jest teamInvite -t "TeamInvite methods"`
Expected: FAIL — cannot find module `./teamInvite` (methods).

- [ ] **Step 3: Create `src/methods/teamInvite.ts`**

```ts
import crypto from 'node:crypto';
import type { FilterQuery, Model, Types } from 'mongoose';
import type { ITeamInvite, TeamInviteRole, TeamInviteStatus } from '~/types';

const DEFAULT_INVITE_TTL_MS = 7 * 24 * 60 * 60 * 1000;

export function createTeamInviteMethods(mongoose: typeof import('mongoose')) {
  function generateInviteToken(): string {
    return crypto.randomBytes(32).toString('hex');
  }

  async function createInvite(params: {
    groupId: string | Types.ObjectId;
    email: string;
    role: TeamInviteRole;
    invitedBy: string | Types.ObjectId;
    invitedUserId?: string | Types.ObjectId | null;
    tenantId?: string;
    ttlMs?: number;
  }): Promise<ITeamInvite> {
    const TeamInvite = mongoose.models.TeamInvite as Model<ITeamInvite>;
    const ttl = params.ttlMs ?? DEFAULT_INVITE_TTL_MS;
    return await TeamInvite.create({
      groupId: params.groupId,
      email: params.email.toLowerCase().trim(),
      role: params.role,
      invitedBy: params.invitedBy,
      invitedUserId: params.invitedUserId ?? undefined,
      tenantId: params.tenantId,
      token: generateInviteToken(),
      status: 'pending',
      expiresAt: new Date(Date.now() + ttl),
    });
  }

  async function findInviteByToken(token: string): Promise<ITeamInvite | null> {
    const TeamInvite = mongoose.models.TeamInvite as Model<ITeamInvite>;
    return await TeamInvite.findOne({ token }).lean<ITeamInvite>();
  }

  async function listPendingInvitesForUser(params: {
    userId?: string | Types.ObjectId;
    email?: string;
  }): Promise<ITeamInvite[]> {
    const TeamInvite = mongoose.models.TeamInvite as Model<ITeamInvite>;
    const or: FilterQuery<ITeamInvite>[] = [];
    if (params.userId) {
      or.push({ invitedUserId: params.userId });
    }
    if (params.email) {
      or.push({ email: params.email.toLowerCase().trim() });
    }
    if (or.length === 0) {
      return [];
    }
    return await TeamInvite.find({
      status: 'pending',
      expiresAt: { $gt: new Date() },
      $or: or,
    }).lean<ITeamInvite[]>();
  }

  async function listInvitesForTeam(params: {
    groupId: string | Types.ObjectId;
    status?: TeamInviteStatus;
  }): Promise<ITeamInvite[]> {
    const TeamInvite = mongoose.models.TeamInvite as Model<ITeamInvite>;
    const filter: FilterQuery<ITeamInvite> = { groupId: params.groupId };
    if (params.status) {
      filter.status = params.status;
    }
    return await TeamInvite.find(filter).lean<ITeamInvite[]>();
  }

  async function acceptInvite(params: {
    token: string;
    userId: string | Types.ObjectId;
  }): Promise<ITeamInvite | null> {
    const TeamInvite = mongoose.models.TeamInvite as Model<ITeamInvite>;
    return await TeamInvite.findOneAndUpdate(
      { token: params.token, status: 'pending', expiresAt: { $gt: new Date() } },
      { $set: { status: 'accepted', invitedUserId: params.userId } },
      { new: true },
    ).lean<ITeamInvite>();
  }

  async function declineInvite(params: { token: string }): Promise<ITeamInvite | null> {
    const TeamInvite = mongoose.models.TeamInvite as Model<ITeamInvite>;
    return await TeamInvite.findOneAndUpdate(
      { token: params.token, status: 'pending' },
      { $set: { status: 'declined' } },
      { new: true },
    ).lean<ITeamInvite>();
  }

  async function revokeInvite(params: {
    inviteId: string | Types.ObjectId;
  }): Promise<ITeamInvite | null> {
    const TeamInvite = mongoose.models.TeamInvite as Model<ITeamInvite>;
    return await TeamInvite.findOneAndUpdate(
      { _id: params.inviteId, status: 'pending' },
      { $set: { status: 'revoked' } },
      { new: true },
    ).lean<ITeamInvite>();
  }

  async function expireStaleInvites(): Promise<number> {
    const TeamInvite = mongoose.models.TeamInvite as Model<ITeamInvite>;
    const result = await TeamInvite.updateMany(
      { status: 'pending', expiresAt: { $lte: new Date() } },
      { $set: { status: 'expired' } },
    );
    return result.modifiedCount ?? 0;
  }

  return {
    createInvite,
    findInviteByToken,
    listPendingInvitesForUser,
    listInvitesForTeam,
    acceptInvite,
    declineInvite,
    revokeInvite,
    expireStaleInvites,
  };
}

export type TeamInviteMethods = ReturnType<typeof createTeamInviteMethods>;
```

- [ ] **Step 4: Run, expect PASS**

Run: `cd packages/data-schemas && npx jest teamInvite`
Expected: PASS (all model + method tests).

- [ ] **Step 5: Commit**

```bash
git add packages/data-schemas/src/methods/teamInvite.ts packages/data-schemas/src/methods/teamInvite.spec.ts
git commit   # "feat(data-schemas): TeamInvite lifecycle methods" + trailers
```

---

## Task 6: Wire barrels, bump version, build & verify

**Files:**
- Modify: `src/models/index.ts`
- Modify: `src/methods/index.ts`
- Modify: `src/schema/index.ts`
- Modify: `src/types/index.ts`
- Modify: `package.json`

**Interfaces:**
- Consumes: `createTeamInviteModel`, `createTeamInviteMethods`, `TeamInviteMethods`, `teamInviteSchema`, and the team types.
- Produces: `createModels()` returns a `TeamInvite` model; `createMethods()` includes all invite methods; `AllMethods` includes `TeamInviteMethods`; barrels re-export the schema/types; published version `0.0.52`.

- [ ] **Step 1: Register the model in `src/models/index.ts`**

Add the import next to the other model imports:

```ts
import { createTeamInviteModel } from './teamInvite';
```

Add to the object returned by `createModels` (next to `Group`):

```ts
    TeamInvite: createTeamInviteModel(mongoose),
```

- [ ] **Step 2: Wire methods in `src/methods/index.ts`**

Add the import near the other method imports (e.g. after the audit-log import):

```ts
/* Team invites */
import { createTeamInviteMethods, type TeamInviteMethods } from './teamInvite';
```

Add `TeamInviteMethods` to the `AllMethods` intersection (append with `&`):

```ts
  AuditLogMethods &
  TeamInviteMethods;
```

Add the spread to the object returned by `createMethods` (after the audit-log spread):

```ts
    /* Team invites */
    ...createTeamInviteMethods(mongoose),
```

Add `TeamInviteMethods` to the trailing `export type { ... }` list:

```ts
  AuditLogMethods,
  TeamInviteMethods,
};
```

- [ ] **Step 3: Re-export schema & types**

In `src/schema/index.ts`, add:

```ts
export { default as teamInviteSchema } from './teamInvite';
```

In `src/types/index.ts`, add (next to the group export):

```ts
export * from './teamInvite';
```

- [ ] **Step 4: Bump the package version**

In `packages/data-schemas/package.json`, change `"version": "0.0.51"` to `"version": "0.0.52"`.

- [ ] **Step 5: Lint & auto-fix the new/modified files**

There is no package-level lint script; ESLint lives at the repo root. Run from the repo root:

```bash
npx eslint --fix "packages/data-schemas/src/**/*.ts"
```

Expected: no remaining errors (import-order/style auto-fixed). Resolve any reported error manually — do not leave ESLint errors (CLAUDE.md). `--fix` only rewrites style, so it cannot break behavior.

- [ ] **Step 6: Run the full package test suite**

Run: `cd packages/data-schemas && npm run test:ci`
Expected: PASS — all suites green, including the existing `userGroup.*` specs (no regressions).

- [ ] **Step 7: Build the package**

Run: `cd packages/data-schemas && npm run build`
Expected: Rollup completes with no type errors (the TypeScript rollup plugin type-checks); `dist/` is regenerated (so `/api` consumes the new methods/types).

- [ ] **Step 8: Commit**

```bash
git add packages/data-schemas/src/models/index.ts packages/data-schemas/src/methods/index.ts packages/data-schemas/src/schema/index.ts packages/data-schemas/src/types/index.ts packages/data-schemas/package.json
git commit   # "feat(data-schemas): register TeamInvite + team methods; bump 0.0.52" + trailers
```

> Do **not** commit `dist/` unless the repo tracks built output for this package — check `git status` after the build; if `dist/` shows as modified and is tracked, include it in a separate `chore(data-schemas): rebuild dist` commit, otherwise leave it ignored.

---

## Self-Review

**Spec coverage** (against `team-workspaces-phase0-data-model.md`):

- §3.1 Group schema fields → Task 1. §3.2 Group types → Task 1. §3.3 TeamInvite schema/model/types → Task 4.
- §4.1 team membership methods (`createTeam`, `addTeamMember`, `removeTeamMember`, `setMemberRole`, `getTeamRole`, `transferOwnership`, `getUserTeams`) → Tasks 2–3.
- §4.2 invite methods (all eight) → Task 5.
- §5 wiring (4 barrels) → Task 6.
- §6 tests (membership/role/consistency + invite lifecycle) → Tasks 2,3,5.
- §7 acceptance (build, `npx jest userGroup.team teamInvite`, `test:ci`, consistency) → Tasks 5–6 + the consistency test in Task 3.
- §9 version bump → Task 6.

**Placeholder scan:** no TBD/TODO; every code step shows complete code. ✔

**Type consistency:** `IGroupMember`, `TeamRole`, `ITeamInvite`, `TeamInviteRole`, `TeamInviteStatus` are defined in Tasks 1/4 and used identically in later tasks. Method names match across Interfaces blocks and implementations (`addTeamMember`, `setMemberRole`, `transferOwnership`, `createInvite`, `acceptInvite`, `expireStaleInvites`). `memberIds` sync formula (`idOnTheSource || userId.toString()`) is identical in `resolveMemberIdValue` and the consistency test. ✔

**Note on out-of-scope:** no `/api`, route, email, FILE ACL, or UI work appears — correct for Phase 0.
