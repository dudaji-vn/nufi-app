# LiteLLM Gateway Sync — Design

- **Date:** 2026-07-13
- **Status:** Approved (design); ready for implementation planning
- **Repo:** `dudaji-vn/nufichat` (this fork). Deploy wiring in `dudaji-vn/nufi-chat`.
- **Branch:** `feat/litellm-gateway-sync`

## Tóm tắt (Vietnamese summary)

Khi admin tạo/sửa/xóa một **custom endpoint** trong admin panel, hệ thống tự động
đăng ký model của endpoint đó vào **LiteLLM proxy trung tâm** (`api.codechi.me`),
tạo một **virtual key** riêng cho endpoint, rồi **rewrite** endpoint ở runtime để
LibreChat gọi LiteLLM thay vì gọi thẳng provider. Mục tiêu: mọi lưu lượng AI đi qua
LiteLLM (cost/logging tập trung, giấu key provider, rate-limit/budget/guardrail tập
trung, một registry model duy nhất). Trải nghiệm admin panel **không đổi**.

---

## 1. Goal & motivation

Make the operator's central LiteLLM proxy the single chokepoint for **all** AI
traffic that flows through admin-created custom endpoints. Concretely:

- Centralized cost tracking, request logging, and observability (Langfuse /
  Prometheus already enabled on the proxy).
- Provider API keys never leave LiteLLM — LibreChat only ever holds a LiteLLM
  virtual key.
- Central rate-limit / budget / guardrail enforcement (Presidio PII masking +
  budget limiters already enabled on the proxy). Future: move the fork's
  app-layer guardrails (`GUARDRAIL_*`) down to the LiteLLM layer.
- LiteLLM becomes the single source of truth for model → provider routing.

## 2. Non-goals

- No change to the admin-panel UI in Phase 1 (it keeps showing the real provider
  values the admin typed).
- Not managing the YAML-defined base endpoint (`Nufi` in `librechat.yaml`). That
  is operator-controlled deployment config — the operator points
  `BACKEND_BASE_URL` at LiteLLM directly if desired. Only **admin-panel-created**
  custom endpoints are governed by this sync system.
- No provider auto-detection. Every custom endpoint is treated as
  OpenAI-compatible (which is what LibreChat custom endpoints already require).
- No multi-tenant fan-out beyond what the existing `Config` principal/tenant
  model already provides (Phase 1 targets the single/base-config case).

## 3. Background — how custom endpoints work today

The fork has a runtime config-override layer on top of the static
`librechat.yaml`:

- **Storage:** MongoDB `Config` collection. One document per principal
  (role/user/group) per tenant, field `overrides` (Mixed) holds a YAML-shaped
  tree, e.g. `{ endpoints: { custom: [ {name, apiKey, baseURL, models, ...} ] } }`.
  Schema: `packages/data-schemas/src/schema/config.ts`.
- **Admin API:** `packages/api/src/admin/config.ts` → `createAdminConfigHandlers`,
  mounted under `/api/admin/config` (guarded by `ACCESS_ADMIN`). Write paths:
  `upsertConfigOverrides` (PUT whole override, ~config.ts:264/352),
  `patchConfigField` (PATCH `.../fields`, ~config.ts:373/461),
  `deleteConfigField` (~config.ts:482), `deleteConfigOverrides` (~config.ts:540).
  The admin panel's `saveBaseConfigFn` uses `PATCH .../fields`.
- **Runtime merge:** `packages/data-schemas/src/app/resolution.ts` →
  `mergeConfigOverrides()`. `ARRAY_MERGE_KEYS = { 'endpoints.custom': 'name' }` so
  custom endpoints merge **by `name`**. Consumed in
  `packages/api/src/app/service.ts` → `getAppConfig()` at line ~202, result
  cached per-principal with a TTL (`DEFAULT_OVERRIDE_CACHE_TTL = 60_000`).
- **Endpoint fields:** `packages/data-provider/src/config.ts` `endpointSchema`
  (`name`, `apiKey`, `baseURL`, `iconURL`, `models {fetch, default}`,
  `modelDisplayLabel`, title/summarize options).
- **Secret crypto:** `packages/data-schemas/src/crypto/index.ts` exports
  `encrypt`/`decrypt` (+V2/V3). Used to encrypt stored virtual keys.

There is currently **no** LiteLLM integration anywhere (only illustrative
comments/test fixtures).

## 4. Design overview & the core invariant

