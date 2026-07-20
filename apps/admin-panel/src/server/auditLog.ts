/**
 * Server functions for the admin audit log.
 *
 * Calls the LibreChat Admin API (/api/admin/audit-log) for the filtered list
 * and (/api/admin/audit-log/export) for a CSV compliance export.
 */

import { z } from 'zod';
import { queryOptions } from '@tanstack/react-query';
import { createServerFn } from '@tanstack/react-start';
import type { AuditLogEntry } from '@/types';
import { apiFetch, extractApiError } from './utils/api';

const auditFilterSchema = z.object({
  search: z.string().optional(),
  /** Any AuditAction key, or omitted for "all". Kept loose so new actions work. */
  action: z.string().optional(),
  /** ISO date (YYYY-MM-DD) inclusive lower bound. */
  from: z.string().optional(),
  /** ISO date (YYYY-MM-DD) inclusive upper bound. */
  to: z.string().optional(),
});

export type AuditFilters = z.infer<typeof auditFilterSchema>;

function buildQuery(filters: AuditFilters): string {
  const params = new URLSearchParams();
  if (filters.search) params.set('search', filters.search);
  if (filters.action) params.set('action', filters.action);
  if (filters.from) params.set('from', filters.from);
  if (filters.to) params.set('to', filters.to);
  const qs = params.toString();
  return qs ? `?${qs}` : '';
}

export const getAuditLogFn = createServerFn({ method: 'GET' })
  .inputValidator(auditFilterSchema)
  .handler(async ({ data }): Promise<{ entries: AuditLogEntry[]; total: number }> => {
    const response = await apiFetch(`/api/admin/audit-log${buildQuery(data)}`);
    if (!response.ok) {
      await extractApiError(response, 'Failed to load audit log');
    }
    const json = (await response.json()) as { entries?: AuditLogEntry[]; total?: number };
    return { entries: json.entries ?? [], total: json.total ?? 0 };
  });

/** Returns the entries array directly, matching the shape consumers expect. */
export const auditLogQueryOptions = (filters: AuditFilters = {}) =>
  queryOptions<AuditLogEntry[]>({
    queryKey: ['auditLog', filters],
    queryFn: () => getAuditLogFn({ data: filters }).then((r) => r.entries),
    staleTime: 30_000,
  });

export const exportAuditLogCsvFn = createServerFn({ method: 'POST' })
  .inputValidator(auditFilterSchema)
  .handler(async ({ data }): Promise<{ csv: string }> => {
    const response = await apiFetch(`/api/admin/audit-log/export${buildQuery(data)}`);
    if (!response.ok) {
      await extractApiError(response, 'Failed to export audit log');
    }
    const csv = await response.text();
    return { csv };
  });
