import { createEndpointRewriter } from './rewrite';
import { SENTINEL_VIRTUAL_KEY } from './naming';
import type { AppConfig } from '@librechat/data-schemas';

jest.mock('@librechat/data-schemas', () => ({
  logger: { error: jest.fn(), info: jest.fn(), warn: jest.fn(), debug: jest.fn() },
}));

const GATEWAY = { enabled: true, baseURL: 'https://api.codechi.me', masterKey: 'sk-master' };
const decrypt = (v: string) => v.replace(/^E:/, '');

function configWith(custom: unknown[]): AppConfig {
  return { config: {}, endpoints: { custom } } as unknown as AppConfig;
}

function record(over: Record<string, unknown> = {}) {
  return {
    endpointName: 'OpenAI',
    status: 'active',
    virtualKey: 'E:sk-virtual',
    models: [{ sourceModel: 'gpt-4o', litellmModelName: 'OpenAI/gpt-4o', litellmModelId: 'id1' }],
    ...over,
  };
}

describe('applyEndpointRewrite', () => {
  it('returns config unchanged when the gateway is off', async () => {
    const rewrite = createEndpointRewriter({
      db: { findLiteLLMSyncByEndpointNames: jest.fn() },
      decrypt,
      getConfig: () => null,
    });
    const cfg = configWith([{ name: 'OpenAI', baseURL: 'https://real', apiKey: 'sk-real' }]);
    expect(await rewrite(cfg, {})).toBe(cfg);
  });

  it('rewrites an active managed endpoint to the LiteLLM base + virtual key + namespaced models', async () => {
    const rewrite = createEndpointRewriter({
      db: { findLiteLLMSyncByEndpointNames: jest.fn().mockResolvedValue([record()]) },
      decrypt,
      getConfig: () => GATEWAY,
    });
    const cfg = configWith([
      { name: 'OpenAI', baseURL: 'https://api.openai.com/v1', apiKey: 'sk-real', models: { fetch: false } },
    ]);
    const out = await rewrite(cfg, {});
    const ep = (out.endpoints!.custom as any[])[0];
    expect(ep.baseURL).toBe('https://api.codechi.me/v1');
    expect(ep.apiKey).toBe('sk-virtual');
    expect(ep.models).toEqual({ fetch: true, default: ['OpenAI/gpt-4o'] });
    // original config object is not mutated
    expect((cfg.endpoints!.custom as any[])[0].baseURL).toBe('https://api.openai.com/v1');
  });

  it('uses the sentinel key for a failed/pending managed endpoint (fail-closed)', async () => {
    const rewrite = createEndpointRewriter({
      db: {
        findLiteLLMSyncByEndpointNames: jest
          .fn()
          .mockResolvedValue([record({ status: 'failed', virtualKey: undefined })]),
      },
      decrypt,
      getConfig: () => GATEWAY,
    });
    const cfg = configWith([{ name: 'OpenAI', baseURL: 'https://api.openai.com/v1', apiKey: 'sk-real' }]);
    const out = await rewrite(cfg, {});
    const ep = (out.endpoints!.custom as any[])[0];
    expect(ep.baseURL).toBe('https://api.codechi.me/v1'); // still rewritten — never leaks provider
    expect(ep.apiKey).toBe(SENTINEL_VIRTUAL_KEY);
  });

  it('passes through an unmanaged endpoint (no sync record) unchanged', async () => {
    const rewrite = createEndpointRewriter({
      db: { findLiteLLMSyncByEndpointNames: jest.fn().mockResolvedValue([]) },
      decrypt,
      getConfig: () => GATEWAY,
    });
    const cfg = configWith([{ name: 'Nufi', baseURL: 'https://base.example/v1', apiKey: '${KEY}' }]);
    const out = await rewrite(cfg, {});
    const ep = (out.endpoints!.custom as any[])[0];
    expect(ep.baseURL).toBe('https://base.example/v1');
    expect(ep.apiKey).toBe('${KEY}');
  });

  it('passes through when there are no custom endpoints', async () => {
    const rewrite = createEndpointRewriter({
      db: { findLiteLLMSyncByEndpointNames: jest.fn() },
      decrypt,
      getConfig: () => GATEWAY,
    });
    const cfg = { config: {}, endpoints: {} } as unknown as AppConfig;
    expect(await rewrite(cfg, {})).toBe(cfg);
  });
});
