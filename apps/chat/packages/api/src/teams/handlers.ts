import { logger, isValidObjectIdString } from '@librechat/data-schemas';
import type { Types, FilterQuery, ClientSession } from 'mongoose';
import type { IGroup, IUser, TeamRole } from '@librechat/data-schemas';
import type { Response } from 'express';
import type { ValidationError } from '~/types/error';
import type { ServerRequest } from '~/types/http';
import { hasMinRole, resolveTeamAccess as resolveTeamAccessShared } from './access';

const DATA_GUARD_MESSAGES: ReadonlySet<string> = new Set([
  'Cannot remove the team owner; transfer ownership first',
  'fromUserId is not the current owner',
  'toUserId is not a member of the team',
  'Cannot change the owner role; use transferOwnership',
]);

function isDataGuardError(error: unknown): boolean {
  if (!(error instanceof Error)) {
    return false;
  }
  if (DATA_GUARD_MESSAGES.has(error.message)) {
    return true;
  }
  return (
    error.message.startsWith('fromUserId is not') ||
    error.message.startsWith('toUserId is not') ||
    error.message.startsWith('Cannot remove') ||
    error.message.startsWith('Cannot change')
  );
}

interface TeamIdParams {
  id: string;
}

interface TeamMemberParams extends TeamIdParams {
  userId: string;
}

export interface TeamsHandlersDeps {
  createTeam: (params: {
    name: string;
    description?: string;
    avatar?: string;
    ownerId: string | Types.ObjectId;
    tenantId?: string;
  }) => Promise<IGroup>;
  getUserTeams: (params: { userId: string | Types.ObjectId }) => Promise<IGroup[]>;
  getTeamRole: (params: {
    groupId: string | Types.ObjectId;
    userId: string | Types.ObjectId;
  }) => Promise<TeamRole | null>;
  removeTeamMember: (params: {
    groupId: string | Types.ObjectId;
    userId: string | Types.ObjectId;
  }) => Promise<IGroup | null>;
  setMemberRole: (params: {
    groupId: string | Types.ObjectId;
    userId: string | Types.ObjectId;
    role: 'admin' | 'member';
  }) => Promise<IGroup | null>;
  transferOwnership: (params: {
    groupId: string | Types.ObjectId;
    fromUserId: string | Types.ObjectId;
    toUserId: string | Types.ObjectId;
  }) => Promise<IGroup | null>;
  deleteInvitesByGroup: (params: { groupId: string | Types.ObjectId }) => Promise<number>;
  findGroupById: (
    groupId: string | Types.ObjectId,
    projection?: Record<string, 0 | 1>,
    session?: ClientSession,
  ) => Promise<IGroup | null>;
  updateGroupById: (
    groupId: string | Types.ObjectId,
    data: Partial<Pick<IGroup, 'name' | 'description' | 'avatar'>>,
    session?: ClientSession,
  ) => Promise<IGroup | null>;
  deleteGroup: (
    groupId: string | Types.ObjectId,
    session?: ClientSession,
  ) => Promise<IGroup | null>;
  findUsers: (
    searchCriteria: FilterQuery<IUser>,
    fieldsToSelect?: string | string[] | null,
  ) => Promise<IUser[]>;
}

interface EnrichedMember {
  userId: string;
  role: TeamRole;
  joinedAt: Date;
  name: string;
  email: string;
  avatar?: string;
  username?: string;
}

async function enrichMembers(
  team: IGroup,
  findUsers: TeamsHandlersDeps['findUsers'],
): Promise<EnrichedMember[]> {
  const rawMembers = team.members ?? [];
  if (rawMembers.length === 0) {
    return [];
  }

  const userIds = rawMembers.map((m) => m.userId.toString());
  const users = await findUsers({ _id: { $in: userIds } }, 'name email avatar username');

  const userMap = new Map<string, IUser>();
  for (const user of users) {
    if (user._id) {
      userMap.set(user._id.toString(), user);
    }
  }

  return rawMembers.map((m) => {
    const uid = m.userId.toString();
    const user = userMap.get(uid);
    return {
      userId: uid,
      role: m.role,
      joinedAt: m.joinedAt,
      name: user?.name ?? uid,
      email: user?.email ?? '',
      avatar: user?.avatar,
      username: user?.username,
    };
  });
}

