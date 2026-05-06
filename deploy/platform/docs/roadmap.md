# NPUOps 2Q Roadmap — Platform Track (sun)

Q2 2026 (2026-04-28 → 2026-06-27, 9 weeks). GPU platform end-to-end with NPU integration ready.

## Pre-W1 Setup (Week of Apr 27)

### Environment Setup

- [x] Initialize Git repo: `npuops-platform`
- [x] Recommended directory structure:
  ```
  npuops-platform/
  ├── docker-compose.yml
  ├── docker-compose.override.yml  # local dev overrides
  ├── litellm/
  │   ├── config.yaml
  │   └── Dockerfile
  ├── langfuse/
  ├── librechat/
  │   └── librechat.yaml
  ├── monitoring/
  │   ├── prometheus.yml
  │   └── grafana/dashboards/
  ├── scripts/
  └── docs/
  ```
- [x] Prepare `.env.example` with placeholders for all secrets
- [x] Set up basic CI (lint, build Docker image) — `.github/workflows/ci.yml`
- [ ] Provision a GPU-enabled server/VM (verify driver and CUDA version)

### Dependencies to Confirm with Team

- GPU model used for development (Llama? Qwen? which size?)
- Domain/subdomain to expose LibreChat
- SSO/Auth provider (if any) — confirm early to avoid refactoring later

---

## Phase 1 · Base Platform (W1–W2)

### W1 (Apr 28 – May 2)

#### Task 1.1 — LiteLLM Proxy + GPU Backend Connection

**Status:** ✅ Done (2026-05-04) — verified locally against Ollama (`qwen2.5:3b`) on Mac. Real GPU backend swap is a `.env` change.

**Goal:** LiteLLM Proxy runs, can call a GPU model, and is testable via curl or the OpenAI SDK.

**Steps:**

1. **Initialize Docker Compose**
   - [x] `docker-compose.yml`
   - [x] `litellm-proxy` service (image `ghcr.io/berriai/litellm:main-stable`)
   - [x] `redis` service (for rate limiting and caching, used from W3)
   - [x] `postgres` service (for LiteLLM virtual key store + Langfuse)
   - [x] Shared network for all services (`npuops`)

2. **Design `config.yaml` to be NPU-extensible**
   - [x] `litellm/config.yaml`

   ```yaml
   model_list:
     # GPU models — active from W1
     - model_name: llama-3-gpu
       litellm_params:
         model: openai/llama-3-8b
         api_base: http://gpu-backend:8000/v1
         api_key: dummy
       model_info:
         backend_type: gpu
         hardware_id: gpu-node-01

     # NPU models — placeholder, commented out until W8
     # - model_name: llama-3-npu
     #   litellm_params:
     #     model: openai/llama-3-8b
     #     api_base: http://npu-backend:8000/v1
     #   model_info:
     #     backend_type: npu

   router_settings:
     routing_strategy: simple-shuffle # change to weighted-pick at W8 for Canary

   general_settings:
     master_key: os.environ/LITELLM_MASTER_KEY
     database_url: os.environ/DATABASE_URL
   ```

   - **Important:** keep the `model_info.backend_type` field from Day 1 so W8 does not require a refactor

3. **Verify**
   - [x] `scripts/smoke-test.sh`
   - [x] `curl http://localhost:4000/v1/models` returns the model list
   - [x] `curl -X POST http://localhost:4000/v1/chat/completions` with a simple prompt returns a valid response
   - [ ] Test with the Python OpenAI SDK _(bash test covers the same OpenAI-compatible surface; SDK pass is a nice-to-have)_

**Acceptance Criteria:**

- [x] `docker compose up -d` runs cleanly
- [x] Healthcheck endpoint `/health/liveliness` returns 200
- [x] Tests cover 3 cases: chat completion, streaming, error handling — `scripts/smoke-test.sh`

**Effort estimate:** 2 days

---

#### Task 1.2 — Langfuse Setup + LiteLLM Integration

**Status:** ✅ Done (2026-05-04) — full Langfuse v3 stack up, traces visible in UI, smoke test 6/6.

> **Heads-up:** The original plan assumed Langfuse v2 (single service, ClickHouse optional).
> Langfuse v3 (current) **requires** ClickHouse + S3-compatible blob storage. The
> stack now includes `clickhouse` + `minio` (+ `minio-init` to provision the
> bucket on first boot) alongside `langfuse-web` and `langfuse-worker`.

**Goal:** Every request through LiteLLM is traced in Langfuse with cost aggregation.

