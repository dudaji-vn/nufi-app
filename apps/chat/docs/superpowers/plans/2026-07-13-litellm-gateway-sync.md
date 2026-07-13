# LiteLLM Gateway Sync — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When an admin creates/edits/deletes a custom endpoint in the admin panel, auto-register its models in the central LiteLLM proxy, mint a per-endpoint virtual key, and rewrite the endpoint at runtime so all LibreChat AI traffic flows through LiteLLM (fail-closed).

**Architecture:** Two decoupled halves that communicate only through a new Mongo collection `LiteLLMSync`. (1) **Write-side reconcile** hooked into the admin config handlers registers/updates/deletes LiteLLM models + a scoped virtual key. (2) **Read-side rewrite** injected into `getAppConfig` replaces each managed endpoint's `baseURL`/`apiKey`/`models` from its `LiteLLMSync` record before the merged config is cached. Admin panel is untouched (it keeps showing the real provider values).

**Tech Stack:** TypeScript, Node, Express, Mongoose (`@librechat/data-schemas`), Jest + mongodb-memory-server, Rollup builds, LiteLLM proxy v1.83.10 admin API.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-13-litellm-gateway-sync-design.md`. All decisions D1–D6 there are binding.
- **Feature flag `LITELLM_SYNC_ENABLED` defaults OFF.** When off: no reconcile, no rewrite (legacy behavior). Nothing may change production behavior until an operator opts in.
- **Fail-closed:** a managed endpoint's runtime `baseURL` is ALWAYS the LiteLLM base; never fall back to the real provider. `active` → virtual key; `pending`/`failed` → sentinel invalid key.
- **Model naming:** LiteLLM `model_name = "<endpointName>/<model>"` (namespaced). `litellm_params.model = "openai/<model>"` + `api_base`/`api_key` = real provider values (every endpoint treated as OpenAI-compatible).
- **Secrets:** virtual keys stored encrypted with `encryptV3`/`decryptV3` (`@librechat/data-schemas`). Requires `CREDS_KEY` = 64 hex chars. Never log or commit `LITELLM_MASTER_KEY` or any virtual key.
- **Tenant isolation:** `@librechat/data-schemas` uses `applyTenantIsolation` + `tenantStorage` (AsyncLocalStorage). New model applies the plugin; methods query by `endpointName` only (tenant auto-applied from the request's ALS context). Admin handlers + config middleware already run inside tenant context.
- **Rebuilds:** after editing `packages/data-schemas/src` run `npm run build` in that package; after editing `packages/api/src` run its build too — the running server consumes the built `dist/`. Unit tests (jest) read `src` directly via `moduleNameMapper`, so tests don't need a rebuild.
- Env vars (read in fork, wired in `nufi-chat` deploy repo): `LITELLM_SYNC_ENABLED`, `LITELLM_BASE_URL` (a trailing `/v1` is normalized), `LITELLM_MASTER_KEY`.
- Branch: `feat/litellm-gateway-sync` (already created off `develop`). Commit frequently. Commit trailers per repo convention.

---

## Task 1: `LiteLLMSync` schema, type, model, methods (data-schemas)

**Files:**
- Create: `packages/data-schemas/src/types/litellmSync.ts`
- Create: `packages/data-schemas/src/schema/litellmSync.ts`
- Create: `packages/data-schemas/src/models/litellmSync.ts`
- Create: `packages/data-schemas/src/methods/litellmSync.ts`
- Create (test): `packages/data-schemas/src/methods/litellmSync.spec.ts`
- Modify: `packages/data-schemas/src/types/index.ts` (add `export * from './litellmSync';`)
- Modify: `packages/data-schemas/src/schema/index.ts` (add `export { default as litellmSyncSchema } from './litellmSync';`)
- Modify: `packages/data-schemas/src/models/index.ts` (import + `LiteLLMSync: createLiteLLMSyncModel(mongoose),`)
- Modify: `packages/data-schemas/src/methods/index.ts` (import, `LiteLLMSyncMethods &` in `AllMethods`, spread in `createMethods`, re-export type)

**Interfaces produced (later tasks rely on these exact names/types):**
- `ILiteLLMSync` (document type) with fields:
  `endpointName: string`, `status: 'pending'|'active'|'failed'`, `virtualKey?: string` (encrypted),
  `models: Array<{ sourceModel: string; litellmModelName: string; litellmModelId: string }>`,
  `realBaseURLHash?: string`, `lastError?: string | null`, `lastSyncedAt?: Date`, `tenantId?: string`,
  `createdAt?: Date`, `updatedAt?: Date`.
- DB methods (surfaced on `require('~/models')` / `db` in the api layer):
  - `findLiteLLMSyncByEndpointName(endpointName: string): Promise<ILiteLLMSync | null>`
  - `findLiteLLMSyncByEndpointNames(names: string[]): Promise<ILiteLLMSync[]>`
  - `listLiteLLMSync(): Promise<ILiteLLMSync[]>`
  - `upsertLiteLLMSync(endpointName: string, patch: Partial<ILiteLLMSync>): Promise<ILiteLLMSync | null>`
  - `deleteLiteLLMSyncByEndpointName(endpointName: string): Promise<ILiteLLMSync | null>`

- [ ] **Step 1: Type** — `types/litellmSync.ts`:

```ts
import type { Document, Types } from 'mongoose';

