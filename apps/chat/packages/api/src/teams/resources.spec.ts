import { Types } from 'mongoose';
import { ResourceType, AccessRoleIds, PrincipalType, PermissionBits } from 'librechat-data-provider';
import { createTeamResourceHandlers } from './resources';
import type { TeamResourceHandlersDeps } from './resources';
import type { IAgent, IPromptGroupDocument, TeamRole } from '@librechat/data-schemas';

function makeId() {
  return new Types.ObjectId().toString();
}

function makeObjectId() {
  return new Types.ObjectId();
}

function makeTeamId() {
  return new Types.ObjectId().toString();
}

function makeAgent(overrides: Partial<IAgent> = {}): IAgent {
  const _id = makeObjectId();
  return {
    _id,
    id: `agent_${_id.toString()}`,
    name: 'Test Agent',
    description: 'A test agent',
    provider: 'openai',
    model: 'gpt-4',
    author: makeObjectId(),
    category: 'general',
    ...overrides,
  } as unknown as IAgent;
}

function makePromptGroup(overrides: Partial<IPromptGroupDocument> = {}): IPromptGroupDocument {
  const _id = makeObjectId();
  return {
    _id,
    name: 'Test Prompt Group',
    numberOfGenerations: 0,
    oneliner: '',
    category: 'general',
    productionId: makeObjectId(),
    author: makeObjectId(),
    authorName: 'Test Author',
    ...overrides,
  } as unknown as IPromptGroupDocument;
}

function makeAclEntry(resourceId: Types.ObjectId, resourceType: string) {
  return {
    _id: makeObjectId(),
    principalType: PrincipalType.GROUP,
    principalId: makeObjectId(),
    resourceType,
    resourceId,
    accessRoleId: AccessRoleIds.AGENT_VIEWER,
    permBits: PermissionBits.VIEW,
  };
}

function makeDeps(overrides: Partial<TeamResourceHandlersDeps> = {}): TeamResourceHandlersDeps {
  return {
    getTeamRole: jest.fn().mockResolvedValue('admin' as TeamRole),
    findGroupById: jest.fn().mockResolvedValue({ _id: makeObjectId(), kind: 'team' }),
    getAgent: jest.fn().mockResolvedValue(null),
    getPromptGroup: jest.fn().mockResolvedValue(null),
    findEntriesByPrincipal: jest.fn().mockResolvedValue([]),
    revokePermission: jest.fn().mockResolvedValue({ deletedCount: 1 }),
    grantPermission: jest.fn().mockResolvedValue({}),
    checkPermission: jest.fn().mockResolvedValue(true),
    ...overrides,
  };
}

function makeReq(params: Record<string, string> = {}, user = { id: makeId(), role: 'USER' }) {
  return {
    params,
    user,
    body: {},
  };
}

function makeRes() {
  const res = {
    status: jest.fn().mockReturnThis(),
    json: jest.fn().mockReturnThis(),
  };
  return res;
}

