import type { Model } from 'mongoose';
import type { ITeamInvite } from '~/types';
import teamInviteSchema from '~/schema/teamInvite';

export function createTeamInviteModel(mongoose: typeof import('mongoose')) {
  return (
    (mongoose.models.TeamInvite as Model<ITeamInvite>) ||
    mongoose.model<ITeamInvite>('TeamInvite', teamInviteSchema)
  );
}
