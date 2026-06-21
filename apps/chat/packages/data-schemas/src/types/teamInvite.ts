import type { Document, Types } from 'mongoose';

export type TeamInviteStatus = 'pending' | 'accepted' | 'declined' | 'expired' | 'revoked';
export type TeamInviteRole = 'admin' | 'member';

/** A pending/historical invitation for a user to join a team. */
export interface ITeamInvite extends Document {
  _id: Types.ObjectId;
  /** The team (Group with kind 'team') being joined. */
  groupId: Types.ObjectId;
  /** Invitee email, stored lowercased. */
  email: string;
  /** Resolved invitee user id, when the email maps to an existing account. */
  invitedUserId?: Types.ObjectId;
  role: TeamInviteRole;
  /** Single-use, high-entropy token (unique). */
  token: string;
  status: TeamInviteStatus;
  invitedBy: Types.ObjectId;
  expiresAt: Date;
  tenantId?: string;
  createdAt?: Date;
  updatedAt?: Date;
}
