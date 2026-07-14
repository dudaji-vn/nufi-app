import { logger } from '@librechat/data-schemas';
import type { ILiteLLMSync, LiteLLMSync, LiteLLMSyncModel } from '@librechat/data-schemas';
import { litellmModelName, providerModel, credFingerprint, keyAlias } from './naming';
import type { LiteLLMClient } from './client';

/** The desired state for one endpoint, resolved from the admin config. */
export interface EndpointInput {
  name: string;
  baseURL: string;
  apiKey: string;
  /** Raw model ids to expose (already resolved by the caller from models.default). */
  models: string[];
}

export interface ReconcilerDb {
  findLiteLLMSyncByEndpointName: (name: string) => Promise<ILiteLLMSync | null>;
  upsertLiteLLMSync: (
    name: string,
    patch: Partial<LiteLLMSync>,
  ) => Promise<ILiteLLMSync | null>;
  deleteLiteLLMSyncByEndpointName: (name: string) => Promise<ILiteLLMSync | null>;
  listLiteLLMSync: () => Promise<ILiteLLMSync[]>;
}

export interface ReconcilerDeps {
  client: LiteLLMClient;
  db: ReconcilerDb;
  encrypt: (value: string) => string;
  decrypt: (value: string) => string;
}

export function createReconciler(deps: ReconcilerDeps) {
  const { client, db, encrypt, decrypt } = deps;

  async function reconcileOne(ep: EndpointInput): Promise<void> {
    // Mark managed immediately so the runtime rewrite treats it fail-closed even
    // if the steps below throw.
    const record = await db.upsertLiteLLMSync(ep.name, { status: 'pending' });

    if (!ep.models || ep.models.length === 0) {
      await db.upsertLiteLLMSync(ep.name, {
        status: 'failed',
        lastError:
          'No models configured for this endpoint. Add explicit models so they can be registered in LiteLLM.',
      });
      return;
    }

    const existing: LiteLLMSyncModel[] = record?.models ?? [];
    const existingBySource = new Map(existing.map((m) => [m.sourceModel, m]));
    const desired = new Set(ep.models);

    const fingerprint = credFingerprint(ep.baseURL, ep.apiKey);
    const drifted = record?.realBaseURLHash !== fingerprint;

    const nextModels: LiteLLMSyncModel[] = [];

    // Remove models no longer desired.
    for (const m of existing) {
      if (!desired.has(m.sourceModel) && m.litellmModelId) {
        try {
          await client.modelDelete(m.litellmModelId);
        } catch (err) {
          logger.error(`[litellm] modelDelete failed for ${m.litellmModelName}:`, err);
        }
      }
    }

    // Add new / update kept models.
    for (const sourceModel of ep.models) {
      const modelName = litellmModelName(ep.name, sourceModel);
      const prior = existingBySource.get(sourceModel);
      if (!prior) {
        const { modelId } = await client.modelNew({
          modelName,
          providerModel: providerModel(sourceModel),
          apiBase: ep.baseURL,
          apiKey: ep.apiKey,
        });
        nextModels.push({ sourceModel, litellmModelName: modelName, litellmModelId: modelId });
      } else {
        if (drifted && prior.litellmModelId) {
          await client.modelUpdate({
            modelId: prior.litellmModelId,
            providerModel: providerModel(sourceModel),
            apiBase: ep.baseURL,
            apiKey: ep.apiKey,
          });
        }
        nextModels.push(prior);
      }
    }

    // Virtual key: create once, then keep its allow-list in sync.
    const allowedNames = nextModels.map((m) => m.litellmModelName);
    let virtualKey = record?.virtualKey;
    if (virtualKey) {
      await client.keyUpdate({ key: decrypt(virtualKey), models: allowedNames });
    } else {
      const { key } = await client.keyGenerate({
        models: allowedNames,
        keyAlias: keyAlias(ep.name),
        metadata: { endpoint: ep.name },
      });
      virtualKey = encrypt(key);
    }

    await db.upsertLiteLLMSync(ep.name, {
      status: 'active',
      virtualKey,
      models: nextModels,
      realBaseURLHash: fingerprint,
      lastError: null,
      lastSyncedAt: new Date(),
    });
  }

  /**
   * Converge LiteLLM to the given set of endpoints. Best-effort per endpoint:
   * a failure marks that endpoint `failed` (fail-closed) and does not abort the
   * others. When `prune` is not false, endpoints previously synced but absent
   * here are torn down — pass `prune: false` for a single-endpoint resync so the
   * other managed endpoints are left untouched.
   */
  async function reconcileEndpoints(params: {
    customEndpoints: EndpointInput[];
    prune?: boolean;
  }): Promise<void> {
    const endpoints = params.customEndpoints ?? [];
    for (const ep of endpoints) {
      try {
        await reconcileOne(ep);
      } catch (err) {
        logger.error(`[litellm] reconcile failed for endpoint "${ep.name}":`, err);
        await db
          .upsertLiteLLMSync(ep.name, {
            status: 'failed',
            lastError: String((err as Error)?.message ?? err),
          })
          .catch(() => undefined);
      }
    }
    if (params.prune !== false) {
      await unsyncMissing(endpoints.map((e) => e.name));
    }
  }

  /** Tear down one endpoint's LiteLLM models + virtual key, then drop its record. */
  async function unsyncEndpoint(name: string): Promise<void> {
    const record = await db.findLiteLLMSyncByEndpointName(name);
    if (!record) {
      return;
    }
    for (const m of record.models ?? []) {
      if (m.litellmModelId) {
        try {
          await client.modelDelete(m.litellmModelId);
        } catch (err) {
          logger.error(`[litellm] modelDelete failed while unsyncing ${m.litellmModelName}:`, err);
        }
      }
    }
    if (record.virtualKey) {
      try {
        await client.keyDelete(decrypt(record.virtualKey));
      } catch (err) {
        logger.error(`[litellm] keyDelete failed while unsyncing ${name}:`, err);
      }
    }
    await db.deleteLiteLLMSyncByEndpointName(name);
  }

  /** Unsync any managed endpoint whose name is not in `keepNames`. */
  async function unsyncMissing(keepNames: string[]): Promise<void> {
    const keep = new Set(keepNames);
    const records = await db.listLiteLLMSync();
    for (const record of records) {
      if (!keep.has(record.endpointName)) {
        await unsyncEndpoint(record.endpointName);
      }
    }
  }

  return { reconcileEndpoints, unsyncEndpoint, unsyncMissing };
}

export type Reconciler = ReturnType<typeof createReconciler>;