export type LiteLLMSyncModel = {
  sourceModel: string;
  litellmModelName: string;
  litellmModelId: string;
};

export type LiteLLMSyncStatus = 'pending' | 'active' | 'failed';

export type LiteLLMSync = {
  endpointName: string;
  status: LiteLLMSyncStatus;
  /** Encrypted (encryptV3) LiteLLM virtual key. Absent until a key is minted. */
  virtualKey?: string;
  models: LiteLLMSyncModel[];
  /** sha256 of the real upstream baseURL — detect drift without storing the URL. */
  realBaseURLHash?: string;
  lastError?: string | null;
  lastSyncedAt?: Date;
  tenantId?: string;
  createdAt?: Date;
  updatedAt?: Date;
};

export type ILiteLLMSync = LiteLLMSync &
  Document & {
    _id: Types.ObjectId;
  };
```

- [ ] **Step 2: Schema** — `schema/litellmSync.ts` (copy `schema/config.ts` conventions; compound unique index incl. `tenantId`):

```ts
import { Schema } from 'mongoose';
import type { ILiteLLMSync } from '~/types';

const litellmSyncModelSchema = new Schema(
  {
    sourceModel: { type: String, required: true },
    litellmModelName: { type: String, required: true },
    litellmModelId: { type: String, default: '' },
  },
  { _id: false },
);

const litellmSyncSchema = new Schema<ILiteLLMSync>(
  {
    endpointName: { type: String, required: true, index: true },
    status: {
      type: String,
      enum: ['pending', 'active', 'failed'],
      default: 'pending',
      required: true,
    },
    virtualKey: { type: String },
    models: { type: [litellmSyncModelSchema], default: [] },
    realBaseURLHash: { type: String },
    lastError: { type: String, default: null },
    lastSyncedAt: { type: Date },
    tenantId: { type: String, index: true },
  },
  { timestamps: true },
);

// One sync record per endpoint per tenant.
litellmSyncSchema.index({ tenantId: 1, endpointName: 1 }, { unique: true });

export default litellmSyncSchema;
```

- [ ] **Step 3: Model** — `models/litellmSync.ts` (apply tenant isolation, guard double-registration; copy `models/config.ts`):

```ts
import litellmSyncSchema from '~/schema/litellmSync';
import { applyTenantIsolation } from '~/models/plugins/tenantIsolation';
import type * as t from '~/types';

export function createLiteLLMSyncModel(mongoose: typeof import('mongoose')) {
  applyTenantIsolation(litellmSyncSchema);
  return (
    mongoose.models.LiteLLMSync ||
    mongoose.model<t.ILiteLLMSync>('LiteLLMSync', litellmSyncSchema)
  );
}
```

- [ ] **Step 4: Methods** — `methods/litellmSync.ts` (per-call model fetch; upsert with 11000 retry; copy `methods/config.ts`):

```ts
import type { Model, ClientSession } from 'mongoose';
import type { ILiteLLMSync, LiteLLMSync } from '~/types';