**Core invariant (fail-closed):** For every admin-created custom endpoint, the
config that LibreChat actually uses at runtime **always** has
`baseURL = <LITELLM_BASE_URL>`. The real provider `baseURL`/`apiKey` never enters
LibreChat's runtime view. An endpoint is "LiteLLM-managed" iff it has a
`LiteLLMSync` record. That record carries a `status`:

- `active` → runtime rewrite injects the working **virtual key** → routes
  normally through LiteLLM.
- `pending` / `failed` (sync incomplete) → still rewritten to LiteLLM, but with
  **no working key** → requests fail with a clear error. No fallback to the
  direct provider. Admin re-syncs.

This makes "everything goes through LiteLLM" a **structural** property, not a
conditional one.

### Two decoupled halves

1. **Write-side reconcile (on admin save/delete):** diff desired custom
   endpoints (from the `Config` override) against actual (`LiteLLMSync` +
   LiteLLM), then create/update/delete LiteLLM models and the per-endpoint
   virtual key to converge.
2. **Read-side rewrite (on `getAppConfig`):** after `mergeConfigOverrides`,
   rewrite each managed custom endpoint's `baseURL`/`apiKey`/`models` from its
   `LiteLLMSync` record before the merged config is cached and returned.

The two halves communicate only through the `LiteLLMSync` collection. The admin
panel keeps reading the raw override (real values); LibreChat reads the rewritten
config. No admin-panel change needed.

## 5. Components (new)

| Component | Path (fork) | Responsibility |
|---|---|---|
| LiteLLM client | `packages/api/src/litellm/client.ts` | Thin wrapper over LiteLLM admin API: `modelNew`, `modelUpdate`, `modelDelete`, `modelInfo`, `keyGenerate`, `keyUpdate`, `keyDelete`. Reads `LITELLM_BASE_URL` + `LITELLM_MASTER_KEY`. Timeouts + typed errors. |
| Reconciler | `packages/api/src/litellm/reconcile.ts` | `reconcileEndpoints(principalScope)`: idempotent diff → converge. Also `unsyncEndpoint(name)` for deletes. Writes `LiteLLMSync`. |
| Rewrite | `packages/api/src/litellm/rewrite.ts` (or inline in `service.ts`) | `rewriteCustomEndpointsToLiteLLM(config)`: per managed endpoint, replace `baseURL`/`apiKey`/`models`. |
| Sync schema | `packages/data-schemas/src/schema/litellmSync.ts` + methods in `.../methods/litellmSync.ts` | Persistent endpoint ↔ LiteLLM mapping. |
| Admin hook | edits in `packages/api/src/admin/config.ts` | After successful save/delete of `endpoints.custom`, call the reconciler. |
| Runtime hook | edits in `packages/api/src/app/service.ts` | Call the rewrite right after `mergeConfigOverrides` (line ~202), before caching. |
| Config/env | `packages/api/src/...` env reads; deploy wiring in `nufi-chat` | New env vars (§10). |

### `LiteLLMSync` schema (fields)

```
{
  tenantId:        string,        // matches Config tenant scoping
  endpointName:    string,        // the custom endpoint `name` (join key)
  status:          'pending' | 'active' | 'failed',
  virtualKey:      string,        // ENCRYPTED (crypto.encrypt) LiteLLM key
  models: [                       // one per endpoint model
    { sourceModel: string,        // raw model the admin entered, e.g. "gpt-4o"
      litellmModelName: string,   // public alias, "<endpoint>/<model>"
      litellmModelId: string }    // uuid returned by /model/new (for update/delete)
  ],
  realBaseURLHash: string,        // sha256 of real baseURL — detect drift w/o storing secret
  lastError:       string | null,
  lastSyncedAt:    Date,
  createdAt, updatedAt
}
// Unique index on (tenantId, endpointName).
```

## 6. Data flows

### 6.1 Create / update (admin saves an endpoint)

```
Admin panel ─PATCH /api/admin/config/.../fields─▶ patchConfigField (config.ts)
  1. Persist override as today (REAL provider baseURL/apiKey).       [unchanged]
  2. Invalidate config caches as today.                              [unchanged]
  3. If LITELLM_SYNC_ENABLED and the change touched endpoints.custom:
        reconcileEndpoints(scope)  ── best-effort, does NOT block/rollback the save
```

