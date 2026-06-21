import { logger, isValidObjectIdString } from '@librechat/data-schemas';
import type { Types, ClientSession } from 'mongoose';
import type { IGroup, ITeamInvite, IUser, TeamRole, TeamInviteRole } from '@librechat/data-schemas';
import type { Response } from 'express';
import type { ServerRequest } from '~/types/http';
import { resolveTeamAccess } from './access';

const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

interface TeamIdParams {
  id: string;
}

interface TokenParams {
  token: string;
}

interface InviteParams extends TeamIdParams {
  inviteId: string;
}

export interface TeamInviteHandlersDeps {
  createInvite: (params: {
    groupId: string | Types.ObjectId;
    email: string;
    role: TeamInviteRole;
    invitedBy: string | Types.ObjectId;
    invitedUserId?: Types.ObjectId | null;
    tenantId?: string;
  }) => Promise<ITeamInvite>;
  findInviteByToken: (token: string) => Promise<ITeamInvite | null>;
  listPendingInvitesForUser: (params: {
    userId?: string | Types.ObjectId;
    email?: string;
  }) => Promise<ITeamInvite[]>;
  listInvitesForTeam: (params: {
    groupId: string | Types.ObjectId;
    status?: string;
  }) => Promise<ITeamInvite[]>;
  acceptInvite: (params: {
    token: string;
    userId: string | Types.ObjectId;
  }) => Promise<ITeamInvite | null>;
  declineInvite: (params: { token: string }) => Promise<ITeamInvite | null>;
  revokeInvite: (params: {
    inviteId: string | Types.ObjectId;
    groupId?: string | Types.ObjectId;
  }) => Promise<ITeamInvite | null>;
  addTeamMember: (params: {
    groupId: string | Types.ObjectId;
    userId: string | Types.ObjectId;
    role: TeamRole;
  }) => Promise<IGroup>;
  getTeamRole: (params: {
    groupId: string | Types.ObjectId;
    userId: string | Types.ObjectId;
  }) => Promise<TeamRole | null>;
  findUser: (criteria: Partial<Pick<IUser, 'email'>>, fields?: string) => Promise<IUser | null>;
  findGroupById: (
    groupId: string | Types.ObjectId,
    projection?: Record<string, 0 | 1>,
    session?: ClientSession,
  ) => Promise<IGroup | null>;
  sendInviteEmail?: (payload: {
    email: string;
    token: string;
    teamName: string;
    inviterName: string;
  }) => Promise<void>;
}

function isCallerBound(invite: ITeamInvite, callerId: string, callerEmail: string): boolean {
  const emailMatch = invite.email.toLowerCase() === callerEmail.toLowerCase();
  const userIdMatch = invite.invitedUserId != null && invite.invitedUserId.toString() === callerId;
  return emailMatch || userIdMatch;
}

function isInviteValid(invite: ITeamInvite): boolean {
  return invite.status === 'pending' && invite.expiresAt > new Date();
}

type InviteWithTeamName = ITeamInvite & { teamName?: string };

