import { logger } from '@librechat/data-schemas';
import { extractEnvVariable } from 'librechat-data-provider';
import type { AppConfig, ILiteLLMSync } from '@librechat/data-schemas';
import { getLiteLLMConfig, createLiteLLMClient } from './client';
import { createReconciler, type EndpointInput, type ReconcilerDb } from './reconcile';
import { createEndpointRewriter } from './rewrite';
import { isSameHost } from './naming';
import { selectSyncModels } from './models';

/**
 * Wires the LiteLLM client + reconciler + rewriter into the three seams the
 * fork consumes: a reconcile hook (admin writes), a rewrite function
 * (getAppConfig), and a manual resync. All are no-ops when the feature is off.
 */

export interface LiteLLMGatewayDeps {
  db: ReconcilerDb & {
    findLiteLLMSyncByEndpointNames: (names: string[]) => Promise<ILiteLLMSync[]>;
  };
  encrypt: (value: string) => string;
  decrypt: (value: string) => string;
  /** Run fn inside the given tenant's ALS context (or as-is when undefined). */
  runInTenant: <T>(tenantId: string | undefined, fn: () => Promise<T>) => Promise<T>;
  /** Read the raw (un-rewritten) custom endpoints from the base config override. */
  getRawCustomEndpoints?: (params: { tenantId?: string }) => Promise<unknown[]>;
  /** Override the provider model-discovery call (tests). */
  discoverModels?: (baseURL: string, apiKey: string) => Promise<string[]>;
}

interface RawEndpoint {
  name?: unknown;
  baseURL?: unknown;
  apiKey?: unknown;
  models?: { default?: unknown; fetch?: unknown } & Record<string, unknown>;
}

/** Per-endpoint sync status surfaced to the admin panel (no secrets). */
export interface EndpointSyncStatus {
  status: 'pending' | 'active' | 'failed';
  modelCount: number;
  lastError: string | null;
  /** ISO timestamp of the last successful sync, or null. */
  lastSyncedAt: string | null;
}

export interface LiteLLMStatusResult {
  enabled: boolean;
  statuses: Record<string, EndpointSyncStatus>;
}

async function defaultDiscoverModels(baseURL: string, apiKey: string): Promise<string[]> {
  try {
    const res = await fetch(`${baseURL.replace(/\/+$/, '')}/models`, {
      headers: { Authorization: `Bearer ${apiKey}` },
      signal: AbortSignal.timeout(10_000),
    });
    if (!res.ok) {
      return [];
    }
    const body = (await res.json()) as { data?: Array<{ id?: string }> };
    return (body.data ?? []).map((m) => m.id).filter((id): id is string => !!id);
  } catch (err) {
    logger.error('[litellm] provider model discovery failed:', err);
    return [];
  }
}