export function createTeamsHandlers(deps: TeamsHandlersDeps) {
  const {
    createTeam,
    getUserTeams,
    getTeamRole,
    removeTeamMember,
    setMemberRole,
    transferOwnership,
    deleteInvitesByGroup,
    findGroupById,
    updateGroupById,
    deleteGroup,
    findUsers,
  } = deps;

  async function resolveTeamAccess(
    id: string,
    callerId: string,
    minRole: TeamRole,
  ): Promise<{ team: IGroup; role: TeamRole } | { error: string; status: 400 | 403 | 404 }> {
    const result = await resolveTeamAccessShared(
      { getTeamRole, findGroupById },
      id,
      callerId,
      minRole,
    );
    if (!result.ok) {
      const error = result.status === 403 ? 'Forbidden' : 'Team not found';
      return { error, status: result.status };
    }
    return { team: result.team, role: result.role };
  }

  async function createHandler(req: ServerRequest, res: Response) {
    try {
      const { name, description, avatar } = req.body as {
        name?: string;
        description?: string;
        avatar?: string;
      };

      if (!name || typeof name !== 'string' || !name.trim()) {
        return res.status(400).json({ error: 'name is required' });
      }

      const callerId = req.user?.id as string;
      const tenantId = req.user?.tenantId;

      const team = await createTeam({
        name: name.trim(),
        description,
        avatar,
        ownerId: callerId,
        tenantId,
      });

      return res.status(201).json({ team });
    } catch (error) {
      if ((error as ValidationError).name === 'ValidationError') {
        return res.status(400).json({ error: (error as ValidationError).message });
      }
      logger.error('[teams] create error:', error);
      return res.status(500).json({ error: 'Failed to create team' });
    }
  }

  async function listHandler(req: ServerRequest, res: Response) {
    try {
      const callerId = req.user?.id as string;
      const teams = await getUserTeams({ userId: callerId });
      return res.status(200).json({ teams });
    } catch (error) {
      logger.error('[teams] list error:', error);
      return res.status(500).json({ error: 'Failed to list teams' });
    }
  }

  async function getHandler(req: ServerRequest, res: Response) {
    try {
      const { id } = req.params as TeamIdParams;
      if (!isValidObjectIdString(id)) {
        return res.status(400).json({ error: 'Invalid team ID format' });
      }

      const callerId = req.user?.id as string;
      const access = await resolveTeamAccess(id, callerId, 'member');

      if ('error' in access) {
        return res.status(access.status).json({ error: access.error });
      }

      const { team } = access;
      const members = await enrichMembers(team, findUsers);

      return res.status(200).json({ team, members });
    } catch (error) {
      logger.error('[teams] get error:', error);
      return res.status(500).json({ error: 'Failed to get team' });
    }
  }

  async function updateHandler(req: ServerRequest, res: Response) {
    try {
      const { id } = req.params as TeamIdParams;
      if (!isValidObjectIdString(id)) {
        return res.status(400).json({ error: 'Invalid team ID format' });
      }

      const callerId = req.user?.id as string;
      const access = await resolveTeamAccess(id, callerId, 'admin');

      if ('error' in access) {
        return res.status(access.status).json({ error: access.error });
      }

      const { name, description, avatar } = req.body as {
        name?: string;
        description?: string;
        avatar?: string;
      };

      const updateData: Partial<Pick<IGroup, 'name' | 'description' | 'avatar'>> = {};
      if (name !== undefined) {
        updateData.name = typeof name === 'string' ? name.trim() : name;
      }
      if (description !== undefined) {
        updateData.description = description;
      }
      if (avatar !== undefined) {
        updateData.avatar = avatar;
      }

      if (Object.keys(updateData).length === 0) {
        return res.status(400).json({ error: 'No valid fields to update' });
      }

      const updated = await updateGroupById(id, updateData);
      if (!updated) {
        return res.status(404).json({ error: 'Team not found' });
      }

      return res.status(200).json({ team: updated });
    } catch (error) {
      if ((error as ValidationError).name === 'ValidationError') {
        return res.status(400).json({ error: (error as ValidationError).message });
      }
      logger.error('[teams] update error:', error);
      return res.status(500).json({ error: 'Failed to update team' });
    }
  }

  async function removeHandler(req: ServerRequest, res: Response) {
    try {
      const { id } = req.params as TeamIdParams;
      if (!isValidObjectIdString(id)) {
        return res.status(400).json({ error: 'Invalid team ID format' });
      }

      const callerId = req.user?.id as string;
      const access = await resolveTeamAccess(id, callerId, 'owner');

      if ('error' in access) {
        return res.status(access.status).json({ error: access.error });
      }

      await deleteInvitesByGroup({ groupId: id });
      await deleteGroup(id);

      return res.status(200).json({ success: true });
    } catch (error) {
      logger.error('[teams] remove error:', error);
      return res.status(500).json({ error: 'Failed to delete team' });
    }
  }

  async function listMembersHandler(req: ServerRequest, res: Response) {
    try {
      const { id } = req.params as TeamIdParams;
      if (!isValidObjectIdString(id)) {
        return res.status(400).json({ error: 'Invalid team ID format' });
      }

      const callerId = req.user?.id as string;
      const access = await resolveTeamAccess(id, callerId, 'member');

      if ('error' in access) {
        return res.status(access.status).json({ error: access.error });
      }

      const { team } = access;
      const members = await enrichMembers(team, findUsers);

      return res.status(200).json({ members });
    } catch (error) {
      logger.error('[teams] listMembers error:', error);
      return res.status(500).json({ error: 'Failed to list team members' });
    }
  }

  async function removeMemberHandler(req: ServerRequest, res: Response) {
    try {
      const { id, userId } = req.params as TeamMemberParams;
      if (!isValidObjectIdString(id)) {
        return res.status(400).json({ error: 'Invalid team ID format' });
      }
      if (!isValidObjectIdString(userId)) {
        return res.status(400).json({ error: 'Invalid user ID format' });
      }

      const callerId = req.user?.id as string;
      const isSelf = callerId === userId;

      const access = await resolveTeamAccess(id, callerId, 'member');
      if ('error' in access) {
        return res.status(access.status).json({ error: access.error });
      }

      const { role } = access;

      if (!isSelf && !hasMinRole(role, 'admin')) {
        return res.status(403).json({ error: 'Forbidden' });
      }

      await removeTeamMember({ groupId: id, userId });

      return res.status(200).json({ success: true });
    } catch (error) {
      if (isDataGuardError(error)) {
        return res.status(409).json({ error: (error as Error).message });
      }
      logger.error('[teams] removeMember error:', error);
      return res.status(500).json({ error: 'Failed to remove team member' });
    }
  }

  async function changeMemberRoleHandler(req: ServerRequest, res: Response) {
    try {
      const { id, userId } = req.params as TeamMemberParams;
      if (!isValidObjectIdString(id)) {
        return res.status(400).json({ error: 'Invalid team ID format' });
      }
      if (!isValidObjectIdString(userId)) {
        return res.status(400).json({ error: 'Invalid user ID format' });
      }

      const callerId = req.user?.id as string;
      const access = await resolveTeamAccess(id, callerId, 'member');

      if ('error' in access) {
        return res.status(access.status).json({ error: access.error });
      }

      const { role: callerRole, team } = access;

      const { role: newRole } = req.body as { role?: string };
      if (newRole !== 'admin' && newRole !== 'member') {
        return res.status(400).json({ error: 'role must be "admin" or "member"' });
      }

      if (!hasMinRole(callerRole, 'admin')) {
        return res.status(403).json({ error: 'Forbidden' });
      }

      const isMember = (team.members ?? []).some((m) => m.userId.toString() === userId);
      if (!isMember) {
        return res.status(404).json({ error: 'Member not found' });
      }

      const updated = await setMemberRole({ groupId: id, userId, role: newRole });

      if (!updated) {
        return res.status(404).json({ error: 'Member not found' });
      }

      return res.status(200).json({ team: updated });
    } catch (error) {
      if (isDataGuardError(error)) {
        return res.status(409).json({ error: (error as Error).message });
      }
      logger.error('[teams] changeMemberRole error:', error);
      return res.status(500).json({ error: 'Failed to change member role' });
    }
  }

  async function transferOwnershipHandler(req: ServerRequest, res: Response) {
    try {
      const { id } = req.params as TeamIdParams;
      if (!isValidObjectIdString(id)) {
        return res.status(400).json({ error: 'Invalid team ID format' });
      }

      const callerId = req.user?.id as string;

      const access = await resolveTeamAccess(id, callerId, 'owner');
      if ('error' in access) {
        return res.status(access.status).json({ error: access.error });
      }

      const { newOwnerId } = req.body as { newOwnerId?: string };

      if (!newOwnerId) {
        return res.status(400).json({ error: 'newOwnerId is required' });
      }
      if (!isValidObjectIdString(newOwnerId)) {
        return res.status(400).json({ error: 'Invalid newOwnerId format' });
      }

      const updated = await transferOwnership({
        groupId: id,
        fromUserId: callerId,
        toUserId: newOwnerId,
      });

      if (!updated) {
        return res.status(404).json({ error: 'Team not found' });
      }

      return res.status(200).json({ team: updated });
    } catch (error) {
      if (isDataGuardError(error)) {
        return res.status(409).json({ error: (error as Error).message });
      }
      logger.error('[teams] transferOwnership error:', error);
      return res.status(500).json({ error: 'Failed to transfer team ownership' });
    }
  }

  return {
    create: createHandler,
    list: listHandler,
    get: getHandler,
    update: updateHandler,
    remove: removeHandler,
    listMembers: listMembersHandler,
    removeMember: removeMemberHandler,
    changeMemberRole: changeMemberRoleHandler,
    transferOwnership: transferOwnershipHandler,
  };
}
