import { Types } from 'mongoose';
import type { IGroup, ITeamInvite, IUser } from '@librechat/data-schemas';
import type { Response } from 'express';
import type { ServerRequest } from '~/types/http';
import type { TeamInviteHandlersDeps } from './invites';
import { createTeamInviteHandlers } from './invites';

jest.mock('@librechat/data-schemas', () => ({
  ...jest.requireActual('@librechat/data-schemas'),
  logger: { error: jest.fn(), warn: jest.fn(), info: jest.fn(), debug: jest.fn() },
}));

describe('createTeamInviteHandlers', () => {
  let validId: string;
  let validUserId: string;
  let validCallerId: string;
  let validInviteId: string;
  let validToken: string;

  beforeEach(() => {
    validId = new Types.ObjectId().toString();
    validUserId = new Types.ObjectId().toString();
    validCallerId = new Types.ObjectId().toString();
    validInviteId = new Types.ObjectId().toString();
    validToken = 'abc123def456abc123def456abc123def456abc123def456abc123def456abc123';
  });

  function mockTeam(overrides: Partial<IGroup> = {}): IGroup {
    return {
      _id: new Types.ObjectId(validId),
      name: 'Test Team',
      source: 'local',
      kind: 'team',
      memberIds: [validCallerId],
      members: [{ userId: new Types.ObjectId(validCallerId), role: 'admin', joinedAt: new Date() }],
      ownerId: new Types.ObjectId(validCallerId),
      createdAt: new Date(),
      updatedAt: new Date(),
      ...overrides,
    } as IGroup;
  }

  function mockInvite(overrides: Partial<ITeamInvite> = {}): ITeamInvite {
    return {
      _id: new Types.ObjectId(validInviteId),
      groupId: new Types.ObjectId(validId),
      email: 'invitee@example.com',
      role: 'member',
      token: validToken,
      status: 'pending',
      invitedBy: new Types.ObjectId(validCallerId),
      expiresAt: new Date(Date.now() + 86400000),
      createdAt: new Date(),
      updatedAt: new Date(),
      ...overrides,
    } as ITeamInvite;
  }

  function mockUser(overrides: Partial<IUser> = {}): IUser {
    return {
      _id: new Types.ObjectId(validUserId),
      name: 'Test User',
      email: 'test@example.com',
      ...overrides,
    } as IUser;
  }

  function createReqRes(
    overrides: {
      params?: Record<string, string>;
      query?: Record<string, string>;
      body?: Record<string, unknown>;
      userId?: string;
      email?: string;
    } = {},
  ) {
    const callerId = overrides.userId ?? validCallerId;
    const req = {
      params: overrides.params ?? {},
      query: overrides.query ?? {},
      body: overrides.body ?? {},
      user: { id: callerId, email: overrides.email ?? 'caller@example.com', tenantId: 'tenant-1' },
    } as unknown as ServerRequest;

    const json = jest.fn();
    const status = jest.fn().mockReturnValue({ json });
    const res = { status, json } as unknown as Response;

    return { req, res, status, json };
  }

  function createDeps(overrides: Partial<TeamInviteHandlersDeps> = {}): TeamInviteHandlersDeps {
    return {
      createInvite: jest.fn().mockResolvedValue(mockInvite()),
      findInviteByToken: jest.fn().mockResolvedValue(null),
      listPendingInvitesForUser: jest.fn().mockResolvedValue([]),
      listInvitesForTeam: jest.fn().mockResolvedValue([]),
      acceptInvite: jest.fn().mockResolvedValue(mockInvite({ status: 'accepted' })),
      declineInvite: jest.fn().mockResolvedValue(mockInvite({ status: 'declined' })),
      revokeInvite: jest.fn().mockResolvedValue(mockInvite({ status: 'revoked' })),
      addTeamMember: jest.fn().mockResolvedValue(mockTeam()),
      getTeamRole: jest.fn().mockResolvedValue(null),
      findUser: jest.fn().mockResolvedValue(null),
      findGroupById: jest.fn().mockResolvedValue(null),
      sendInviteEmail: undefined,
      ...overrides,
    };
  }

  // ── listMine ─────────────────────────────────────────────────────────────────
  describe('listMine', () => {
    it('returns pending invites enriched with team name and includes token', async () => {
      const invite = mockInvite();
      const team = mockTeam({ name: 'Fancy Team' });
      const deps = createDeps({
        listPendingInvitesForUser: jest.fn().mockResolvedValue([invite]),
        findGroupById: jest.fn().mockResolvedValue(team),
      });
      const handlers = createTeamInviteHandlers(deps);
      const { req, res, status, json } = createReqRes({
        userId: validCallerId,
        email: 'caller@example.com',
      });

      await handlers.listMine(req, res);

      expect(deps.listPendingInvitesForUser).toHaveBeenCalledWith({
        userId: validCallerId,
        email: 'caller@example.com',
      });
      expect(status).toHaveBeenCalledWith(200);
      const { invites } = json.mock.calls[0][0];
      expect(invites).toHaveLength(1);
      expect(invites[0].teamName).toBe('Fancy Team');
      expect(invites[0].token).toBeDefined();
    });

    it('uses groupId as fallback when team not found', async () => {
      const invite = mockInvite();
      const deps = createDeps({
        listPendingInvitesForUser: jest.fn().mockResolvedValue([invite]),
        findGroupById: jest.fn().mockResolvedValue(null),
      });
      const handlers = createTeamInviteHandlers(deps);
      const { req, res, status, json } = createReqRes();

      await handlers.listMine(req, res);

      expect(status).toHaveBeenCalledWith(200);
      const { invites } = json.mock.calls[0][0];
      expect(invites[0].teamName).toBeUndefined();
    });

    it('returns 500 on error', async () => {
      const deps = createDeps({
        listPendingInvitesForUser: jest.fn().mockRejectedValue(new Error('db down')),
      });
      const handlers = createTeamInviteHandlers(deps);
      const { req, res, status, json } = createReqRes();

      await handlers.listMine(req, res);

      expect(status).toHaveBeenCalledWith(500);
      expect(json).toHaveBeenCalledWith({ error: 'Failed to list invites' });
    });
  });

  // ── accept ────────────────────────────────────────────────────────────────────
  describe('accept', () => {
    it('happy path: acceptInvite claimed before addTeamMember, returns 200 {team}', async () => {
      const invite = mockInvite({ invitedUserId: new Types.ObjectId(validCallerId) });
      const team = mockTeam();
      const deps = createDeps({
        findInviteByToken: jest.fn().mockResolvedValue(invite),
        addTeamMember: jest.fn().mockResolvedValue(team),
        acceptInvite: jest.fn().mockResolvedValue(invite),
        findGroupById: jest.fn().mockResolvedValue(team),
      });
      const handlers = createTeamInviteHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { token: validToken },
        userId: validCallerId,
      });

      const addTeamMemberOrder: string[] = [];
      (deps.addTeamMember as jest.Mock).mockImplementation(async () => {
        addTeamMemberOrder.push('addTeamMember');
        return team;
      });
      (deps.acceptInvite as jest.Mock).mockImplementation(async () => {
        addTeamMemberOrder.push('acceptInvite');
        return invite;
      });

      await handlers.accept(req, res);

      expect(status).toHaveBeenCalledWith(200);
      expect(json.mock.calls[0][0]).toHaveProperty('team');
      expect(addTeamMemberOrder).toEqual(['acceptInvite', 'addTeamMember']);
    });

    it('returns 404 when invite not found', async () => {
      const deps = createDeps({ findInviteByToken: jest.fn().mockResolvedValue(null) });
      const handlers = createTeamInviteHandlers(deps);
      const { req, res, status, json } = createReqRes({ params: { token: validToken } });

      await handlers.accept(req, res);

      expect(status).toHaveBeenCalledWith(404);
      expect(json).toHaveBeenCalledWith({ error: 'Invite not found' });
    });

    it('returns 410 when invite status is not pending', async () => {
      const invite = mockInvite({
        status: 'accepted',
        invitedUserId: new Types.ObjectId(validCallerId),
      });
      const deps = createDeps({ findInviteByToken: jest.fn().mockResolvedValue(invite) });
      const handlers = createTeamInviteHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { token: validToken },
        userId: validCallerId,
      });

      await handlers.accept(req, res);

      expect(status).toHaveBeenCalledWith(410);
      expect(json).toHaveBeenCalledWith({ error: 'Invite is no longer valid' });
    });

    it('returns 410 when invite is expired', async () => {
      const invite = mockInvite({
        status: 'pending',
        expiresAt: new Date(Date.now() - 1000),
        invitedUserId: new Types.ObjectId(validCallerId),
      });
      const deps = createDeps({ findInviteByToken: jest.fn().mockResolvedValue(invite) });
      const handlers = createTeamInviteHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { token: validToken },
        userId: validCallerId,
      });

      await handlers.accept(req, res);

      expect(status).toHaveBeenCalledWith(410);
      expect(json).toHaveBeenCalledWith({ error: 'Invite is no longer valid' });
    });

    it('returns 403 when caller email and invitedUserId do not match', async () => {
      const invite = mockInvite({
        email: 'someone-else@example.com',
        invitedUserId: new Types.ObjectId(),
      });
      const deps = createDeps({ findInviteByToken: jest.fn().mockResolvedValue(invite) });
      const handlers = createTeamInviteHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { token: validToken },
        userId: validCallerId,
        email: 'caller@example.com',
      });

      await handlers.accept(req, res);

      expect(status).toHaveBeenCalledWith(403);
      expect(json).toHaveBeenCalledWith({ error: 'Forbidden' });
    });

    it('allows accept when invite email matches caller email', async () => {
      const callerEmail = 'caller@example.com';
      const invite = mockInvite({ email: callerEmail });
      const team = mockTeam();
      const deps = createDeps({
        findInviteByToken: jest.fn().mockResolvedValue(invite),
        addTeamMember: jest.fn().mockResolvedValue(team),
        acceptInvite: jest.fn().mockResolvedValue(invite),
        findGroupById: jest.fn().mockResolvedValue(team),
      });
      const handlers = createTeamInviteHandlers(deps);
      const { req, res, status } = createReqRes({
        params: { token: validToken },
        userId: validCallerId,
        email: callerEmail,
      });

      await handlers.accept(req, res);

      expect(status).toHaveBeenCalledWith(200);
    });

    it('calls addTeamMember with correct params', async () => {
      const invite = mockInvite({ email: 'caller@example.com', role: 'admin' });
      const team = mockTeam();
      const deps = createDeps({
        findInviteByToken: jest.fn().mockResolvedValue(invite),
        addTeamMember: jest.fn().mockResolvedValue(team),
        acceptInvite: jest.fn().mockResolvedValue(invite),
        findGroupById: jest.fn().mockResolvedValue(team),
      });
      const handlers = createTeamInviteHandlers(deps);
      const { req, res } = createReqRes({
        params: { token: validToken },
        userId: validCallerId,
        email: 'caller@example.com',
      });

      await handlers.accept(req, res);

      expect(deps.addTeamMember).toHaveBeenCalledWith({
        groupId: invite.groupId.toString(),
        userId: validCallerId,
        role: 'admin',
      });
      expect(deps.acceptInvite).toHaveBeenCalledWith({
        token: validToken,
        userId: validCallerId,
      });
    });

    it('returns 500 on unexpected error', async () => {
      const invite = mockInvite({ email: 'caller@example.com' });
      const deps = createDeps({
        findInviteByToken: jest.fn().mockResolvedValue(invite),
        addTeamMember: jest.fn().mockRejectedValue(new Error('db down')),
      });
      const handlers = createTeamInviteHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { token: validToken },
        email: 'caller@example.com',
      });

      await handlers.accept(req, res);

      expect(status).toHaveBeenCalledWith(500);
      expect(json).toHaveBeenCalledWith({ error: 'Failed to accept invite' });
    });

    it('returns 403 when maxMembersPerTeam is configured and team is at capacity', async () => {
      const callerEmail = 'caller@example.com';
      const invite = mockInvite({ email: callerEmail });
      const fullTeam = mockTeam({
        members: [
          { userId: new Types.ObjectId(validCallerId), role: 'admin', joinedAt: new Date() },
          { userId: new Types.ObjectId(validUserId), role: 'member', joinedAt: new Date() },
        ],
      });
      const deps = createDeps({
        findInviteByToken: jest.fn().mockResolvedValue(invite),
        findGroupById: jest.fn().mockResolvedValue(fullTeam),
      });
      const handlers = createTeamInviteHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { token: validToken },
        userId: validCallerId,
        email: callerEmail,
      });
      (req as unknown as Record<string, unknown>).config = {
        config: { teams: { maxMembersPerTeam: 2 } },
      };

      await handlers.accept(req, res);

      expect(status).toHaveBeenCalledWith(403);
      expect(json).toHaveBeenCalledWith({ error: 'Team is full' });
      expect(deps.addTeamMember).not.toHaveBeenCalled();
    });

    it('proceeds when maxMembersPerTeam is configured and team has capacity', async () => {
      const callerEmail = 'caller@example.com';
      const invite = mockInvite({ email: callerEmail });
      const team = mockTeam({
        members: [
          { userId: new Types.ObjectId(validCallerId), role: 'admin', joinedAt: new Date() },
        ],
      });
      const deps = createDeps({
        findInviteByToken: jest.fn().mockResolvedValue(invite),
        findGroupById: jest.fn().mockResolvedValue(team),
        addTeamMember: jest.fn().mockResolvedValue(team),
        acceptInvite: jest.fn().mockResolvedValue(invite),
      });
      const handlers = createTeamInviteHandlers(deps);
      const { req, res, status } = createReqRes({
        params: { token: validToken },
        userId: validCallerId,
        email: callerEmail,
      });
      (req as unknown as Record<string, unknown>).config = {
        config: { teams: { maxMembersPerTeam: 5 } },
      };

      await handlers.accept(req, res);

      expect(status).toHaveBeenCalledWith(200);
      expect(deps.addTeamMember).toHaveBeenCalled();
    });

    it('proceeds when maxMembersPerTeam is not configured (unlimited)', async () => {
      const callerEmail = 'caller@example.com';
      const invite = mockInvite({ email: callerEmail });
      const team = mockTeam();
      const deps = createDeps({
        findInviteByToken: jest.fn().mockResolvedValue(invite),
        addTeamMember: jest.fn().mockResolvedValue(team),
        acceptInvite: jest.fn().mockResolvedValue(invite),
        findGroupById: jest.fn().mockResolvedValue(team),
      });
      const handlers = createTeamInviteHandlers(deps);
      const { req, res, status } = createReqRes({
        params: { token: validToken },
        userId: validCallerId,
        email: callerEmail,
      });

      await handlers.accept(req, res);

      expect(status).toHaveBeenCalledWith(200);
    });

    it('returns 410 and does not add the member when acceptInvite loses the race (returns null)', async () => {
      const callerEmail = 'caller@example.com';
      const invite = mockInvite({ email: callerEmail });
      const deps = createDeps({
        findInviteByToken: jest.fn().mockResolvedValue(invite),
        acceptInvite: jest.fn().mockResolvedValue(null),
      });
      const handlers = createTeamInviteHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { token: validToken },
        userId: validCallerId,
        email: callerEmail,
      });

      await handlers.accept(req, res);

      expect(status).toHaveBeenCalledWith(410);
      expect(json).toHaveBeenCalledWith({ error: 'Invite is no longer valid' });
      expect(deps.addTeamMember).not.toHaveBeenCalled();
    });

    it('claims the invite before adding the member (acceptInvite runs before addTeamMember)', async () => {
      const callerEmail = 'caller@example.com';
      const invite = mockInvite({ email: callerEmail });
      const callOrder: string[] = [];
      const deps = createDeps({
        findInviteByToken: jest.fn().mockResolvedValue(invite),
        acceptInvite: jest.fn().mockImplementation(async () => {
          callOrder.push('accept');
          return mockInvite({ status: 'accepted' });
        }),
        addTeamMember: jest.fn().mockImplementation(async () => {
          callOrder.push('addMember');
          return mockTeam();
        }),
      });
      const handlers = createTeamInviteHandlers(deps);
      const { req, res, status } = createReqRes({
        params: { token: validToken },
        userId: validCallerId,
        email: callerEmail,
      });

      await handlers.accept(req, res);

      expect(status).toHaveBeenCalledWith(200);
      expect(callOrder).toEqual(['accept', 'addMember']);
    });
  });

  // ── decline ───────────────────────────────────────────────────────────────────
  describe('decline', () => {
    it('happy path: returns 200 {success:true}', async () => {
      const invite = mockInvite({ email: 'caller@example.com' });
      const deps = createDeps({ findInviteByToken: jest.fn().mockResolvedValue(invite) });
      const handlers = createTeamInviteHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { token: validToken },
        email: 'caller@example.com',
      });

      await handlers.decline(req, res);

      expect(deps.declineInvite).toHaveBeenCalledWith({ token: validToken });
      expect(status).toHaveBeenCalledWith(200);
      expect(json).toHaveBeenCalledWith({ success: true });
    });

    it('returns 404 when invite not found', async () => {
      const deps = createDeps({ findInviteByToken: jest.fn().mockResolvedValue(null) });
      const handlers = createTeamInviteHandlers(deps);
      const { req, res, status, json } = createReqRes({ params: { token: validToken } });

      await handlers.decline(req, res);

      expect(status).toHaveBeenCalledWith(404);
      expect(json).toHaveBeenCalledWith({ error: 'Invite not found' });
    });

    it('returns 410 when invite is not pending', async () => {
      const invite = mockInvite({ status: 'declined', email: 'caller@example.com' });
      const deps = createDeps({ findInviteByToken: jest.fn().mockResolvedValue(invite) });
      const handlers = createTeamInviteHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { token: validToken },
        email: 'caller@example.com',
      });

      await handlers.decline(req, res);

      expect(status).toHaveBeenCalledWith(410);
      expect(json).toHaveBeenCalledWith({ error: 'Invite is no longer valid' });
    });

    it('returns 403 when caller is not the invitee', async () => {
      const invite = mockInvite({
        email: 'other@example.com',
        invitedUserId: new Types.ObjectId(),
      });
      const deps = createDeps({ findInviteByToken: jest.fn().mockResolvedValue(invite) });
      const handlers = createTeamInviteHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { token: validToken },
        userId: validCallerId,
        email: 'caller@example.com',
      });

      await handlers.decline(req, res);

      expect(status).toHaveBeenCalledWith(403);
      expect(json).toHaveBeenCalledWith({ error: 'Forbidden' });
    });

    it('returns 500 on unexpected error', async () => {
      const invite = mockInvite({ email: 'caller@example.com' });
      const deps = createDeps({
        findInviteByToken: jest.fn().mockResolvedValue(invite),
        declineInvite: jest.fn().mockRejectedValue(new Error('db down')),
      });
      const handlers = createTeamInviteHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { token: validToken },
        email: 'caller@example.com',
      });

      await handlers.decline(req, res);

      expect(status).toHaveBeenCalledWith(500);
      expect(json).toHaveBeenCalledWith({ error: 'Failed to decline invite' });
    });

    it('returns 410 when invite is expired (status pending but expiresAt in the past) and does not call declineInvite', async () => {
      const invite = mockInvite({
        status: 'pending',
        email: 'caller@example.com',
        expiresAt: new Date(Date.now() - 1000),
      });
      const deps = createDeps({ findInviteByToken: jest.fn().mockResolvedValue(invite) });
      const handlers = createTeamInviteHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { token: validToken },
        email: 'caller@example.com',
      });

      await handlers.decline(req, res);

      expect(status).toHaveBeenCalledWith(410);
      expect(json).toHaveBeenCalledWith({ error: 'Invite is no longer valid' });
      expect(deps.declineInvite).not.toHaveBeenCalled();
    });

    it('allows decline when invite email is mixed-case and caller email matches case-insensitively', async () => {
      const invite = mockInvite({ email: 'User@Example.com' });
      const deps = createDeps({ findInviteByToken: jest.fn().mockResolvedValue(invite) });
      const handlers = createTeamInviteHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { token: validToken },
        email: 'user@example.com',
      });

      await handlers.decline(req, res);

      expect(status).toHaveBeenCalledWith(200);
      expect(json).toHaveBeenCalledWith({ success: true });
      expect(deps.declineInvite).toHaveBeenCalledWith({ token: validToken });
    });

    it('returns 410 when declineInvite loses the race (returns null)', async () => {
      const invite = mockInvite({ email: 'caller@example.com' });
      const deps = createDeps({
        findInviteByToken: jest.fn().mockResolvedValue(invite),
        declineInvite: jest.fn().mockResolvedValue(null),
      });
      const handlers = createTeamInviteHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { token: validToken },
        email: 'caller@example.com',
      });

      await handlers.decline(req, res);

      expect(status).toHaveBeenCalledWith(410);
      expect(json).toHaveBeenCalledWith({ error: 'Invite is no longer valid' });
    });
  });

  // ── create ────────────────────────────────────────────────────────────────────
  describe('create', () => {
    it('happy path: admin creates invite, returns 201 with token', async () => {
      const invite = mockInvite();
      const team = mockTeam();
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('admin'),
        findGroupById: jest.fn().mockResolvedValue(team),
        createInvite: jest.fn().mockResolvedValue(invite),
        findUser: jest.fn().mockResolvedValue(null),
      });
      const handlers = createTeamInviteHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { id: validId },
        body: { email: 'invitee@example.com', role: 'member' },
        userId: validCallerId,
      });

      await handlers.create(req, res);

      expect(status).toHaveBeenCalledWith(201);
      const { invite: result } = json.mock.calls[0][0];
      expect(result).toBeDefined();
      expect(result.token).toBeDefined();
    });

    it('calls createInvite with correct params including tenantId', async () => {
      const invite = mockInvite();
      const team = mockTeam();
      const targetUser = mockUser({
        _id: new Types.ObjectId(validUserId),
        email: 'invitee@example.com',
      });
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('admin'),
        findGroupById: jest.fn().mockResolvedValue(team),
        createInvite: jest.fn().mockResolvedValue(invite),
        findUser: jest.fn().mockResolvedValue(targetUser),
      });
      const handlers = createTeamInviteHandlers(deps);
      const { req, res } = createReqRes({
        params: { id: validId },
        body: { email: 'invitee@example.com', role: 'member' },
        userId: validCallerId,
      });

      await handlers.create(req, res);

      expect(deps.createInvite).toHaveBeenCalledWith({
        groupId: validId,
        email: 'invitee@example.com',
        role: 'member',
        invitedBy: validCallerId,
        invitedUserId: targetUser._id,
        tenantId: 'tenant-1',
      });
    });

    it('returns 400 when email is missing', async () => {
      const team = mockTeam();
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('admin'),
        findGroupById: jest.fn().mockResolvedValue(team),
      });
      const handlers = createTeamInviteHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { id: validId },
        body: { role: 'member' },
      });

      await handlers.create(req, res);

      expect(status).toHaveBeenCalledWith(400);
      expect(json).toHaveBeenCalledWith({ error: 'email is required' });
    });

    it('returns 400 when email is invalid', async () => {
      const team = mockTeam();
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('admin'),
        findGroupById: jest.fn().mockResolvedValue(team),
      });
      const handlers = createTeamInviteHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { id: validId },
        body: { email: 'not-an-email', role: 'member' },
      });

      await handlers.create(req, res);

      expect(status).toHaveBeenCalledWith(400);
      expect(json).toHaveBeenCalledWith({ error: 'Invalid email format' });
    });

    it('returns 400 when role is invalid', async () => {
      const team = mockTeam();
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('admin'),
        findGroupById: jest.fn().mockResolvedValue(team),
      });
      const handlers = createTeamInviteHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { id: validId },
        body: { email: 'valid@example.com', role: 'owner' },
      });

      await handlers.create(req, res);

      expect(status).toHaveBeenCalledWith(400);
      expect(json).toHaveBeenCalledWith({ error: 'role must be "admin" or "member"' });
    });

    it('returns 400 when role is missing', async () => {
      const team = mockTeam();
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('admin'),
        findGroupById: jest.fn().mockResolvedValue(team),
      });
      const handlers = createTeamInviteHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { id: validId },
        body: { email: 'valid@example.com' },
      });

      await handlers.create(req, res);

      expect(status).toHaveBeenCalledWith(400);
      expect(json).toHaveBeenCalledWith({ error: 'role must be "admin" or "member"' });
    });

    it('returns 404 when team not found (admin gate)', async () => {
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue(null),
        findGroupById: jest.fn().mockResolvedValue(null),
      });
      const handlers = createTeamInviteHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { id: validId },
        body: { email: 'valid@example.com', role: 'member' },
      });

      await handlers.create(req, res);

      expect(status).toHaveBeenCalledWith(404);
      expect(json).toHaveBeenCalledWith({ error: 'Team not found' });
    });

    it('returns 403 when caller is a member but not admin', async () => {
      const team = mockTeam();
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('member'),
        findGroupById: jest.fn().mockResolvedValue(team),
      });
      const handlers = createTeamInviteHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { id: validId },
        body: { email: 'valid@example.com', role: 'member' },
      });

      await handlers.create(req, res);

      expect(status).toHaveBeenCalledWith(403);
      expect(json).toHaveBeenCalledWith({ error: 'Forbidden' });
    });

    it('calls sendInviteEmail with correct payload when provided', async () => {
      const invite = mockInvite({ token: validToken });
      const team = mockTeam({ name: 'Great Team' });
      const callerUser = mockUser({ _id: new Types.ObjectId(validCallerId), name: 'Admin User' });
      const sendInviteEmail = jest.fn().mockResolvedValue(undefined);
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('admin'),
        findGroupById: jest
          .fn()
          .mockResolvedValueOnce(team)
          .mockResolvedValueOnce(callerUser as unknown as IGroup),
        createInvite: jest.fn().mockResolvedValue(invite),
        findUser: jest.fn().mockResolvedValueOnce(null).mockResolvedValueOnce(callerUser),
        sendInviteEmail,
      });
      const handlers = createTeamInviteHandlers(deps);
      const { req, res, status } = createReqRes({
        params: { id: validId },
        body: { email: 'invitee@example.com', role: 'member' },
        userId: validCallerId,
      });

      await handlers.create(req, res);

      expect(status).toHaveBeenCalledWith(201);
      expect(sendInviteEmail).toHaveBeenCalledWith(
        expect.objectContaining({
          email: 'invitee@example.com',
          token: validToken,
          teamName: 'Great Team',
        }),
      );
    });

    it('still returns 201 when sendInviteEmail is not provided', async () => {
      const invite = mockInvite();
      const team = mockTeam();
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('admin'),
        findGroupById: jest.fn().mockResolvedValue(team),
        createInvite: jest.fn().mockResolvedValue(invite),
        sendInviteEmail: undefined,
      });
      const handlers = createTeamInviteHandlers(deps);
      const { req, res, status } = createReqRes({
        params: { id: validId },
        body: { email: 'invitee@example.com', role: 'member' },
      });

      await handlers.create(req, res);

      expect(status).toHaveBeenCalledWith(201);
    });

    it('still returns 201 when sendInviteEmail throws (best-effort)', async () => {
      const invite = mockInvite();
      const team = mockTeam();
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('admin'),
        findGroupById: jest.fn().mockResolvedValue(team),
        createInvite: jest.fn().mockResolvedValue(invite),
        sendInviteEmail: jest.fn().mockRejectedValue(new Error('SMTP error')),
      });
      const handlers = createTeamInviteHandlers(deps);
      const { req, res, status } = createReqRes({
        params: { id: validId },
        body: { email: 'invitee@example.com', role: 'member' },
      });

      await handlers.create(req, res);

      expect(status).toHaveBeenCalledWith(201);
    });

    it('returns 500 on unexpected error', async () => {
      const team = mockTeam();
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('admin'),
        findGroupById: jest.fn().mockResolvedValue(team),
        createInvite: jest.fn().mockRejectedValue(new Error('db down')),
      });
      const handlers = createTeamInviteHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { id: validId },
        body: { email: 'invitee@example.com', role: 'member' },
      });

      await handlers.create(req, res);

      expect(status).toHaveBeenCalledWith(500);
      expect(json).toHaveBeenCalledWith({ error: 'Failed to create invite' });
    });

    it('returns 409 when the invited user is already a team member', async () => {
      const invitedUser = mockUser({
        _id: new Types.ObjectId(validUserId),
        email: 'invitee@example.com',
      });
      const team = mockTeam({
        members: [
          { userId: new Types.ObjectId(validCallerId), role: 'admin', joinedAt: new Date() },
          { userId: new Types.ObjectId(validUserId), role: 'member', joinedAt: new Date() },
        ],
      });
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('admin'),
        findGroupById: jest.fn().mockResolvedValue(team),
        findUser: jest.fn().mockResolvedValue(invitedUser),
      });
      const handlers = createTeamInviteHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { id: validId },
        body: { email: 'invitee@example.com', role: 'member' },
        userId: validCallerId,
      });

      await handlers.create(req, res);

      expect(status).toHaveBeenCalledWith(409);
      expect(json).toHaveBeenCalledWith({ error: 'User is already a team member' });
      expect(deps.createInvite).not.toHaveBeenCalled();
    });

    it('returns 409 when a pending invite already exists for the email', async () => {
      const team = mockTeam();
      const existing = mockInvite({ email: 'invitee@example.com', status: 'pending' });
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('admin'),
        findGroupById: jest.fn().mockResolvedValue(team),
        findUser: jest.fn().mockResolvedValue(null),
        listInvitesForTeam: jest.fn().mockResolvedValue([existing]),
      });
      const handlers = createTeamInviteHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { id: validId },
        body: { email: 'Invitee@Example.com', role: 'member' },
        userId: validCallerId,
      });

      await handlers.create(req, res);

      expect(status).toHaveBeenCalledWith(409);
      expect(json).toHaveBeenCalledWith({
        error: 'A pending invite already exists for this email',
      });
      expect(deps.createInvite).not.toHaveBeenCalled();
    });

    it('allows the invite when a pending invite exists only for a different email', async () => {
      const team = mockTeam();
      const otherInvite = mockInvite({ email: 'someone-else@example.com', status: 'pending' });
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('admin'),
        findGroupById: jest.fn().mockResolvedValue(team),
        findUser: jest.fn().mockResolvedValue(null),
        listInvitesForTeam: jest.fn().mockResolvedValue([otherInvite]),
        createInvite: jest.fn().mockResolvedValue(mockInvite()),
      });
      const handlers = createTeamInviteHandlers(deps);
      const { req, res, status } = createReqRes({
        params: { id: validId },
        body: { email: 'invitee@example.com', role: 'member' },
        userId: validCallerId,
      });

      await handlers.create(req, res);

      expect(status).toHaveBeenCalledWith(201);
      expect(deps.createInvite).toHaveBeenCalled();
    });
  });

  // ── listForTeam ───────────────────────────────────────────────────────────────
  describe('listForTeam', () => {
    it('returns invites with token stripped for admin', async () => {
      const team = mockTeam();
      const invite = mockInvite({ token: 'secret-token' });
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('admin'),
        findGroupById: jest.fn().mockResolvedValue(team),
        listInvitesForTeam: jest.fn().mockResolvedValue([invite]),
      });
      const handlers = createTeamInviteHandlers(deps);
      const { req, res, status, json } = createReqRes({ params: { id: validId } });

      await handlers.listForTeam(req, res);

      expect(deps.listInvitesForTeam).toHaveBeenCalledWith({
        groupId: validId,
        status: 'pending',
      });
      expect(status).toHaveBeenCalledWith(200);
      const { invites } = json.mock.calls[0][0];
      expect(invites).toHaveLength(1);
      expect(invites[0].token).toBeUndefined();
    });

    it('returns 404 when team not found (non-member)', async () => {
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue(null),
        findGroupById: jest.fn().mockResolvedValue(null),
      });
      const handlers = createTeamInviteHandlers(deps);
      const { req, res, status, json } = createReqRes({ params: { id: validId } });

      await handlers.listForTeam(req, res);

      expect(status).toHaveBeenCalledWith(404);
      expect(json).toHaveBeenCalledWith({ error: 'Team not found' });
    });

    it('returns 403 when caller is member but not admin', async () => {
      const team = mockTeam();
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('member'),
        findGroupById: jest.fn().mockResolvedValue(team),
      });
      const handlers = createTeamInviteHandlers(deps);
      const { req, res, status, json } = createReqRes({ params: { id: validId } });

      await handlers.listForTeam(req, res);

      expect(status).toHaveBeenCalledWith(403);
      expect(json).toHaveBeenCalledWith({ error: 'Forbidden' });
    });

    it('returns 500 on error', async () => {
      const team = mockTeam();
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('admin'),
        findGroupById: jest.fn().mockResolvedValue(team),
        listInvitesForTeam: jest.fn().mockRejectedValue(new Error('db down')),
      });
      const handlers = createTeamInviteHandlers(deps);
      const { req, res, status, json } = createReqRes({ params: { id: validId } });

      await handlers.listForTeam(req, res);

      expect(status).toHaveBeenCalledWith(500);
      expect(json).toHaveBeenCalledWith({ error: 'Failed to list team invites' });
    });
  });

  // ── revoke ────────────────────────────────────────────────────────────────────
  describe('revoke', () => {
    it('happy path: admin revokes invite, returns 200 {success:true}', async () => {
      const team = mockTeam();
      const revokedInvite = mockInvite({ status: 'revoked' });
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('admin'),
        findGroupById: jest.fn().mockResolvedValue(team),
        revokeInvite: jest.fn().mockResolvedValue(revokedInvite),
      });
      const handlers = createTeamInviteHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { id: validId, inviteId: validInviteId },
      });

      await handlers.revoke(req, res);

      expect(deps.revokeInvite).toHaveBeenCalledWith({
        inviteId: validInviteId,
        groupId: validId,
      });
      expect(status).toHaveBeenCalledWith(200);
      expect(json).toHaveBeenCalledWith({ success: true });
    });

    it('returns 400 for invalid inviteId', async () => {
      const team = mockTeam();
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('admin'),
        findGroupById: jest.fn().mockResolvedValue(team),
      });
      const handlers = createTeamInviteHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { id: validId, inviteId: 'not-an-id' },
      });

      await handlers.revoke(req, res);

      expect(status).toHaveBeenCalledWith(400);
      expect(json).toHaveBeenCalledWith({ error: 'Invalid invite ID format' });
    });

    it('returns 404 when revokeInvite returns null', async () => {
      const team = mockTeam();
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('admin'),
        findGroupById: jest.fn().mockResolvedValue(team),
        revokeInvite: jest.fn().mockResolvedValue(null),
      });
      const handlers = createTeamInviteHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { id: validId, inviteId: validInviteId },
      });

      await handlers.revoke(req, res);

      expect(status).toHaveBeenCalledWith(404);
      expect(json).toHaveBeenCalledWith({ error: 'Invite not found' });
    });

    it('returns 404 when team not found (non-member)', async () => {
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue(null),
        findGroupById: jest.fn().mockResolvedValue(null),
      });
      const handlers = createTeamInviteHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { id: validId, inviteId: validInviteId },
      });

      await handlers.revoke(req, res);

      expect(status).toHaveBeenCalledWith(404);
      expect(json).toHaveBeenCalledWith({ error: 'Team not found' });
    });

    it('returns 403 when caller is member but not admin', async () => {
      const team = mockTeam();
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('member'),
        findGroupById: jest.fn().mockResolvedValue(team),
      });
      const handlers = createTeamInviteHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { id: validId, inviteId: validInviteId },
      });

      await handlers.revoke(req, res);

      expect(status).toHaveBeenCalledWith(403);
      expect(json).toHaveBeenCalledWith({ error: 'Forbidden' });
    });

    it('returns 500 on unexpected error', async () => {
      const team = mockTeam();
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('admin'),
        findGroupById: jest.fn().mockResolvedValue(team),
        revokeInvite: jest.fn().mockRejectedValue(new Error('db down')),
      });
      const handlers = createTeamInviteHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { id: validId, inviteId: validInviteId },
      });

      await handlers.revoke(req, res);

      expect(status).toHaveBeenCalledWith(500);
      expect(json).toHaveBeenCalledWith({ error: 'Failed to revoke invite' });
    });
  });
});
