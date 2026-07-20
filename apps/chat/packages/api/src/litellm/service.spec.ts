import { createLiteLLMGateway } from './service';
import type { AppConfig } from '@librechat/data-schemas';

jest.mock('@librechat/data-schemas', () => ({
  logger: { error: jest.fn(), info: jest.fn(), warn: jest.fn(), debug: jest.fn() },
}));

const encrypt = (v: string) => `E:${v}`;
const decrypt = (v: string) => v.replace(/^E:/, '');
const runInTenant = <T>(_t: string | undefined, fn: () => Promise<T>) => fn();

function fakeDb() {
  const store = new Map<string, any>();
  return {
    _store: store,
    findLiteLLMSyncByEndpointName: jest.fn(async (n: string) => store.get(n) ?? null),
    findLiteLLMSyncByEndpointNames: jest.fn(async (names: string[]) =>
      names.map((n) => store.get(n)).filter(Boolean),
    ),
    listLiteLLMSync: jest.fn(async () => [...store.values()]),
    upsertLiteLLMSync: jest.fn(async (n: string, patch: any) => {
      const next = { ...(store.get(n) ?? { endpointName: n, models: [] }), ...patch, endpointName: n };
      store.set(n, next);
      return next;
    }),
    deleteLiteLLMSyncByEndpointName: jest.fn(async (n: string) => {
      const prev = store.get(n) ?? null;
      store.delete(n);
      return prev;
    }),
  };
}

const OLD_ENV = { ...process.env };
const originalFetch = global.fetch;
const mockFetch = jest.fn() as unknown as jest.MockedFunction<typeof fetch>;
const ok = (body: unknown) =>
  ({ ok: true, status: 200, text: async () => JSON.stringify(body), json: async () => body }) as Response;

beforeEach(() => {
  jest.clearAllMocks();
  process.env = { ...OLD_ENV };
  global.fetch = mockFetch;
  let n = 0;
  mockFetch.mockImplementation(async (url: any) => {
    const u = String(url);
    if (u.endsWith('/model/new')) return ok({ model_info: { id: `mid-${n++}` } });
    if (u.endsWith('/key/generate')) return ok({ key: 'sk-virtual' });
    if (u.endsWith('/models')) return ok({ data: [{ id: 'discovered-model' }] });
    return ok({});
  });
});
afterAll(() => {
  process.env = { ...OLD_ENV };
  global.fetch = originalFetch;
});

function enable() {
  process.env.LITELLM_SYNC_ENABLED = 'true';
  process.env.LITELLM_BASE_URL = 'https://api.codechi.me';
  process.env.LITELLM_MASTER_KEY = 'sk-master';
}

test('no-op when feature flag is off', async () => {
  process.env.LITELLM_SYNC_ENABLED = 'false';
  const db = fakeDb();
  const gw = createLiteLLMGateway({ db: db as any, encrypt, decrypt, runInTenant });
  await gw.reconcileLiteLLM({
    customEndpoints: [{ name: 'X', baseURL: 'https://u/v1', apiKey: 'k', models: { default: ['m'] } }],
  });
  expect(db.upsertLiteLLMSync).not.toHaveBeenCalled();
  const cfg = { config: {}, endpoints: { custom: [{ name: 'X' }] } } as unknown as AppConfig;
  expect(await gw.applyEndpointRewrite(cfg, {})).toBe(cfg);
});

test('reconciles an endpoint using its explicit models.default', async () => {
  enable();
  const db = fakeDb();
  const gw = createLiteLLMGateway({ db: db as any, encrypt, decrypt, runInTenant });
  await gw.reconcileLiteLLM({
    tenantId: 't1',
    customEndpoints: [
      { name: 'OpenAI', baseURL: 'https://api.openai.com/v1', apiKey: 'sk-real', models: { default: ['gpt-4o'], fetch: false } },
    ],
  });
  const rec = db._store.get('OpenAI');
  expect(rec.status).toBe('active');
  expect(rec.models[0].litellmModelName).toBe('OpenAI/gpt-4o');
  expect(rec.virtualKey).toBe('E:sk-virtual');
});

test('discovers models from the provider when no explicit list is given', async () => {
  enable();
  const db = fakeDb();
  const discoverModels = jest.fn(async () => ['auto-model']);
  const gw = createLiteLLMGateway({ db: db as any, encrypt, decrypt, runInTenant, discoverModels });
  await gw.reconcileLiteLLM({
    customEndpoints: [{ name: 'OpenAI', baseURL: 'https://api.openai.com/v1', apiKey: 'sk-real', models: {} }],
  });
  expect(discoverModels).toHaveBeenCalledWith('https://api.openai.com/v1', 'sk-real');
  expect(db._store.get('OpenAI').models[0].litellmModelName).toBe('OpenAI/auto-model');
});