describe('createTeamResourceHandlers', () => {
  const teamId = makeTeamId();

  describe('shareAgent', () => {
    it('returns 201 on happy path — grant is called with correct args', async () => {
      const agent = makeAgent();
      const deps = makeDeps({ getAgent: jest.fn().mockResolvedValue(agent) });
      const { shareAgent } = createTeamResourceHandlers(deps);

      const req = makeReq({ id: teamId, agentId: agent.id });
      const res = makeRes();

      await shareAgent(req as never, res as never);

      expect(res.status).toHaveBeenCalledWith(201);
      expect(res.json).toHaveBeenCalledWith(
        expect.objectContaining({ success: true, id: agent.id }),
      );
      expect(deps.grantPermission).toHaveBeenCalledWith(
        expect.objectContaining({
          principalType: PrincipalType.GROUP,
          principalId: teamId,
          resourceType: ResourceType.AGENT,
          resourceId: agent._id,
          accessRoleId: AccessRoleIds.AGENT_VIEWER,
        }),
      );
    });

    it('returns 404 when caller is not a team member', async () => {
      const agent = makeAgent();
      const deps = makeDeps({
        getAgent: jest.fn().mockResolvedValue(agent),
        getTeamRole: jest.fn().mockResolvedValue(null),
      });
      const { shareAgent } = createTeamResourceHandlers(deps);

      const req = makeReq({ id: teamId, agentId: agent.id });
      const res = makeRes();

      await shareAgent(req as never, res as never);

      expect(res.status).toHaveBeenCalledWith(404);
      expect(deps.grantPermission).not.toHaveBeenCalled();
    });

    it('returns 403 when caller is a member but not an admin', async () => {
      const agent = makeAgent();
      const deps = makeDeps({
        getAgent: jest.fn().mockResolvedValue(agent),
        getTeamRole: jest.fn().mockResolvedValue('member' as TeamRole),
      });
      const { shareAgent } = createTeamResourceHandlers(deps);

      const req = makeReq({ id: teamId, agentId: agent.id });
      const res = makeRes();

      await shareAgent(req as never, res as never);

      expect(res.status).toHaveBeenCalledWith(403);
      expect(deps.grantPermission).not.toHaveBeenCalled();
    });

    it('returns 403 when caller lacks SHARE permission on the agent', async () => {
      const agent = makeAgent();
      const deps = makeDeps({
        getAgent: jest.fn().mockResolvedValue(agent),
        checkPermission: jest.fn().mockResolvedValue(false),
      });
      const { shareAgent } = createTeamResourceHandlers(deps);

      const req = makeReq({ id: teamId, agentId: agent.id });
      const res = makeRes();

      await shareAgent(req as never, res as never);

      expect(res.status).toHaveBeenCalledWith(403);
      expect(deps.grantPermission).not.toHaveBeenCalled();
    });

    it('returns 404 when agent does not exist', async () => {
      const deps = makeDeps({ getAgent: jest.fn().mockResolvedValue(null) });
      const { shareAgent } = createTeamResourceHandlers(deps);

      const req = makeReq({ id: teamId, agentId: 'agent_nonexistent' });
      const res = makeRes();

      await shareAgent(req as never, res as never);

      expect(res.status).toHaveBeenCalledWith(404);
    });
  });

  describe('revokeAgent', () => {
    it('returns 200 and calls revokePermission scoped to team + agent _id', async () => {
      const agent = makeAgent();
      const deps = makeDeps({ getAgent: jest.fn().mockResolvedValue(agent) });
      const { revokeAgent } = createTeamResourceHandlers(deps);

      const req = makeReq({ id: teamId, agentId: agent.id });
      const res = makeRes();

      await revokeAgent(req as never, res as never);

      expect(res.status).toHaveBeenCalledWith(200);
      expect(deps.revokePermission).toHaveBeenCalledWith(
        PrincipalType.GROUP,
        teamId,
        ResourceType.AGENT,
        agent._id,
      );
    });

    it('returns 404 for non-member', async () => {
      const agent = makeAgent();
      const deps = makeDeps({
        getAgent: jest.fn().mockResolvedValue(agent),
        getTeamRole: jest.fn().mockResolvedValue(null),
      });
      const { revokeAgent } = createTeamResourceHandlers(deps);

      const req = makeReq({ id: teamId, agentId: agent.id });
      const res = makeRes();

      await revokeAgent(req as never, res as never);

      expect(res.status).toHaveBeenCalledWith(404);
      expect(deps.revokePermission).not.toHaveBeenCalled();
    });

    it('returns 404 when agent does not exist', async () => {
      const deps = makeDeps({ getAgent: jest.fn().mockResolvedValue(null) });
      const { revokeAgent } = createTeamResourceHandlers(deps);

      const req = makeReq({ id: teamId, agentId: 'agent_nonexistent' });
      const res = makeRes();

      await revokeAgent(req as never, res as never);

      expect(res.status).toHaveBeenCalledWith(404);
    });
  });

  describe('listAgents', () => {
    it('returns 200 with empty array when no agents are shared', async () => {
      const deps = makeDeps({
        getTeamRole: jest.fn().mockResolvedValue('member' as TeamRole),
        findEntriesByPrincipal: jest.fn().mockResolvedValue([]),
      });
      const { listAgents } = createTeamResourceHandlers(deps);

      const req = makeReq({ id: teamId });
      const res = makeRes();

      await listAgents(req as never, res as never);

      expect(res.status).toHaveBeenCalledWith(200);
      expect(res.json).toHaveBeenCalledWith({ resources: [] });
    });

    it('returns 200 with resolved agents from ACL entries (member-gated)', async () => {
      const agent = makeAgent();
      const entry = makeAclEntry(agent._id as Types.ObjectId, ResourceType.AGENT);
      const deps = makeDeps({
        getTeamRole: jest.fn().mockResolvedValue('member' as TeamRole),
        findEntriesByPrincipal: jest.fn().mockResolvedValue([entry]),
        getAgent: jest.fn().mockResolvedValue(agent),
      });
      const { listAgents } = createTeamResourceHandlers(deps);

      const req = makeReq({ id: teamId });
      const res = makeRes();

      await listAgents(req as never, res as never);

      expect(res.status).toHaveBeenCalledWith(200);
      expect(res.json).toHaveBeenCalledWith(
        expect.objectContaining({
          resources: expect.arrayContaining([
            expect.objectContaining({ id: agent.id, name: agent.name }),
          ]),
        }),
      );
    });

    it('returns 404 when caller is not a team member', async () => {
      const deps = makeDeps({ getTeamRole: jest.fn().mockResolvedValue(null) });
      const { listAgents } = createTeamResourceHandlers(deps);

      const req = makeReq({ id: teamId });
      const res = makeRes();

      await listAgents(req as never, res as never);

      expect(res.status).toHaveBeenCalledWith(404);
    });
  });

  describe('sharePromptGroup', () => {
    it('returns 201 on happy path — grant called with PROMPTGROUP resourceType', async () => {
      const pg = makePromptGroup();
      const deps = makeDeps({ getPromptGroup: jest.fn().mockResolvedValue(pg) });
      const { sharePromptGroup } = createTeamResourceHandlers(deps);

      const req = makeReq({ id: teamId, promptGroupId: pg._id.toString() });
      const res = makeRes();

      await sharePromptGroup(req as never, res as never);

      expect(res.status).toHaveBeenCalledWith(201);
      expect(deps.grantPermission).toHaveBeenCalledWith(
        expect.objectContaining({
          resourceType: ResourceType.PROMPTGROUP,
          accessRoleId: AccessRoleIds.PROMPTGROUP_VIEWER,
        }),
      );
    });

    it('returns 404 when prompt group does not exist', async () => {
      const deps = makeDeps({ getPromptGroup: jest.fn().mockResolvedValue(null) });
      const { sharePromptGroup } = createTeamResourceHandlers(deps);

      const req = makeReq({ id: teamId, promptGroupId: new Types.ObjectId().toString() });
      const res = makeRes();

      await sharePromptGroup(req as never, res as never);

      expect(res.status).toHaveBeenCalledWith(404);
    });

    it('returns 403 when caller lacks SHARE permission on the prompt group', async () => {
      const pg = makePromptGroup();
      const deps = makeDeps({
        getPromptGroup: jest.fn().mockResolvedValue(pg),
        checkPermission: jest.fn().mockResolvedValue(false),
      });
      const { sharePromptGroup } = createTeamResourceHandlers(deps);

      const req = makeReq({ id: teamId, promptGroupId: pg._id.toString() });
      const res = makeRes();

      await sharePromptGroup(req as never, res as never);

      expect(res.status).toHaveBeenCalledWith(403);
      expect(deps.grantPermission).not.toHaveBeenCalled();
    });

    it('returns 400 for invalid promptGroupId (non-ObjectId string)', async () => {
      const deps = makeDeps();
      const { sharePromptGroup } = createTeamResourceHandlers(deps);

      const req = makeReq({ id: teamId, promptGroupId: 'not-a-valid-objectid' });
      const res = makeRes();

      await sharePromptGroup(req as never, res as never);

      expect(res.status).toHaveBeenCalledWith(404);
      expect(deps.grantPermission).not.toHaveBeenCalled();
    });
  });

  describe('listPromptGroups', () => {
    it('returns 200 with empty array when no prompt groups shared', async () => {
      const deps = makeDeps({
        getTeamRole: jest.fn().mockResolvedValue('member' as TeamRole),
        findEntriesByPrincipal: jest.fn().mockResolvedValue([]),
      });
      const { listPromptGroups } = createTeamResourceHandlers(deps);

      const req = makeReq({ id: teamId });
      const res = makeRes();

      await listPromptGroups(req as never, res as never);

      expect(res.status).toHaveBeenCalledWith(200);
      expect(res.json).toHaveBeenCalledWith({ resources: [] });
    });

    it('returns 200 with resolved prompt groups', async () => {
      const pg = makePromptGroup();
      const entry = makeAclEntry(pg._id as Types.ObjectId, ResourceType.PROMPTGROUP);
      const deps = makeDeps({
        getTeamRole: jest.fn().mockResolvedValue('member' as TeamRole),
        findEntriesByPrincipal: jest.fn().mockResolvedValue([entry]),
        getPromptGroup: jest.fn().mockResolvedValue(pg),
      });
      const { listPromptGroups } = createTeamResourceHandlers(deps);

      const req = makeReq({ id: teamId });
      const res = makeRes();

      await listPromptGroups(req as never, res as never);

      expect(res.status).toHaveBeenCalledWith(200);
      expect(res.json).toHaveBeenCalledWith(
        expect.objectContaining({
          resources: expect.arrayContaining([
            expect.objectContaining({ id: pg._id.toString(), name: pg.name }),
          ]),
        }),
      );
    });
  });

  describe('revokePromptGroup', () => {
    it('returns 200 and calls revokePermission with correct args', async () => {
      const pg = makePromptGroup();
      const deps = makeDeps({ getPromptGroup: jest.fn().mockResolvedValue(pg) });
      const { revokePromptGroup } = createTeamResourceHandlers(deps);

      const req = makeReq({ id: teamId, promptGroupId: pg._id.toString() });
      const res = makeRes();

      await revokePromptGroup(req as never, res as never);

      expect(res.status).toHaveBeenCalledWith(200);
      expect(deps.revokePermission).toHaveBeenCalledWith(
        PrincipalType.GROUP,
        teamId,
        ResourceType.PROMPTGROUP,
        pg._id,
      );
    });
  });
});
