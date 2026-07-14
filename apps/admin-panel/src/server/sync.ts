import { z } from 'zod';
import { queryOptions } from '@tanstack/react-query';
import { createServerFn } from '@tanstack/react-start';
import type * as t from '@/types';
import { apiFetch, extractApiError } from './utils/api';

/** Fetch per-endpoint LiteLLM sync status. Returns { enabled:false } when off. */
export const getEndpointSyncStatusFn = createServerFn({ method: 'GET' }).handler(async () => {
  const response = await apiFetch('/api/admin/litellm/status');
  if (!response.ok) {
    return extractApiError(response, 'Failed to fetch LiteLLM sync status');
  }
  return (await response.json()) as t.LiteLLMStatusResult;
});

export const endpointSyncStatusOptions = queryOptions({
  queryKey: ['endpointSyncStatus'],
  queryFn: () => getEndpointSyncStatusFn(),
  staleTime: 30_000,
});

/** Trigger a re-sync of a single endpoint by name. */
export const resyncEndpointFn = createServerFn({ method: 'POST' })
  .inputValidator(z.object({ name: z.string().min(1) }))
  .handler(async ({ data }) => {
    const response = await apiFetch('/api/admin/litellm/resync', {
      method: 'POST',
      body: JSON.stringify({ name: data.name }),
    });
    if (!response.ok) {
      return extractApiError(response, 'Failed to re-sync endpoint');
    }
    return { success: true } as const;
  });
