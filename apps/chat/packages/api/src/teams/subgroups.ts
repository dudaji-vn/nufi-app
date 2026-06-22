import { logger, isValidObjectIdString } from '@librechat/data-schemas';
import type { Types } from 'mongoose';
import type { IGroup, TeamRole } from '@librechat/data-schemas';
import type { Response } from 'express';
import type { ServerRequest } from '~/types/http';
import { resolveTeamAccess } from './access';

interface TeamIdParams {
  id: string;
}

interface SubgroupParams extends TeamIdParams {
  sgId: string;
}

interface SubgroupMemberParams extends SubgroupParams {
  userId: string;
}

export interface SubgroupsHandlersDeps {
  getTeamRole: (params: {
    groupId: string | Types.ObjectId;
    userId: string | Types.ObjectId;
  }) => Promise<TeamRole | null>;
  findGroupById: (
    groupId: string | Types.ObjectId,
    projection?: Record<string, 0 | 1>,
  ) => Promise<IGroup | null>;
  createSubgroup: (params: {
    parentTeamId: string | Types.ObjectId;
    name: string;
    description?: string;
    ownerId: string | Types.ObjectId;
    tenantId?: string;
  }) => Promise<IGroup>;
  getTeamSubgroups: (parentTeamId: string | Types.ObjectId) => Promise<IGroup[]>;
  getSubgroupById: (subgroupId: string | Types.ObjectId) => Promise<IGroup | null>;
  updateSubgroup: (
    subgroupId: string | Types.ObjectId,
    updates: { name?: string; description?: string },
  ) => Promise<IGroup | null>;
  deleteSubgroup: (subgroupId: string | Types.ObjectId) => Promise<void>;
  addSubgroupMember: (params: {
    subgroupId: string | Types.ObjectId;
    userId: string;
  }) => Promise<IGroup>;
  removeSubgroupMember: (params: {
    subgroupId: string | Types.ObjectId;
    userId: string;
  }) => Promise<IGroup>;
  getUserSubgroups: (params: {
    userId: string;
    parentTeamId: string | Types.ObjectId;
  }) => Promise<IGroup[]>;
  deleteAclEntries: (filter: Record<string, unknown>) => Promise<unknown>;
}

function toSubgroupDTO(sg: IGroup, memberCount: number) {
  return {
    _id: sg._id.toString(),
    name: sg.name,
    description: sg.description,
    parentTeamId: sg.parentTeamId?.toString() ?? '',
    memberCount,
  };
}

/** Verify the sub-group belongs to the given team. Returns true if valid, false if not. */
function isSubgroupOfTeam(sg: IGroup, teamId: string): boolean {
  return !!sg.parentTeamId && sg.parentTeamId.toString() === teamId;
}