`reconcileEndpoints(scope)`:
1. Load desired endpoints from the merged override for that scope.
2. Load existing `LiteLLMSync` records for the scope.
3. For each desired endpoint, upsert a `LiteLLMSync` record (`status='pending'`),
   then converge with LiteLLM:
   - **New model:** `POST /model/new`
     `{ model_name: "<endpoint>/<model>",
        litellm_params: { model: "openai/<model>", api_base: <realBaseURL>, api_key: <realKey> } }`
     → store returned `litellmModelId`.
   - **Changed baseURL/apiKey (realBaseURLHash drift or key change):**
     `POST /model/update` for each affected model (by `litellmModelId`).
   - **Removed model:** `POST /model/delete { id }`.
   - **Virtual key:** if none, `POST /key/generate`
     `{ models: ["<endpoint>/<m1>", ...], key_alias: "nufi-ep-<endpoint>",
        metadata: { endpoint: "<endpoint>", tenant: "<tenantId>" } }`;
     else `POST /key/update { key, models: [...] }` to keep the allow-list in
     sync. Store the key **encrypted**.
4. On full success → `status='active'`, `lastError=null`. On any failure →
   `status='failed'`, `lastError=<msg>` (endpoint stays fail-closed).

Reconcile is a **diff/converge** operation keyed by endpoint name + model name,
so it is idempotent and robust regardless of which admin handler triggered it.

### 6.2 Delete (admin removes an endpoint or the whole override)

`deleteConfigField` / `deleteConfigOverrides` → after the delete:
- For each affected endpoint: `POST /model/delete` for every `litellmModelId`,
  `POST /key/delete { keys: [virtualKey] }`, then remove the `LiteLLMSync` record.

### 6.3 Runtime rewrite (chat + model fetch)

In `getAppConfig`, right after `const merged = mergeConfigOverrides(...)`:

```
merged = await rewriteCustomEndpointsToLiteLLM(merged, { tenantId });
// then cache + return `merged` (rewritten form is what gets cached)
```

`rewriteCustomEndpointsToLiteLLM`:
- For each `endpoints.custom[]` that has a `LiteLLMSync` record:
  - `baseURL` → `<LITELLM_BASE_URL>` (e.g. `https://api.codechi.me/v1`).
  - `apiKey` → decrypted `virtualKey` if `status='active'`, else a sentinel
    invalid key (fail-closed).
  - `models.fetch` → `true`; `models.default` → the `litellmModelName` list.
    (The scoped virtual key makes `/v1/models` return exactly this endpoint's
    namespaced models, keeping the dropdown correct and isolated.)
- Endpoints **without** a sync record (e.g. the YAML base `Nufi`) pass through
  unchanged.

Because the rewritten config is what gets cached (TTL 60s), the extra DB lookup
per managed endpoint is amortized. Rewrite reads `LiteLLMSync` (cheap, indexed)
and decrypts keys in-process.

## 7. LiteLLM API contract (proxy v1.83.10, master key)

- `POST /model/new` — `{ model_name, litellm_params, model_info? }` → `{ model_id }`.
- `POST /model/update` — update by `model_info.id`.
- `POST /model/delete` — `{ id }`.
- `GET  /model/info` — list registered models (diff/repair).
- `POST /key/generate` — `{ models, key_alias, metadata, max_budget? }` → `{ key }`.
- `POST /key/update` — `{ key, models }`.
- `POST /key/delete` — `{ keys: [...] }`.

The proxy has a connected DB, so models/keys created via API persist across
restarts. Exact request/response shapes are confirmed against the live proxy in
a disposable scratch test before wiring (create → verify → delete), never
against real admin data.

## 8. Key decisions (locked)

| # | Decision | Choice |
|---|---|---|
| D1 | Rewrite strategy | **Store real values; rewrite only in LibreChat runtime.** Admin panel unchanged. |
| D2 | Provider registration | Treat every endpoint as OpenAI-compatible → `litellm_params.model = "openai/<model>"` + `api_base`. No provider guessing. |
| D3 | Virtual key | **One key per endpoint**, scoped to that endpoint's namespaced models, with cost metadata. |
| D4 | Model naming | **Namespaced:** `model_name = "<endpoint>/<model>"`. Guarantees no cross-endpoint collision; LibreChat dropdown shows `"<endpoint>/<model>"`. |
| D5 | Failure mode | **Fail-closed.** No fallback to the direct provider; unsynced endpoints are non-functional until re-synced. |
| D6 | Feature flag | `LITELLM_SYNC_ENABLED`. Off → no reconcile, no rewrite (legacy behavior: endpoints call providers directly). |

