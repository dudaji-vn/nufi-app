import { logger } from '@librechat/data-schemas';

/**
 * Thin wrapper over the LiteLLM proxy admin API (v1.83.x). All admin calls
 * authenticate with the master key. Used by the reconciler to register/update/
 * delete models and mint per-endpoint virtual keys.
 *
 * NEVER log the master key or any virtual key.
 */

export interface LiteLLMConfig {
  enabled: boolean;
  /** Root base URL with any trailing slash and trailing `/v1` stripped. */
  baseURL: string;
  masterKey: string;
}

const REQUEST_TIMEOUT_MS = 15_000;

/**
 * Normalize a LiteLLM base URL to its root (no trailing slash, no `/v1`).
 * Admin routes live at the root (`/model/new`); the OpenAI-compatible chat API
 * lives under `/v1`. The runtime rewrite appends `/v1` back for chat/model calls.
 */
export function normalizeBaseURL(raw: string): string {
  let url = (raw ?? '').trim().replace(/\/+$/, '');
  url = url.replace(/\/v1$/, '');
  return url;
}

/**
 * Read the LiteLLM gateway config from env. Returns null when the feature is
 * disabled or misconfigured (missing base URL / master key) — callers treat
 * null as "feature off" and no-op.
 */
export function getLiteLLMConfig(): LiteLLMConfig | null {
  if (process.env.LITELLM_SYNC_ENABLED !== 'true') {
    return null;
  }
  const baseURL = normalizeBaseURL(process.env.LITELLM_BASE_URL ?? '');
  const masterKey = (process.env.LITELLM_MASTER_KEY ?? '').trim();
  if (!baseURL || !masterKey) {
    logger.warn(
      '[litellm] LITELLM_SYNC_ENABLED=true but LITELLM_BASE_URL or LITELLM_MASTER_KEY is empty — gateway sync disabled.',
    );
    return null;
  }
  return { enabled: true, baseURL, masterKey };
}

export class LiteLLMError extends Error {
  status?: number;
  body?: string;
  constructor(message: string, status?: number, body?: string) {
    super(message);
    this.name = 'LiteLLMError';
    this.status = status;
    this.body = body;
  }
}

export interface ModelNewParams {
  modelName: string;
  providerModel: string;
  apiBase: string;
  apiKey: string;
}

export interface ModelUpdateParams {
  modelId: string;
  providerModel: string;
  apiBase: string;
  apiKey: string;
}

export interface KeyGenerateParams {
  models: string[];
  keyAlias: string;
  metadata: Record<string, unknown>;
}

export interface LiteLLMModelInfo {
  modelName: string;
  modelId: string;
}

export function createLiteLLMClient(cfg: LiteLLMConfig) {
  async function call<T = unknown>(path: string, body: unknown): Promise<T> {
    let res: Response;
    try {
      res = await fetch(`${cfg.baseURL}${path}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${cfg.masterKey}`,
        },
        body: JSON.stringify(body),
        signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
      });
    } catch (err) {
      throw new LiteLLMError(`LiteLLM request to ${path} failed: ${(err as Error).message}`);
    }
    const text = await res.text();
    if (!res.ok) {
      // Truncate the body and never echo the request (which carries secrets).
      throw new LiteLLMError(
        `LiteLLM ${path} responded ${res.status}`,
        res.status,
        text.slice(0, 500),
      );
    }
    return (text ? JSON.parse(text) : {}) as T;
  }

  async function get<T = unknown>(path: string): Promise<T> {
    let res: Response;
    try {
      res = await fetch(`${cfg.baseURL}${path}`, {
        method: 'GET',
        headers: { Authorization: `Bearer ${cfg.masterKey}` },
        signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
      });
    } catch (err) {
      throw new LiteLLMError(`LiteLLM request to ${path} failed: ${(err as Error).message}`);
    }
    const text = await res.text();
    if (!res.ok) {
      throw new LiteLLMError(`LiteLLM ${path} responded ${res.status}`, res.status, text.slice(0, 500));
    }
    return (text ? JSON.parse(text) : {}) as T;
  }

  /** List registered models (id + public name). Used as a fallback to resolve ids. */
  async function modelInfo(): Promise<LiteLLMModelInfo[]> {
    const data = await get<{ data?: Array<{ model_name?: string; model_info?: { id?: string } }> }>(
      '/model/info',
    );
    return (data.data ?? []).map((m) => ({
      modelName: m.model_name ?? '',
      modelId: m.model_info?.id ?? '',
    }));
  }

  /**
   * Register a new model. Returns its LiteLLM model_id. Every custom endpoint is
   * treated as OpenAI-compatible: `litellm_params.model = "openai/<model>"`.
   */
  async function modelNew(p: ModelNewParams): Promise<{ modelId: string }> {
    const data = await call<{ model_info?: { id?: string }; model_id?: string; id?: string }>(
      '/model/new',
      {
        model_name: p.modelName,
        litellm_params: {
          model: p.providerModel,
          api_base: p.apiBase,
          api_key: p.apiKey,
        },
      },
    );
    let modelId = data.model_info?.id ?? data.model_id ?? data.id ?? '';
    if (!modelId) {
      // Older/newer responses may omit the id — resolve it by public name.
      const info = await modelInfo();
      modelId = info.find((m) => m.modelName === p.modelName)?.modelId ?? '';
    }
    return { modelId };
  }

  async function modelUpdate(p: ModelUpdateParams): Promise<void> {
    await call('/model/update', {
      model_info: { id: p.modelId },
      litellm_params: {
        model: p.providerModel,
        api_base: p.apiBase,
        api_key: p.apiKey,
      },
    });
  }

  async function modelDelete(modelId: string): Promise<void> {
    await call('/model/delete', { id: modelId });
  }

  async function keyGenerate(p: KeyGenerateParams): Promise<{ key: string }> {
    const data = await call<{ key?: string }>('/key/generate', {
      models: p.models,
      key_alias: p.keyAlias,
      metadata: p.metadata,
    });
    if (!data.key) {
      throw new LiteLLMError('LiteLLM /key/generate did not return a key');
    }
    return { key: data.key };
  }

  async function keyUpdate(p: { key: string; models: string[] }): Promise<void> {
    await call('/key/update', { key: p.key, models: p.models });
  }

  async function keyDelete(key: string): Promise<void> {
    await call('/key/delete', { keys: [key] });
  }

  return {
    modelInfo,
    modelNew,
    modelUpdate,
    modelDelete,
    keyGenerate,
    keyUpdate,
    keyDelete,
  };
}

export type LiteLLMClient = ReturnType<typeof createLiteLLMClient>;
