import { Schema } from 'mongoose';
import type { IGroup, IGroupMember } from '~/types';

const groupMemberSchema = new Schema<IGroupMember>(
  {
    userId: {
      type: Schema.Types.ObjectId,
      ref: 'User',
      required: true,
    },
    role: {
      type: String,
      enum: ['owner', 'admin', 'member'],
      default: 'member',
      required: true,
    },
    joinedAt: {
      type: Date,
      default: Date.now,
    },
  },
  { _id: false },
);

const groupSchema = new Schema<IGroup>(
  {
    name: {
      type: String,
      required: true,
      index: true,
    },
    description: {
      type: String,
      required: false,
    },
    email: {
      type: String,
      required: false,
      index: true,
    },
    avatar: {
      type: String,
      required: false,
    },
    memberIds: [
      {
        type: String,
        required: false,
      },
    ],
    source: {
      type: String,
      enum: ['local', 'entra'],
      default: 'local',
    },
    /** External ID (e.g., Entra ID) */
    idOnTheSource: {
      type: String,
      sparse: true,
      index: true,
      required: function (this: IGroup) {
        return this.source !== 'local';
      },
    },
    tenantId: {
      type: String,
      index: true,
    },
    kind: {
      type: String,
      enum: ['group', 'team', 'team_subgroup'],
      default: 'group',
      index: true,
    },
    parentTeamId: {
      type: Schema.Types.ObjectId,
      ref: 'Group',
      index: true,
    },
    ownerId: {
      type: Schema.Types.ObjectId,
      ref: 'User',
      index: true,
    },
    members: {
      type: [groupMemberSchema],
      default: undefined,
    },
    joinPolicy: {
      type: String,
      enum: ['invite'],
      default: 'invite',
    },
  },
  { timestamps: true },
);

groupSchema.index(
  { idOnTheSource: 1, source: 1, tenantId: 1 },
  {
    unique: true,
    partialFilterExpression: { idOnTheSource: { $exists: true } },
  },
);
groupSchema.index({ memberIds: 1 });
groupSchema.index({ 'members.userId': 1 });
groupSchema.index({ ownerId: 1, kind: 1 });

export default groupSchema;
