import type { Document, Types } from 'mongoose';
import { CursorPaginationParams } from '~/common';

export type TeamRole = 'owner' | 'admin' | 'member';
export type GroupKind = 'group' | 'team' | 'team_subgroup';

export interface IGroupMember {
  userId: Types.ObjectId;
  role: TeamRole;
  joinedAt: Date;
}

export interface IGroup extends Document {
  _id: Types.ObjectId;
  name: string;
  description?: string;
  email?: string;
  avatar?: string;
  /** Array of member IDs (stores idOnTheSource values, not ObjectIds) */
  memberIds?: string[];
  source: 'local' | 'entra';
  /** External ID (e.g., Entra ID) - required for non-local sources */
  idOnTheSource?: string;
  createdAt?: Date;
  updatedAt?: Date;
  tenantId?: string;
  /** 'team' = self-service workspace; 'group' = admin/Entra group (default); 'team_subgroup' = sub-group within a team. */
  kind?: GroupKind;
  /** The single team owner. Always equals a member whose role is 'owner'. */
  ownerId?: Types.ObjectId;
  /** Parent team ID for sub-groups (kind='team_subgroup'). */
  parentTeamId?: Types.ObjectId;
  /** Per-member roles for teams. Source of truth for role; kept in sync with memberIds. */
  members?: IGroupMember[];
  joinPolicy?: 'invite';
}

export interface CreateGroupRequest {
  name: string;
  description?: string;
  email?: string;
  avatar?: string;
  memberIds?: string[];
  source: 'local' | 'entra';
  idOnTheSource?: string;
}

export interface UpdateGroupRequest {
  name?: string;
  description?: string;
  email?: string;
  avatar?: string;
  memberIds?: string[];
  source?: 'local' | 'entra' | 'ldap';
  idOnTheSource?: string;
}

export interface GroupFilterOptions extends CursorPaginationParams {
  // Includes email, name and description
  search?: string;
  source?: 'local' | 'entra' | 'ldap';
  hasMember?: string;
}