export function createLiteLLMSyncMethods(mongoose: typeof import('mongoose')) {
  function model(): Model<ILiteLLMSync> {
    return mongoose.models.LiteLLMSync as Model<ILiteLLMSync>;
  }

  async function findLiteLLMSyncByEndpointName(
    endpointName: string,
    session?: ClientSession,
  ): Promise<ILiteLLMSync | null> {
    return await model()
      .findOne({ endpointName })
      .session(session ?? null)
      .lean<ILiteLLMSync>();
  }

  async function findLiteLLMSyncByEndpointNames(
    names: string[],
  ): Promise<ILiteLLMSync[]> {
    if (!names || names.length === 0) {
      return [];
    }
    return await model()
      .find({ endpointName: { $in: names } })
      .lean<ILiteLLMSync[]>();
  }

  async function listLiteLLMSync(): Promise<ILiteLLMSync[]> {
    return await model().find({}).lean<ILiteLLMSync[]>();
  }

  async function upsertLiteLLMSync(
    endpointName: string,
    patch: Partial<LiteLLMSync>,
    session?: ClientSession,
  ): Promise<ILiteLLMSync | null> {
    const query = { endpointName };
    const update = { $set: { ...patch, endpointName } };
    const options = {
      upsert: true,
      new: true,
      setDefaultsOnInsert: true,
      ...(session ? { session } : {}),
    };
    try {
      return await model().findOneAndUpdate(query, update, options);
    } catch (err: unknown) {
      if ((err as { code?: number }).code === 11000) {
        return await model().findOneAndUpdate(query, update, {
          new: true,
          ...(session ? { session } : {}),
        });
      }
      throw err;
    }
  }

  async function deleteLiteLLMSyncByEndpointName(
    endpointName: string,
    session?: ClientSession,
  ): Promise<ILiteLLMSync | null> {
    return await model()
      .findOneAndDelete({ endpointName })
      .session(session ?? null);
  }

  return {
    findLiteLLMSyncByEndpointName,
    findLiteLLMSyncByEndpointNames,
    listLiteLLMSync,
    upsertLiteLLMSync,
    deleteLiteLLMSyncByEndpointName,
  };
}

export type LiteLLMSyncMethods = ReturnType<typeof createLiteLLMSyncMethods>;
```

- [ ] **Step 5: Barrels** — apply the 4 barrel edits exactly as in the Files list (types, schema, models, methods `index.ts`). In `methods/index.ts`: add `import { createLiteLLMSyncMethods, type LiteLLMSyncMethods } from './litellmSync';`, add `LiteLLMSyncMethods &` to the `AllMethods` intersection, add `...createLiteLLMSyncMethods(mongoose),` to the `createMethods` return object, and add `LiteLLMSyncMethods,` to the trailing `export type { ... }` block.

- [ ] **Step 6: Test** — `methods/litellmSync.spec.ts` (mongodb-memory-server + tenant wrapper; copy `methods/auditLog.spec.ts` + tenant pattern from `tenantIsolation.spec.ts`):

```ts
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
  const all = await run(() => methods.listLiteLLMSync());
  expect(all).toHaveLength(1);
});

test('findByEndpointNames returns only matching records', async () => {
  await run(() => methods.upsertLiteLLMSync('OpenAI', { status: 'active' }));
  await run(() => methods.upsertLiteLLMSync('Azure', { status: 'active' }));
  const found = await run(() => methods.findLiteLLMSyncByEndpointNames(['OpenAI', 'Nope']));
  expect(found.map((r) => r.endpointName).sort()).toEqual(['OpenAI']);
});

