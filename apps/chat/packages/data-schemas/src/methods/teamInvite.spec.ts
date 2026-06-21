import mongoose from 'mongoose';
import { MongoMemoryServer } from 'mongodb-memory-server';
import type * as t from '~/types';
import { createTeamInviteModel } from '~/models/teamInvite';
import { createTeamInviteMethods } from './teamInvite';

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

let inviteMethods: ReturnType<typeof createTeamInviteMethods>;

beforeAll(() => {
  inviteMethods = createTeamInviteMethods(mongoose);
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
    await inviteMethods.createInvite({
      groupId: gid,
      email: 'by-email@test.com',
      role: 'member',
      invitedBy: userId(),
    });
    await inviteMethods.createInvite({
      groupId: gid,
      email: 'z@test.com',
      role: 'admin',
      invitedBy: userId(),
      invitedUserId: uid,
    });
    const expired = await inviteMethods.createInvite({
      groupId: gid,
      email: 'old@test.com',
      role: 'member',
      invitedBy: userId(),
      invitedUserId: uid,
      ttlMs: 1,
    });
    await new Promise((r) => setTimeout(r, 5));

    const byEmail = await inviteMethods.listPendingInvitesForUser({ email: 'BY-EMAIL@test.com' });
    expect(byEmail).toHaveLength(1);

    const byUser = await inviteMethods.listPendingInvitesForUser({ userId: uid });
    expect(byUser.map((i) => i.token)).not.toContain(expired.token);
    expect(byUser.length).toBeGreaterThanOrEqual(1);
  });

  test('listInvitesForTeam filters by groupId and optional status', async () => {
    const gid = groupId();
    await inviteMethods.createInvite({
      groupId: gid,
      email: 'a@test.com',
      role: 'member',
      invitedBy: userId(),
    });
    await inviteMethods.createInvite({
      groupId: groupId(),
      email: 'b@test.com',
      role: 'member',
      invitedBy: userId(),
    });
    const all = await inviteMethods.listInvitesForTeam({ groupId: gid });
    expect(all).toHaveLength(1);
    const pending = await inviteMethods.listInvitesForTeam({ groupId: gid, status: 'pending' });
    expect(pending).toHaveLength(1);
  });

  test('acceptInvite transitions pending->accepted once; double-accept returns null', async () => {
    const invite = await inviteMethods.createInvite({
      groupId: groupId(),
      email: 'a@test.com',
      role: 'member',
      invitedBy: userId(),
    });
    const uid = userId();
    const accepted = await inviteMethods.acceptInvite({ token: invite.token, userId: uid });
    expect(accepted?.status).toBe('accepted');
    expect(accepted?.invitedUserId?.toString()).toBe(uid.toString());
    const again = await inviteMethods.acceptInvite({ token: invite.token, userId: uid });
    expect(again).toBeNull();
  });

  test('acceptInvite rejects an expired invite (returns null)', async () => {
    const invite = await inviteMethods.createInvite({
      groupId: groupId(),
      email: 'a@test.com',
      role: 'member',
      invitedBy: userId(),
      ttlMs: 1,
    });
    await new Promise((r) => setTimeout(r, 5));
    const result = await inviteMethods.acceptInvite({ token: invite.token, userId: userId() });
    expect(result).toBeNull();
  });

  test('declineInvite and revokeInvite transition only from pending', async () => {
    const a = await inviteMethods.createInvite({
      groupId: groupId(),
      email: 'a@test.com',
      role: 'member',
      invitedBy: userId(),
    });
    expect((await inviteMethods.declineInvite({ token: a.token }))?.status).toBe('declined');
    expect(await inviteMethods.declineInvite({ token: a.token })).toBeNull();

    const b = await inviteMethods.createInvite({
      groupId: groupId(),
      email: 'b@test.com',
      role: 'member',
      invitedBy: userId(),
    });
    expect((await inviteMethods.revokeInvite({ inviteId: b._id }))?.status).toBe('revoked');
  });

  test('deleteInvitesByGroup hard-deletes all invites for a group and returns count', async () => {
    const gidA = groupId();
    const gidB = groupId();

    await inviteMethods.createInvite({
      groupId: gidA,
      email: 'a1@test.com',
      role: 'member',
      invitedBy: userId(),
    });
    await inviteMethods.createInvite({
      groupId: gidA,
      email: 'a2@test.com',
      role: 'admin',
      invitedBy: userId(),
    });
    await inviteMethods.createInvite({
      groupId: gidB,
      email: 'b1@test.com',
      role: 'member',
      invitedBy: userId(),
    });

    const deleted = await inviteMethods.deleteInvitesByGroup({ groupId: gidA });
    expect(deleted).toBe(2);

    const remaining = await inviteMethods.listInvitesForTeam({ groupId: gidA });
    expect(remaining).toHaveLength(0);

    const bRemaining = await inviteMethods.listInvitesForTeam({ groupId: gidB });
    expect(bRemaining).toHaveLength(1);
  });

  test('expireStaleInvites flips only past-due pending invites and returns the count', async () => {
    await inviteMethods.createInvite({
      groupId: groupId(),
      email: 'fresh@test.com',
      role: 'member',
      invitedBy: userId(),
    });
    await inviteMethods.createInvite({
      groupId: groupId(),
      email: 'stale@test.com',
      role: 'member',
      invitedBy: userId(),
      ttlMs: 1,
    });
    await new Promise((r) => setTimeout(r, 5));
    const count = await inviteMethods.expireStaleInvites();
    expect(count).toBe(1);
  });
});
