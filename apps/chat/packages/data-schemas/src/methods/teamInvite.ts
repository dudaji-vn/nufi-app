import crypto from 'node:crypto';
import type { FilterQuery, Model, Types } from 'mongoose';
import type { ITeamInvite, TeamInviteRole, TeamInviteStatus } from '~/types';

const DEFAULT_INVITE_TTL_MS = 7 * 24 * 60 * 60 * 1000;

export function createTeamInviteMethods(mongoose: typeof import('mongoose')) {
  function generateInviteToken(): string {
    return crypto.randomBytes(32).toString('hex');
  }

  async function createInvite(params: {
    groupId: string | Types.ObjectId;
    email: string;
    role: TeamInviteRole;
    invitedBy: string | Types.ObjectId;
    invitedUserId?: string | Types.ObjectId | null;
    tenantId?: string;
    ttlMs?: number;
  }): Promise<ITeamInvite> {
    const TeamInvite = mongoose.models.TeamInvite as Model<ITeamInvite>;
    const ttl = params.ttlMs ?? DEFAULT_INVITE_TTL_MS;
    return await TeamInvite.create({
      groupId: params.groupId,
      email: params.email.toLowerCase().trim(),
      role: params.role,
      invitedBy: params.invitedBy,
      invitedUserId: params.invitedUserId ?? undefined,
      tenantId: params.tenantId,
      token: generateInviteToken(),
      status: 'pending',
      expiresAt: new Date(Date.now() + ttl),
    });
  }

  async function findInviteByToken(token: string): Promise<ITeamInvite | null> {
    const TeamInvite = mongoose.models.TeamInvite as Model<ITeamInvite>;
    return await TeamInvite.findOne({ token }).lean<ITeamInvite>();
  }

  async function listPendingInvitesForUser(params: {
    userId?: string | Types.ObjectId;
    email?: string;
  }): Promise<ITeamInvite[]> {
    const TeamInvite = mongoose.models.TeamInvite as Model<ITeamInvite>;
    const or: FilterQuery<ITeamInvite>[] = [];
    if (params.userId) {
      or.push({ invitedUserId: params.userId });
    }
    if (params.email) {
      or.push({ email: params.email.toLowerCase().trim() });
    }
    if (or.length === 0) {
      return [];
    }
    return await TeamInvite.find({
      status: 'pending',
      expiresAt: { $gt: new Date() },
      $or: or,
    }).lean<ITeamInvite[]>();
  }

  async function listInvitesForTeam(params: {
    groupId: string | Types.ObjectId;
    status?: TeamInviteStatus;
  }): Promise<ITeamInvite[]> {
    const TeamInvite = mongoose.models.TeamInvite as Model<ITeamInvite>;
    const filter: FilterQuery<ITeamInvite> = { groupId: params.groupId };
    if (params.status) {
      filter.status = params.status;
    }
    return await TeamInvite.find(filter).lean<ITeamInvite[]>();
  }

  async function acceptInvite(params: {
    token: string;
    userId: string | Types.ObjectId;
  }): Promise<ITeamInvite | null> {
    const TeamInvite = mongoose.models.TeamInvite as Model<ITeamInvite>;
    return await TeamInvite.findOneAndUpdate(
      { token: params.token, status: 'pending', expiresAt: { $gt: new Date() } },
      { $set: { status: 'accepted', invitedUserId: params.userId } },
      { new: true },
    ).lean<ITeamInvite>();
  }

  async function declineInvite(params: { token: string }): Promise<ITeamInvite | null> {
    const TeamInvite = mongoose.models.TeamInvite as Model<ITeamInvite>;
    return await TeamInvite.findOneAndUpdate(
      { token: params.token, status: 'pending' },
      { $set: { status: 'declined' } },
      { new: true },
    ).lean<ITeamInvite>();
  }

  async function revokeInvite(params: {
    inviteId: string | Types.ObjectId;
    groupId?: string | Types.ObjectId;
  }): Promise<ITeamInvite | null> {
    const TeamInvite = mongoose.models.TeamInvite as Model<ITeamInvite>;
    const filter: FilterQuery<ITeamInvite> = { _id: params.inviteId, status: 'pending' };
    if (params.groupId) {
      filter.groupId = params.groupId;
    }
    return await TeamInvite.findOneAndUpdate(
      filter,
      { $set: { status: 'revoked' } },
      { new: true },
    ).lean<ITeamInvite>();
  }

  async function expireStaleInvites(): Promise<number> {
    const TeamInvite = mongoose.models.TeamInvite as Model<ITeamInvite>;
    const result = await TeamInvite.updateMany(
      { status: 'pending', expiresAt: { $lte: new Date() } },
      { $set: { status: 'expired' } },
    );
    return result.modifiedCount ?? 0;
  }

  async function deleteInvitesByGroup(params: {
    groupId: string | Types.ObjectId;
  }): Promise<number> {
    const TeamInvite = mongoose.models.TeamInvite as Model<ITeamInvite>;
    const result = await TeamInvite.deleteMany({ groupId: params.groupId });
    return result.deletedCount ?? 0;
  }

  return {
    createInvite,
    findInviteByToken,
    listPendingInvitesForUser,
    listInvitesForTeam,
    acceptInvite,
    declineInvite,
    revokeInvite,
    expireStaleInvites,
    deleteInvitesByGroup,
  };
}

export type TeamInviteMethods = ReturnType<typeof createTeamInviteMethods>;