test('delete removes the record', async () => {
  await run(() => methods.upsertLiteLLMSync('OpenAI', { status: 'active' }));
  await run(() => methods.deleteLiteLLMSyncByEndpointName('OpenAI'));
  expect(await run(() => methods.listLiteLLMSync())).toHaveLength(0);
});
```

- [ ] **Step 7: Run tests** — from `packages/data-schemas/`: `npx jest src/methods/litellmSync.spec.ts` → PASS.
- [ ] **Step 8: Build** — from `packages/data-schemas/`: `npm run build` → succeeds, `dist/` regenerated.
- [ ] **Step 9: Commit** — `git add packages/data-schemas/src && git commit` (message: `feat(data-schemas): add LiteLLMSync schema + methods`).

---

## Task 2: LiteLLM admin API client

**Files:**
- Create: `packages/api/src/litellm/client.ts`
- Create (test): `packages/api/src/litellm/client.spec.ts`

**Interfaces produced:**
- `getLiteLLMConfig(): { enabled: boolean; baseURL: string; masterKey: string } | null` — reads env, normalizes `baseURL` (strips a trailing `/v1` and trailing slash so both `/v1/...` chat calls and `/model/*` admin calls compose correctly), returns `null` if disabled/unconfigured.
- `createLiteLLMClient(cfg)` returning:
  - `modelNew(p: { modelName: string; providerModel: string; apiBase: string; apiKey: string }): Promise<{ modelId: string }>`
  - `modelUpdate(p: { modelId: string; providerModel: string; apiBase: string; apiKey: string }): Promise<void>`
  - `modelDelete(modelId: string): Promise<void>`
  - `keyGenerate(p: { models: string[]; keyAlias: string; metadata: Record<string, unknown> }): Promise<{ key: string }>`
  - `keyUpdate(p: { key: string; models: string[] }): Promise<void>`
  - `keyDelete(key: string): Promise<void>`
- `class LiteLLMError extends Error { status?: number; body?: string }`

**Notes for implementer:**
- Use global `fetch` (Node 18+). Every admin call sends `Authorization: Bearer <masterKey>` + `Content-Type: application/json`. 15s timeout via `AbortSignal.timeout(15000)`.
- Admin routes (relative to normalized base, no `/v1`): `POST /model/new`, `POST /model/update`, `POST /model/delete`, `POST /key/generate`, `POST /key/update`, `POST /key/delete`.
- `modelNew` body: `{ model_name, litellm_params: { model: providerModel, api_base: apiBase, api_key: apiKey } }`; response has `model_info.id` (fall back to top-level `model_id`/`id`).
- `modelUpdate` body: `{ model_info: { id: modelId }, litellm_params: { model, api_base, api_key } }`.
- `modelDelete` body: `{ id: modelId }`.
- `keyGenerate` body: `{ models, key_alias: keyAlias, metadata }`; response `{ key }`.
- `keyUpdate` body: `{ key, models }`. `keyDelete` body: `{ keys: [key] }`.
- Non-2xx → throw `LiteLLMError` with `status` + truncated `body`. NEVER include the master key or virtual key in error messages/logs.

- [ ] **Step 1: Write `client.ts`** implementing the interfaces above.
- [ ] **Step 2: Write `client.spec.ts`** — mock global `fetch` (`global.fetch = jest.fn()`); assert: `getLiteLLMConfig` returns null when `LITELLM_SYNC_ENABLED!=='true'`; base normalization strips `/v1`; `modelNew` posts to `<base>/model/new` with the right body and parses `model_info.id`; a 500 response throws `LiteLLMError` with `status===500` and the body does not contain the master key.
- [ ] **Step 3: Run** — `cd packages/api && npx jest src/litellm/client.spec.ts` → PASS.
- [ ] **Step 4: Commit** — `feat(api): add LiteLLM admin API client`.

---

## Task 3: Reconciler

**Files:**
- Create: `packages/api/src/litellm/naming.ts` (pure helpers)
- Create: `packages/api/src/litellm/reconcile.ts`
- Create (test): `packages/api/src/litellm/naming.spec.ts`
- Create (test): `packages/api/src/litellm/reconcile.spec.ts`

**Interfaces produced:**
- `naming.ts`: `litellmModelName(endpointName: string, model: string): string` → `"<endpointName>/<model>"`; `hashBaseURL(url: string): string` → sha256 hex; `keyAlias(endpointName: string): string` → `"nufi-ep-<slug>"`; `SENTINEL_VIRTUAL_KEY: string` (an obviously-invalid key used fail-closed).
- `reconcile.ts` (dependency-injected so it's unit-testable):
  - `createReconciler(deps: { client, db, encrypt, decrypt }) => { reconcileEndpoints(params: { customEndpoints: EndpointInput[] }): Promise<void>; unsyncEndpoint(endpointName: string): Promise<void>; unsyncMissing(keepNames: string[]): Promise<void> }`
  - `EndpointInput = { name: string; baseURL: string; apiKey: string; models: string[] }` (models = the raw model list the admin configured; if empty, derive from `models.default`).
  - `db` shape consumed: `findLiteLLMSyncByEndpointName`, `upsertLiteLLMSync`, `deleteLiteLLMSyncByEndpointName`, `listLiteLLMSync` (from Task 1).

**Reconcile algorithm (per endpoint, idempotent):**
1. `upsertLiteLLMSync(name, { status: 'pending' })` (marks managed immediately → fail-closed even if later steps fail).
2. Load existing record. Build desired model set = `{ sourceModel → litellmModelName }`.
3. For each desired model not in the record's `models`: `client.modelNew(...)` → collect `{sourceModel, litellmModelName, litellmModelId}`. For each record model no longer desired: `client.modelDelete(litellmModelId)`. For models present in both when `hashBaseURL(baseURL)` differs from `record.realBaseURLHash` OR apiKey changed (can't compare hash of key cheaply → on any baseURL drift, `client.modelUpdate` all kept models): update.
4. Virtual key: if `record.virtualKey` absent → `client.keyGenerate({ models: allLitellmModelNames, keyAlias, metadata })`, store `encrypt(key)`. Else `client.keyUpdate({ key: decrypt(record.virtualKey), models: allLitellmModelNames })`.
5. `upsertLiteLLMSync(name, { status: 'active', virtualKey, models, realBaseURLHash, lastError: null, lastSyncedAt: new Date() })`.
6. On any thrown error: `upsertLiteLLMSync(name, { status: 'failed', lastError: String(err) })` and continue with the next endpoint (do not throw out of `reconcileEndpoints`).

- `unsyncEndpoint(name)`: load record; `modelDelete` each `litellmModelId`; `keyDelete(decrypt(virtualKey))`; `deleteLiteLLMSyncByEndpointName(name)`. Best-effort per call (catch + continue) so a partially-deleted upstream still clears the record.
- `unsyncMissing(keepNames)`: `listLiteLLMSync()` → for any record whose `endpointName ∉ keepNames`, `unsyncEndpoint(name)`. (Handles endpoints removed from the array on an edit.)

- [ ] **Step 1: `naming.ts`** + `naming.spec.ts` (assert namespacing, stable sha256, slug). Run → PASS.
- [ ] **Step 2: `reconcile.ts`** implementing `createReconciler`.
- [ ] **Step 3: `reconcile.spec.ts`** — inject a fake `client` (jest mocks) + in-memory `db` (plain object with jest.fn() or a Map-backed fake) + identity `encrypt`/`decrypt`. Cover:
  - new endpoint → `modelNew` per model + `keyGenerate` + record `status==='active'` with `litellmModelId`s and encrypted key.
  - adding a model on re-reconcile → one new `modelNew` + `keyUpdate` with the widened model list; no duplicate `modelNew` for existing models.
  - removing a model → `modelDelete` + `keyUpdate` narrower list.
  - `client.modelNew` throws → record `status==='failed'`, `lastError` set, loop continues to next endpoint.
  - `unsyncEndpoint` → `modelDelete` all + `keyDelete` + record removed.
  - `unsyncMissing(['A'])` with records A,B → B unsynced, A kept.
- [ ] **Step 4: Run** — `cd packages/api && npx jest src/litellm/reconcile.spec.ts src/litellm/naming.spec.ts` → PASS.
- [ ] **Step 5: Commit** — `feat(api): add LiteLLM reconciler`.

---

## Task 4: Runtime rewrite injected into `getAppConfig`

**Files:**
- Create: `packages/api/src/litellm/rewrite.ts`
- Create (test): `packages/api/src/litellm/rewrite.spec.ts`
- Modify: `packages/api/src/app/service.ts` (add optional dep + call in Branch F)
- Modify (test): `packages/api/src/app/service.spec.ts` (or the existing service test file) — assert the dep is invoked on the merged branch and its result is what gets cached/returned.

**Interfaces produced:**
- `rewrite.ts`:
  - `createEndpointRewriter(deps: { db: { findLiteLLMSyncByEndpointNames }, decrypt: (s: string) => string, getConfig: () => { baseURL: string } | null }) => (config: AppConfig, opts: { tenantId?: string }) => Promise<AppConfig>`
  - Returned function = `applyEndpointRewrite`. Behavior:
    - If `getConfig()` is null (flag off/unconfigured) → return `config` unchanged.
    - `custom = config.endpoints?.custom`; if not a non-empty array → return unchanged.
    - `records = await db.findLiteLLMSyncByEndpointNames(custom.map(e => e.name))`; index by name.
    - Map each endpoint: if no record → passthrough (unmanaged, e.g. YAML base). If record → new object `{ ...e, baseURL: <normalized LITELLM base>+'/v1', apiKey: record.status==='active' ? decrypt(record.virtualKey) : SENTINEL_VIRTUAL_KEY, models: { ...e.models, fetch: true, default: record.models.map(m => m.litellmModelName) } }`.
    - Return a new config with the rewritten `endpoints.custom` (do not mutate the input's nested arrays in place beyond replacing the `custom` array reference).

**`service.ts` change (Branch F only — managed endpoints only ever appear in the merged config):**
- Add to `AppConfigServiceDeps` (after `overrideCacheTtl?`):
  ```ts
  /** Optional: rewrite managed custom endpoints (LiteLLM gateway). No-op when unset. */
  applyEndpointRewrite?: (config: AppConfig, opts: { tenantId?: string }) => Promise<AppConfig>;
  ```
- Destructure it in `createAppConfigService`.
- In `getAppConfig`, replace the Branch F block (currently lines ~202-204):
  ```ts
  const merged = mergeConfigOverrides(baseConfig, configs);
  const finalConfig = applyEndpointRewrite ? await applyEndpointRewrite(merged, { tenantId }) : merged;
  await cache.set(cacheKey, finalConfig, overrideCacheTtl);
  return finalConfig;
  ```
  Leave Branch E (`configs.length === 0`, line ~197-200) unchanged — no admin-created endpoints can exist there, and skipping avoids a needless DB read.

- [ ] **Step 1: `rewrite.ts`** implementing `createEndpointRewriter`.
- [ ] **Step 2: `rewrite.spec.ts`** — fake `db.findLiteLLMSyncByEndpointNames`, identity `decrypt`, `getConfig` returning `{ baseURL: 'https://api.codechi.me' }`. Cover: managed active endpoint → baseURL rewritten to `https://api.codechi.me/v1`, apiKey = virtual key, `models.default` = namespaced list; managed `failed`/`pending` → apiKey = sentinel; unmanaged endpoint (no record) → unchanged (real baseURL preserved is FINE for unmanaged/YAML); flag off (`getConfig` null) → unchanged.
- [ ] **Step 3: `service.ts` edit** as above. Update/extend the service test to pass a mock `applyEndpointRewrite` and assert the merged branch calls it and caches its return.
- [ ] **Step 4: Run** — `cd packages/api && npx jest src/litellm/rewrite.spec.ts src/app/service.spec.ts` → PASS.
- [ ] **Step 5: Commit** — `feat(api): rewrite managed custom endpoints to LiteLLM in getAppConfig`.

