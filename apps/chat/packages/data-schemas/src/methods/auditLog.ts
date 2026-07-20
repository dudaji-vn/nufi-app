import type { FilterQuery, Model } from 'mongoose';
import logger from '~/config/winston';
import type { IAuditLog } from '~/types';

export interface AuditLogQuery {
  /** Free-text match against actorName, targetName, action, and details. */
  search?: string;
  /** Exact action key filter, e.g. 'grant_assigned'. */
  action?: string;
  /** 'admin' excludes guardrail_* actions; 'security' includes only them. */
  category?: 'admin' | 'security' | string;
  /** ISO date — inclusive lower bound on createdAt. */
  from?: string;
  /** ISO date — inclusive upper bound on createdAt (extended to end-of-day). */
  to?: string;
  /** Page size (1–1000, default 200). */
  limit?: number;
  /** Offset for pagination. */
  skip?: number;
}

export function createAuditLogMethods(mongoose: typeof import('mongoose')) {
  function buildFilter({ search, action, category, from, to }: AuditLogQuery): FilterQuery<IAuditLog> {
    const filter: FilterQuery<IAuditLog> = {};

    if (action) {
      filter.action = action;
    } else if (category === 'security') {
      filter.action = { $regex: /^guardrail_/ };
    } else if (category === 'admin') {
      filter.action = { $not: /^guardrail_/ };
    }

    if (from || to) {
      const range: Record<string, Date> = {};
      if (from) {
        range.$gte = new Date(from);
      }
      if (to) {
        const end = new Date(to);
        end.setHours(23, 59, 59, 999);
        range.$lte = end;
      }
      filter.createdAt = range;
    }

    if (search) {
      const escaped = search.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      const rx = new RegExp(escaped, 'i');
      filter.$or = [{ actorName: rx }, { targetName: rx }, { action: rx }, { details: rx }];
    }

    return filter;
  }

  /**
   * Append a single audit entry. Best-effort: a write failure is logged but never
   * thrown, so audit logging can never break the action being audited.
   */
  async function createAuditLog(entry: Partial<IAuditLog>): Promise<IAuditLog | null> {
    try {
      const AuditLog = mongoose.models.AuditLog as Model<IAuditLog>;
      return await AuditLog.create(entry);
    } catch (error) {
      logger.error('[createAuditLog] Failed to write audit entry', error);
      return null;
    }
  }

  /** List audit entries newest-first, with optional filters and pagination. */
  async function getAuditLogs(query: AuditLogQuery = {}): Promise<IAuditLog[]> {
    const AuditLog = mongoose.models.AuditLog as Model<IAuditLog>;
    const limit = Math.min(Math.max(query.limit ?? 200, 1), 1000);
    const skip = Math.max(query.skip ?? 0, 0);
    return (await AuditLog.find(buildFilter(query))
      .sort({ createdAt: -1 })
      .skip(skip)
      .limit(limit)
      .lean()) as unknown as IAuditLog[];
  }

  /** Count audit entries matching the filters (for pagination totals). */
  async function countAuditLogs(query: AuditLogQuery = {}): Promise<number> {
    const AuditLog = mongoose.models.AuditLog as Model<IAuditLog>;
    return AuditLog.countDocuments(buildFilter(query));
  }

  /** Count entries grouped by action within the filter (for summary strips). */
  async function getAuditLogCounts(query: AuditLogQuery = {}): Promise<Record<string, number>> {
    const AuditLog = mongoose.models.AuditLog as Model<IAuditLog>;
    const rows = await AuditLog.aggregate<{ _id: string; count: number }>([
      { $match: buildFilter(query) },
      { $group: { _id: '$action', count: { $sum: 1 } } },
    ]);
    const counts: Record<string, number> = {};
    for (const row of rows) {
      counts[row._id] = row.count;
    }
    return counts;
  }

  return { createAuditLog, getAuditLogs, countAuditLogs, getAuditLogCounts };
}

export type AuditLogMethods = ReturnType<typeof createAuditLogMethods>;