export function createTeamInviteHandlers(deps: TeamInviteHandlersDeps) {
  const {
    createInvite,
    findInviteByToken,
    listPendingInvitesForUser,
    listInvitesForTeam,
    acceptInvite,
    declineInvite,
    revokeInvite,
    addTeamMember,
    findUser,
    findGroupById,
  } = deps;

  async function listMine(req: ServerRequest, res: Response) {
    try {
      const callerId = req.user?.id as string;
      const callerEmail = req.user?.email as string;

      const rawInvites = await listPendingInvitesForUser({ userId: callerId, email: callerEmail });

      const invites: InviteWithTeamName[] = await Promise.all(
        rawInvites.map(async (invite) => {
          const team = await findGroupById(invite.groupId.toString(), { name: 1 });
          return { ...invite, teamName: team?.name } as InviteWithTeamName;
        }),
      );

      return res.status(200).json({ invites });
    } catch (error) {
      logger.error('[invites] listMine error:', error);
      return res.status(500).json({ error: 'Failed to list invites' });
    }
  }

  async function accept(req: ServerRequest, res: Response) {
    try {
      const { token } = req.params as TokenParams;
      const callerId = req.user?.id as string;
      const callerEmail = (req.user?.email as string).toLowerCase();

      const invite = await findInviteByToken(token);
      if (!invite) {
        return res.status(404).json({ error: 'Invite not found' });
      }

      if (!isCallerBound(invite, callerId, callerEmail)) {
        return res.status(403).json({ error: 'Forbidden' });
      }

      if (!isInviteValid(invite)) {
        return res.status(410).json({ error: 'Invite is no longer valid' });
      }

      await addTeamMember({
        groupId: invite.groupId.toString(),
        userId: callerId,
        role: invite.role,
      });
      await acceptInvite({ token, userId: callerId });

      const team = await findGroupById(invite.groupId.toString());
      return res.status(200).json({ team });
    } catch (error) {
      logger.error('[invites] accept error:', error);
      return res.status(500).json({ error: 'Failed to accept invite' });
    }
  }

  async function decline(req: ServerRequest, res: Response) {
    try {
      const { token } = req.params as TokenParams;
      const callerId = req.user?.id as string;
      const callerEmail = (req.user?.email as string).toLowerCase();

      const invite = await findInviteByToken(token);
      if (!invite) {
        return res.status(404).json({ error: 'Invite not found' });
      }

      if (!isCallerBound(invite, callerId, callerEmail)) {
        return res.status(403).json({ error: 'Forbidden' });
      }

      if (!isInviteValid(invite)) {
        return res.status(410).json({ error: 'Invite is no longer valid' });
      }

      await declineInvite({ token });
      return res.status(200).json({ success: true });
    } catch (error) {
      logger.error('[invites] decline error:', error);
      return res.status(500).json({ error: 'Failed to decline invite' });
    }
  }

  async function create(req: ServerRequest, res: Response) {
    try {
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

      const { email, role } = req.body as { email?: string; role?: string };

      if (!email || typeof email !== 'string' || !email.trim()) {
        return res.status(400).json({ error: 'email is required' });
      }
      if (!EMAIL_REGEX.test(email.trim())) {
        return res.status(400).json({ error: 'Invalid email format' });
      }
      if (role !== 'admin' && role !== 'member') {
        return res.status(400).json({ error: 'role must be "admin" or "member"' });
      }

      const invitedUser = await findUser({ email: email.trim() });
      const invitedUserId = invitedUser?._id ?? null;

      const invite = await createInvite({
        groupId: id,
        email: email.trim(),
        role,
        invitedBy: callerId,
        invitedUserId,
        tenantId: req.user?.tenantId,
      });

      if (deps.sendInviteEmail) {
        const inviterUser = await findUser({ email: req.user?.email as string });
        try {
          await deps.sendInviteEmail({
            email: email.trim(),
            token: invite.token,
            teamName: access.team.name,
            inviterName: inviterUser?.name ?? callerId,
          });
        } catch (emailError) {
          logger.warn('[invites] sendInviteEmail failed (best-effort):', emailError);
        }
      }

      return res.status(201).json({ invite });
    } catch (error) {
      logger.error('[invites] create error:', error);
      return res.status(500).json({ error: 'Failed to create invite' });
    }
  }

  async function listForTeam(req: ServerRequest, res: Response) {
    try {
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

      const rawInvites = await listInvitesForTeam({ groupId: id, status: 'pending' });

      const invites = rawInvites.map(({ token: _token, ...rest }) => rest);

      return res.status(200).json({ invites });
    } catch (error) {
      logger.error('[invites] listForTeam error:', error);
      return res.status(500).json({ error: 'Failed to list team invites' });
    }
  }

  async function revoke(req: ServerRequest, res: Response) {
    try {
      const { id, inviteId } = req.params as InviteParams;
      if (!isValidObjectIdString(id)) {
        return res.status(400).json({ error: 'Invalid team ID format' });
      }

      const callerId = req.user?.id as string;
      const access = await resolveTeamAccess(deps, id, callerId, 'admin');
      if (!access.ok) {
        const error = access.status === 403 ? 'Forbidden' : 'Team not found';
        return res.status(access.status).json({ error });
      }

      if (!isValidObjectIdString(inviteId)) {
        return res.status(400).json({ error: 'Invalid invite ID format' });
      }

      const revoked = await revokeInvite({ inviteId, groupId: id });
      if (!revoked) {
        return res.status(404).json({ error: 'Invite not found' });
      }

      return res.status(200).json({ success: true });
    } catch (error) {
      logger.error('[invites] revoke error:', error);
      return res.status(500).json({ error: 'Failed to revoke invite' });
    }
  }

  return { listMine, accept, decline, create, listForTeam, revoke };
}
