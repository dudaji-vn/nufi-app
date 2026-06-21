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