---

## Task 5: Admin-handler hooks + composition root + re-sync route

**Files:**
- Modify: `packages/api/src/admin/config.ts` (add `reconcileLiteLLM` dep + destructure + call in 4 write handlers)
- Modify (test): `packages/api/src/admin/config.handler.spec.ts` (add `reconcileLiteLLM: jest.fn()` to `createHandlers`; assert it fires only for `endpoints.custom` writes)
- Create: `packages/api/src/litellm/index.ts` (barrel exporting client/reconcile/rewrite/naming + a `buildReconcileHook` helper)
- Create: `api/server/services/LiteLLM/index.js` (fork-layer wiring: build client from env, build reconciler from `db` + crypto, expose `reconcileLiteLLM(params)`, `applyEndpointRewrite`, `resyncAll()`)
- Modify: `api/server/routes/admin/config.js` (import + pass `reconcileLiteLLM` dep)
- Modify: `api/server/services/Config/app.js` (wire `applyEndpointRewrite` into `createAppConfigService`)
- Create: `api/server/routes/admin/litellm.js` (POST `/api/admin/litellm/resync` → `resyncAll()`), mount alongside the existing admin config route
- Modify: wherever admin routes are mounted (`api/server/index.js` or `api/server/routes/admin/index.js`) to mount the resync route under the same `requireJwtAuth, requireAdminAccess` guard.

