import { logger } from '@librechat/data-schemas';
import type { AppConfig, ILiteLLMSync } from '@librechat/data-schemas';
import type { LiteLLMConfig } from './client';
import { SENTINEL_VIRTUAL_KEY } from './naming';

/**
 * Runtime rewrite of admin-managed custom endpoints so LibreChat talks to the
 * central LiteLLM gateway instead of the real provider.
 *
 * Fail-closed invariant: any endpoint with a LiteLLMSync record always has its
 * runtime `baseURL` replaced with the LiteLLM base. An `active` record injects
 * the working virtual key; a `pending`/`failed` record injects a sentinel key
 * so requests error clearly and never reach the real provider. Endpoints WITHOUT
 * a sync record (e.g. the YAML base "Nufi") are passed through unchanged.
 */

interface RewriterDeps {
  db: { findLiteLLMSyncByEndpointNames: (names: string[]) => Promise<ILiteLLMSync[]> };
  decrypt: (value: string) => string;
  /** Returns the LiteLLM gateway config, or null when the feature is off. */
  getConfig: () => LiteLLMConfig | null;
}

interface ManagedEndpoint {
  name?: string;
  baseURL?: string;
  apiKey?: string;
  models?: { fetch?: boolean; default?: string[] } & Record<string, unknown>;
  [key: string]: unknown;
}

export function createEndpointRewriter(deps: RewriterDeps) {
  const { db, decrypt, getConfig } = deps;

  return async function applyEndpointRewrite(
    config: AppConfig,
    _opts: { tenantId?: string } = {},
  ): Promise<AppConfig> {
    const cfg = getConfig();
    if (!cfg) {
      return config;
    }
    const custom = config.endpoints?.custom as ManagedEndpoint[] | undefined;
    if (!Array.isArray(custom) || custom.length === 0) {
      return config;
    }

    const names = custom.map((e) => e.name).filter((n): n is string => !!n);
    let records: ILiteLLMSync[];
    try {
      records = await db.findLiteLLMSyncByEndpointNames(names);
    } catch (err) {
      // The managed-endpoint markers live in the same DB whose config overrides
      // were already read to build this merged config, so a failure here is very
      // unlikely. If it happens, we cannot tell managed from unmanaged, so we
      // pass through unchanged rather than break the YAML base endpoint too.
      logger.error('[litellm] rewrite lookup failed; passing endpoints through:', err);
      return config;
    }
    const byName = new Map(records.map((r) => [r.endpointName, r]));
    const litellmBase = `${cfg.baseURL}/v1`;

    const rewritten = custom.map((e) => {
      // An endpoint is "managed" iff it has a LiteLLMSync record. No record →
      // unmanaged (e.g. the YAML base endpoint) → passthrough unchanged.
      const record = e.name ? byName.get(e.name) : undefined;
      if (!record) {
        return e;
      }
      const apiKey =
        record.status === 'active' && record.virtualKey
          ? safeDecrypt(decrypt, record.virtualKey)
          : SENTINEL_VIRTUAL_KEY;
      return {
        ...e,
        baseURL: litellmBase,
        apiKey,
        models: {
          ...(e.models ?? {}),
          fetch: true,
          default: record.models.map((m) => m.litellmModelName),
        },
      } as ManagedEndpoint;
    });

    return {
      ...config,
      endpoints: {
        ...config.endpoints,
        custom: rewritten,
      },
    } as AppConfig;
  };
}

function safeDecrypt(decrypt: (v: string) => string, value: string): string {
  try {
    return decrypt(value);
  } catch {
    // A corrupt/undecryptable key must not fall back to the real provider.
    return SENTINEL_VIRTUAL_KEY;
  }
}