## 9. Failure handling & fail-closed semantics

- **Reconcile fails on save:** the config save still succeeds (admin isn't
  blocked), but the endpoint's `LiteLLMSync.status` stays `pending`/`failed`.
  Runtime rewrite serves it fail-closed (rewritten to LiteLLM, no working key →
  requests error clearly). A manual **re-sync** entry point (admin API +
  Phase-2 panel button) retries.
- **LiteLLM unreachable at rewrite time:** the rewrite only needs the stored
  (encrypted) virtual key from `LiteLLMSync` — no live LiteLLM call — so chat
  keeps working as long as the key was minted. If the record is `failed`, the
  endpoint stays down (correct fail-closed behavior).
- **Partial model sync:** per-model `litellmModelId` tracking lets reconcile
  resume and converge without duplicating models.
- **Drift/repair:** `realBaseURLHash` detects an admin changing the upstream
  URL; reconcile issues `/model/update`.

## 10. Config / env

New env vars (read in the fork; wired in `nufi-chat` `docker-compose.yml` +
`.env.example`):

```
LITELLM_SYNC_ENABLED=true                 # master switch for this feature
LITELLM_BASE_URL=https://api.codechi.me   # rewrite target (a "/v1" suffix is normalized)
LITELLM_MASTER_KEY=<rotated master key>   # admin API auth; NEVER commit
```

Virtual keys are encrypted at rest with the existing `CREDS_KEY`/`CREDS_IV`
mechanism (`crypto.encrypt`).

## 11. Security considerations

- ⚠️ The master key was shared in plaintext during design → **rotate it** and use
  the new key for `LITELLM_MASTER_KEY`. Never commit either key.
- LibreChat stores only encrypted **virtual** keys (scoped, revocable,
  budget-capped) — real provider keys live solely in LiteLLM (goal: hide keys).
- The reconciler runs only inside `ACCESS_ADMIN`-guarded handlers.

## 12. Phasing

**Phase 1 (MVP)**
- `LiteLLMSync` schema + methods.
- LiteLLM client + reconciler (create/update/delete, per-endpoint virtual key).
- Runtime rewrite in `getAppConfig`.
- Admin-handler hooks (upsert/patch/delete).
- Feature flag + env wiring in `nufi-chat`.
- Fail-closed behavior + clear errors + a manual re-sync admin route.
- Tests (§13).

**Phase 2 (later)**
- Background periodic re-reconcile (self-heal after LiteLLM downtime).
- Admin-panel sync-status badge + "re-sync" button per endpoint.
- Multi-tenant hardening; bulk import reconcile.
- Optional: move `GUARDRAIL_*` enforcement to the LiteLLM layer.

## 13. Testing strategy

- **Unit:** reconciler diff logic (new/changed/removed model, key allow-list
  update) with a mocked LiteLLM client; rewrite function (active vs
  pending/failed → sentinel key); `realBaseURLHash` drift detection.
- **Schema/crypto:** virtual key round-trips encrypt/decrypt; unique index.
- **Integration (disposable):** against the live proxy with a throwaway endpoint
  name — create endpoint → assert model+key exist in LiteLLM → chat routes →
  delete endpoint → assert cleanup. Never touches real endpoints.
- **Fail-closed:** simulate LiteLLM 5xx on save → endpoint `failed` → chat
  request errors (does not hit the real provider).

## 14. Rollout

1. Merge into `develop`, cut a release via the nufi-release flow → GHCR image.
2. In `nufi-chat`: add the three env vars, bump `IMAGE_TAG`, redeploy (Railway).
3. Verify: create a test custom endpoint in admin panel → confirm it appears in
   LiteLLM `/model/info` and chat works → confirm real provider baseURL never
   appears in LibreChat's runtime config.

## 15. Open questions / risks

- Dropdown shows namespaced `"<endpoint>/<model>"`. Acceptable per D4; a friendly
  display-label mapping can be added later if desired.
- `getAppConfig` rewrite adds a per-principal DB read on cache miss (every 60s).
  Cheap and indexed; acceptable. Revisit if it shows up in profiling.
- Confirm both the chat-completion path and `loadConfigModels` read endpoint
  `baseURL`/`apiKey` **from the `getAppConfig` merged config** (so a single
  rewrite covers both). To be verified first thing during implementation.
```
