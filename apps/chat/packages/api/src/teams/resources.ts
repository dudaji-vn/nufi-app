import { logger, isValidObjectIdString } from '@librechat/data-schemas';
import {
  ResourceType,
  AccessRoleIds,
  PrincipalType,
  PermissionBits,
} from 'librechat-data-provider';
import { Types } from 'mongoose';
import type {
  IAgent,
  IAclEntry,
  IGroup,
  IPromptGroupDocument,
  TeamRole,
} from '@librechat/data-schemas';
import type { Response } from 'express';
import type { ServerRequest } from '~/types/http';
import { resolveTeamAccess } from './access';

interface TeamIdParams {
  id: string;
}

interface AgentParams extends TeamIdParams {
  agentId: string;
}

interface PromptGroupParams extends TeamIdParams {
  promptGroupId: string;
}

type SafeAgentInfo = {
  id: string;
  name?: string;
  description?: string;
};

type SafePromptGroupInfo = {
  id: string;
  name: string;
};

export interface TeamResourceHandlersDeps {
  getTeamRole: (params: {
    groupId: string | Types.ObjectId;
    userId: string | Types.ObjectId;
  }) => Promise<TeamRole | null>;
  findGroupById: (
    groupId: string | Types.ObjectId,
    projection?: Record<string, 0 | 1>,
  ) => Promise<IGroup | null>;
  getAgent: (filter: Record<string, unknown>) => Promise<IAgent | null>;
  getPromptGroup: (filter: Record<string, unknown>) => Promise<IPromptGroupDocument | null>;
  findEntriesByPrincipal: (
    principalType: string,
    principalId: string | Types.ObjectId,
    resourceType?: string,
  ) => Promise<IAclEntry[]>;
  revokePermission: (
    principalType: string,
    principalId: string | Types.ObjectId,
    resourceType: string,
    resourceId: string | Types.ObjectId,
  ) => Promise<unknown>;
  grantPermission: (params: {
    principalType: string;
    principalId: string | Types.ObjectId;
    resourceType: string;
    resourceId: string | Types.ObjectId;
    accessRoleId: string;
    grantedBy: string | Types.ObjectId;
  }) => Promise<unknown>;
  checkPermission: (params: {
    userId: string | Types.ObjectId;
    role?: string;
    resourceType: string;
    resourceId: string | Types.ObjectId;
    requiredPermission: number;
  }) => Promise<boolean>;
}

interface ResourceSpec<TDoc> {
  resourceType: string;
  viewerRoleId: string;
  /** Resolve a resource from the URL path param (e.g. agent string id or promptGroup _id string). */
  resolveByPathId: (pathId: string) => Promise<TDoc | null>;
  /** Resolve a resource from its Mongo _id (used when listing ACL entries). */
  resolveByObjectId: (objectId: Types.ObjectId) => Promise<TDoc | null>;
  toSafe: (doc: TDoc) => SafeAgentInfo | SafePromptGroupInfo;
  getDocId: (doc: TDoc) => Types.ObjectId;
  getDocStringId: (doc: TDoc) => string;
}

function createResourceHandlers<TDoc>(deps: TeamResourceHandlersDeps, spec: ResourceSpec<TDoc>) {
  const { findEntriesByPrincipal, revokePermission, grantPermission, checkPermission } = deps;
  const {
    resourceType,
    viewerRoleId,
    resolveByPathId,
    resolveByObjectId,
    toSafe,
    getDocId,
    getDocStringId,
  } = spec;

  async function share(req: ServerRequest, res: Response, pathId: string): Promise<Response> {
    const { id } = req.params as TeamIdParams;
    if (!isValidObjectIdString(id)) {
      return res.status(400).json({ error: 'Invalid team ID format' });
    }

    const callerId = req.user?.id as string;
    const access = await resolveTeamAccess(deps, id, callerId, 'admin');
    if (!access.ok) {
      const error = access.status === 403 ? 'Forbidden' : 'Team not found';
      return res.status(access.status).json({ error });
    }

    const resource = await resolveByPathId(pathId);
    if (!resource) {
      return res.status(404).json({ error: 'Resource not found' });
    }

    const docId = getDocId(resource);
    const hasShare = await checkPermission({
      userId: callerId,
      role: (req.user as { role?: string })?.role,
      resourceType,
      resourceId: docId,
      requiredPermission: PermissionBits.SHARE,
    });
    if (!hasShare) {
      return res
        .status(403)
        .json({ error: 'Forbidden: you do not have SHARE permission on this resource' });
    }

    await grantPermission({
      principalType: PrincipalType.GROUP,
      principalId: id,
      resourceType,
      resourceId: docId,
      accessRoleId: viewerRoleId,
      grantedBy: callerId,
    });

    return res.status(201).json({ success: true, id: getDocStringId(resource) });
  }

  async function revoke(req: ServerRequest, res: Response, pathId: string): Promise<Response> {
    const { id } = req.params as TeamIdParams;
    if (!isValidObjectIdString(id)) {
      return res.status(400).json({ error: 'Invalid team ID format' });
    }

    const callerId = req.user?.id as string;
    const access = await resolveTeamAccess(deps, id, callerId, 'admin');
    if (!access.ok) {
      const error = access.status === 403 ? 'Forbidden' : 'Team not found';
      return res.status(access.status).json({ error });
    }

    const resource = await resolveByPathId(pathId);
    if (!resource) {
      return res.status(404).json({ error: 'Resource not found' });
    }

    await revokePermission(PrincipalType.GROUP, id, resourceType, getDocId(resource));

    return res.status(200).json({ success: true });
  }

  async function list(req: ServerRequest, res: Response): Promise<Response> {
    const { id } = req.params as TeamIdParams;
    if (!isValidObjectIdString(id)) {
      return res.status(400).json({ error: 'Invalid team ID format' });
    }

    const callerId = req.user?.id as string;
    const access = await resolveTeamAccess(deps, id, callerId, 'member');
    if (!access.ok) {
      const error = access.status === 403 ? 'Forbidden' : 'Team not found';
      return res.status(access.status).json({ error });
    }

    const groupObjectId = new Types.ObjectId(id);
    const entries = await findEntriesByPrincipal(PrincipalType.GROUP, groupObjectId, resourceType);

    if (!entries.length) {
      return res.status(200).json({ resources: [] });
    }

    const settled = await Promise.all(
      entries.map((e) => resolveByObjectId(e.resourceId as Types.ObjectId)),
    );

    const resources = settled
      .filter((doc): doc is NonNullable<typeof doc> => doc !== null)
      .map(toSafe);

    return res.status(200).json({ resources });
  }

  return { share, revoke, list };
}