test('skips endpoints missing name/baseURL/apiKey', async () => {
  enable();
  const db = fakeDb();
  const gw = createLiteLLMGateway({ db: db as any, encrypt, decrypt, runInTenant });
  await gw.reconcileLiteLLM({
    customEndpoints: [{ name: 'OpenAI', baseURL: '', apiKey: 'sk', models: { default: ['m'] } }],
  });
  expect(db._store.size).toBe(0);
});

test('applyEndpointRewrite runs inside the tenant context', async () => {
  enable();
  const db = fakeDb();
  db._store.set('OpenAI', {
    endpointName: 'OpenAI',
    status: 'active',
    virtualKey: 'E:sk-v',
    models: [{ sourceModel: 'gpt-4o', litellmModelName: 'OpenAI/gpt-4o', litellmModelId: 'id1' }],
  });
  const spyRunInTenant = jest.fn((_t: string | undefined, fn: () => Promise<unknown>) => fn());
  const gw = createLiteLLMGateway({
    db: db as any,
    encrypt,
    decrypt,
    runInTenant: spyRunInTenant as any,
  });
  const cfg = {
    config: {},
    endpoints: { custom: [{ name: 'OpenAI', baseURL: 'https://real/v1', apiKey: 'sk-real' }] },
  } as unknown as AppConfig;
  const out = await gw.applyEndpointRewrite(cfg, { tenantId: 't1' });
  expect(spyRunInTenant).toHaveBeenCalledWith('t1', expect.any(Function));
  expect((out.endpoints!.custom as any[])[0].baseURL).toBe('https://api.codechi.me/v1');
  expect((out.endpoints!.custom as any[])[0].apiKey).toBe('sk-v');
});

test('resyncAll re-reconciles from raw base-config endpoints', async () => {
  enable();
  const db = fakeDb();
  const getRawCustomEndpoints = jest.fn(async () => [
    { name: 'OpenAI', baseURL: 'https://api.openai.com/v1', apiKey: 'sk-real', models: { default: ['gpt-4o'], fetch: false } },
  ]);
  const gw = createLiteLLMGateway({ db: db as any, encrypt, decrypt, runInTenant, getRawCustomEndpoints });
  await gw.resyncAll({ tenantId: 't1' });
  expect(getRawCustomEndpoints).toHaveBeenCalled();
  expect(db._store.get('OpenAI').status).toBe('active');
});

test('getStatus returns enabled:false when the feature is off', async () => {
  process.env.LITELLM_SYNC_ENABLED = 'false';
  const db = fakeDb();
  const gw = createLiteLLMGateway({ db: db as any, encrypt, decrypt, runInTenant });
  expect(await gw.getStatus({ tenantId: 't1' })).toEqual({ enabled: false, statuses: {} });
  expect(db.listLiteLLMSync).not.toHaveBeenCalled();
});

test('getStatus returns sanitized per-endpoint status without secrets', async () => {
  enable();
  const db = fakeDb();
  db._store.set('OpenAI', {
    endpointName: 'OpenAI',
    status: 'active',
    virtualKey: 'E:sk-secret',
    models: [{ sourceModel: 'gpt-4o', litellmModelName: 'OpenAI/gpt-4o', litellmModelId: 'id1' }],
    lastError: null,
    lastSyncedAt: new Date('2026-07-14T00:00:00.000Z'),
  });
  db._store.set('Broken', {
    endpointName: 'Broken',
    status: 'failed',
    models: [],
    lastError: 'boom',
  });
  const gw = createLiteLLMGateway({ db: db as any, encrypt, decrypt, runInTenant });
  const { enabled, statuses } = await gw.getStatus({ tenantId: 't1' });
  expect(enabled).toBe(true);
  expect(statuses.OpenAI).toEqual({
    status: 'active',
    modelCount: 1,
    lastError: null,
    lastSyncedAt: '2026-07-14T00:00:00.000Z',
  });
  expect(statuses.Broken).toEqual({
    status: 'failed',
    modelCount: 0,
    lastError: 'boom',
    lastSyncedAt: null,
  });
  // never leaks the virtual key
  expect(JSON.stringify(statuses)).not.toContain('sk-secret');
});

