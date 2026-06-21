import { Types } from 'mongoose';
import type { IGroup, IUser } from '@librechat/data-schemas';
import type { Response } from 'express';
import type { ServerRequest } from '~/types/http';
import type { TeamsHandlersDeps } from './handlers';
import { createTeamsHandlers } from './handlers';

jest.mock('@librechat/data-schemas', () => ({
  ...jest.requireActual('@librechat/data-schemas'),
  logger: { error: jest.fn(), warn: jest.fn(), info: jest.fn(), debug: jest.fn() },
}));

describe('createTeamsHandlers', () => {
  let validId: string;
  let validUserId: string;
  let validCallerId: string;

  beforeEach(() => {
    validId = new Types.ObjectId().toString();
    validUserId = new Types.ObjectId().toString();
    validCallerId = new Types.ObjectId().toString();
  });

  function mockTeam(overrides: Partial<IGroup> = {}): IGroup {
    return {
      _id: new Types.ObjectId(validId),
      name: 'Test Team',
      source: 'local',
      kind: 'team',
      memberIds: [validCallerId],
      members: [{ userId: new Types.ObjectId(validCallerId), role: 'owner', joinedAt: new Date() }],
      ownerId: new Types.ObjectId(validCallerId),
      createdAt: new Date(),
      updatedAt: new Date(),
      ...overrides,
    } as IGroup;
  }

  function mockUser(overrides: Partial<IUser> = {}): IUser {
    return {
      _id: new Types.ObjectId(validUserId),
      name: 'Test User',
      email: 'test@example.com',
      avatar: 'https://example.com/avatar.png',
      username: 'testuser',
      ...overrides,
    } as IUser;
  }

  function createReqRes(
    overrides: {
      params?: Record<string, string>;
      query?: Record<string, string>;
      body?: Record<string, unknown>;
      userId?: string;
    } = {},
  ) {
    const callerId = overrides.userId ?? validCallerId;
    const req = {
      params: overrides.params ?? {},
      query: overrides.query ?? {},
      body: overrides.body ?? {},
      user: { id: callerId, tenantId: 'tenant-1' },
    } as unknown as ServerRequest;

    const json = jest.fn();
    const status = jest.fn().mockReturnValue({ json });
    const res = { status, json } as unknown as Response;

    return { req, res, status, json };
  }

  function createDeps(overrides: Partial<TeamsHandlersDeps> = {}): TeamsHandlersDeps {
    return {
      createTeam: jest.fn().mockResolvedValue(mockTeam()),
      getUserTeams: jest.fn().mockResolvedValue([]),
      getTeamRole: jest.fn().mockResolvedValue(null),
      removeTeamMember: jest.fn().mockResolvedValue(mockTeam()),
      setMemberRole: jest.fn().mockResolvedValue(mockTeam()),
      transferOwnership: jest.fn().mockResolvedValue(mockTeam()),
      deleteInvitesByGroup: jest.fn().mockResolvedValue(0),
      findGroupById: jest.fn().mockResolvedValue(null),
      updateGroupById: jest.fn().mockResolvedValue(null),
      deleteGroup: jest.fn().mockResolvedValue(null),
      findUsers: jest.fn().mockResolvedValue([]),
      ...overrides,
    };
  }

  describe('create', () => {
    it('creates team and returns 201', async () => {
      const team = mockTeam();
      const deps = createDeps({ createTeam: jest.fn().mockResolvedValue(team) });
      const handlers = createTeamsHandlers(deps);
      const { req, res, status, json } = createReqRes({
        body: { name: 'My Team', description: 'A great team' },
        userId: validCallerId,
      });

      await handlers.create(req, res);

      expect(status).toHaveBeenCalledWith(201);
      expect(json).toHaveBeenCalledWith({ team });
      expect(deps.createTeam).toHaveBeenCalledWith({
        name: 'My Team',
        description: 'A great team',
        avatar: undefined,
        ownerId: validCallerId,
        tenantId: 'tenant-1',
      });
    });

    it('returns 400 when name is missing', async () => {
      const deps = createDeps();
      const handlers = createTeamsHandlers(deps);
      const { req, res, status, json } = createReqRes({ body: {} });

      await handlers.create(req, res);

      expect(status).toHaveBeenCalledWith(400);
      expect(json).toHaveBeenCalledWith({ error: 'name is required' });
      expect(deps.createTeam).not.toHaveBeenCalled();
    });

    it('returns 400 when name is whitespace-only', async () => {
      const deps = createDeps();
      const handlers = createTeamsHandlers(deps);
      const { req, res, status, json } = createReqRes({ body: { name: '   ' } });

      await handlers.create(req, res);

      expect(status).toHaveBeenCalledWith(400);
      expect(json).toHaveBeenCalledWith({ error: 'name is required' });
    });

    it('returns 400 on ValidationError', async () => {
      const err = new Error('name is too long');
      err.name = 'ValidationError';
      const deps = createDeps({ createTeam: jest.fn().mockRejectedValue(err) });
      const handlers = createTeamsHandlers(deps);
      const { req, res, status, json } = createReqRes({ body: { name: 'Test' } });

      await handlers.create(req, res);

      expect(status).toHaveBeenCalledWith(400);
      expect(json).toHaveBeenCalledWith({ error: 'name is too long' });
    });

    it('returns 500 on unexpected error', async () => {
      const deps = createDeps({ createTeam: jest.fn().mockRejectedValue(new Error('db crash')) });
      const handlers = createTeamsHandlers(deps);
      const { req, res, status, json } = createReqRes({ body: { name: 'Test' } });

      await handlers.create(req, res);

      expect(status).toHaveBeenCalledWith(500);
      expect(json).toHaveBeenCalledWith({ error: 'Failed to create team' });
    });
  });

  describe('list', () => {
    it('returns teams with 200', async () => {
      const teams = [mockTeam()];
      const deps = createDeps({ getUserTeams: jest.fn().mockResolvedValue(teams) });
      const handlers = createTeamsHandlers(deps);
      const { req, res, status, json } = createReqRes({ userId: validCallerId });

      await handlers.list(req, res);

      expect(deps.getUserTeams).toHaveBeenCalledWith({ userId: validCallerId });
      expect(status).toHaveBeenCalledWith(200);
      expect(json).toHaveBeenCalledWith({ teams });
    });

    it('returns 500 on error', async () => {
      const deps = createDeps({ getUserTeams: jest.fn().mockRejectedValue(new Error('db down')) });
      const handlers = createTeamsHandlers(deps);
      const { req, res, status, json } = createReqRes();

      await handlers.list(req, res);

      expect(status).toHaveBeenCalledWith(500);
      expect(json).toHaveBeenCalledWith({ error: 'Failed to list teams' });
    });
  });

  describe('get', () => {
    it('returns team with enriched members on 200', async () => {
      const team = mockTeam();
      const user = mockUser({ _id: new Types.ObjectId(validCallerId) });
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('owner'),
        findGroupById: jest.fn().mockResolvedValue(team),
        findUsers: jest.fn().mockResolvedValue([user]),
      });
      const handlers = createTeamsHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { id: validId },
        userId: validCallerId,
      });

      await handlers.get(req, res);

      expect(status).toHaveBeenCalledWith(200);
      const result = json.mock.calls[0][0];
      expect(result.team).toBeDefined();
      expect(Array.isArray(result.members)).toBe(true);
    });

    it('returns 400 for invalid team ID', async () => {
      const deps = createDeps();
      const handlers = createTeamsHandlers(deps);
      const { req, res, status, json } = createReqRes({ params: { id: 'bad-id' } });

      await handlers.get(req, res);

      expect(status).toHaveBeenCalledWith(400);
      expect(json).toHaveBeenCalledWith({ error: 'Invalid team ID format' });
    });

    it('returns 404 when team not found', async () => {
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue(null),
        findGroupById: jest.fn().mockResolvedValue(null),
      });
      const handlers = createTeamsHandlers(deps);
      const { req, res, status, json } = createReqRes({ params: { id: validId } });

      await handlers.get(req, res);

      expect(status).toHaveBeenCalledWith(404);
      expect(json).toHaveBeenCalledWith({ error: 'Team not found' });
    });

    it('returns 404 when caller is not a member (non-member gets 404 not 403)', async () => {
      const team = mockTeam();
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue(null),
        findGroupById: jest.fn().mockResolvedValue(team),
      });
      const handlers = createTeamsHandlers(deps);
      const { req, res, status, json } = createReqRes({ params: { id: validId } });

      await handlers.get(req, res);

      expect(status).toHaveBeenCalledWith(404);
      expect(json).toHaveBeenCalledWith({ error: 'Team not found' });
    });

    it('returns 404 when group has kind != team', async () => {
      const group = { ...mockTeam(), kind: 'group' } as IGroup;
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('member'),
        findGroupById: jest.fn().mockResolvedValue(group),
      });
      const handlers = createTeamsHandlers(deps);
      const { req, res, status, json } = createReqRes({ params: { id: validId } });

      await handlers.get(req, res);

      expect(status).toHaveBeenCalledWith(404);
      expect(json).toHaveBeenCalledWith({ error: 'Team not found' });
    });

    it('returns 500 on error', async () => {
      const deps = createDeps({
        getTeamRole: jest.fn().mockRejectedValue(new Error('db down')),
        findGroupById: jest.fn().mockResolvedValue(mockTeam()),
      });
      const handlers = createTeamsHandlers(deps);
      const { req, res, status, json } = createReqRes({ params: { id: validId } });

      await handlers.get(req, res);

      expect(status).toHaveBeenCalledWith(500);
      expect(json).toHaveBeenCalledWith({ error: 'Failed to get team' });
    });
  });

  describe('update', () => {
    it('updates team and returns 200 for admin', async () => {
      const updated = mockTeam({ name: 'Renamed' });
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('admin'),
        findGroupById: jest.fn().mockResolvedValue(mockTeam()),
        updateGroupById: jest.fn().mockResolvedValue(updated),
      });
      const handlers = createTeamsHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { id: validId },
        body: { name: 'Renamed' },
      });

      await handlers.update(req, res);

      expect(status).toHaveBeenCalledWith(200);
      expect(json).toHaveBeenCalledWith({ team: updated });
    });

    it('returns 400 for invalid team ID', async () => {
      const deps = createDeps();
      const handlers = createTeamsHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { id: 'nope' },
        body: { name: 'Test' },
      });

      await handlers.update(req, res);

      expect(status).toHaveBeenCalledWith(400);
      expect(json).toHaveBeenCalledWith({ error: 'Invalid team ID format' });
    });

    it('returns 400 when no valid update fields provided (admin caller, empty body)', async () => {
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('admin'),
        findGroupById: jest.fn().mockResolvedValue(mockTeam()),
      });
      const handlers = createTeamsHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { id: validId },
        body: {},
      });

      await handlers.update(req, res);

      expect(status).toHaveBeenCalledWith(400);
      expect(json).toHaveBeenCalledWith({ error: 'No valid fields to update' });
    });

    it('returns 404 (not 400) when non-member sends empty body — authz runs before body validation', async () => {
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue(null),
        findGroupById: jest.fn().mockResolvedValue(mockTeam()),
      });
      const handlers = createTeamsHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { id: validId },
        body: {},
      });

      await handlers.update(req, res);

      expect(status).toHaveBeenCalledWith(404);
      expect(json).toHaveBeenCalledWith({ error: 'Team not found' });
    });

    it('returns 404 when caller is not a member (hidden from outsiders)', async () => {
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue(null),
        findGroupById: jest.fn().mockResolvedValue(null),
      });
      const handlers = createTeamsHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { id: validId },
        body: { name: 'X' },
      });

      await handlers.update(req, res);

      expect(status).toHaveBeenCalledWith(404);
      expect(json).toHaveBeenCalledWith({ error: 'Team not found' });
    });

    it('returns 403 when caller is a member but not admin', async () => {
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('member'),
        findGroupById: jest.fn().mockResolvedValue(mockTeam()),
      });
      const handlers = createTeamsHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { id: validId },
        body: { name: 'X' },
      });

      await handlers.update(req, res);

      expect(status).toHaveBeenCalledWith(403);
      expect(json).toHaveBeenCalledWith({ error: 'Forbidden' });
    });

    it('returns 400 on ValidationError', async () => {
      const err = new Error('name too long');
      err.name = 'ValidationError';
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('admin'),
        findGroupById: jest.fn().mockResolvedValue(mockTeam()),
        updateGroupById: jest.fn().mockRejectedValue(err),
      });
      const handlers = createTeamsHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { id: validId },
        body: { name: 'New' },
      });

      await handlers.update(req, res);

      expect(status).toHaveBeenCalledWith(400);
      expect(json).toHaveBeenCalledWith({ error: 'name too long' });
    });

    it('returns 500 on unexpected error', async () => {
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('owner'),
        findGroupById: jest.fn().mockResolvedValue(mockTeam()),
        updateGroupById: jest.fn().mockRejectedValue(new Error('db down')),
      });
      const handlers = createTeamsHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { id: validId },
        body: { name: 'Test' },
      });

      await handlers.update(req, res);

      expect(status).toHaveBeenCalledWith(500);
      expect(json).toHaveBeenCalledWith({ error: 'Failed to update team' });
    });
  });

  describe('remove', () => {
    it('deletes team, cascades invites, returns 200 for owner', async () => {
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('owner'),
        findGroupById: jest.fn().mockResolvedValue(mockTeam()),
        deleteInvitesByGroup: jest.fn().mockResolvedValue(2),
        deleteGroup: jest.fn().mockResolvedValue(mockTeam()),
      });
      const handlers = createTeamsHandlers(deps);
      const { req, res, status, json } = createReqRes({ params: { id: validId } });

      await handlers.remove(req, res);

      expect(deps.deleteInvitesByGroup).toHaveBeenCalledWith({ groupId: validId });
      expect(deps.deleteGroup).toHaveBeenCalledWith(validId);
      expect(status).toHaveBeenCalledWith(200);
      expect(json).toHaveBeenCalledWith({ success: true });
    });

    it('returns 400 for invalid team ID', async () => {
      const deps = createDeps();
      const handlers = createTeamsHandlers(deps);
      const { req, res, status, json } = createReqRes({ params: { id: 'bad' } });

      await handlers.remove(req, res);

      expect(status).toHaveBeenCalledWith(400);
      expect(json).toHaveBeenCalledWith({ error: 'Invalid team ID format' });
    });

    it('returns 404 for non-member caller', async () => {
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue(null),
        findGroupById: jest.fn().mockResolvedValue(mockTeam()),
      });
      const handlers = createTeamsHandlers(deps);
      const { req, res, status, json } = createReqRes({ params: { id: validId } });

      await handlers.remove(req, res);

      expect(status).toHaveBeenCalledWith(404);
      expect(json).toHaveBeenCalledWith({ error: 'Team not found' });
    });

    it('returns 403 when caller is admin but not owner', async () => {
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('admin'),
        findGroupById: jest.fn().mockResolvedValue(mockTeam()),
      });
      const handlers = createTeamsHandlers(deps);
      const { req, res, status, json } = createReqRes({ params: { id: validId } });

      await handlers.remove(req, res);

      expect(status).toHaveBeenCalledWith(403);
      expect(json).toHaveBeenCalledWith({ error: 'Forbidden' });
    });

    it('returns 500 on unexpected error', async () => {
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('owner'),
        findGroupById: jest.fn().mockResolvedValue(mockTeam()),
        deleteInvitesByGroup: jest.fn().mockRejectedValue(new Error('db down')),
      });
      const handlers = createTeamsHandlers(deps);
      const { req, res, status, json } = createReqRes({ params: { id: validId } });

      await handlers.remove(req, res);

      expect(status).toHaveBeenCalledWith(500);
      expect(json).toHaveBeenCalledWith({ error: 'Failed to delete team' });
    });
  });

  describe('listMembers', () => {
    it('returns enriched members for a team member', async () => {
      const team = mockTeam({
        members: [
          { userId: new Types.ObjectId(validCallerId), role: 'owner', joinedAt: new Date() },
          { userId: new Types.ObjectId(validUserId), role: 'member', joinedAt: new Date() },
        ],
      });
      const callerUser = mockUser({
        _id: new Types.ObjectId(validCallerId),
        name: 'Owner',
        email: 'owner@example.com',
      });
      const memberUser = mockUser({
        _id: new Types.ObjectId(validUserId),
        name: 'Member',
        email: 'member@example.com',
      });
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('owner'),
        findGroupById: jest.fn().mockResolvedValue(team),
        findUsers: jest.fn().mockResolvedValue([callerUser, memberUser]),
      });
      const handlers = createTeamsHandlers(deps);
      const { req, res, status, json } = createReqRes({ params: { id: validId } });

      await handlers.listMembers(req, res);

      expect(status).toHaveBeenCalledWith(200);
      const { members } = json.mock.calls[0][0];
      expect(Array.isArray(members)).toBe(true);
      expect(members).toHaveLength(2);
      expect(members[0]).toMatchObject({ role: 'owner' });
    });

    it('returns 400 for invalid team ID', async () => {
      const deps = createDeps();
      const handlers = createTeamsHandlers(deps);
      const { req, res, status, json } = createReqRes({ params: { id: 'bad' } });

      await handlers.listMembers(req, res);

      expect(status).toHaveBeenCalledWith(400);
      expect(json).toHaveBeenCalledWith({ error: 'Invalid team ID format' });
    });

    it('returns 404 for non-member caller', async () => {
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue(null),
        findGroupById: jest.fn().mockResolvedValue(mockTeam()),
      });
      const handlers = createTeamsHandlers(deps);
      const { req, res, status, json } = createReqRes({ params: { id: validId } });

      await handlers.listMembers(req, res);

      expect(status).toHaveBeenCalledWith(404);
      expect(json).toHaveBeenCalledWith({ error: 'Team not found' });
    });

    it('returns 500 on error', async () => {
      const deps = createDeps({
        getTeamRole: jest.fn().mockRejectedValue(new Error('db down')),
      });
      const handlers = createTeamsHandlers(deps);
      const { req, res, status, json } = createReqRes({ params: { id: validId } });

      await handlers.listMembers(req, res);

      expect(status).toHaveBeenCalledWith(500);
      expect(json).toHaveBeenCalledWith({ error: 'Failed to list team members' });
    });
  });

  describe('removeMember', () => {
    it('allows admin to remove another member', async () => {
      const teamWithTarget = mockTeam({
        members: [
          { userId: new Types.ObjectId(validCallerId), role: 'admin', joinedAt: new Date() },
          { userId: new Types.ObjectId(validUserId), role: 'member', joinedAt: new Date() },
        ],
      });
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('admin'),
        findGroupById: jest.fn().mockResolvedValue(teamWithTarget),
        removeTeamMember: jest.fn().mockResolvedValue(mockTeam()),
      });
      const handlers = createTeamsHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { id: validId, userId: validUserId },
        userId: validCallerId,
      });

      await handlers.removeMember(req, res);

      expect(deps.removeTeamMember).toHaveBeenCalledWith({
        groupId: validId,
        userId: validUserId,
      });
      expect(status).toHaveBeenCalledWith(200);
      expect(json).toHaveBeenCalledWith({ success: true });
    });

    it('allows a member to self-leave', async () => {
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('member'),
        findGroupById: jest.fn().mockResolvedValue(mockTeam()),
        removeTeamMember: jest.fn().mockResolvedValue(mockTeam()),
      });
      const handlers = createTeamsHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { id: validId, userId: validCallerId },
        userId: validCallerId,
      });

      await handlers.removeMember(req, res);

      expect(status).toHaveBeenCalledWith(200);
      expect(json).toHaveBeenCalledWith({ success: true });
    });

    it('returns 400 for invalid team ID', async () => {
      const deps = createDeps();
      const handlers = createTeamsHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { id: 'bad', userId: validUserId },
      });

      await handlers.removeMember(req, res);

      expect(status).toHaveBeenCalledWith(400);
      expect(json).toHaveBeenCalledWith({ error: 'Invalid team ID format' });
    });

    it('returns 400 for invalid target userId', async () => {
      const deps = createDeps({ getTeamRole: jest.fn().mockResolvedValue('admin') });
      const handlers = createTeamsHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { id: validId, userId: 'not-an-id' },
      });

      await handlers.removeMember(req, res);

      expect(status).toHaveBeenCalledWith(400);
      expect(json).toHaveBeenCalledWith({ error: 'Invalid user ID format' });
    });

    it('returns 404 for non-member caller', async () => {
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue(null),
        findGroupById: jest.fn().mockResolvedValue(mockTeam()),
      });
      const handlers = createTeamsHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { id: validId, userId: validUserId },
      });

      await handlers.removeMember(req, res);

      expect(status).toHaveBeenCalledWith(404);
      expect(json).toHaveBeenCalledWith({ error: 'Team not found' });
    });

    it('returns 403 when member tries to remove another member', async () => {
      const anotherUserId = new Types.ObjectId().toString();
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('member'),
        findGroupById: jest.fn().mockResolvedValue(mockTeam()),
      });
      const handlers = createTeamsHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { id: validId, userId: anotherUserId },
        userId: validCallerId,
      });

      await handlers.removeMember(req, res);

      expect(status).toHaveBeenCalledWith(403);
      expect(json).toHaveBeenCalledWith({ error: 'Forbidden' });
    });

    it('maps data-layer guard throw to 409', async () => {
      const guardErr = new Error('Cannot remove the team owner; transfer ownership first');
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('admin'),
        findGroupById: jest.fn().mockResolvedValue(mockTeam()),
        removeTeamMember: jest.fn().mockRejectedValue(guardErr),
      });
      const handlers = createTeamsHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { id: validId, userId: validUserId },
      });

      await handlers.removeMember(req, res);

      expect(status).toHaveBeenCalledWith(409);
      expect(json).toHaveBeenCalledWith({
        error: 'Cannot remove the team owner; transfer ownership first',
      });
    });

    it('returns 500 on unexpected error', async () => {
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('admin'),
        findGroupById: jest.fn().mockResolvedValue(mockTeam()),
        removeTeamMember: jest.fn().mockRejectedValue(new Error('db down')),
      });
      const handlers = createTeamsHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { id: validId, userId: validUserId },
      });

      await handlers.removeMember(req, res);

      expect(status).toHaveBeenCalledWith(500);
      expect(json).toHaveBeenCalledWith({ error: 'Failed to remove team member' });
    });
  });

  describe('changeMemberRole', () => {
    it('changes role and returns 200 for admin', async () => {
      const updated = mockTeam();
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('admin'),
        findGroupById: jest.fn().mockResolvedValue(mockTeam()),
        setMemberRole: jest.fn().mockResolvedValue(updated),
      });
      const handlers = createTeamsHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { id: validId, userId: validUserId },
        body: { role: 'admin' },
      });

      await handlers.changeMemberRole(req, res);

      expect(deps.setMemberRole).toHaveBeenCalledWith({
        groupId: validId,
        userId: validUserId,
        role: 'admin',
      });
      expect(status).toHaveBeenCalledWith(200);
      expect(json).toHaveBeenCalledWith({ team: updated });
    });

    it('returns 400 for invalid team ID', async () => {
      const deps = createDeps();
      const handlers = createTeamsHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { id: 'bad', userId: validUserId },
        body: { role: 'member' },
      });

      await handlers.changeMemberRole(req, res);

      expect(status).toHaveBeenCalledWith(400);
      expect(json).toHaveBeenCalledWith({ error: 'Invalid team ID format' });
    });

    it('returns 400 for invalid target userId', async () => {
      const deps = createDeps({ getTeamRole: jest.fn().mockResolvedValue('admin') });
      const handlers = createTeamsHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { id: validId, userId: 'not-an-id' },
        body: { role: 'member' },
      });

      await handlers.changeMemberRole(req, res);

      expect(status).toHaveBeenCalledWith(400);
      expect(json).toHaveBeenCalledWith({ error: 'Invalid user ID format' });
    });

    it('returns 400 when role is invalid', async () => {
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('admin'),
        findGroupById: jest.fn().mockResolvedValue(mockTeam()),
      });
      const handlers = createTeamsHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { id: validId, userId: validUserId },
        body: { role: 'owner' },
      });

      await handlers.changeMemberRole(req, res);

      expect(status).toHaveBeenCalledWith(400);
      expect(json).toHaveBeenCalledWith({ error: 'role must be "admin" or "member"' });
    });

    it('returns 403 when caller is member, not admin', async () => {
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('member'),
        findGroupById: jest.fn().mockResolvedValue(mockTeam()),
      });
      const handlers = createTeamsHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { id: validId, userId: validUserId },
        body: { role: 'admin' },
      });

      await handlers.changeMemberRole(req, res);

      expect(status).toHaveBeenCalledWith(403);
      expect(json).toHaveBeenCalledWith({ error: 'Forbidden' });
    });

    it('maps data-layer guard throw to 409', async () => {
      const guardErr = new Error('Cannot change the owner role; use transferOwnership');
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('admin'),
        findGroupById: jest.fn().mockResolvedValue(mockTeam()),
        setMemberRole: jest.fn().mockRejectedValue(guardErr),
      });
      const handlers = createTeamsHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { id: validId, userId: validUserId },
        body: { role: 'member' },
      });

      await handlers.changeMemberRole(req, res);

      expect(status).toHaveBeenCalledWith(409);
      expect(json).toHaveBeenCalledWith({
        error: 'Cannot change the owner role; use transferOwnership',
      });
    });

    it('returns 500 on unexpected error', async () => {
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('admin'),
        findGroupById: jest.fn().mockResolvedValue(mockTeam()),
        setMemberRole: jest.fn().mockRejectedValue(new Error('db down')),
      });
      const handlers = createTeamsHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { id: validId, userId: validUserId },
        body: { role: 'member' },
      });

      await handlers.changeMemberRole(req, res);

      expect(status).toHaveBeenCalledWith(500);
      expect(json).toHaveBeenCalledWith({ error: 'Failed to change member role' });
    });

    it('returns 404 when setMemberRole resolves null (target not a member)', async () => {
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('admin'),
        findGroupById: jest.fn().mockResolvedValue(mockTeam()),
        setMemberRole: jest.fn().mockResolvedValue(null),
      });
      const handlers = createTeamsHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { id: validId, userId: validUserId },
        body: { role: 'member' },
      });

      await handlers.changeMemberRole(req, res);

      expect(status).toHaveBeenCalledWith(404);
      expect(json).toHaveBeenCalledWith({ error: 'Member not found' });
    });
  });

  describe('transferOwnership', () => {
    it('transfers ownership and returns 200 for owner', async () => {
      const newOwnerId = new Types.ObjectId().toString();
      const updated = mockTeam();
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('owner'),
        findGroupById: jest.fn().mockResolvedValue(mockTeam()),
        transferOwnership: jest.fn().mockResolvedValue(updated),
      });
      const handlers = createTeamsHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { id: validId },
        body: { newOwnerId },
        userId: validCallerId,
      });

      await handlers.transferOwnership(req, res);

      expect(deps.transferOwnership).toHaveBeenCalledWith({
        groupId: validId,
        fromUserId: validCallerId,
        toUserId: newOwnerId,
      });
      expect(status).toHaveBeenCalledWith(200);
      expect(json).toHaveBeenCalledWith({ team: updated });
    });

    it('returns 400 for invalid team ID', async () => {
      const deps = createDeps();
      const handlers = createTeamsHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { id: 'bad' },
        body: { newOwnerId: validUserId },
      });

      await handlers.transferOwnership(req, res);

      expect(status).toHaveBeenCalledWith(400);
      expect(json).toHaveBeenCalledWith({ error: 'Invalid team ID format' });
    });

    it('returns 400 for invalid newOwnerId', async () => {
      const deps = createDeps({ getTeamRole: jest.fn().mockResolvedValue('owner') });
      const handlers = createTeamsHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { id: validId },
        body: { newOwnerId: 'not-an-id' },
      });

      await handlers.transferOwnership(req, res);

      expect(status).toHaveBeenCalledWith(400);
      expect(json).toHaveBeenCalledWith({ error: 'Invalid newOwnerId format' });
    });

    it('returns 400 when newOwnerId missing', async () => {
      const deps = createDeps({ getTeamRole: jest.fn().mockResolvedValue('owner') });
      const handlers = createTeamsHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { id: validId },
        body: {},
      });

      await handlers.transferOwnership(req, res);

      expect(status).toHaveBeenCalledWith(400);
      expect(json).toHaveBeenCalledWith({ error: 'newOwnerId is required' });
    });

    it('returns 403 when caller is not owner', async () => {
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('admin'),
        findGroupById: jest.fn().mockResolvedValue(mockTeam()),
      });
      const handlers = createTeamsHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { id: validId },
        body: { newOwnerId: validUserId },
      });

      await handlers.transferOwnership(req, res);

      expect(status).toHaveBeenCalledWith(403);
      expect(json).toHaveBeenCalledWith({ error: 'Forbidden' });
    });

    it('maps data-layer guard throw to 409', async () => {
      const guardErr = new Error('toUserId is not a member of the team');
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('owner'),
        findGroupById: jest.fn().mockResolvedValue(mockTeam()),
        transferOwnership: jest.fn().mockRejectedValue(guardErr),
      });
      const handlers = createTeamsHandlers(deps);
      const newOwnerId = new Types.ObjectId().toString();
      const { req, res, status, json } = createReqRes({
        params: { id: validId },
        body: { newOwnerId },
      });

      await handlers.transferOwnership(req, res);

      expect(status).toHaveBeenCalledWith(409);
      expect(json).toHaveBeenCalledWith({ error: 'toUserId is not a member of the team' });
    });

    it('returns 500 on unexpected error', async () => {
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('owner'),
        findGroupById: jest.fn().mockResolvedValue(mockTeam()),
        transferOwnership: jest.fn().mockRejectedValue(new Error('db down')),
      });
      const handlers = createTeamsHandlers(deps);
      const newOwnerId = new Types.ObjectId().toString();
      const { req, res, status, json } = createReqRes({
        params: { id: validId },
        body: { newOwnerId },
      });

      await handlers.transferOwnership(req, res);

      expect(status).toHaveBeenCalledWith(500);
      expect(json).toHaveBeenCalledWith({ error: 'Failed to transfer team ownership' });
    });

    it('returns 404 when transferOwnership resolves null', async () => {
      const newOwnerId = new Types.ObjectId().toString();
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('owner'),
        findGroupById: jest.fn().mockResolvedValue(mockTeam()),
        transferOwnership: jest.fn().mockResolvedValue(null),
      });
      const handlers = createTeamsHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { id: validId },
        body: { newOwnerId },
        userId: validCallerId,
      });

      await handlers.transferOwnership(req, res);

      expect(status).toHaveBeenCalledWith(404);
      expect(json).toHaveBeenCalledWith({ error: 'Team not found' });
    });
  });
});
