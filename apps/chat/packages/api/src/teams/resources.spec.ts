import { Types } from 'mongoose';
import { ResourceType, AccessRoleIds, PrincipalType, PermissionBits } from 'librechat-data-provider';
import { createTeamResourceHandlers } from './resources';
import type { TeamResourceHandlersDeps } from './resources';
import type { IAgent, IAclEntry, IGroup, IPromptGroupDocument, TeamRole } from '@librechat/data-schemas';

type ResourceTarget =
  | { type: 'team' }
  | { type: 'subgroup'; id: string; name: string };

function makeSubgroup(id: string, parentTeamId: string): IGroup {
  return {
    _id: new Types.ObjectId(id),
    name: 'Sub-group Beta',
    kind: 'team_subgroup',
    parentTeamId: new Types.ObjectId(parentTeamId),
    members: [],
    memberIds: [],
  } as unknown as IGroup;
}

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
    getSubgroupById: jest.fn().mockResolvedValue(null),
    getTeamSubgroups: jest.fn().mockResolvedValue([]),
    getUserTeamPrincipals: jest.fn().mockResolvedValue([]),
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

    it('grants to sub-group principal when valid targetSubgroupId in body', async () => {
      const sgId = makeId();
      const agent = makeAgent();
      const subgroup = makeSubgroup(sgId, teamId);
      const deps = makeDeps({
        getAgent: jest.fn().mockResolvedValue(agent),
        getSubgroupById: jest.fn().mockResolvedValue(subgroup),
      });
      const { shareAgent } = createTeamResourceHandlers(deps);

      const req = { ...makeReq({ id: teamId, agentId: agent.id }), body: { targetSubgroupId: sgId } };
      const res = makeRes();

      await shareAgent(req as never, res as never);

      expect(res.status).toHaveBeenCalledWith(201);
      expect(deps.grantPermission).toHaveBeenCalledWith(
        expect.objectContaining({ principalId: sgId }),
      );
    });

    it('returns 404 when targetSubgroupId in body belongs to a different team', async () => {
      const sgId = makeId();
      const otherTeamId = makeId();
      const agent = makeAgent();
      const subgroup = makeSubgroup(sgId, otherTeamId);
      const deps = makeDeps({
        getAgent: jest.fn().mockResolvedValue(agent),
        getSubgroupById: jest.fn().mockResolvedValue(subgroup),
      });
      const { shareAgent } = createTeamResourceHandlers(deps);

      const req = { ...makeReq({ id: teamId, agentId: agent.id }), body: { targetSubgroupId: sgId } };
      const res = makeRes();

      await shareAgent(req as never, res as never);

      expect(res.status).toHaveBeenCalledWith(404);
      expect(deps.grantPermission).not.toHaveBeenCalled();
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

    it('revokes from sub-group principal when valid targetSubgroupId in query', async () => {
      const sgId = makeId();
      const agent = makeAgent();
      const subgroup = makeSubgroup(sgId, teamId);
      const deps = makeDeps({
        getAgent: jest.fn().mockResolvedValue(agent),
        getSubgroupById: jest.fn().mockResolvedValue(subgroup),
      });
      const { revokeAgent } = createTeamResourceHandlers(deps);

      const req = { ...makeReq({ id: teamId, agentId: agent.id }), query: { targetSubgroupId: sgId } };
      const res = makeRes();

      await revokeAgent(req as never, res as never);

      expect(res.status).toHaveBeenCalledWith(200);
      expect(deps.revokePermission).toHaveBeenCalledWith(
        PrincipalType.GROUP,
        sgId,
        ResourceType.AGENT,
        agent._id,
      );
    });

    it('returns 404 when targetSubgroupId in query does not belong to this team', async () => {
      const sgId = makeId();
      const otherTeamId = makeId();
      const agent = makeAgent();
      const subgroup = makeSubgroup(sgId, otherTeamId);
      const deps = makeDeps({
        getAgent: jest.fn().mockResolvedValue(agent),
        getSubgroupById: jest.fn().mockResolvedValue(subgroup),
      });
      const { revokeAgent } = createTeamResourceHandlers(deps);

      const req = { ...makeReq({ id: teamId, agentId: agent.id }), query: { targetSubgroupId: sgId } };
      const res = makeRes();

      await revokeAgent(req as never, res as never);

      expect(res.status).toHaveBeenCalledWith(404);
      expect(deps.revokePermission).not.toHaveBeenCalled();
    });
  });

  describe('listAgents', () => {
    it('returns 200 with empty array when no agents are shared', async () => {
      const deps = makeDeps({
        getTeamRole: jest.fn().mockResolvedValue('member' as TeamRole),
        findEntriesByPrincipal: jest.fn().mockResolvedValue([]),
        getUserTeamPrincipals: jest.fn().mockResolvedValue([teamId]),
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
      const teamObjId = new Types.ObjectId(teamId);
      const fullEntry: IAclEntry = {
        ...(entry as IAclEntry),
        principalId: teamObjId,
      };
      const deps = makeDeps({
        getTeamRole: jest.fn().mockResolvedValue('member' as TeamRole),
        getUserTeamPrincipals: jest.fn().mockResolvedValue([teamId]),
        getTeamSubgroups: jest.fn().mockResolvedValue([]),
        findEntriesByPrincipal: jest.fn().mockResolvedValue([fullEntry]),
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

    describe('access matrix — caller-scoped with target annotation', () => {
      const ownerId = makeId();
      const m1Id = makeId();
      const m2Id = makeId();
      const sgAId = makeId();
      const sgBId = makeId();

      function makeSubgroupA(): IGroup {
        return {
          _id: new Types.ObjectId(sgAId),
          name: 'Sub-group A',
          kind: 'team_subgroup',
          parentTeamId: new Types.ObjectId(teamId),
          members: [],
          memberIds: [],
        } as unknown as IGroup;
      }

      function makeSubgroupB(): IGroup {
        return {
          _id: new Types.ObjectId(sgBId),
          name: 'Sub-group B',
          kind: 'team_subgroup',
          parentTeamId: new Types.ObjectId(teamId),
          members: [],
          memberIds: [],
        } as unknown as IGroup;
      }

      function makeAclEntryForPrincipal(
        resourceId: Types.ObjectId,
        principalId: Types.ObjectId,
      ): IAclEntry {
        return {
          _id: makeObjectId(),
          principalType: PrincipalType.GROUP,
          principalId,
          resourceType: ResourceType.AGENT,
          resourceId,
          accessRoleId: AccessRoleIds.AGENT_VIEWER,
          permBits: PermissionBits.VIEW,
        } as unknown as IAclEntry;
      }

      it('m1 (in sub-group A) sees agent-team and agent-A but NOT agent-B', async () => {
        const agentTeam = makeAgent({ name: 'Agent-Team' });
        const agentA = makeAgent({ name: 'Agent-A' });
        const agentB = makeAgent({ name: 'Agent-B' });

        const teamObjId = new Types.ObjectId(teamId);
        const sgAObjId = new Types.ObjectId(sgAId);

        const entryTeam = makeAclEntryForPrincipal(agentTeam._id as Types.ObjectId, teamObjId);
        const entryA = makeAclEntryForPrincipal(agentA._id as Types.ObjectId, sgAObjId);

        const sgA = makeSubgroupA();
        const sgB = makeSubgroupB();

        const agentMap = new Map([
          [agentTeam._id.toString(), agentTeam],
          [agentA._id.toString(), agentA],
          [agentB._id.toString(), agentB],
        ]);

        const deps = makeDeps({
          getTeamRole: jest.fn().mockResolvedValue('member' as TeamRole),
          getUserTeamPrincipals: jest.fn().mockResolvedValue([teamId, sgAId]),
          getTeamSubgroups: jest.fn().mockResolvedValue([sgA, sgB]),
          findEntriesByPrincipal: jest
            .fn()
            .mockResolvedValueOnce([entryTeam])
            .mockResolvedValueOnce([entryA]),
          getAgent: jest.fn().mockImplementation(({ _id }: { _id: Types.ObjectId }) =>
            Promise.resolve(agentMap.get(_id.toString()) ?? null),
          ),
        });

        const { listAgents } = createTeamResourceHandlers(deps);
        const req = makeReq({ id: teamId }, { id: m1Id, role: 'USER' });
        const res = makeRes();

        await listAgents(req as never, res as never);

        expect(res.status).toHaveBeenCalledWith(200);
        const body = (res.json as jest.Mock).mock.calls[0][0];
        const ids = body.resources.map((r: { id: string }) => r.id);
        expect(ids).toContain(agentTeam.id);
        expect(ids).toContain(agentA.id);
        expect(ids).not.toContain(agentB.id);

        const teamEntry = body.resources.find((r: { id: string }) => r.id === agentTeam.id);
        const aEntry = body.resources.find((r: { id: string }) => r.id === agentA.id);
        expect(teamEntry.target).toEqual({ type: 'team' });
        expect(aEntry.target).toEqual({ type: 'subgroup', id: sgAId, name: 'Sub-group A' });
      });

      it('m2 (in sub-group B) sees agent-team and agent-B but NOT agent-A', async () => {
        const agentTeam = makeAgent({ name: 'Agent-Team' });
        const agentA = makeAgent({ name: 'Agent-A' });
        const agentB = makeAgent({ name: 'Agent-B' });

        const teamObjId = new Types.ObjectId(teamId);
        const sgBObjId = new Types.ObjectId(sgBId);

        const entryTeam = makeAclEntryForPrincipal(agentTeam._id as Types.ObjectId, teamObjId);
        const entryB = makeAclEntryForPrincipal(agentB._id as Types.ObjectId, sgBObjId);

        const sgA = makeSubgroupA();
        const sgB = makeSubgroupB();

        const agentMap = new Map([
          [agentTeam._id.toString(), agentTeam],
          [agentA._id.toString(), agentA],
          [agentB._id.toString(), agentB],
        ]);

        const deps = makeDeps({
          getTeamRole: jest.fn().mockResolvedValue('member' as TeamRole),
          getUserTeamPrincipals: jest.fn().mockResolvedValue([teamId, sgBId]),
          getTeamSubgroups: jest.fn().mockResolvedValue([sgA, sgB]),
          findEntriesByPrincipal: jest
            .fn()
            .mockResolvedValueOnce([entryTeam])
            .mockResolvedValueOnce([entryB]),
          getAgent: jest.fn().mockImplementation(({ _id }: { _id: Types.ObjectId }) =>
            Promise.resolve(agentMap.get(_id.toString()) ?? null),
          ),
        });

        const { listAgents } = createTeamResourceHandlers(deps);
        const req = makeReq({ id: teamId }, { id: m2Id, role: 'USER' });
        const res = makeRes();

        await listAgents(req as never, res as never);

        expect(res.status).toHaveBeenCalledWith(200);
        const body = (res.json as jest.Mock).mock.calls[0][0];
        const ids = body.resources.map((r: { id: string }) => r.id);
        expect(ids).toContain(agentTeam.id);
        expect(ids).toContain(agentB.id);
        expect(ids).not.toContain(agentA.id);

        const teamEntry = body.resources.find((r: { id: string }) => r.id === agentTeam.id);
        const bEntry = body.resources.find((r: { id: string }) => r.id === agentB.id);
        expect(teamEntry.target).toEqual({ type: 'team' });
        expect(bEntry.target).toEqual({ type: 'subgroup', id: sgBId, name: 'Sub-group B' });
      });

      it('owner sees all three agents each annotated with correct target', async () => {
        const agentTeam = makeAgent({ name: 'Agent-Team' });
        const agentA = makeAgent({ name: 'Agent-A' });
        const agentB = makeAgent({ name: 'Agent-B' });

        const teamObjId = new Types.ObjectId(teamId);
        const sgAObjId = new Types.ObjectId(sgAId);
        const sgBObjId = new Types.ObjectId(sgBId);

        const entryTeam = makeAclEntryForPrincipal(agentTeam._id as Types.ObjectId, teamObjId);
        const entryA = makeAclEntryForPrincipal(agentA._id as Types.ObjectId, sgAObjId);
        const entryB = makeAclEntryForPrincipal(agentB._id as Types.ObjectId, sgBObjId);

        const sgA = makeSubgroupA();
        const sgB = makeSubgroupB();

        const agentMap = new Map([
          [agentTeam._id.toString(), agentTeam],
          [agentA._id.toString(), agentA],
          [agentB._id.toString(), agentB],
        ]);

        const deps = makeDeps({
          getTeamRole: jest.fn().mockResolvedValue('owner' as TeamRole),
          getTeamSubgroups: jest.fn().mockResolvedValue([sgA, sgB]),
          findEntriesByPrincipal: jest
            .fn()
            .mockResolvedValueOnce([entryTeam])
            .mockResolvedValueOnce([entryA])
            .mockResolvedValueOnce([entryB]),
          getAgent: jest.fn().mockImplementation(({ _id }: { _id: Types.ObjectId }) =>
            Promise.resolve(agentMap.get(_id.toString()) ?? null),
          ),
        });

        const { listAgents } = createTeamResourceHandlers(deps);
        const req = makeReq({ id: teamId }, { id: ownerId, role: 'USER' });
        const res = makeRes();

        await listAgents(req as never, res as never);

        expect(res.status).toHaveBeenCalledWith(200);
        const body = (res.json as jest.Mock).mock.calls[0][0];
        const ids = body.resources.map((r: { id: string }) => r.id);
        expect(ids).toContain(agentTeam.id);
        expect(ids).toContain(agentA.id);
        expect(ids).toContain(agentB.id);

        const teamEntry = body.resources.find((r: { id: string }) => r.id === agentTeam.id);
        const aEntry = body.resources.find((r: { id: string }) => r.id === agentA.id);
        const bEntry = body.resources.find((r: { id: string }) => r.id === agentB.id);
        expect(teamEntry.target).toEqual({ type: 'team' });
        expect(aEntry.target).toEqual({ type: 'subgroup', id: sgAId, name: 'Sub-group A' });
        expect(bEntry.target).toEqual({ type: 'subgroup', id: sgBId, name: 'Sub-group B' });
      });
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
        getUserTeamPrincipals: jest.fn().mockResolvedValue([teamId]),
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
      const teamObjId = new Types.ObjectId(teamId);
      const entry = {
        ...makeAclEntry(pg._id as Types.ObjectId, ResourceType.PROMPTGROUP),
        principalId: teamObjId,
      } as IAclEntry;
      const deps = makeDeps({
        getTeamRole: jest.fn().mockResolvedValue('member' as TeamRole),
        getUserTeamPrincipals: jest.fn().mockResolvedValue([teamId]),
        getTeamSubgroups: jest.fn().mockResolvedValue([]),
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

    it('grants to sub-group principal when valid targetSubgroupId in body', async () => {
      const sgId = makeId();
      const pg = makePromptGroup();
      const subgroup = makeSubgroup(sgId, teamId);
      const deps = makeDeps({
        getPromptGroup: jest.fn().mockResolvedValue(pg),
        getSubgroupById: jest.fn().mockResolvedValue(subgroup),
      });
      const { sharePromptGroup } = createTeamResourceHandlers(deps);

      const req = {
        ...makeReq({ id: teamId, promptGroupId: pg._id.toString() }),
        body: { targetSubgroupId: sgId },
      };
      const res = makeRes();

      await sharePromptGroup(req as never, res as never);

      expect(res.status).toHaveBeenCalledWith(201);
      expect(deps.grantPermission).toHaveBeenCalledWith(
        expect.objectContaining({
          principalId: sgId,
          resourceType: ResourceType.PROMPTGROUP,
        }),
      );
    });

    it('revokes from sub-group principal when valid targetSubgroupId in query', async () => {
      const sgId = makeId();
      const pg = makePromptGroup();
      const subgroup = makeSubgroup(sgId, teamId);
      const deps = makeDeps({
        getPromptGroup: jest.fn().mockResolvedValue(pg),
        getSubgroupById: jest.fn().mockResolvedValue(subgroup),
      });
      const { revokePromptGroup } = createTeamResourceHandlers(deps);

      const req = {
        ...makeReq({ id: teamId, promptGroupId: pg._id.toString() }),
        query: { targetSubgroupId: sgId },
      };
      const res = makeRes();

      await revokePromptGroup(req as never, res as never);

      expect(res.status).toHaveBeenCalledWith(200);
      expect(deps.revokePermission).toHaveBeenCalledWith(
        PrincipalType.GROUP,
        sgId,
        ResourceType.PROMPTGROUP,
        pg._id,
      );
    });
  });
});
