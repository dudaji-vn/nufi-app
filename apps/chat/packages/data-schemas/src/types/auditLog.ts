import type { Document, Types } from 'mongoose';

/** Outcome of an audited administrative action. */
export type AuditStatus = 'success' | 'failure';

/**
 * Persisted audit log entry for an administrative action.
 *
 * Append-only: written by the recordAdminAction middleware and the admin login
 * handler, never updated or deleted through the application (WORM-style trail).
 */
export interface IAuditLog extends Document {
  /** Machine action key, e.g. 'user_deleted', 'grant_assigned', 'config_updated'. */
  action: string;
  /** User who performed the action. */
  actorId?: Types.ObjectId;
  /** Denormalised display name/email of the actor at write time. */
  actorName: string;
  /** Domain the action touched: 'user' | 'role' | 'group' | 'grant' | 'config'. */
  targetType?: string;
  /** Identifier of the affected resource, when applicable. */
  targetId?: string;
  /** Denormalised display name of the affected resource. */
  targetName?: string;
  /** Capability string, set for grant actions. */
  capability?: string;
  /** Human-readable summary of the change. */
  details?: string;
  /** HTTP method of the originating request. */
  method?: string;
  /** Request path of the originating request. */
  path?: string;
  /** Client IP address. */
  ipAddress?: string;
  /** Client user agent. */
  userAgent?: string;
  /** Outcome of the action. */
  status: AuditStatus;
  /** HTTP status code returned to the client. */
  statusCode?: number;
  createdAt?: Date;
  updatedAt?: Date;
}
