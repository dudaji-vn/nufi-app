import type { Model } from 'mongoose';
import type { ITeamInvite } from '~/types';
import teamInviteSchema from '~/schema/teamInvite';
import { applyTenantIsolation } from '~/models/plugins/tenantIsolation';

export function createTeamInviteModel(mongoose: typeof import('mongoose')) {
  applyTenantIsolation(teamInviteSchema);
  return (
    (mongoose.models.TeamInvite as Model<ITeamInvite>) ||
    mongoose.model<ITeamInvite>('TeamInvite', teamInviteSchema)
  );
}