**`packages/api/src/admin/config.ts` edits:**
- `AdminConfigDeps` — add:
  ```ts
  /** Fire-and-forget LiteLLM reconcile after a custom-endpoints write. */
  reconcileLiteLLM?: (params: { tenantId?: string; customEndpoints: unknown[] }) => Promise<void>;
  ```
- Destructure `reconcileLiteLLM` in `createAdminConfigHandlers`.
- Helper near the top of the factory:
  ```ts
  const touchesCustom = (paths: string[]) =>
    paths.some((p) => p === 'endpoints.custom' || getTopLevelSection(p) === 'endpoints');
  ```
- In `patchConfigField` (after `config` obtained, next to cache invalidation ~469-471):
  ```ts
  if (reconcileLiteLLM && touchesCustom(Object.keys(fields))) {
    reconcileLiteLLM({
      tenantId: user.tenantId,
      customEndpoints: (config?.overrides as { endpoints?: { custom?: unknown[] } })?.endpoints?.custom ?? [],
    }).catch((err) => logger.error('[adminConfig] LiteLLM reconcile failed:', err));
  }
  ```
- In `upsertConfigOverrides` (between save and response ~358-363): same, using `filteredOverrides.endpoints?.custom`.
- In `deleteConfigField` (~525-530): guard `getTopLevelSection(fieldPath) === 'endpoints'`; pass `config?.overrides?.endpoints?.custom ?? []`.
- In `deleteConfigOverrides` (~563-568): the returned `config` is the deleted doc, so pass `customEndpoints: []` (principal removed → reconcile will `unsyncMissing([])` and tear everything down for that scope). Only fire if the deleted override actually had custom endpoints (`config?.overrides?.endpoints?.custom?.length`).

