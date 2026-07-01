/**
 * Server functions for the admin Security events page. Reads the shared
 * audit-log endpoint scoped to guardrail events (category=security), plus its
 * per-action counts for the summary strip.
 */

import { z } from 'zod';
import { queryOptions } from '@tanstack/react-query';
import { createServerFn } from '@tanstack/react-start';
import type { SecurityEvent } from '@/types';
import { apiFetch, extractApiError } from './utils/api';

const securityFilterSchema = z.object({
  search: z.string().optional(),
  /** A guardrail_* action key, or omitted for "all". */
  action: z.string().optional(),
  from: z.string().optional(),
  to: z.string().optional(),
});

export type SecurityFilters = z.infer<typeof securityFilterSchema>;

export interface SecurityEventsResult {
  entries: SecurityEvent[];
  total: number;
  countsByAction: Record<string, number>;
}

function buildQuery(filters: SecurityFilters): string {
  const params = new URLSearchParams();
  params.set('category', 'security');
  if (filters.search) params.set('search', filters.search);
  if (filters.action) params.set('action', filters.action);
  if (filters.from) params.set('from', filters.from);
  if (filters.to) params.set('to', filters.to);
  return `?${params.toString()}`;
}

export const getSecurityEventsFn = createServerFn({ method: 'GET' })
  .inputValidator(securityFilterSchema)
  .handler(async ({ data }): Promise<SecurityEventsResult> => {
    const response = await apiFetch(`/api/admin/audit-log${buildQuery(data)}`);
    if (!response.ok) {
      await extractApiError(response, 'Failed to load security events');
    }
    const json = (await response.json()) as Partial<SecurityEventsResult>;
    return {
      entries: json.entries ?? [],
      total: json.total ?? 0,
      countsByAction: json.countsByAction ?? {},
    };
  });

export const securityEventsQueryOptions = (filters: SecurityFilters = {}) =>
  queryOptions<SecurityEventsResult>({
    queryKey: ['securityEvents', filters],
    queryFn: () => getSecurityEventsFn({ data: filters }),
    staleTime: 30_000,
  });

export const exportSecurityEventsCsvFn = createServerFn({ method: 'POST' })
  .inputValidator(securityFilterSchema)
  .handler(async ({ data }): Promise<{ csv: string }> => {
    const response = await apiFetch(`/api/admin/audit-log/export${buildQuery(data)}`);
    if (!response.ok) {
      await extractApiError(response, 'Failed to export security events');
    }
    const csv = await response.text();
    return { csv };
  });