**Steps:**

1. **Deploy Langfuse v3 stack**
   - [x] `docker-compose.yml`
   - [x] `clickhouse` service (`clickhouse/clickhouse-server:24.8-alpine`)
   - [x] `minio` service (S3-compatible blob store) + `minio-init` to create the `langfuse` bucket
   - [x] `langfuse-web` service (`langfuse/langfuse:3`) on port 3000
   - [x] `langfuse-worker` service (`langfuse/langfuse-worker:3`)
   - [x] Separate `langfuse` database on the shared Postgres (provisioned via `scripts/postgres-init.sh`)

2. **Auto-provision the project** — [x] via `LANGFUSE_INIT_*` env vars on `langfuse-web`
   - Org `npuops`, project `npuops-default`, admin user from `.env`
   - `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` from `.env` are wired in on first boot — no manual UI step needed

3. **Enable callbacks in LiteLLM** — [x] `litellm/config.yaml`

   ```yaml
   litellm_settings:
     success_callback: ["langfuse"]
     failure_callback: ["langfuse"]
     langfuse_default_tags: ["hardware_id", "backend_type"]
   ```

   - [x] Env vars passed through compose: `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST` (= `http://langfuse-web:3000`)

4. **Verify cost aggregation** — [x] `scripts/smoke-test.sh` step 6 queries `/api/public/traces`
   - [x] Send 10–20 test requests against the running stack — covered by smoke test
   - [x] Confirm traces appear in the Langfuse UI at <http://localhost:3000>
   - [x] Confirm token counts and `cost` are populated (pricing from `model_info.input_cost_per_token` / `output_cost_per_token` in `litellm/config.yaml`)

**Acceptance Criteria:**

- [x] 100% of requests have a corresponding trace in Langfuse
- [x] Cost field is never null
- [ ] Latency overhead < 50ms _(not benchmarked yet — defer to W4 perf pass)_

**Effort estimate:** 2 days

**Gotchas captured during implementation (2026-05-04):**

- Don't use `clickhouse/clickhouse-server:*-alpine` on Apple Silicon — server hangs silently. Use the Ubuntu-based tag.
- ClickHouse healthcheck must use `127.0.0.1`, not `localhost` (Docker Desktop disables IPv6, but `localhost` resolves to `::1` first inside the alpine wget shipped in the healthcheck).
- Quote `.env` values containing spaces (e.g. `LANGFUSE_INIT_USER_NAME="NPUOps Admin"`) so shell scripts that `source .env` don't break.
- LiteLLM does not hot-reload `config.yaml`. After editing callbacks, run `docker compose restart litellm-proxy`.
- Langfuse `LANGFUSE_INIT_*` env vars only auto-provision the project on a fresh DB. If the `langfuse` Postgres database already exists, drop+recreate before restarting `langfuse-web`.

---

#### Task 1.3 — W1 Buffer & Cleanup

**Status:** 🟢 Tag pushed (2026-05-04) — demo to team still pending.

- [x] Write a setup README for new team members — `README.md` + `scripts/bootstrap.sh` (one-command setup)
- [x] Push to repo, tag `v0.1.0-alpha` — Git Flow release: `release/0.1.0-alpha` → `main` (commit `14b289b`), tag pushed to `origin`
- [ ] Demo to the team on Friday (2026-05-08)

**Effort estimate:** 1 day

---

### W2 (May 5 – May 9)

#### Task 2.1 — LibreChat Deploy + LiteLLM Connection

**Status:** ✅ Done (2026-05-04) — LibreChat live at http://localhost:3080, model dropdown auto-populated from LiteLLM, chat → Ollama → Langfuse trace flow verified.

> **Decision (2026-05-04):** Replaced Open WebUI with LibreChat. Open WebUI's
> license shifted away from pure open-source in 2025 (commercial-branding
> restrictions). LibreChat is Apache-2.0 with native support for OpenAI-compatible
> custom endpoints — perfect fit for the LiteLLM proxy.

**Goal:** Users have a chat UI, connected to LiteLLM, with basic branding.

**Steps:**

1. **Deploy LibreChat + MongoDB** — [x] `docker-compose.yml`
   - [x] `mongodb` service (image `mongo:7`) — LibreChat stores users / convos here
   - [x] `librechat` service (image `ghcr.io/danny-avila/librechat:v0.7.5` — pinned)
   - Configure env (loaded from root `.env`):
     ```
     APP_TITLE=NPUOps
     MONGO_URI=mongodb://librechat:.../LibreChat?authSource=admin
     JWT_SECRET=...
     JWT_REFRESH_SECRET=...
     CREDS_KEY=...                # 32-byte hex
     CREDS_IV=...                 # 16-byte hex
     ENDPOINTS=custom
     ```
   - Volume-mount `./librechat/librechat.yaml:/app/librechat.yaml:ro` for endpoint config

