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
    expect(updated?.members?.some((m) => m.userId.toString() === entraUser._id.toString())).toBe(
      true,
    );
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
    expect(updated?.members?.some((m) => m.userId.toString() === member._id.toString())).toBe(
      false,
    );
    expect(updated?.memberIds).not.toContain(member._id.toString());
  });

  test('removeTeamMember refuses to remove the owner', async () => {
    const owner = await makeUser();
    const team = await methods.createTeam({ name: 'T', ownerId: owner._id });
    await expect(
      methods.removeTeamMember({ groupId: team._id, userId: owner._id }),
    ).rejects.toThrow(/owner/i);
  });

  test('removeTeamMember pulls idOnTheSource value from memberIds', async () => {
    const owner = await makeUser();
    const entraUser = await makeUser('entra-rm-1');
    const team = await methods.createTeam({ name: 'T', ownerId: owner._id });
    await methods.addTeamMember({ groupId: team._id, userId: entraUser._id });
    const updated = await methods.removeTeamMember({ groupId: team._id, userId: entraUser._id });
    expect(updated?.members?.some((m) => m.userId.toString() === entraUser._id.toString())).toBe(
      false,
    );
    expect(updated?.memberIds).not.toContain('entra-rm-1');
  });

  test('removeTeamMember on a non-existent group returns null', async () => {
    expect(
      await methods.removeTeamMember({
        groupId: new mongoose.Types.ObjectId(),
        userId: (await makeUser())._id,
      }),
    ).toBeNull();
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
      members: [{ userId: ownerId, role: 'owner', joinedAt: new Date() }, { userId: memberId }],
    });
    const reloaded = await Group.findById(team._id).lean<t.IGroup>();
    expect(reloaded?.kind).toBe('team');
    expect(reloaded?.ownerId?.toString()).toBe(ownerId.toString());
    expect(reloaded?.members).toHaveLength(2);
    expect(reloaded?.members?.[1].role).toBe('member');
    expect(reloaded?.members?.[1].joinedAt).toBeInstanceOf(Date);
  });
});
