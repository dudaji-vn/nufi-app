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

describe('sub-group CRUD + membership methods', () => {
  async function makeUser(idOnTheSource?: string) {
    return User.create({
      name: 'U' + Math.random(),
      email: `u${Math.random()}@test.com`,
      provider: 'local',
      ...(idOnTheSource ? { idOnTheSource } : {}),
    });
  }

  async function setupTeamWithMembers() {
    const owner = await makeUser();
    const u1 = await makeUser();
    const u2 = await makeUser();
    const team = await methods.createTeam({ name: 'TestTeam', ownerId: owner._id });
    await methods.addTeamMember({ groupId: team._id, userId: u1._id });
    await methods.addTeamMember({ groupId: team._id, userId: u2._id });
    return {
      team,
      ownerId: owner._id.toString(),
      u1: u1._id.toString(),
      u2: u2._id.toString(),
    };
  }

  test('createSubgroup stores kind/parentTeamId and inherits tenantId', async () => {
    const { team, ownerId } = await setupTeamWithMembers();
    const sg = await methods.createSubgroup({
      parentTeamId: team._id,
      name: 'Eng',
      ownerId,
      tenantId: 'tenant-abc',
    });
    expect(sg.kind).toBe('team_subgroup');
    expect(sg.parentTeamId?.toString()).toBe(team._id.toString());
    expect(sg.name).toBe('Eng');
    expect(sg.tenantId).toBe('tenant-abc');
  });

  test('addSubgroupMember adds a team member (dual-writes memberIds + members)', async () => {
    const { team, ownerId, u1 } = await setupTeamWithMembers();
    const sg = await methods.createSubgroup({ parentTeamId: team._id, name: 'Eng', ownerId });
    const updated = await methods.addSubgroupMember({ subgroupId: sg._id, userId: u1 });
    expect(updated.memberIds).toContain(u1);
    expect(updated.members?.find((m) => m.userId.toString() === u1)).toBeTruthy();
    expect(updated.members?.find((m) => m.userId.toString() === u1)?.role).toBe('member');
  });

  test('addSubgroupMember REJECTS a non-team-member', async () => {
    const { team, ownerId } = await setupTeamWithMembers();
    const sg = await methods.createSubgroup({ parentTeamId: team._id, name: 'Eng', ownerId });
    await expect(
      methods.addSubgroupMember({ subgroupId: sg._id, userId: 'stranger' }),
    ).rejects.toThrow(/not a member of the team/i);
  });

  test('addSubgroupMember is a no-op if user already in subgroup', async () => {
    const { team, ownerId, u1 } = await setupTeamWithMembers();
    const sg = await methods.createSubgroup({ parentTeamId: team._id, name: 'Eng', ownerId });
    const first = await methods.addSubgroupMember({ subgroupId: sg._id, userId: u1 });
    const second = await methods.addSubgroupMember({ subgroupId: sg._id, userId: u1 });
    // memberIds should not have duplicates
    expect(second.memberIds?.filter((id) => id === u1)).toHaveLength(1);
  });

  test('getUserSubgroups returns only the subgroups the user belongs to', async () => {
    const { team, ownerId, u1 } = await setupTeamWithMembers();
    const a = await methods.createSubgroup({ parentTeamId: team._id, name: 'A', ownerId });
    const b = await methods.createSubgroup({ parentTeamId: team._id, name: 'B', ownerId });
    await methods.addSubgroupMember({ subgroupId: a._id, userId: u1 });
    const got = await methods.getUserSubgroups({ userId: u1, parentTeamId: team._id });
    expect(got.map((g) => g._id.toString())).toEqual([a._id.toString()]);
    // b is excluded because u1 is not in it
    expect(got.map((g) => g._id.toString())).not.toContain(b._id.toString());
  });

  test('getUserSubgroups excludes subgroups of a different team', async () => {
    const { team: team1, ownerId: ownerId1, u1 } = await setupTeamWithMembers();
    const owner2 = await makeUser();
    const team2 = await methods.createTeam({ name: 'Team2', ownerId: owner2._id });
    await methods.addTeamMember({ groupId: team2._id, userId: u1 });

    const sg1 = await methods.createSubgroup({ parentTeamId: team1._id, name: 'SG1', ownerId: ownerId1 });
    const sg2 = await methods.createSubgroup({
      parentTeamId: team2._id,
      name: 'SG2',
      ownerId: owner2._id.toString(),
    });
    await methods.addSubgroupMember({ subgroupId: sg1._id, userId: u1 });
    await methods.addSubgroupMember({ subgroupId: sg2._id, userId: u1 });

    const got = await methods.getUserSubgroups({ userId: u1, parentTeamId: team1._id });
    expect(got).toHaveLength(1);
    expect(got[0]._id.toString()).toBe(sg1._id.toString());
  });

  test('removeSubgroupMember pulls from memberIds and members', async () => {
    const { team, ownerId, u1 } = await setupTeamWithMembers();
    const sg = await methods.createSubgroup({ parentTeamId: team._id, name: 'Eng', ownerId });
    await methods.addSubgroupMember({ subgroupId: sg._id, userId: u1 });
    const updated = await methods.removeSubgroupMember({ subgroupId: sg._id, userId: u1 });
    expect(updated.memberIds).not.toContain(u1);
    expect(updated.members?.find((m) => m.userId.toString() === u1)).toBeFalsy();
  });

  test('getTeamSubgroups lists all subgroups of a team', async () => {
    const { team, ownerId } = await setupTeamWithMembers();
    const owner2 = await makeUser();
    const otherTeam = await methods.createTeam({ name: 'OtherTeam', ownerId: owner2._id });

    const sg1 = await methods.createSubgroup({ parentTeamId: team._id, name: 'A', ownerId });
    const sg2 = await methods.createSubgroup({ parentTeamId: team._id, name: 'B', ownerId });
    // subgroup of a different team — must not appear
    await methods.createSubgroup({
      parentTeamId: otherTeam._id,
      name: 'Other',
      ownerId: owner2._id.toString(),
    });

    const sgs = await methods.getTeamSubgroups(team._id);
    expect(sgs).toHaveLength(2);
    const ids = sgs.map((sg) => sg._id.toString());
    expect(ids).toContain(sg1._id.toString());
    expect(ids).toContain(sg2._id.toString());
  });

  test('getSubgroupById returns the subgroup or null', async () => {
    const { team, ownerId } = await setupTeamWithMembers();
    const sg = await methods.createSubgroup({ parentTeamId: team._id, name: 'Eng', ownerId });
    const found = await methods.getSubgroupById(sg._id);
    expect(found).not.toBeNull();
    expect(found?._id.toString()).toBe(sg._id.toString());

    const missing = await methods.getSubgroupById(new mongoose.Types.ObjectId());
    expect(missing).toBeNull();
  });

  test('updateSubgroup patches name and description', async () => {
    const { team, ownerId } = await setupTeamWithMembers();
    const sg = await methods.createSubgroup({ parentTeamId: team._id, name: 'Old', ownerId });
    const updated = await methods.updateSubgroup(sg._id, {
      name: 'New',
      description: 'Updated desc',
    });
    expect(updated?.name).toBe('New');
    expect(updated?.description).toBe('Updated desc');
  });

  test('deleteSubgroup removes the document', async () => {
    const { team, ownerId } = await setupTeamWithMembers();
    const sg = await methods.createSubgroup({ parentTeamId: team._id, name: 'Doomed', ownerId });
    await methods.deleteSubgroup(sg._id);
    const after = await Group.findById(sg._id).lean();
    expect(after).toBeNull();
  });
});