2. **Wire LiteLLM as the only endpoint**
   - [x] `librechat/librechat.yaml`

   ```yaml
   version: 1.2.1
   endpoints:
     custom:
       - name: "NPUOps"
         apiKey: "${LITELLM_MASTER_KEY}"
         baseURL: "http://litellm-proxy:4000/v1"
         models:
           default: ["llama-3-gpu"]
           fetch: true # auto-discover from LiteLLM /v1/models
         titleConvo: true
         titleModel: "llama-3-gpu"
         modelDisplayLabel: "NPUOps"
   ```

3. **Branding customization** — [~] partial
   - [x] App name via `APP_TITLE` env var (defaults to `NPUOps`)
   - [ ] Logo / favicon: drop into `librechat/assets/` and mount into the container's `client/public/assets/`
   - [x] `interface` block scaffolded in `librechat.yaml` (privacy / TOS placeholders ready)

4. **Test the model dropdown**
   - [x] Verify LibreChat fetches `/v1/models` from LiteLLM and shows `llama-3-gpu`
   - [x] Send a message → response streams back

5. **Conversation history**
   - [x] Built-in; persisted in MongoDB. Verified after `docker compose restart librechat`.

**Acceptance Criteria:**

- [x] Register → login → select model → chat → response streams
- [x] Conversations persist after page reload and container restart
- [~] Branding — `APP_TITLE` works; logo / favicon swap deferred until brand assets are finalized

**Effort estimate:** 2 days

---

#### Task 2.2 — End-to-end Smoke Test + W2 Checkpoint

**Status:** ✅ Done (2026-05-05) — `./scripts/e2e-smoke-test.sh` runs
containerised; 6/7 hard checks green, 1 soft warning surfaces a `hardware_id`
propagation gap (see follow-ups below). Earlier checkpoint deck removed in
`daa4ca2` — re-create before the team demo (now paired with W4 demo on
2026-05-08).

**Goal:** The flow `User → LibreChat → LiteLLM → GPU → Langfuse trace` works.

**Steps:**

1. [x] Write an automated smoke test script (Python) to:
   - [x] Authenticate against LibreChat (register-or-login → JWT)
   - [x] Send a message via `POST /api/ask/custom` (the endpoint name is in
         the body; the URL path is the endpoint _type_, not the name — see
         `validateEndpoint` middleware in LibreChat 0.7.5)
   - [x] Assert the response stream returns non-empty text
   - [x] Query the Langfuse API → assert the trace exists, has cost, and
         records the right model
2. [x] Prepare W2 checkpoint demo: `docs/demos/w2-checkpoint.md` (5 slides),
       live demo for gom and hoon on Friday 2026-05-08

**Effort estimate:** 2 days (delivered in 0.5 day; the `add-model.sh` SIGPIPE
fix and config dedup that came along ate another half day).

**Findings during implementation (2026-05-05):**

- **`uaParser` middleware** in LibreChat 0.7.5 rejects any request whose
  User-Agent isn't a recognised browser — the e2e client must spoof a Firefox
  UA. Documented in `scripts/e2e/e2e_smoke_test.py`.
- **`hardware_id` propagation gap.** `langfuse_default_tags: ["hardware_id"]`
  in `litellm/config.yaml` is silently ignored — LiteLLM only resolves
  `cache_hit`/`cache_key` natively (see
  `litellm/integrations/langfuse/langfuse.py::add_default_langfuse_tags`).
  **Resolved 2026-05-06** by a custom pre-call hook
  (`litellm/callbacks/hardware_metadata.py`) that reads `model_info` from
  `config.yaml` and stamps `hardware_id` + `backend_type` onto every trace
  as both Langfuse tags (queryable) and `trace_metadata` (structured).
  E2E section 7/7 now hard-asserts the propagation.
- **SIGPIPE bug in `add-model.sh:314` and `bootstrap.sh:543/614`** — the
  uniqueness check used `yq | grep -Fxq "$NAME"`, which under `set -o pipefail`
  returns 141 (SIGPIPE on yq) when grep matches early, so the `if` evaluated
  the success case as false. That's why duplicates accumulated. Fixed by
  switching to `yq … any_c(.model_name == strenv(NAME))` and treating
  re-registration as idempotent (skip silently).

