import { Types } from 'mongoose';
import type { IGroup } from '@librechat/data-schemas';
import type { Response } from 'express';
import type { ServerRequest } from '~/types/http';
import type { SubgroupsHandlersDeps } from './subgroups';
import { createSubgroupsHandlers } from './subgroups';

jest.mock('@librechat/data-schemas', () => ({
  ...jest.requireActual('@librechat/data-schemas'),
  logger: { error: jest.fn(), warn: jest.fn(), info: jest.fn(), debug: jest.fn() },
}));

describe('createSubgroupsHandlers', () => {
  let teamId: string;
  let callerId: string;
  let memberId: string;
  let sgId: string;

  beforeEach(() => {
    teamId = new Types.ObjectId().toString();
    callerId = new Types.ObjectId().toString();
    memberId = new Types.ObjectId().toString();
    sgId = new Types.ObjectId().toString();
  });

  function mockTeam(overrides: Partial<IGroup> = {}): IGroup {
    return {
      _id: new Types.ObjectId(teamId),
      name: 'Test Team',
      source: 'local',
      kind: 'team',
      memberIds: [callerId],
      members: [{ userId: new Types.ObjectId(callerId), role: 'owner', joinedAt: new Date() }],
      ownerId: new Types.ObjectId(callerId),
      tenantId: 'tenant-1',
      createdAt: new Date(),
      updatedAt: new Date(),
      ...overrides,
    } as IGroup;
  }

  function mockSubgroup(overrides: Partial<IGroup> = {}): IGroup {
    return {
      _id: new Types.ObjectId(sgId),
      name: 'Engineering',
      source: 'local',
      kind: 'team_subgroup',
      parentTeamId: new Types.ObjectId(teamId),
      memberIds: [],
      members: [],
      ownerId: new Types.ObjectId(callerId),
      tenantId: 'tenant-1',
      createdAt: new Date(),
      updatedAt: new Date(),
      ...overrides,
    } as IGroup;
  }

  function createReqRes(
    overrides: {
      params?: Record<string, string>;
      query?: Record<string, string>;
      body?: Record<string, unknown>;
      userId?: string;
    } = {},
  ) {
    const userId = overrides.userId ?? callerId;
    const req = {
      params: overrides.params ?? {},
      query: overrides.query ?? {},
      body: overrides.body ?? {},
      user: { id: userId, tenantId: 'tenant-1' },
    } as unknown as ServerRequest;

    const json = jest.fn();
    const status = jest.fn().mockReturnValue({ json });
    const res = { status, json } as unknown as Response;

    return { req, res, status, json };
  }

  function createDeps(overrides: Partial<SubgroupsHandlersDeps> = {}): SubgroupsHandlersDeps {
    return {
      getTeamRole: jest.fn().mockResolvedValue(null),
      findGroupById: jest.fn().mockResolvedValue(null),
      createSubgroup: jest.fn().mockResolvedValue(mockSubgroup()),
      getTeamSubgroups: jest.fn().mockResolvedValue([]),
      getSubgroupById: jest.fn().mockResolvedValue(null),
      updateSubgroup: jest.fn().mockResolvedValue(null),
      deleteSubgroup: jest.fn().mockResolvedValue(undefined),
      addSubgroupMember: jest.fn().mockResolvedValue(mockSubgroup()),
      removeSubgroupMember: jest.fn().mockResolvedValue(mockSubgroup()),
      findUsers: jest.fn().mockResolvedValue([]),
      deleteAclEntries: jest.fn().mockResolvedValue({ deletedCount: 0 }),
      ...overrides,
    };
  }

  describe('create', () => {
    it('owner can create a sub-group → 201 with {subgroup}', async () => {
      const team = mockTeam();
      const sg = mockSubgroup({ name: 'Engineering' });
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('owner'),
        findGroupById: jest.fn().mockResolvedValue(team),
        createSubgroup: jest.fn().mockResolvedValue(sg),
      });
      const handlers = createSubgroupsHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { id: teamId },
        body: { name: 'Engineering' },
      });

      await handlers.create(req, res);

      expect(status).toHaveBeenCalledWith(201);
      const body = json.mock.calls[0][0];
      expect(body.subgroup).toBeDefined();
      expect(body.subgroup._id).toBe(sg._id.toString());
      expect(body.subgroup.name).toBe('Engineering');
      expect(body.subgroup.parentTeamId).toBe(teamId);
      expect(typeof body.subgroup.memberCount).toBe('number');
    });

    it('admin can create a sub-group → 201', async () => {
      const team = mockTeam();
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('admin'),
        findGroupById: jest.fn().mockResolvedValue(team),
        createSubgroup: jest.fn().mockResolvedValue(mockSubgroup()),
      });
      const handlers = createSubgroupsHandlers(deps);
      const { req, res, status } = createReqRes({
        params: { id: teamId },
        body: { name: 'Design' },
      });

      await handlers.create(req, res);

      expect(status).toHaveBeenCalledWith(201);
    });

    it('plain member is denied → 403', async () => {
      const team = mockTeam();
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('member'),
        findGroupById: jest.fn().mockResolvedValue(team),
      });
      const handlers = createSubgroupsHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { id: teamId },
        body: { name: 'Engineering' },
      });

      await handlers.create(req, res);

      expect(status).toHaveBeenCalledWith(403);
      expect(json).toHaveBeenCalledWith({ error: 'Forbidden' });
      expect(deps.createSubgroup).not.toHaveBeenCalled();
    });

    it('non-member is denied → 404', async () => {
      const team = mockTeam();
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue(null),
        findGroupById: jest.fn().mockResolvedValue(team),
      });
      const handlers = createSubgroupsHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { id: teamId },
        body: { name: 'Engineering' },
      });

      await handlers.create(req, res);

      expect(status).toHaveBeenCalledWith(404);
      expect(json).toHaveBeenCalledWith({ error: 'Team not found' });
    });

    it('returns 400 when name is missing', async () => {
      const team = mockTeam();
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('owner'),
        findGroupById: jest.fn().mockResolvedValue(team),
      });
      const handlers = createSubgroupsHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { id: teamId },
        body: {},
      });

      await handlers.create(req, res);

      expect(status).toHaveBeenCalledWith(400);
      expect(json).toHaveBeenCalledWith({ error: 'name is required' });
    });

    it('returns 400 when name is whitespace-only', async () => {
      const team = mockTeam();
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('owner'),
        findGroupById: jest.fn().mockResolvedValue(team),
      });
      const handlers = createSubgroupsHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { id: teamId },
        body: { name: '   ' },
      });

      await handlers.create(req, res);

      expect(status).toHaveBeenCalledWith(400);
      expect(json).toHaveBeenCalledWith({ error: 'name is required' });
    });

    it('returns 400 for invalid team ID format', async () => {
      const deps = createDeps();
      const handlers = createSubgroupsHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { id: 'bad-id' },
        body: { name: 'Engineering' },
      });

      await handlers.create(req, res);

      expect(status).toHaveBeenCalledWith(400);
      expect(json).toHaveBeenCalledWith({ error: 'Invalid team ID format' });
    });

    it('returns 500 on unexpected error', async () => {
      const team = mockTeam();
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('owner'),
        findGroupById: jest.fn().mockResolvedValue(team),
        createSubgroup: jest.fn().mockRejectedValue(new Error('db crash')),
      });
      const handlers = createSubgroupsHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { id: teamId },
        body: { name: 'Engineering' },
      });

      await handlers.create(req, res);

      expect(status).toHaveBeenCalledWith(500);
      expect(json).toHaveBeenCalledWith({ error: 'Failed to create sub-group' });
    });

    it('returns 403 when maxSubgroupsPerTeam limit is reached', async () => {
      const team = mockTeam();
      const existingSg = mockSubgroup({ name: 'Existing' });
      const getTeamSubgroups = jest.fn().mockResolvedValue([existingSg]);
      const createSubgroup = jest.fn();
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('owner'),
        findGroupById: jest.fn().mockResolvedValue(team),
        getTeamSubgroups,
        createSubgroup,
      });
      const handlers = createSubgroupsHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { id: teamId },
        body: { name: 'Second' },
      });
      (req as unknown as Record<string, unknown>).config = {
        config: { teams: { maxSubgroupsPerTeam: 1 } },
      };

      await handlers.create(req, res);

      expect(status).toHaveBeenCalledWith(403);
      expect(json).toHaveBeenCalledWith({ error: 'Sub-group limit reached' });
      expect(createSubgroup).not.toHaveBeenCalled();
    });

    it('allows creation when maxSubgroupsPerTeam is unset (unlimited)', async () => {
      const team = mockTeam();
      const existingSg = mockSubgroup({ name: 'Existing' });
      const getTeamSubgroups = jest.fn().mockResolvedValue([existingSg]);
      const sg = mockSubgroup({ name: 'Second' });
      const createSubgroup = jest.fn().mockResolvedValue(sg);
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('owner'),
        findGroupById: jest.fn().mockResolvedValue(team),
        getTeamSubgroups,
        createSubgroup,
      });
      const handlers = createSubgroupsHandlers(deps);
      const { req, res, status } = createReqRes({
        params: { id: teamId },
        body: { name: 'Second' },
      });

      await handlers.create(req, res);

      expect(status).toHaveBeenCalledWith(201);
      expect(createSubgroup).toHaveBeenCalled();
    });
  });

  describe('list', () => {
    it('returns sub-groups with memberCount for admin', async () => {
      const team = mockTeam();
      const sg1 = mockSubgroup({ memberIds: [callerId, memberId] });
      const sg2 = mockSubgroup({ _id: new Types.ObjectId(), name: 'Design', memberIds: [] });
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('admin'),
        findGroupById: jest.fn().mockResolvedValue(team),
        getTeamSubgroups: jest.fn().mockResolvedValue([sg1, sg2]),
      });
      const handlers = createSubgroupsHandlers(deps);
      const { req, res, status, json } = createReqRes({ params: { id: teamId } });

      await handlers.list(req, res);

      expect(status).toHaveBeenCalledWith(200);
      const { subgroups } = json.mock.calls[0][0];
      expect(Array.isArray(subgroups)).toBe(true);
      expect(subgroups).toHaveLength(2);
      expect(subgroups[0].memberCount).toBe(2);
      expect(subgroups[1].memberCount).toBe(0);
    });

    it('returns 403 for plain member', async () => {
      const team = mockTeam();
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('member'),
        findGroupById: jest.fn().mockResolvedValue(team),
      });
      const handlers = createSubgroupsHandlers(deps);
      const { req, res, status, json } = createReqRes({ params: { id: teamId } });

      await handlers.list(req, res);

      expect(status).toHaveBeenCalledWith(403);
      expect(json).toHaveBeenCalledWith({ error: 'Forbidden' });
    });

    it('returns 400 for invalid team ID', async () => {
      const deps = createDeps();
      const handlers = createSubgroupsHandlers(deps);
      const { req, res, status, json } = createReqRes({ params: { id: 'bad' } });

      await handlers.list(req, res);

      expect(status).toHaveBeenCalledWith(400);
      expect(json).toHaveBeenCalledWith({ error: 'Invalid team ID format' });
    });

    it('returns 500 on error', async () => {
      const team = mockTeam();
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('owner'),
        findGroupById: jest.fn().mockResolvedValue(team),
        getTeamSubgroups: jest.fn().mockRejectedValue(new Error('db down')),
      });
      const handlers = createSubgroupsHandlers(deps);
      const { req, res, status, json } = createReqRes({ params: { id: teamId } });

      await handlers.list(req, res);

      expect(status).toHaveBeenCalledWith(500);
      expect(json).toHaveBeenCalledWith({ error: 'Failed to list sub-groups' });
    });
  });

  describe('get', () => {
    it('returns sub-group detail for admin with enriched member name and email', async () => {
      const team = mockTeam();
      const memberObjId = new Types.ObjectId(callerId);
      const sg = mockSubgroup({ memberIds: [callerId], members: [{ userId: memberObjId, role: 'member', joinedAt: new Date() }] });
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('admin'),
        findGroupById: jest.fn().mockResolvedValue(team),
        getSubgroupById: jest.fn().mockResolvedValue(sg),
        findUsers: jest.fn().mockResolvedValue([
          { _id: memberObjId, name: 'Alice', email: 'alice@example.com' },
        ]),
      });
      const handlers = createSubgroupsHandlers(deps);
      const { req, res, status, json } = createReqRes({ params: { id: teamId, sgId } });

      await handlers.get(req, res);

      expect(status).toHaveBeenCalledWith(200);
      const body = json.mock.calls[0][0];
      expect(body.subgroup).toBeDefined();
      expect(Array.isArray(body.members)).toBe(true);
      expect(body.members[0].name).toBe('Alice');
      expect(body.members[0].email).toBe('alice@example.com');
    });

    it('returns 404 when sgId belongs to a different team (cross-team guard)', async () => {
      const team = mockTeam();
      const otherTeamId = new Types.ObjectId().toString();
      // Sub-group whose parentTeamId does NOT match the :id param
      const sg = mockSubgroup({ parentTeamId: new Types.ObjectId(otherTeamId) });
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('admin'),
        findGroupById: jest.fn().mockResolvedValue(team),
        getSubgroupById: jest.fn().mockResolvedValue(sg),
      });
      const handlers = createSubgroupsHandlers(deps);
      const { req, res, status, json } = createReqRes({ params: { id: teamId, sgId } });

      await handlers.get(req, res);

      expect(status).toHaveBeenCalledWith(404);
      expect(json).toHaveBeenCalledWith({ error: 'Sub-group not found' });
    });

    it('returns 404 when sub-group does not exist', async () => {
      const team = mockTeam();
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('admin'),
        findGroupById: jest.fn().mockResolvedValue(team),
        getSubgroupById: jest.fn().mockResolvedValue(null),
      });
      const handlers = createSubgroupsHandlers(deps);
      const { req, res, status, json } = createReqRes({ params: { id: teamId, sgId } });

      await handlers.get(req, res);

      expect(status).toHaveBeenCalledWith(404);
      expect(json).toHaveBeenCalledWith({ error: 'Sub-group not found' });
    });

    it('returns 400 for invalid sgId', async () => {
      const team = mockTeam();
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('admin'),
        findGroupById: jest.fn().mockResolvedValue(team),
      });
      const handlers = createSubgroupsHandlers(deps);
      const { req, res, status, json } = createReqRes({ params: { id: teamId, sgId: 'bad-id' } });

      await handlers.get(req, res);

      expect(status).toHaveBeenCalledWith(400);
      expect(json).toHaveBeenCalledWith({ error: 'Invalid sub-group ID format' });
    });
  });

  describe('update', () => {
    it('updates a sub-group and returns 200 for admin', async () => {
      const team = mockTeam();
      const sg = mockSubgroup();
      const updated = mockSubgroup({ name: 'Renamed' });
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('admin'),
        findGroupById: jest.fn().mockResolvedValue(team),
        getSubgroupById: jest.fn().mockResolvedValue(sg),
        updateSubgroup: jest.fn().mockResolvedValue(updated),
      });
      const handlers = createSubgroupsHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { id: teamId, sgId },
        body: { name: 'Renamed' },
      });

      await handlers.update(req, res);

      expect(status).toHaveBeenCalledWith(200);
      const body = json.mock.calls[0][0];
      expect(body.subgroup.name).toBe('Renamed');
    });

    it('returns 400 when no valid fields provided', async () => {
      const team = mockTeam();
      const sg = mockSubgroup();
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('admin'),
        findGroupById: jest.fn().mockResolvedValue(team),
        getSubgroupById: jest.fn().mockResolvedValue(sg),
      });
      const handlers = createSubgroupsHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { id: teamId, sgId },
        body: {},
      });

      await handlers.update(req, res);

      expect(status).toHaveBeenCalledWith(400);
      expect(json).toHaveBeenCalledWith({ error: 'No valid fields to update' });
    });

    it('returns 400 when name is whitespace-only', async () => {
      const team = mockTeam();
      const sg = mockSubgroup();
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('admin'),
        findGroupById: jest.fn().mockResolvedValue(team),
        getSubgroupById: jest.fn().mockResolvedValue(sg),
      });
      const handlers = createSubgroupsHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { id: teamId, sgId },
        body: { name: '   ' },
      });

      await handlers.update(req, res);

      expect(status).toHaveBeenCalledWith(400);
      expect(json).toHaveBeenCalledWith({ error: 'name cannot be empty' });
      expect(deps.updateSubgroup).not.toHaveBeenCalled();
    });

    it('returns 403 for plain member', async () => {
      const team = mockTeam();
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('member'),
        findGroupById: jest.fn().mockResolvedValue(team),
      });
      const handlers = createSubgroupsHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { id: teamId, sgId },
        body: { name: 'X' },
      });

      await handlers.update(req, res);

      expect(status).toHaveBeenCalledWith(403);
      expect(json).toHaveBeenCalledWith({ error: 'Forbidden' });
    });

    it('cross-team guard: returns 404 if sgId belongs to another team', async () => {
      const team = mockTeam();
      const otherTeamId = new Types.ObjectId().toString();
      const sg = mockSubgroup({ parentTeamId: new Types.ObjectId(otherTeamId) });
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('admin'),
        findGroupById: jest.fn().mockResolvedValue(team),
        getSubgroupById: jest.fn().mockResolvedValue(sg),
      });
      const handlers = createSubgroupsHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { id: teamId, sgId },
        body: { name: 'X' },
      });

      await handlers.update(req, res);

      expect(status).toHaveBeenCalledWith(404);
      expect(json).toHaveBeenCalledWith({ error: 'Sub-group not found' });
    });
  });

  describe('remove', () => {
    it('deletes the sub-group, calls deleteAclEntries first, returns 200 for owner', async () => {
      const team = mockTeam();
      const sg = mockSubgroup();
      const deleteAclEntries = jest.fn().mockResolvedValue({ deletedCount: 0 });
      const deleteSubgroup = jest.fn().mockResolvedValue(undefined);
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('owner'),
        findGroupById: jest.fn().mockResolvedValue(team),
        getSubgroupById: jest.fn().mockResolvedValue(sg),
        deleteAclEntries,
        deleteSubgroup,
      });
      const handlers = createSubgroupsHandlers(deps);
      const { req, res, status, json } = createReqRes({ params: { id: teamId, sgId } });

      await handlers.remove(req, res);

      expect(deleteAclEntries).toHaveBeenCalledWith({ principalId: sg._id });
      expect(deleteSubgroup).toHaveBeenCalledWith(sg._id);
      expect(status).toHaveBeenCalledWith(200);
      expect(json).toHaveBeenCalledWith({ success: true });
    });

    it('deleteAclEntries is called BEFORE deleteSubgroup', async () => {
      const team = mockTeam();
      const sg = mockSubgroup();
      const callOrder: string[] = [];
      const deleteAclEntries = jest.fn().mockImplementation(async () => { callOrder.push('deleteAclEntries'); return { deletedCount: 0 }; });
      const deleteSubgroup = jest.fn().mockImplementation(async () => { callOrder.push('deleteSubgroup'); });
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('owner'),
        findGroupById: jest.fn().mockResolvedValue(team),
        getSubgroupById: jest.fn().mockResolvedValue(sg),
        deleteAclEntries,
        deleteSubgroup,
      });
      const handlers = createSubgroupsHandlers(deps);
      const { req, res } = createReqRes({ params: { id: teamId, sgId } });

      await handlers.remove(req, res);

      expect(callOrder).toEqual(['deleteAclEntries', 'deleteSubgroup']);
    });

    it('returns 403 for plain member', async () => {
      const team = mockTeam();
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('member'),
        findGroupById: jest.fn().mockResolvedValue(team),
      });
      const handlers = createSubgroupsHandlers(deps);
      const { req, res, status, json } = createReqRes({ params: { id: teamId, sgId } });

      await handlers.remove(req, res);

      expect(status).toHaveBeenCalledWith(403);
      expect(json).toHaveBeenCalledWith({ error: 'Forbidden' });
      expect(deps.deleteAclEntries).not.toHaveBeenCalled();
      expect(deps.deleteSubgroup).not.toHaveBeenCalled();
    });

    it('cross-team guard: returns 404 if sgId belongs to another team', async () => {
      const team = mockTeam();
      const otherTeamId = new Types.ObjectId().toString();
      const sg = mockSubgroup({ parentTeamId: new Types.ObjectId(otherTeamId) });
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('admin'),
        findGroupById: jest.fn().mockResolvedValue(team),
        getSubgroupById: jest.fn().mockResolvedValue(sg),
      });
      const handlers = createSubgroupsHandlers(deps);
      const { req, res, status, json } = createReqRes({ params: { id: teamId, sgId } });

      await handlers.remove(req, res);

      expect(status).toHaveBeenCalledWith(404);
      expect(json).toHaveBeenCalledWith({ error: 'Sub-group not found' });
      expect(deps.deleteAclEntries).not.toHaveBeenCalled();
      expect(deps.deleteSubgroup).not.toHaveBeenCalled();
    });

    it('returns 500 on unexpected error', async () => {
      const team = mockTeam();
      const sg = mockSubgroup();
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('owner'),
        findGroupById: jest.fn().mockResolvedValue(team),
        getSubgroupById: jest.fn().mockResolvedValue(sg),
        deleteAclEntries: jest.fn().mockRejectedValue(new Error('db down')),
      });
      const handlers = createSubgroupsHandlers(deps);
      const { req, res, status, json } = createReqRes({ params: { id: teamId, sgId } });

      await handlers.remove(req, res);

      expect(status).toHaveBeenCalledWith(500);
      expect(json).toHaveBeenCalledWith({ error: 'Failed to delete sub-group' });
    });
  });

  describe('addMember', () => {
    it('adds a team member to the sub-group → 200', async () => {
      const team = mockTeam({ memberIds: [callerId, memberId] });
      const sg = mockSubgroup({ memberIds: [] });
      const updated = mockSubgroup({ memberIds: [memberId], members: [{ userId: new Types.ObjectId(memberId), role: 'member', joinedAt: new Date() }] });
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('admin'),
        findGroupById: jest.fn().mockResolvedValue(team),
        getSubgroupById: jest.fn().mockResolvedValue(sg),
        addSubgroupMember: jest.fn().mockResolvedValue(updated),
      });
      const handlers = createSubgroupsHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { id: teamId, sgId },
        body: { userId: memberId },
      });

      await handlers.addMember(req, res);

      expect(status).toHaveBeenCalledWith(200);
      const body = json.mock.calls[0][0];
      expect(body.subgroup).toBeDefined();
      expect(body.subgroup.memberCount).toBe(1);
    });

    it('rejects a non-team-member → 400 (team-subset invariant)', async () => {
      const team = mockTeam({ memberIds: [callerId] }); // memberId NOT in team
      const sg = mockSubgroup();
      const nonMemberId = new Types.ObjectId().toString();
      const invariantError = new Error('User is not a member of the team');
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('admin'),
        findGroupById: jest.fn().mockResolvedValue(team),
        getSubgroupById: jest.fn().mockResolvedValue(sg),
        addSubgroupMember: jest.fn().mockRejectedValue(invariantError),
      });
      const handlers = createSubgroupsHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { id: teamId, sgId },
        body: { userId: nonMemberId },
      });

      await handlers.addMember(req, res);

      expect(status).toHaveBeenCalledWith(400);
      expect(json).toHaveBeenCalledWith({ error: 'User is not a member of the team' });
    });

    it('returns 400 when userId is missing', async () => {
      const team = mockTeam();
      const sg = mockSubgroup();
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('admin'),
        findGroupById: jest.fn().mockResolvedValue(team),
        getSubgroupById: jest.fn().mockResolvedValue(sg),
      });
      const handlers = createSubgroupsHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { id: teamId, sgId },
        body: {},
      });

      await handlers.addMember(req, res);

      expect(status).toHaveBeenCalledWith(400);
      expect(json).toHaveBeenCalledWith({ error: 'userId is required' });
    });

    it('returns 403 for plain member', async () => {
      const team = mockTeam();
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('member'),
        findGroupById: jest.fn().mockResolvedValue(team),
      });
      const handlers = createSubgroupsHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { id: teamId, sgId },
        body: { userId: memberId },
      });

      await handlers.addMember(req, res);

      expect(status).toHaveBeenCalledWith(403);
      expect(json).toHaveBeenCalledWith({ error: 'Forbidden' });
    });

    it('cross-team guard: returns 404 if sgId belongs to another team', async () => {
      const team = mockTeam();
      const otherTeamId = new Types.ObjectId().toString();
      const sg = mockSubgroup({ parentTeamId: new Types.ObjectId(otherTeamId) });
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('admin'),
        findGroupById: jest.fn().mockResolvedValue(team),
        getSubgroupById: jest.fn().mockResolvedValue(sg),
      });
      const handlers = createSubgroupsHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { id: teamId, sgId },
        body: { userId: memberId },
      });

      await handlers.addMember(req, res);

      expect(status).toHaveBeenCalledWith(404);
      expect(json).toHaveBeenCalledWith({ error: 'Sub-group not found' });
    });

    it('returns 500 on unexpected error', async () => {
      const team = mockTeam();
      const sg = mockSubgroup();
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('admin'),
        findGroupById: jest.fn().mockResolvedValue(team),
        getSubgroupById: jest.fn().mockResolvedValue(sg),
        addSubgroupMember: jest.fn().mockRejectedValue(new Error('db down')),
      });
      const handlers = createSubgroupsHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { id: teamId, sgId },
        body: { userId: memberId },
      });

      await handlers.addMember(req, res);

      expect(status).toHaveBeenCalledWith(500);
      expect(json).toHaveBeenCalledWith({ error: 'Failed to add sub-group member' });
    });
  });

  describe('removeMember', () => {
    it('removes a member from the sub-group → 200', async () => {
      const team = mockTeam();
      const sg = mockSubgroup({ memberIds: [memberId], members: [{ userId: new Types.ObjectId(memberId), role: 'member', joinedAt: new Date() }] });
      const updated = mockSubgroup({ memberIds: [], members: [] });
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('admin'),
        findGroupById: jest.fn().mockResolvedValue(team),
        getSubgroupById: jest.fn().mockResolvedValue(sg),
        removeSubgroupMember: jest.fn().mockResolvedValue(updated),
      });
      const handlers = createSubgroupsHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { id: teamId, sgId, userId: memberId },
      });

      await handlers.removeMember(req, res);

      expect(status).toHaveBeenCalledWith(200);
      const body = json.mock.calls[0][0];
      expect(body.subgroup.memberCount).toBe(0);
    });

    it('returns 403 for plain member', async () => {
      const team = mockTeam();
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('member'),
        findGroupById: jest.fn().mockResolvedValue(team),
      });
      const handlers = createSubgroupsHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { id: teamId, sgId, userId: memberId },
      });

      await handlers.removeMember(req, res);

      expect(status).toHaveBeenCalledWith(403);
      expect(json).toHaveBeenCalledWith({ error: 'Forbidden' });
    });

    it('cross-team guard: returns 404 if sgId belongs to another team', async () => {
      const team = mockTeam();
      const otherTeamId = new Types.ObjectId().toString();
      const sg = mockSubgroup({ parentTeamId: new Types.ObjectId(otherTeamId) });
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('admin'),
        findGroupById: jest.fn().mockResolvedValue(team),
        getSubgroupById: jest.fn().mockResolvedValue(sg),
      });
      const handlers = createSubgroupsHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { id: teamId, sgId, userId: memberId },
      });

      await handlers.removeMember(req, res);

      expect(status).toHaveBeenCalledWith(404);
      expect(json).toHaveBeenCalledWith({ error: 'Sub-group not found' });
    });

    it('returns 500 on unexpected error', async () => {
      const team = mockTeam();
      const sg = mockSubgroup({ memberIds: [memberId] });
      const deps = createDeps({
        getTeamRole: jest.fn().mockResolvedValue('admin'),
        findGroupById: jest.fn().mockResolvedValue(team),
        getSubgroupById: jest.fn().mockResolvedValue(sg),
        removeSubgroupMember: jest.fn().mockRejectedValue(new Error('db down')),
      });
      const handlers = createSubgroupsHandlers(deps);
      const { req, res, status, json } = createReqRes({
        params: { id: teamId, sgId, userId: memberId },
      });

      await handlers.removeMember(req, res);

      expect(status).toHaveBeenCalledWith(500);
      expect(json).toHaveBeenCalledWith({ error: 'Failed to remove sub-group member' });
    });
  });
});
