import { Schema } from 'mongoose';
import type { ITeamInvite } from '~/types';

const teamInviteSchema = new Schema<ITeamInvite>(
  {
    groupId: {
      type: Schema.Types.ObjectId,
      ref: 'Group',
      required: true,
    },
    email: {
      type: String,
      required: true,
      lowercase: true,
    },
    invitedUserId: {
      type: Schema.Types.ObjectId,
      ref: 'User',
    },
    role: {
      type: String,
      enum: ['admin', 'member'],
      default: 'member',
      required: true,
    },
    token: {
      type: String,
      required: true,
    },
    status: {
      type: String,
      enum: ['pending', 'accepted', 'declined', 'expired', 'revoked'],
      default: 'pending',
    },
    invitedBy: {
      type: Schema.Types.ObjectId,
      ref: 'User',
      required: true,
    },
    expiresAt: {
      type: Date,
      required: true,
    },
    tenantId: {
      type: String,
      index: true,
    },
  },
  { timestamps: true },
);

teamInviteSchema.index({ token: 1 }, { unique: true });
teamInviteSchema.index({ email: 1, status: 1 });
teamInviteSchema.index({ groupId: 1, status: 1 });
teamInviteSchema.index({ invitedUserId: 1, status: 1 });
teamInviteSchema.index({ status: 1, expiresAt: 1 });

export default teamInviteSchema;