export function createTeamResourceHandlers(deps: TeamResourceHandlersDeps) {
  const agentSpec: ResourceSpec<IAgent> = {
    resourceType: ResourceType.AGENT,
    viewerRoleId: AccessRoleIds.AGENT_VIEWER,
    resolveByPathId: (agentId: string) => deps.getAgent({ id: agentId }),
    resolveByObjectId: (objectId: Types.ObjectId) => deps.getAgent({ _id: objectId }),
    toSafe: (doc: IAgent): SafeAgentInfo => ({
      id: doc.id,
      name: doc.name,
      description: doc.description,
    }),
    getDocId: (doc: IAgent) => doc._id as Types.ObjectId,
    getDocStringId: (doc: IAgent) => doc.id,
  };

  const promptGroupSpec: ResourceSpec<IPromptGroupDocument> = {
    resourceType: ResourceType.PROMPTGROUP,
    viewerRoleId: AccessRoleIds.PROMPTGROUP_VIEWER,
    resolveByPathId: (promptGroupId: string) => {
      if (!isValidObjectIdString(promptGroupId)) {
        return Promise.resolve(null);
      }
      return deps.getPromptGroup({ _id: promptGroupId });
    },
    resolveByObjectId: (objectId: Types.ObjectId) => deps.getPromptGroup({ _id: objectId }),
    toSafe: (doc: IPromptGroupDocument): SafePromptGroupInfo => ({
      id: doc._id.toString(),
      name: doc.name,
    }),
    getDocId: (doc: IPromptGroupDocument) => doc._id as Types.ObjectId,
    getDocStringId: (doc: IPromptGroupDocument) => doc._id.toString(),
  };

  const agentHandlers = createResourceHandlers(deps, agentSpec);
  const promptHandlers = createResourceHandlers(deps, promptGroupSpec);

  async function shareAgent(req: ServerRequest, res: Response): Promise<Response> {
    try {
      const { agentId } = req.params as AgentParams;
      return await agentHandlers.share(req, res, agentId);
    } catch (error) {
      logger.error('[resources] shareAgent error:', error);
      return res.status(500).json({ error: 'Failed to share agent with team' });
    }
  }

  async function revokeAgent(req: ServerRequest, res: Response): Promise<Response> {
    try {
      const { agentId } = req.params as AgentParams;
      return await agentHandlers.revoke(req, res, agentId);
    } catch (error) {
      logger.error('[resources] revokeAgent error:', error);
      return res.status(500).json({ error: 'Failed to remove agent from team' });
    }
  }

  async function listAgents(req: ServerRequest, res: Response): Promise<Response> {
    try {
      return await agentHandlers.list(req, res);
    } catch (error) {
      logger.error('[resources] listAgents error:', error);
      return res.status(500).json({ error: 'Failed to list team agents' });
    }
  }

  async function sharePromptGroup(req: ServerRequest, res: Response): Promise<Response> {
    try {
      const { promptGroupId } = req.params as PromptGroupParams;
      return await promptHandlers.share(req, res, promptGroupId);
    } catch (error) {
      logger.error('[resources] sharePromptGroup error:', error);
      return res.status(500).json({ error: 'Failed to share prompt group with team' });
    }
  }

  async function revokePromptGroup(req: ServerRequest, res: Response): Promise<Response> {
    try {
      const { promptGroupId } = req.params as PromptGroupParams;
      return await promptHandlers.revoke(req, res, promptGroupId);
    } catch (error) {
      logger.error('[resources] revokePromptGroup error:', error);
      return res.status(500).json({ error: 'Failed to remove prompt group from team' });
    }
  }

  async function listPromptGroups(req: ServerRequest, res: Response): Promise<Response> {
    try {
      return await promptHandlers.list(req, res);
    } catch (error) {
      logger.error('[resources] listPromptGroups error:', error);
      return res.status(500).json({ error: 'Failed to list team prompt groups' });
    }
  }

  return {
    shareAgent,
    revokeAgent,
    listAgents,
    sharePromptGroup,
    revokePromptGroup,
    listPromptGroups,
  };
}