**Fork-layer `reconcileLiteLLM` semantics** (`api/server/services/LiteLLM/index.js`): wrap in `tenantStorage.run({ tenantId }, ...)`, map `customEndpoints` → `EndpointInput[]` (extract `name`, interpolate+read `baseURL`/`apiKey`, `models` from `models.default` or a fetched list), call `reconciler.reconcileEndpoints({ customEndpoints })` then `reconciler.unsyncMissing(names)`. Guard the whole thing behind `getLiteLLMConfig()` (no-op when flag off).

- [ ] **Step 1:** `packages/api/src/litellm/index.ts` barrel + build helper.
- [ ] **Step 2:** `config.ts` dep + destructure + 4 handler hooks.
- [ ] **Step 3:** Extend `config.handler.spec.ts`: add `reconcileLiteLLM: jest.fn()` mock; assert (a) a `patchConfigField` with `fields={'endpoints.custom': [...]}` calls `reconcileLiteLLM` once with the array; (b) a `patchConfigField` touching only `registration.enabled` does NOT call it; (c) it is fire-and-forget (handler still responds 200 even if the mock rejects).
- [ ] **Step 4:** Fork wiring: `api/server/services/LiteLLM/index.js`, `api/server/services/Config/app.js` (`applyEndpointRewrite`), `api/server/routes/admin/config.js` (`reconcileLiteLLM`), resync route + mount.
- [ ] **Step 5: Run** — `cd packages/api && npx jest src/admin/config.handler.spec.ts` → PASS. Then `npm run build` in `packages/api`.
- [ ] **Step 6: Commit** — `feat: hook LiteLLM reconcile into admin config + add resync route`.

---

## Task 6: Env wiring in the `nufi-chat` deploy repo

**Files (repo `/Users/sun/Workspace/DudajiVN/nufi-chat`):**
- Modify: `.env.example` (document the three vars)
- Modify: `docker-compose.yml` (pass them into the `api` service env)

