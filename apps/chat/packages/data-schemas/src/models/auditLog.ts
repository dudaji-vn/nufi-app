import type { Model } from 'mongoose';
import type { IAuditLog } from '~/types';
import auditLogSchema from '~/schema/auditLog';

export function createAuditLogModel(mongoose: typeof import('mongoose')) {
  return (
    (mongoose.models.AuditLog as Model<IAuditLog>) ||
    mongoose.model<IAuditLog>('AuditLog', auditLogSchema)
  );
}