> 🏁 **W2 Checkpoint:** GPU platform flow works end-to-end

---

## Phase 2 · Self-Service Features (W3–W4)

### W3 (May 12 – May 16)

#### Task 3.1 — API Key Issuance UI

**Status:** ✅ Done (2026-05-05) — shipped in `console/` (PR #8). Backend wraps LiteLLM `/key/{generate,delete,list,info}` in `console/server/router/keys.ts`; UI at `console/src/routes/keys.tsx` with name / team / project / expiry, reveal-once modal on creation, masked list (`sk-...abc123`), copy + delete actions. Footer link from LibreChat lands the user already authenticated (PR #10 soft-fork submodule + patches).

**Goal:** Users can self-serve API keys via a UI without admin intervention.

**Steps:**

1. **Backend (using LiteLLM Virtual Keys API)**
   - LiteLLM exposes `/key/generate`, `/key/delete`, `/key/list`
   - Wrap in an internal API if extra logic for team/project tagging is needed

2. **UI design**
   - LibreChat doesn't have a stable plugin API for custom admin pages, so
     build a **standalone admin app** (Next.js / React) and link to it from
     LibreChat's `interface.customWelcome` or as an external link
   - Authenticate the admin app against LiteLLM's master key (admin role only)
   - Required components:
     - Form fields: `name`, `team`, `project`, `expiry`
     - Generate button
     - Modal showing the key once after creation (with "shown only once" warning)
     - Key list table: name, masked key (`sk-...abc123`), team, project, created_at, action
     - Copy and delete buttons

3. **Masking logic**
   - Frontend shows only first 4 + last 4 characters
   - Backend never returns the full key after creation

4. **Team/project separation**
   - LiteLLM supports `team_id` in key metadata
   - Store team→project mapping in DB if needed

**Acceptance Criteria:**

- Generate key → copy → use it to call LiteLLM successfully
- Delete key → key is rejected immediately afterwards
- Keys are masked correctly in list views

**Effort estimate:** 3 days

---

#### Task 3.2 — Budget & Rate Limit Management

**Status:** ✅ Done (2026-05-05) — `max_budget`, `budget_duration`, `tpm_limit`, `rpm_limit` are real passthrough fields on key create (defaults in `keys.ts`); live remaining-budget + rate-limit windows shown on the keys table via `/key/info`. Redis already wired since W1; no extra config needed. (PR #8)

**Goal:** Each key has a budget and rate limits; requests over the limits are rejected.

**Steps:**

1. **Configure LiteLLM**
   - In `config.yaml`:
     ```yaml
     general_settings:
       max_budget: 1000 # default fallback
       budget_duration: 30d
     ```
   - When generating keys, set:
     - `max_budget`
     - `tpm_limit` (tokens per minute)
     - `rpm_limit` (requests per minute)

2. **Redis counting**
   - LiteLLM uses Redis for rate limit counters
   - Verify Redis is running and reachable from LiteLLM
   - Set `redis_url` in config

3. **UI**
   - Add budget/rate limit fields to the key generation form
   - Show current usage in the list view (call `/key/info`)

4. **Tests**
   - Create a key with `tpm_limit: 100`
   - Spam requests → verify 429 is returned
   - Create a key with `max_budget: 0.10` → verify 403 after budget is exhausted

**Acceptance Criteria:**

- Rate limit exceeded → 429 with a clear error message
- Budget exceeded → 403 with a clear error message
- Counters reset correctly per period

**Effort estimate:** 2 days

---

### W4 (May 19 – May 23)

#### Task 4.1 — Self-Service Usage Dashboard

**Status:** ✅ Done (2026-05-06) — `/usage` route shipped end-to-end (PR #9, three Day-1/2/3 commits `fc73156` → `37cae56`). Procedures live in `console/server/router/usage.ts`: `usage.daily`, `usage.byModel`, `usage.recent`, `usage.byHardware`. Frontend renders summary cards, daily line chart with 7/30/90-day toggle, by-model bar chart, by-hardware bar chart (auto-hidden when only one hardware seen), and a recent-requests table. Langfuse client + 60s in-memory trace cache in `console/server/lib/langfuse.ts`. USER/ADMIN role filtering reuses the W3 middleware.

**Goal:** Users can view their token usage and cost over time.

> **Hosting decision (locked 2026-05-06):** Extend the standalone console
> shipped in W3 (Bun + Hono + oRPC + React 19, container `npuops-console` on
> port 3001). The `/usage` route already exists as a placeholder. No
> LibreChat fork. Integration point is the LibreChat footer link
> (`CUSTOM_FOOTER` env, set in `9535386`); LibreChat 0.7.5 doesn't expose
> `interface.customLinks` — pre-W3 verification confirmed this.

**Stack (inherited from W3 console):**

- BFF: Bun + Hono + oRPC, master-key auth to LiteLLM, JWT-cookie SSO
- Frontend: React 19 + Vite + TanStack Router + TanStack Query + Zustand
- UI: Tailwind + shadcn/ui (no new component library)
- Charts: shadcn/ui Chart primitive (Recharts under the hood — already aligned
  with shadcn styling we use everywhere else; no Tremor/visx dependency)

**Data sources (hybrid):**

- **Langfuse `/api/public/traces`** for per-request facts: cost, tokens,
  model, latency, and `hardware_id` (newly stamped by the W2.5 callback in
  `litellm/callbacks/hardware_metadata.py`, commit `77dfa1b`). Pulls the
  richer surface for charts and the recent-requests table.
- **LiteLLM `/key/info`** + `/user/info` for live budget remaining and
  rate-limit windows (the console's existing `LiteLLMClient` already wraps
  these — re-use, don't fork).

**What's already in place from W3** (don't rebuild):

- `usage.daily` procedure — buckets `spendLogsForUser` by UTC day, returns
  series + total + peak + most-recent + request count
- `UsageChart`, `AvailableHero`, `SpendBreakdown`, `TopKeysCard`,
  `LimitsBar`, `StatCard`, `BudgetCard` — already shipped on the profile
  route (`/`)
- Profile route shows the 7-day mini-dashboard. So W4 isn't building from
  scratch — it's adding the dedicated, deeper `/usage` route.

**Steps:**

1. **BFF — extend `console/server/router/usage.ts`**:
   - keep `usage.daily` as-is (backs both profile mini-chart and `/usage`
     when period=7/30)
   - `usage.byModel` → per-model spend + request count (re-aggregate
     `spendLogsForUser` server-side; no new client needed)
   - `usage.recent` → last 50 spend logs formatted for a table
   - `usage.byHardware` → per-`hardware_id` totals (uses Langfuse —
     LiteLLM spend logs don't carry hardware_id; this exercises the W2.5
     fix and prepares the API surface W6 will consume)

2. **Langfuse client** in `console/server/lib/langfuse.ts`:
   - Thin wrapper around `/api/public/traces` with paging
   - 60s in-memory cache (per `userId` + period) to absorb dashboard polling
   - All non-admin queries filter by `userId` (LibreChat's Mongo `_id` —
     LiteLLM `user` field is already populated per pre-W3 verification)

3. **Frontend — `/usage` route**:
   - Summary cards (4): budget remaining %, requests this period, total cost,
     primary `hardware_id`
   - Line chart: tokens/day with model overlay (7/30-day toggle)
   - Bar chart: cost by model
   - Bar chart: cost by hardware (hidden if user only ever hit one — common
     case until W8 NPU lands)
   - Table: last 50 requests, paginated, with model + hardware_id columns
   - 30s TanStack Query refetch interval; manual refresh button

4. **Role filtering** (re-use the W3 `role` middleware): USER sees their own
   `userId` only; ADMIN can pick a user from a dropdown or see "all".

5. **Smoke test** — extend `console/scripts/smoke.ts` with a hard check that
   `/usage` returns non-empty data after the chat smoke test runs.

**Out of scope (W4):**

- Cost projection / forecasting → revisit if useful in W8 cost-saving page
- CSV export → defer; users can hit the BFF directly if needed

**Acceptance Criteria:**

- Dashboard loads in < 2s on a populated database
- Totals match Langfuse UI within 1% drift
- USER role sees only their own data (verified by smoke test)
- ADMIN role can select any user
- `/usage` link in LibreChat footer → already-authenticated dashboard

**Effort estimate:** ~3 days (W3 infra + components carry most of it):

- **Day 1** — `/usage` route + period selector (7/30/90d), wire nav,
  re-use `usage.daily` + `UsageChart`. Add `usage.byModel` and
  `usage.recent` procedures (LiteLLM-only, server-side re-aggregation of
  `spendLogsForUser`). Render bar chart + recent-requests table.
- **Day 2** — Langfuse BFF client + `usage.byHardware` procedure. Add
  by-hardware bar chart (hidden when only one hardware seen). Smoke
  test extension. Polish.
- **Day 3** — buffer for charts/UI polish, demo script, W4.2 checkpoint.

---

#### Task 4.2 — W4 Checkpoint Demo

**Status:** 🟢 Code done (2026-05-06); team demo still pending (target Friday 2026-05-08, paired with the W2 demo that slipped). Earlier draft `docs/demos/w4-checkpoint.md` was deleted in `daa4ca2` — replace with a fresh deck before the demo.

**Effort estimate:** 1 day

> 🏁 **W4 Checkpoint:** Self-service Key / Budget / Usage complete — reached 2026-05-06, ~2 weeks ahead of the nominal W4 window (May 19–23).

---

## Phase 3 · Security · Audit · Reporting (W5–W7)

### W5 (May 26 – May 30)

#### Task 5.1 — LLM Guard Inline Integration

**Goal:** All requests are scanned for PII and prompt injection, with results logged to Langfuse.

**Steps:**

1. **Deploy LLM Guard**
   - Two options:
     - **Sidecar pattern:** LLM Guard as a separate service called over HTTP from LiteLLM
     - **Inline:** use LiteLLM Guardrails (built-in support for LLM Guard)
   - Recommendation: inline guardrails — simpler

2. **Configure guardrails in LiteLLM**

   ```yaml
   guardrails:
     - guardrail_name: pii-anonymizer
       litellm_params:
         guardrail: presidio
         mode: pre_call
         mask_request_content: true

     - guardrail_name: prompt-injection-detector
       litellm_params:
         guardrail: lakera_ai # or llm_guard
         mode: pre_call
         api_key: os.environ/LAKERA_API_KEY
   ```

3. **Langfuse Span logging**
   - LiteLLM auto-logs guardrail results as spans
   - Verify in Langfuse UI: traces have `guardrail.pii`, `guardrail.injection` spans

4. **Failure mode**
   - PII detected → mask before forwarding
   - Injection detected → reject with 400
   - Error handling: if the guardrail is down → fail-open or fail-closed? (Discuss with the security team)

**Acceptance Criteria:**

- Requests with PII (SSN, email, phone) are anonymized
- Requests with injection patterns are rejected
- Latency overhead < 200ms

**Effort estimate:** 3 days

---

#### Task 5.2 — Prometheus + Grafana Monitoring

**Goal:** Real-time platform health dashboards with Slack alerts.

**Steps:**

1. **Deploy Prometheus**
   - Service in Docker Compose
   - Scrape config:
     ```yaml
     scrape_configs:
       - job_name: litellm
         static_configs:
           - targets: ["litellm-proxy:4000"]
         metrics_path: /metrics
     ```
   - Enable `/metrics` in LiteLLM (`general_settings.prometheus_endpoint: true`)

2. **Deploy Grafana**
   - Provision Prometheus as a datasource
   - Import a community dashboard for LiteLLM, or build one

3. **Required dashboard panels**
   - Request rate (RPS) by model
   - Latency p50 / p95 / p99
   - Error rate (4xx / 5xx)
   - Token throughput
   - Active keys / spend rate

4. **Alertmanager → Slack**
   - Alert rules:
     - Error rate > 5% over 5 minutes
     - p95 latency > 10s over 5 minutes
     - Service down
   - Webhook to Slack channel `#npuops-alerts`

**Acceptance Criteria:**

- Dashboard loads quickly with near-real-time data (< 30s lag)
- Test alert fires → Slack receives it in < 2 minutes
- Dashboard is shareable via link

**Effort estimate:** 2 days

---

### W6 (Jun 2 – Jun 6)

#### Task 6.1 — NPU Utilization Certification Report (PDF)

**Goal:** Auto-generate a PDF report in the format required for government submission.

**Steps:**

1. **Define the PDF template**
   - Confirm the required format with the business team (e.g. NIPA / Korean government)
   - Required fields: company name, report period, hardware ID, total inference count, total compute time, cost savings vs. GPU
   - Mock the layout in Figma / Word first

2. **Tech stack**
   - **Recommended:** Python + WeasyPrint (HTML → PDF, easy templating)
   - Alternative: ReportLab (more granular control, but verbose)

3. **Data pipeline**
   - Cron job at the start of each month
   - Query the Langfuse API → aggregate by `hardware_id`
   - Render template → save PDF
   - Upload to S3 or local volume

4. **API endpoint**
   - `GET /reports/npu-utilization?month=2026-05` → returns the PDF
   - Authenticated (admin role only)

5. **Hardware ID field**
   - Ensure every request logs `hardware_id` in metadata from W1 onward
   - If missing — backfill from LiteLLM `model_info`

**Acceptance Criteria:**

- Generated PDF for a test month has the correct format and numbers
- Hardware ID is shown
- Includes a digital signature / hash for integrity verification (if required)

**Effort estimate:** 3 days

---

#### Task 6.2 — Monthly SLA Report

**Goal:** Customer-facing PDF aggregating SLA metrics.

**Steps:**

1. **Reuse infra from Task 6.1**
   - Same template engine
   - Different data: availability (uptime %), response time p50/p95, error rate, quality score (from gom)

2. **Quality score**
   - Coordinate with gom: gom exposes endpoint `/quality/monthly?month=...`
   - If not ready by W6 — placeholder N/A, fill in later

3. **Template**
   - Cover page with logo
   - Executive summary (1 page)
   - Charts (line for latency, bar for usage)
   - Appendix with raw numbers

**Acceptance Criteria:**

- PDF is clean and professional
- Numbers match Grafana / Langfuse
- Customizable per customer (logo, company name)

**Effort estimate:** 2 days

---

### W7 (Jun 9 – Jun 13)

#### Task 7.1 — GPU↔NPU Quality Equivalence Validation UI

**Goal:** UI for users to send a prompt and compare GPU vs. NPU responses.

**Steps:**

1. **Backend logic**
   - `POST /validation/compare` endpoint
     - Input: prompt
     - Logic: call both `llama-3-gpu` and `llama-3-npu` (W7 has no real NPU yet → mock with a second GPU using different params)
     - Output: 2 responses with latency and cost for each side
   - Diff metrics: BLEU / ROUGE / cosine similarity (use sentence-transformer)

2. **UI**
   - Prompt input (textarea)
   - "Compare" button
   - 2 columns: GPU response | NPU response
   - Diff highlight (use `react-diff-viewer`)
   - Numeric scores: similarity %, latency ratio, cost ratio
   - "Export PDF" button → generate a validation report

3. **Validation PDF**
   - List of test cases run
   - Aggregate scores
   - Conclusion: PASS / FAIL based on threshold (similarity > 95%)

**Acceptance Criteria:**

- UI is responsive, diff is clearly visible
- PDF generation completes in < 10s for 100 test cases
- Threshold is configurable

**Effort estimate:** 3 days

---

#### Task 7.2 — Batch Processing API + Webhook Alerts

**Goal:** Process large volumes asynchronously.

**Steps:**

1. **Job queue**
   - Use Celery + Redis (or RQ for simplicity)
   - Dedicated worker service

2. **API endpoints**
   - `POST /batch` — submit a batch (CSV / JSONL file)
     - Response: `{job_id}`
   - `GET /batch/{job_id}` — check status
   - `GET /batch/{job_id}/result` — download the result

3. **Webhook**
   - User provides `webhook_url` at submission time
   - Fired on:
     - Job complete
     - Job failed
     - Budget exhausted (< 10% remaining)
     - Error spike (> 10% during the batch)
   - Retry policy: 3 attempts with exponential backoff

4. **Alert config**
   - UI for users to set up webhooks and filter alert types

**Acceptance Criteria:**

- Submit a batch of 1000 requests → all processed, none missed
- Webhooks fire on the correct events with retries on failure
- Status endpoint is accurate

**Effort estimate:** 3 days

---

## Phase 4 · Integration + Buffer (W8–W9)

### W8 (Jun 16 – Jun 20)

⚠️ **High dependency on gom — sync at the start of the week**

#### Task 8.1 — Model Card + Canary Control UI

**Goal:** Admins can see the model list and control GPU/NPU traffic split via a slider.

**Steps:**

1. **Model list**
   - `GET /models/info` from LiteLLM
   - Display: name, backend (GPU/NPU), spec (context length, cost), status

2. **Canary slider UI**
   - For each model that has both GPU and NPU versions:
     - Slider: 0–100% NPU traffic
     - Save → update LiteLLM router config
   - **Important:** use LiteLLM `routing_strategy: weighted-pick` with corresponding weights

3. **Backend update**
   - LiteLLM supports hot reload via `/config/update` endpoint
   - Or edit `config.yaml` and signal a reload

4. **Rollback button**
   - Quick action: 100% GPU
   - Confirmation modal

**Dependencies:**

- gom must complete "Connect NPU backend" in W8 (same week) — sync early

**Acceptance Criteria:**

- Slider at 50% → ~50% requests to NPU, ~50% to GPU (verified via Langfuse)
- Rollback button completes in < 5s
- UI shows status in real time

**Effort estimate:** 3 days

---

#### Task 8.2 — Cost-Saving Report Page

**Goal:** A page showing savings from using NPU.

**Steps:**

1. **Integrate gom's Cost Calculator API**
   - **Sync with gom:** confirm endpoint signature in W7
   - Mock endpoint for development: returns `{gpu_cost: X, npu_cost: Y, savings: Z}`

2. **UI**
   - Big number: total savings this month
   - Chart: GPU cost vs. NPU cost by day
   - Breakdown by model
   - Projection: estimated savings if 100% migrated to NPU

3. **Export**
   - Reuse PDF infra from W6
   - "Export Cost Report" button

**Acceptance Criteria:**

- Numbers match gom's API
- Charts load in < 2s
- Edge case: division by zero (no NPU usage yet) → display "N/A"

**Effort estimate:** 2 days

---

### W9 (Jun 23 – Jun 27)

#### Task 9.1 — Bug Fix + Performance Tuning

**Goal:** Address all validation reports from hoon and tune performance.

**Allocation:**

- 3 days: bug fixes by priority (critical → high → medium)
- 1 day: performance tuning
  - Profile slow endpoints
  - Add caching where appropriate (Redis)
  - Optimize DB queries (indexes, N+1)

#### Task 9.2 — Demo Environment

**Steps:**

1. **Reset to a clean environment**
   - Fresh DB
   - Pre-populate demo data (sample API keys, sample usage)

2. **Demo scenario script**
   - Login as user → create API key → send chat → view dashboard
   - Login as admin → review Canary control → view Cost report → generate SLA PDF
   - End-to-end in 15 minutes

3. **Backup + rollback plan**
   - Snapshot DB before the demo
   - Have screenshot fallbacks if live demo fails

**Effort estimate:** 2 days

> 🏁 **Q2 Complete (Jun 27):** Platform ready for first customer pilot

---

## Risks & Mitigation

| Risk                                     | Impact                   | Mitigation                                                              |
| ---------------------------------------- | ------------------------ | ----------------------------------------------------------------------- |
| Breaking change in a new LiteLLM version | Blocks the entire flow   | Pin the version in the Docker image; test upgrades on a separate branch |
| gom delays the cost-saving API in W7     | Blocks Task 8.2          | Mock the endpoint early; agree on the contract by W6                    |
| gom delays NPU connection in W8          | Blocks Canary UI testing | Build with a mock NPU endpoint; swap in the real one when ready         |
| LLM Guard latency too high               | Hurts UX                 | Use async patterns; fail-open mode for non-critical guards              |
| LibreChat branding/customization is hard | Delays W2                | Fallback: minimal `APP_TITLE` + logo only; defer deep theming to W9     |
| Slow PDF generation at scale             | Delays reports           | Async jobs + email link; do not block the UI                            |
| Many bugs in hoon's validation reports   | W9 is too short          | 20% buffer per phase; fix bugs early                                    |

---

## Communication Plan

### Daily

- 15-minute standup (sun + gom + hoon)
- Slack channel `#npuops-dev` for async updates

### Weekly

- **Friday:** demo features delivered that week to the team
- **Friday:** 30-minute retro
- **Monday:** plan for the new week

### Sync with gom

- **End of W6:** lock the contract for the cost-saving API (Task 8.2 dependency)
- **End of W7:** lock the contract for NPU backend connection (Task 8.1 dependency)
- **W8 Monday:** pair work for integration

### Sync with hoon

- **After each task:** notify hoon for immediate validation
- **Every Thursday:** review the validation report

---

## Definition of Done (per task)

- [ ] Code merged to `main` via PR
- [ ] At least 1 unit test for the core logic
- [ ] At least 1 integration test for the main flow
- [ ] Documentation updated (README + API docs)
- [ ] hoon has validated, no critical bugs
- [ ] Deployable to staging
- [ ] Demoed to the team

---

## Total Effort Estimate

| Phase     | Weeks       | Effort (days) |
| --------- | ----------- | ------------- |
| Setup     | Pre-W1      | 2             |
| Phase 1   | W1–W2       | 9             |
| Phase 2   | W3–W4       | 10            |
| Phase 3   | W5–W7       | 16            |
| Phase 4   | W8–W9       | 9             |
| **Total** | **9 weeks** | **~46 days**  |

→ ~10% buffer for meetings, unblocks, and urgent fixes