- [ ] **Step 1:** Append to `.env.example` after the Backend LLM section:
  ```
  # --- LiteLLM gateway sync (optional) -------------------------------------
  # When enabled, custom endpoints admins create in the admin panel are
  # auto-registered in the central LiteLLM proxy and all their traffic is
  # routed through it (per-endpoint virtual keys, fail-closed). OFF by default.
  LITELLM_SYNC_ENABLED=false
  # Base URL of your LiteLLM proxy (a trailing /v1 is normalized).
  LITELLM_BASE_URL=https://api.codechi.me
  # LiteLLM master key (admin API). Sent as Authorization: Bearer. NEVER commit.
  LITELLM_MASTER_KEY=
  ```
- [ ] **Step 2:** In `docker-compose.yml` `api.environment`, add:
  ```yaml
      LITELLM_SYNC_ENABLED: ${LITELLM_SYNC_ENABLED:-false}
      LITELLM_BASE_URL: ${LITELLM_BASE_URL:-}
      LITELLM_MASTER_KEY: ${LITELLM_MASTER_KEY:-}
  ```
- [ ] **Step 3: Commit** (in nufi-chat, on a feature branch there): `feat: add LiteLLM gateway sync env vars (default off)`.

---

## Task 7: Verify, PR, handoff

- [ ] **Step 1: Typecheck + unit tests (fork).** From repo root: `npm run test:packages:data-schemas` and `npm run test:packages:api` (or the single-file jest runs already done). All green. Run the package builds (`npm run build:data-schemas`, and `packages/api` build) → no TS errors.
- [ ] **Step 2: Disposable live-proxy integration check.** A throwaway node script (in scratchpad, NOT committed) using the real `LITELLM_BASE_URL`/`LITELLM_MASTER_KEY`: `modelNew` a `zzz-scratch/gpt-test` pointing at a dummy base → `keyGenerate` scoped to it → `GET /v1/models` with that key shows exactly that model → `keyDelete` + `modelDelete` → confirm gone via `/model/info`. Confirms the client's request/response shapes against v1.83.10. Clean up everything; never touch real endpoints.
- [ ] **Step 3: Push + PR.** Push `feat/litellm-gateway-sync` (fork) and the nufi-chat branch. Open a PR into `develop` on `dudaji-vn/nufichat` (`gh pr create --repo dudaji-vn/nufichat --base develop`). Body: summary, the fail-closed invariant, the flag-off-by-default safety, test evidence, and the manual handoff checklist.
- [ ] **Step 4: Handoff checklist** (in the PR + to the user): rotate the LiteLLM master key; review PR; merge to `develop`; run the nufi-release flow to build the GHCR image; set the three env vars (with the rotated key) + bump `IMAGE_TAG` in the Railway deploy; flip `LITELLM_SYNC_ENABLED=true`; smoke-test by creating a custom endpoint in the admin panel and confirming it appears in LiteLLM `/model/info` and that chat routes through it.

---

## Self-Review

**Spec coverage:** schema/methods (T1) ✓; client (T2) ✓; reconciler create/update/delete + per-endpoint virtual key + namespacing + status (T3) ✓; runtime rewrite + fail-closed sentinel (T4) ✓; admin hooks + re-sync route (T5) ✓; env + flag-off default (T6) ✓; verify/PR/handoff incl. disposable live check + key rotation (T7) ✓. LiteLLM API contract (spec §7) exercised in T2 + T7. Non-goals respected (admin panel untouched; YAML base endpoint passthrough in T4).

**Placeholder scan:** No TBD/TODO; each task has concrete code or exact signatures + commands.

**Type consistency:** `ILiteLLMSync`/`LiteLLMSync`, method names (`findLiteLLMSyncByEndpointNames`, `upsertLiteLLMSync`, ...), `applyEndpointRewrite`, `reconcileLiteLLM`, `EndpointInput`, `SENTINEL_VIRTUAL_KEY`, `litellmModelName` used consistently across T1→T5.

**Known risk carried from spec §15:** RESOLVED — agent trace confirmed both chat + model-fetch read from `getAppConfig` merged config; rewrite placed in Branch F (managed endpoints only appear there). Dropdown shows namespaced `"<endpoint>/<model>"` (accepted per D4).
