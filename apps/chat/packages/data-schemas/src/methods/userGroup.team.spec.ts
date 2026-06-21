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
