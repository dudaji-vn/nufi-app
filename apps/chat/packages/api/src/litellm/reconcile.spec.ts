import { createReconciler } from './reconcile';
import type { EndpointInput } from './reconcile';

jest.mock('@librechat/data-schemas', () => ({
  logger: { error: jest.fn(), info: jest.fn(), warn: jest.fn(), debug: jest.fn() },
}));

// Reversible fake crypto so we can assert the encrypted value is what gets stored
// and that decrypt is applied before reuse.
const encrypt = (v: string) => `E:${v}`;
const decrypt = (v: string) => v.replace(/^E:/, '');

function makeDb() {
  const store = new Map<string, any>();
  return {
    _store: store,
    findLiteLLMSyncByEndpointName: jest.fn(async (name: string) => store.get(name) ?? null),
    upsertLiteLLMSync: jest.fn(async (name: string, patch: any) => {
      const prev = store.get(name) ?? { endpointName: name, models: [] };
      const next = { ...prev, ...patch, endpointName: name };
      store.set(name, next);
      return next;
    }),
    deleteLiteLLMSyncByEndpointName: jest.fn(async (name: string) => {
      const prev = store.get(name) ?? null;
      store.delete(name);
      return prev;
    }),
    listLiteLLMSync: jest.fn(async () => [...store.values()]),
  };
}

function makeClient() {
  return {
    modelInfo: jest.fn(async () => []),
    modelNew: jest.fn(async ({ modelName }: { modelName: string }) => ({ modelId: `id-${modelName}` })),
    modelUpdate: jest.fn(async (_p: Record<string, unknown>) => undefined),
    modelDelete: jest.fn(async (_id: string) => undefined),
    keyGenerate: jest.fn(async (_p: Record<string, unknown>) => ({ key: 'sk-virtual' })),
    keyUpdate: jest.fn(async (_p: { key: string; models: string[] }) => undefined),
    keyDelete: jest.fn(async (_key: string) => undefined),
  };
}

const ep = (over: Partial<EndpointInput> = {}): EndpointInput => ({
  name: 'OpenAI',
  baseURL: 'https://api.openai.com/v1',
  apiKey: 'sk-real',
  models: ['gpt-4o', 'gpt-4o-mini'],
  ...over,
});

