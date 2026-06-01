/**
 * Audit log entry as returned by the NUFI admin audit-log endpoint
 * (`/api/admin/audit-log`). Defined locally rather than imported from
 * `@librechat/data-schemas` so the panel is decoupled from the data-schemas
 * publish cycle: the installed version still types `AdminAuditLogEntry` as the
 * grant-only shape, while the endpoint returns the full admin audit shape.
 */
export interface AuditLogEntry {
  id: string;
  /** Action key, e.g. 'user_created', 'grant_assigned', 'config_updated'. */
  action: string;
  actorId: string;
  actorName: string;
  /** Domain the action touched: 'user' | 'role' | 'group' | 'grant' | 'config'. */
  targetType?: string;
  targetId?: string;
  targetName?: string;
  /** Capability string, set for grant actions. */
  capability?: string;
  /** Human-readable summary of the change. */
  details?: string;
  ipAddress?: string;
  status?: 'success' | 'failure';
  timestamp: string;
}
