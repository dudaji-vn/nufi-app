import { Schema } from 'mongoose';
import type { IAuditLog } from '~/types';

/**
 * Append-only audit trail of administrative actions. Entries are written by the
 * recordAdminAction middleware and the admin login handler; the application
 * never updates or deletes them (WORM-style retention). Compliance tooling can
 * enforce true immutability at the storage layer on top of this collection.
 */
const auditLogSchema = new Schema<IAuditLog>(
  {
    action: {
      type: String,
      required: true,
      index: true,
    },
    actorId: {
      type: Schema.Types.ObjectId,
      ref: 'User',
    },
    actorName: {
      type: String,
      required: true,
    },
    targetType: {
      type: String,
    },
    targetId: {
      type: String,
    },
    targetName: {
      type: String,
    },
    capability: {
      type: String,
    },
    details: {
      type: String,
    },
    method: {
      type: String,
    },
    path: {
      type: String,
    },
    ipAddress: {
      type: String,
    },
    userAgent: {
      type: String,
    },
    status: {
      type: String,
      enum: ['success', 'failure'],
      default: 'success',
    },
    statusCode: {
      type: Number,
    },
    metadata: {
      type: Schema.Types.Mixed,
    },
  },
  { timestamps: true },
);

/* Most reads are newest-first, optionally filtered by action. */
auditLogSchema.index({ createdAt: -1 });
auditLogSchema.index({ action: 1, createdAt: -1 });

export default auditLogSchema;
