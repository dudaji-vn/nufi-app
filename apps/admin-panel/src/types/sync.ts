/** LiteLLM gateway per-endpoint sync status (mirrors the backend, no secrets). */
export interface EndpointSyncStatus {
  status: 'pending' | 'active' | 'failed';
  modelCount: number;
  lastError: string | null;
  /** ISO timestamp of the last successful sync, or null. */
  lastSyncedAt: string | null;
}

export interface LiteLLMStatusResult {
  /** False when LITELLM_SYNC_ENABLED is off — the panel then hides sync UI. */
  enabled: boolean;
  /** Keyed by custom-endpoint name. */
  statuses: Record<string, EndpointSyncStatus>;
}