test('resyncEndpoint re-syncs only the named endpoint and does NOT prune others', async () => {
  enable();
  const db = fakeDb();
  // an existing managed endpoint that must be left untouched
  db._store.set('Other', {
    endpointName: 'Other',
    status: 'active',
    virtualKey: 'E:sk-other',
    models: [{ sourceModel: 'm', litellmModelName: 'Other/m', litellmModelId: 'idO' }],
  });
  const getRawCustomEndpoints = jest.fn(async () => [
    { name: 'OpenAI', baseURL: 'https://api.openai.com/v1', apiKey: 'sk-real', models: { default: ['gpt-4o'], fetch: false } },
    { name: 'Other', baseURL: 'https://other/v1', apiKey: 'sk-o', models: { default: ['m'], fetch: false } },
  ]);
  const gw = createLiteLLMGateway({ db: db as any, encrypt, decrypt, runInTenant, getRawCustomEndpoints });

  await gw.resyncEndpoint({ tenantId: 't1', name: 'OpenAI' });

  expect(db._store.get('OpenAI').status).toBe('active'); // the target got synced
  expect(db._store.has('Other')).toBe(true); // NOT torn down (prune:false)
});

test('resyncEndpoint is a no-op for an unknown endpoint name', async () => {
  enable();
  const db = fakeDb();
  const getRawCustomEndpoints = jest.fn(async () => [
    { name: 'OpenAI', baseURL: 'https://api.openai.com/v1', apiKey: 'sk-real', models: { default: ['gpt-4o'], fetch: false } },
  ]);
  const gw = createLiteLLMGateway({ db: db as any, encrypt, decrypt, runInTenant, getRawCustomEndpoints });
  await gw.resyncEndpoint({ tenantId: 't1', name: 'Nope' });
  expect(db._store.size).toBe(0);
});

type GatewayDeps = Parameters<typeof createLiteLLMGateway>[0];

test('skips an endpoint that already points at the gateway instead of double-proxying it', async () => {
  // Regression: the production "Nufi" endpoint's baseURL already resolved to the
  // gateway, so syncing it registered a model whose upstream was LiteLLM itself.
  enable();
  const db = fakeDb();
  const gw = createLiteLLMGateway({
    db: db as unknown as GatewayDeps['db'],
    encrypt,
    decrypt,
    runInTenant,
  });

  await gw.reconcileLiteLLM({
    customEndpoints: [
      {
        name: 'Self',
        baseURL: 'https://api.codechi.me/v1',
        apiKey: 'k',
        models: { default: ['m'] },
      },
    ],
  });

  expect(db.upsertLiteLLMSync).not.toHaveBeenCalled();
  // Unmanaged endpoints must pass through the rewriter untouched.
  const cfg = {
    endpoints: { custom: [{ name: 'Self', baseURL: 'https://api.codechi.me/v1', apiKey: 'k' }] },
  } as unknown as AppConfig;
  const out = await gw.applyEndpointRewrite(cfg, {});
  expect((out.endpoints!.custom as Array<{ apiKey?: string }>)[0].apiKey).toBe('k');
});

test('never registers the "loading..." placeholder as a model', async () => {
  // Regression: this took the production "Nufi" endpoint down — its only
  // registered model was literally named "loading...".
  enable();
  const db = fakeDb();
  const gw = createLiteLLMGateway({
    db: db as unknown as GatewayDeps['db'],
    encrypt,
    decrypt,
    runInTenant,
  });

  await gw.reconcileLiteLLM({
    customEndpoints: [
      {
        name: 'Ep',
        baseURL: 'https://upstream.example/v1',
        apiKey: 'k',
        models: { fetch: true, default: ['loading...'] },
      },
    ],
  });

  const record = db._store.get('Ep');
  expect(record.status).toBe('active');
  const registered = record.models.map((m: { sourceModel: string }) => m.sourceModel);
  expect(registered).not.toContain('loading...');
  expect(registered).toEqual(['discovered-model']);
});

test('drops non-chat models returned by provider discovery', async () => {
  enable();
  (mockFetch as jest.Mock).mockImplementation(async (url: string | URL | Request) => {
    const u = String(url);
    if (u.endsWith('/model/new')) return ok({ model_info: { id: 'mid' } });
    if (u.endsWith('/key/generate')) return ok({ key: 'sk-virtual' });
    if (u.endsWith('/models')) {
      return ok({
        data: [
          { id: 'models/gemini-2.5-flash' },
          { id: 'models/gemini-embedding-001' },
          { id: 'models/veo-3.1-generate-preview' },
          { id: 'models/imagen-4.0-generate-001' },
        ],
      });
    }
    return ok({});
  });
  const db = fakeDb();
  const gw = createLiteLLMGateway({
    db: db as unknown as GatewayDeps['db'],
    encrypt,
    decrypt,
    runInTenant,
  });

  await gw.reconcileLiteLLM({
    customEndpoints: [
      { name: 'Ep', baseURL: 'https://upstream.example/v1', apiKey: 'k', models: { fetch: true } },
    ],
  });

  expect(db._store.get('Ep').models.map((m: { sourceModel: string }) => m.sourceModel)).toEqual([
    'models/gemini-2.5-flash',
  ]);
});