export function createSubgroupsHandlers(deps: SubgroupsHandlersDeps) {
  const { getTeamRole, findGroupById } = deps;

  async function resolveAdmin(
    id: string,
    callerId: string,
  ): Promise<{ team: IGroup; role: TeamRole } | { error: string; status: 400 | 403 | 404 }> {
    const result = await resolveTeamAccess({ getTeamRole, findGroupById }, id, callerId, 'admin');
    if (!result.ok) {
      const error = result.status === 403 ? 'Forbidden' : 'Team not found';
      return { error, status: result.status };
    }
    return { team: result.team, role: result.role };
  }

  async function createHandler(req: ServerRequest, res: Response) {
    try {
      const { id } = req.params as TeamIdParams;
      if (!isValidObjectIdString(id)) {
        return res.status(400).json({ error: 'Invalid team ID format' });
      }

      const callerId = req.user?.id as string;
      const access = await resolveAdmin(id, callerId);
      if ('error' in access) {
        return res.status(access.status).json({ error: access.error });
      }

      const { name, description } = req.body as { name?: string; description?: string };
      if (!name || typeof name !== 'string' || !name.trim()) {
        return res.status(400).json({ error: 'name is required' });
      }

      const { team } = access;
      const sg = await deps.createSubgroup({
        parentTeamId: team._id,
        name: name.trim(),
        description,
        ownerId: team.ownerId as Types.ObjectId,
        tenantId: team.tenantId,
      });

      return res.status(201).json({ subgroup: toSubgroupDTO(sg, (sg.memberIds ?? []).length) });
    } catch (error) {
      logger.error('[subgroups] create error:', error);
      return res.status(500).json({ error: 'Failed to create sub-group' });
    }
  }

  async function listHandler(req: ServerRequest, res: Response) {
    try {
      const { id } = req.params as TeamIdParams;
      if (!isValidObjectIdString(id)) {
        return res.status(400).json({ error: 'Invalid team ID format' });
      }

      const callerId = req.user?.id as string;
      const access = await resolveAdmin(id, callerId);
      if ('error' in access) {
        return res.status(access.status).json({ error: access.error });
      }

      const sgs = await deps.getTeamSubgroups(access.team._id);
      return res.status(200).json({
        subgroups: sgs.map((sg) => toSubgroupDTO(sg, (sg.memberIds ?? []).length)),
      });
    } catch (error) {
      logger.error('[subgroups] list error:', error);
      return res.status(500).json({ error: 'Failed to list sub-groups' });
    }
  }

  async function getHandler(req: ServerRequest, res: Response) {
    try {
      const { id, sgId } = req.params as SubgroupParams;
      if (!isValidObjectIdString(id)) {
        return res.status(400).json({ error: 'Invalid team ID format' });
      }
      if (!isValidObjectIdString(sgId)) {
        return res.status(400).json({ error: 'Invalid sub-group ID format' });
      }

      const callerId = req.user?.id as string;
      const access = await resolveAdmin(id, callerId);
      if ('error' in access) {
        return res.status(access.status).json({ error: access.error });
      }

      const sg = await deps.getSubgroupById(sgId);
      if (!sg || !isSubgroupOfTeam(sg, id)) {
        return res.status(404).json({ error: 'Sub-group not found' });
      }

      const members = (sg.members ?? []).map((m) => ({
        userId: m.userId.toString(),
        role: m.role,
        joinedAt: m.joinedAt,
      }));

      return res.status(200).json({
        subgroup: toSubgroupDTO(sg, (sg.memberIds ?? []).length),
        members,
      });
    } catch (error) {
      logger.error('[subgroups] get error:', error);
      return res.status(500).json({ error: 'Failed to get sub-group' });
    }
  }

  async function updateHandler(req: ServerRequest, res: Response) {
    try {
      const { id, sgId } = req.params as SubgroupParams;
      if (!isValidObjectIdString(id)) {
        return res.status(400).json({ error: 'Invalid team ID format' });
      }
      if (!isValidObjectIdString(sgId)) {
        return res.status(400).json({ error: 'Invalid sub-group ID format' });
      }

      const callerId = req.user?.id as string;
      const access = await resolveAdmin(id, callerId);
      if ('error' in access) {
        return res.status(access.status).json({ error: access.error });
      }

      const sg = await deps.getSubgroupById(sgId);
      if (!sg || !isSubgroupOfTeam(sg, id)) {
        return res.status(404).json({ error: 'Sub-group not found' });
      }

      const { name, description } = req.body as { name?: string; description?: string };
      const updates: { name?: string; description?: string } = {};
      if (name !== undefined) {
        updates.name = typeof name === 'string' ? name.trim() : name;
      }
      if (description !== undefined) {
        updates.description = description;
      }

      if (Object.keys(updates).length === 0) {
        return res.status(400).json({ error: 'No valid fields to update' });
      }

      const updated = await deps.updateSubgroup(sgId, updates);
      if (!updated) {
        return res.status(404).json({ error: 'Sub-group not found' });
      }

      return res.status(200).json({ subgroup: toSubgroupDTO(updated, (updated.memberIds ?? []).length) });
    } catch (error) {
      logger.error('[subgroups] update error:', error);
      return res.status(500).json({ error: 'Failed to update sub-group' });
    }
  }

  async function removeHandler(req: ServerRequest, res: Response) {
    try {
      const { id, sgId } = req.params as SubgroupParams;
      if (!isValidObjectIdString(id)) {
        return res.status(400).json({ error: 'Invalid team ID format' });
      }
      if (!isValidObjectIdString(sgId)) {
        return res.status(400).json({ error: 'Invalid sub-group ID format' });
      }

      const callerId = req.user?.id as string;
      const access = await resolveAdmin(id, callerId);
      if ('error' in access) {
        return res.status(access.status).json({ error: access.error });
      }

      const sg = await deps.getSubgroupById(sgId);
      if (!sg || !isSubgroupOfTeam(sg, id)) {
        return res.status(404).json({ error: 'Sub-group not found' });
      }

      await deps.deleteAclEntries({ principalId: sg._id });
      await deps.deleteSubgroup(sg._id);

      return res.status(200).json({ success: true });
    } catch (error) {
      logger.error('[subgroups] remove error:', error);
      return res.status(500).json({ error: 'Failed to delete sub-group' });
    }
  }

  async function addMemberHandler(req: ServerRequest, res: Response) {
    try {
      const { id, sgId } = req.params as SubgroupParams;
      if (!isValidObjectIdString(id)) {
        return res.status(400).json({ error: 'Invalid team ID format' });
      }
      if (!isValidObjectIdString(sgId)) {
        return res.status(400).json({ error: 'Invalid sub-group ID format' });
      }

      const callerId = req.user?.id as string;
      const access = await resolveAdmin(id, callerId);
      if ('error' in access) {
        return res.status(access.status).json({ error: access.error });
      }

      const sg = await deps.getSubgroupById(sgId);
      if (!sg || !isSubgroupOfTeam(sg, id)) {
        return res.status(404).json({ error: 'Sub-group not found' });
      }

      const { userId } = req.body as { userId?: string };
      if (!userId) {
        return res.status(400).json({ error: 'userId is required' });
      }

      let updated: IGroup;
      try {
        updated = await deps.addSubgroupMember({ subgroupId: sg._id, userId });
      } catch (invariantError) {
        if (
          invariantError instanceof Error &&
          /not a member of the team/i.test(invariantError.message)
        ) {
          return res.status(400).json({ error: invariantError.message });
        }
        throw invariantError;
      }
      return res.status(200).json({ subgroup: toSubgroupDTO(updated, (updated.memberIds ?? []).length) });
    } catch (error) {
      logger.error('[subgroups] addMember error:', error);
      return res.status(500).json({ error: 'Failed to add sub-group member' });
    }
  }

  async function removeMemberHandler(req: ServerRequest, res: Response) {
    try {
      const { id, sgId, userId } = req.params as SubgroupMemberParams;
      if (!isValidObjectIdString(id)) {
        return res.status(400).json({ error: 'Invalid team ID format' });
      }
      if (!isValidObjectIdString(sgId)) {
        return res.status(400).json({ error: 'Invalid sub-group ID format' });
      }

      const callerId = req.user?.id as string;
      const access = await resolveAdmin(id, callerId);
      if ('error' in access) {
        return res.status(access.status).json({ error: access.error });
      }

      const sg = await deps.getSubgroupById(sgId);
      if (!sg || !isSubgroupOfTeam(sg, id)) {
        return res.status(404).json({ error: 'Sub-group not found' });
      }

      if (!userId || !isValidObjectIdString(userId)) {
        return res.status(400).json({ error: 'Invalid user ID format' });
      }

      const updated = await deps.removeSubgroupMember({ subgroupId: sg._id, userId });
      return res.status(200).json({ subgroup: toSubgroupDTO(updated, (updated.memberIds ?? []).length) });
    } catch (error) {
      logger.error('[subgroups] removeMember error:', error);
      return res.status(500).json({ error: 'Failed to remove sub-group member' });
    }
  }

  return {
    create: createHandler,
    list: listHandler,
    get: getHandler,
    update: updateHandler,
    remove: removeHandler,
    addMember: addMemberHandler,
    removeMember: removeMemberHandler,
  };
}