export function createLiteLLMGateway(deps: LiteLLMGatewayDeps) {
  const { db, encrypt, decrypt, runInTenant, getRawCustomEndpoints } = deps;
  const discoverModels = deps.discoverModels ?? defaultDiscoverModels;

  async function mapToEndpointInput(raw: RawEndpoint): Promise<EndpointInput | null> {
    const name = typeof raw.name === 'string' ? raw.name : '';
    const baseURL = extractEnvVariable(typeof raw.baseURL === 'string' ? raw.baseURL : '');
    const apiKey = extractEnvVariable(typeof raw.apiKey === 'string' ? raw.apiKey : '');
    if (!name || !baseURL || !apiKey) {
      return null;
    }
    // An endpoint already pointing at the gateway must not be proxied through
    // the gateway a second time — that only adds a hop and makes LiteLLM call
    // itself. Returning null leaves it unmanaged, so the rewriter passes it
    // through untouched, which is already the routing we want.
    const cfg = getLiteLLMConfig();
    if (cfg && isSameHost(baseURL, cfg.baseURL)) {
      logger.info(`[litellm] endpoint "${name}" already targets the gateway — skipping sync.`);
      return null;
    }

    const declared = Array.isArray(raw.models?.default)
      ? (raw.models!.default as unknown[]).filter((m): m is string => typeof m === 'string')
      : [];
    const shouldFetch = raw.models?.fetch !== false;
    const discovered = shouldFetch ? await discoverModels(baseURL, apiKey) : [];
    const models = selectSyncModels({ declared, discovered, fetch: shouldFetch });
    return { name, baseURL, apiKey, models };
  }

  async function toInputs(customEndpoints: unknown[]): Promise<EndpointInput[]> {
    const inputs: EndpointInput[] = [];
    for (const raw of customEndpoints ?? []) {
      const input = await mapToEndpointInput(raw as RawEndpoint);
      if (input) {
        inputs.push(input);
      }
    }
    return inputs;
  }

  /** Build a reconciler bound to the live LiteLLM config, or null when off. */
  function buildReconciler() {
    const cfg = getLiteLLMConfig();
    if (!cfg) {
      return null;
    }
    const client = createLiteLLMClient(cfg);
    return createReconciler({ client, db, encrypt, decrypt });
  }

  async function reconcileLiteLLM(params: {
    tenantId?: string;
    customEndpoints: unknown[];
  }): Promise<void> {
    const reconciler = buildReconciler();
    if (!reconciler) {
      return;
    }
    await runInTenant(params.tenantId, async () => {
      const inputs = await toInputs(params.customEndpoints);
      await reconciler.reconcileEndpoints({ customEndpoints: inputs });
    });
  }

  const rewriter = createEndpointRewriter({
    db: { findLiteLLMSyncByEndpointNames: db.findLiteLLMSyncByEndpointNames },
    decrypt,
    getConfig: getLiteLLMConfig,
  });

  async function applyEndpointRewrite(
    config: AppConfig,
    opts: { tenantId?: string },
  ): Promise<AppConfig> {
    return runInTenant(opts.tenantId, () => rewriter(config, opts));
  }

  /** Re-run reconcile from the current raw base-config endpoints (recovery). */
  async function resyncAll(params: { tenantId?: string }): Promise<void> {
    const cfg = getLiteLLMConfig();
    if (!cfg || !getRawCustomEndpoints) {
      return;
    }
    const raw = await runInTenant(params.tenantId, () =>
      getRawCustomEndpoints({ tenantId: params.tenantId }),
    );
    await reconcileLiteLLM({ tenantId: params.tenantId, customEndpoints: raw });
  }

  /** Re-sync a single endpoint by name, leaving other managed endpoints untouched. */
  async function resyncEndpoint(params: { tenantId?: string; name: string }): Promise<void> {
    const reconciler = buildReconciler();
    if (!reconciler || !getRawCustomEndpoints) {
      return;
    }
    await runInTenant(params.tenantId, async () => {
      const raw = await getRawCustomEndpoints({ tenantId: params.tenantId });
      const match = (raw ?? []).find((e) => (e as RawEndpoint)?.name === params.name);
      if (!match) {
        return;
      }
      const input = await mapToEndpointInput(match as RawEndpoint);
      if (!input) {
        return;
      }
      await reconciler.reconcileEndpoints({ customEndpoints: [input], prune: false });
    });
  }

  /** Per-endpoint sync status for the admin panel. Secrets are never included. */
  async function getStatus(params: { tenantId?: string }): Promise<LiteLLMStatusResult> {
    const cfg = getLiteLLMConfig();
    if (!cfg) {
      return { enabled: false, statuses: {} };
    }
    const records = await runInTenant(params.tenantId, () => db.listLiteLLMSync());
    const statuses: Record<string, EndpointSyncStatus> = {};
    for (const r of records) {
      statuses[r.endpointName] = {
        status: r.status,
        modelCount: r.models?.length ?? 0,
        lastError: r.lastError ?? null,
        lastSyncedAt: r.lastSyncedAt ? new Date(r.lastSyncedAt).toISOString() : null,
      };
    }
    return { enabled: true, statuses };
  }

  return { reconcileLiteLLM, applyEndpointRewrite, resyncAll, resyncEndpoint, getStatus };
}

export type LiteLLMGateway = ReturnType<typeof createLiteLLMGateway>;
