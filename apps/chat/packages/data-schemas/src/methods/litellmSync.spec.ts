import mongoose from 'mongoose';
import { MongoMemoryServer } from 'mongodb-memory-server';
import type * as t from '~/types';
import { createLiteLLMSyncMethods } from './litellmSync';
import litellmSyncSchema from '~/schema/litellmSync';
import { applyTenantIsolation } from '~/models/plugins/tenantIsolation';
import { tenantStorage } from '~/config/tenantContext';

jest.mock('~/config/winston', () => ({ error: jest.fn(), info: jest.fn(), debug: jest.fn() }));

let mongoServer: MongoMemoryServer;
let methods: ReturnType<typeof createLiteLLMSyncMethods>;

beforeAll(async () => {
  mongoServer = await MongoMemoryServer.create();
  await mongoose.connect(mongoServer.getUri());
  applyTenantIsolation(litellmSyncSchema);
  if (!mongoose.models.LiteLLMSync) {
    mongoose.model<t.ILiteLLMSync>('LiteLLMSync', litellmSyncSchema);
  }
  methods = createLiteLLMSyncMethods(mongoose);
});

afterAll(async () => {
  await mongoose.disconnect();
  await mongoServer.stop();
});

beforeEach(async () => {
  await mongoose.models.LiteLLMSync.deleteMany({});
});

const run = <T>(fn: () => Promise<T>) => tenantStorage.run({ tenantId: 'tenant-a' }, fn);

test('upsert creates then updates a sync record by endpointName', async () => {
  await run(() =>
    methods.upsertLiteLLMSync('OpenAI', {
      status: 'pending',
      models: [{ sourceModel: 'gpt-4o', litellmModelName: 'OpenAI/gpt-4o', litellmModelId: '' }],
    }),
  );
  const updated = await run(() =>
    methods.upsertLiteLLMSync('OpenAI', { status: 'active', virtualKey: 'v3:enc' }),
  );
  expect(updated?.status).toBe('active');
  expect(updated?.virtualKey).toBe('v3:enc');
  // update must not wipe the previously-stored models
  expect(updated?.models).toHaveLength(1);
  const all = await run(() => methods.listLiteLLMSync());
  expect(all).toHaveLength(1);
});

test('findByEndpointNames returns only matching records', async () => {
  await run(() => methods.upsertLiteLLMSync('OpenAI', { status: 'active' }));
  await run(() => methods.upsertLiteLLMSync('Azure', { status: 'active' }));
  const found = await run(() => methods.findLiteLLMSyncByEndpointNames(['OpenAI', 'Nope']));
  expect(found.map((r) => r.endpointName).sort()).toEqual(['OpenAI']);
});

test('findByEndpointNames returns [] for empty input', async () => {
  await run(() => methods.upsertLiteLLMSync('OpenAI', { status: 'active' }));
  const found = await run(() => methods.findLiteLLMSyncByEndpointNames([]));
  expect(found).toEqual([]);
});

test('findByEndpointName returns a single record or null', async () => {
  await run(() => methods.upsertLiteLLMSync('OpenAI', { status: 'active' }));
  expect((await run(() => methods.findLiteLLMSyncByEndpointName('OpenAI')))?.status).toBe('active');
  expect(await run(() => methods.findLiteLLMSyncByEndpointName('Nope'))).toBeNull();
});

test('delete removes the record', async () => {
  await run(() => methods.upsertLiteLLMSync('OpenAI', { status: 'active' }));
  await run(() => methods.deleteLiteLLMSyncByEndpointName('OpenAI'));
  expect(await run(() => methods.listLiteLLMSync())).toHaveLength(0);
});

test('tenant isolation: a record created under one tenant is invisible to another', async () => {
  await tenantStorage.run({ tenantId: 'tenant-a' }, () =>
    methods.upsertLiteLLMSync('OpenAI', { status: 'active' }),
  );
  const fromB = await tenantStorage.run({ tenantId: 'tenant-b' }, () => methods.listLiteLLMSync());
  expect(fromB).toHaveLength(0);
  const fromA = await tenantStorage.run({ tenantId: 'tenant-a' }, () => methods.listLiteLLMSync());
  expect(fromA).toHaveLength(1);
});