describe('reconcileEndpoints', () => {
  it('registers each model and mints one scoped virtual key for a new endpoint', async () => {
    const db = makeDb();
    const client = makeClient();
    const r = createReconciler({ client: client as any, db: db as any, encrypt, decrypt });

    await r.reconcileEndpoints({ customEndpoints: [ep()] });

    expect(client.modelNew).toHaveBeenCalledTimes(2);
    expect(client.modelNew.mock.calls.map((c) => (c[0] as any).modelName).sort()).toEqual([
      'OpenAI/gpt-4o',
      'OpenAI/gpt-4o-mini',
    ]);
    expect((client.modelNew.mock.calls[0][0] as any).providerModel).toMatch(/^openai\//);
    expect(client.keyGenerate).toHaveBeenCalledTimes(1);
    expect((client.keyGenerate.mock.calls[0][0] as any).models.sort()).toEqual([
      'OpenAI/gpt-4o',
      'OpenAI/gpt-4o-mini',
    ]);

    const rec = db._store.get('OpenAI');
    expect(rec.status).toBe('active');
    expect(rec.virtualKey).toBe('E:sk-virtual');
    expect(rec.models).toHaveLength(2);
    expect(rec.realBaseURLHash).toMatch(/^[a-f0-9]{64}$/);
  });

  it('adds only the new model and updates the key allow-list on re-reconcile', async () => {
    const db = makeDb();
    const client = makeClient();
    const r = createReconciler({ client: client as any, db: db as any, encrypt, decrypt });

    await r.reconcileEndpoints({ customEndpoints: [ep({ models: ['gpt-4o'] })] });
    client.modelNew.mockClear();
    client.keyGenerate.mockClear();

    await r.reconcileEndpoints({ customEndpoints: [ep({ models: ['gpt-4o', 'gpt-4o-mini'] })] });

    expect(client.modelNew).toHaveBeenCalledTimes(1);
    expect((client.modelNew.mock.calls[0][0] as any).modelName).toBe('OpenAI/gpt-4o-mini');
    expect(client.keyGenerate).not.toHaveBeenCalled(); // reuse existing key
    expect(client.keyUpdate).toHaveBeenCalled();
    expect((client.keyUpdate.mock.calls.at(-1)![0] as any).models.sort()).toEqual([
      'OpenAI/gpt-4o',
      'OpenAI/gpt-4o-mini',
    ]);
    expect((client.keyUpdate.mock.calls.at(-1)![0] as any).key).toBe('sk-virtual'); // decrypted
  });

  it('deletes a removed model and narrows the key allow-list', async () => {
    const db = makeDb();
    const client = makeClient();
    const r = createReconciler({ client: client as any, db: db as any, encrypt, decrypt });

    await r.reconcileEndpoints({ customEndpoints: [ep({ models: ['gpt-4o', 'gpt-4o-mini'] })] });
    client.modelDelete.mockClear();

    await r.reconcileEndpoints({ customEndpoints: [ep({ models: ['gpt-4o'] })] });

    expect(client.modelDelete).toHaveBeenCalledWith('id-OpenAI/gpt-4o-mini');
    expect((client.keyUpdate.mock.calls.at(-1)![0] as any).models).toEqual(['OpenAI/gpt-4o']);
  });

  it('updates kept models when the upstream credentials change (drift)', async () => {
    const db = makeDb();
    const client = makeClient();
    const r = createReconciler({ client: client as any, db: db as any, encrypt, decrypt });

    await r.reconcileEndpoints({ customEndpoints: [ep({ models: ['gpt-4o'] })] });
    client.modelUpdate.mockClear();

    await r.reconcileEndpoints({
      customEndpoints: [ep({ models: ['gpt-4o'], apiKey: 'sk-rotated' })],
    });

    expect(client.modelUpdate).toHaveBeenCalledTimes(1);
    expect((client.modelUpdate.mock.calls[0][0] as any).apiKey).toBe('sk-rotated');
  });

  it('marks an endpoint failed (fail-closed) and continues when a LiteLLM call throws', async () => {
    const db = makeDb();
    const client = makeClient();
    client.modelNew.mockRejectedValueOnce(new Error('boom'));
    const r = createReconciler({ client: client as any, db: db as any, encrypt, decrypt });

    await r.reconcileEndpoints({
      customEndpoints: [ep({ name: 'Bad', models: ['gpt-4o'] }), ep({ name: 'Good', models: ['gpt-4o'] })],
    });

    expect(db._store.get('Bad').status).toBe('failed');
    expect(db._store.get('Bad').lastError).toContain('boom');
    expect(db._store.get('Good').status).toBe('active'); // not aborted
  });

  it('marks failed with a helpful message when no models are configured', async () => {
    const db = makeDb();
    const client = makeClient();
    const r = createReconciler({ client: client as any, db: db as any, encrypt, decrypt });

    await r.reconcileEndpoints({ customEndpoints: [ep({ models: [] })] });

    expect(client.modelNew).not.toHaveBeenCalled();
    expect(db._store.get('OpenAI').status).toBe('failed');
    expect(db._store.get('OpenAI').lastError).toMatch(/no models/i);
  });

  it('with prune:false, does NOT tear down endpoints absent from the set', async () => {
    const db = makeDb();
    const client = makeClient();
    const r = createReconciler({ client: client as any, db: db as any, encrypt, decrypt });

    await r.reconcileEndpoints({ customEndpoints: [ep({ name: 'A', models: ['gpt-4o'] }), ep({ name: 'B', models: ['gpt-4o'] })] });
    client.modelDelete.mockClear();

    // resync only A, prune:false — B must survive
    await r.reconcileEndpoints({ customEndpoints: [ep({ name: 'A', models: ['gpt-4o'] })], prune: false });

    expect(client.modelDelete).not.toHaveBeenCalled();
    expect(db._store.has('A')).toBe(true);
    expect(db._store.has('B')).toBe(true);
  });

  it('tears down endpoints that disappear from the set', async () => {
    const db = makeDb();
    const client = makeClient();
    const r = createReconciler({ client: client as any, db: db as any, encrypt, decrypt });

    await r.reconcileEndpoints({ customEndpoints: [ep({ name: 'OpenAI', models: ['gpt-4o'] })] });
    await r.reconcileEndpoints({ customEndpoints: [] });

    expect(client.modelDelete).toHaveBeenCalledWith('id-OpenAI/gpt-4o');
    expect(client.keyDelete).toHaveBeenCalledWith('sk-virtual');
    expect(db._store.has('OpenAI')).toBe(false);
  });
});

describe('unsyncEndpoint / unsyncMissing', () => {
  it('unsyncEndpoint deletes models + key + record', async () => {
    const db = makeDb();
    const client = makeClient();
    const r = createReconciler({ client: client as any, db: db as any, encrypt, decrypt });
    await r.reconcileEndpoints({ customEndpoints: [ep({ name: 'OpenAI', models: ['gpt-4o'] })] });

    await r.unsyncEndpoint('OpenAI');

    expect(client.modelDelete).toHaveBeenCalledWith('id-OpenAI/gpt-4o');
    expect(client.keyDelete).toHaveBeenCalledWith('sk-virtual');
    expect(db._store.has('OpenAI')).toBe(false);
  });

  it('unsyncMissing keeps named endpoints and removes the rest', async () => {
    const db = makeDb();
    const client = makeClient();
    const r = createReconciler({ client: client as any, db: db as any, encrypt, decrypt });
    await r.reconcileEndpoints({
      customEndpoints: [ep({ name: 'A', models: ['gpt-4o'] }), ep({ name: 'B', models: ['gpt-4o'] })],
    });
    client.modelDelete.mockClear();

    await r.unsyncMissing(['A']);

    expect(db._store.has('A')).toBe(true);
    expect(db._store.has('B')).toBe(false);
  });
});
