# W3 — Admin App (API Key Self-Service + Budget / Rate-Limit Management)

**Period:** 2026-05-12 → 2026-05-16 (W3, 5 days)
**Branch:** `feature/w3-admin-app`
**Covers:** Roadmap Task 3.1 (API Key Issuance UI) + Task 3.2 (Budget & Rate Limit Management)

## Goal

End users can self-issue LiteLLM API keys with budgets and per-key rate limits — no admin intervention, no second login. Generated keys are usable directly against LiteLLM (`http://localhost:4000/v1/*`).

## Why standalone, not a LibreChat fork

Every feature this app delivers — key generation, budget enforcement, rpm/tpm limits, per-key spend — is already a native LiteLLM capability exposed via its admin API. A LibreChat fork would only change *where the UI lives*, not *what it does*, at the cost of a permanent rebase tax against LibreChat's release cadence. Standalone is faster to build, isolated from upstream churn, and matches LibreChat's own direction (their 0.8.5+ Admin Panel ships as a separate service).

## Architecture

### One container, one origin (single-domain, like LibreChat does it)

```
┌───────────────────────────────────────────────────┐
│  admin-app  (single Docker container, port 3000)  │
│                                                   │
│  Hono server:                                     │
│   ├─ /api/* ─────► BFF handlers (TypeScript)      │
│   └─ everything else ► serve dist/index.html      │
│                                                   │
│  Build-time: Vite builds React SPA into ./dist    │
└───────────────────────────────────────────────────┘
                         │
                         ▼ master-key auth (server-side only)
              LiteLLM admin API (/user/*, /key/*, /spend/*)
```

The browser sees one origin. Frontend and BFF are indistinguishable from outside. This mirrors how LibreChat's Express server serves both the React build and `/api/*` on a single port.

### Identity flow (SSO via shared JWT)

1. User logs into LibreChat → JWT cookie set with `domain=.npuops.local` (parent domain)
2. User opens admin app → browser sends the same JWT cookie
3. Hono `auth` middleware verifies the JWT with the shared `JWT_SECRET`
4. Extracts `userId`, `email`, `role` from the token
5. **JIT provisioning:** if this is the user's first admin-app open, BFF calls `POST /user/new` on LiteLLM with the LibreChat `_id`, email, role, default budget — then continues
6. Every downstream LiteLLM call is filtered by `user_id` for non-admins (one middleware does it)

### Stack

- **Vite + React 19** — fast HMR, no SSR overhead
- **TanStack Router** — type-safe routes + search params (matters for filter-heavy admin pages)
- **Hono** — server runtime; serves the oRPC handler + static SPA fallback in the same process
- **oRPC** — end-to-end type-safe RPC; defines procedures once on the server, auto-generates typed TanStack Query hooks for the client. Single source of truth per endpoint.
- **Tailwind + shadcn/ui** — UI primitives
- **`hono/jwt`** — HS256 verification with shared `JWT_SECRET`
- **TanStack Query** — server-state cache; consumed via oRPC's generated hooks
- **Zustand** — client-state (modal open/close, toasts, transient UI flags)
- **Zod** — input/output schemas attached to oRPC procedures; shared automatically between client and server

### Data ownership (no duplication)

| Service             | Owns                                                   |
| ------------------- | ------------------------------------------------------ |
| LibreChat (Mongo)   | User accounts, JWT, conversations                      |
| LiteLLM (Postgres)  | Virtual keys, key→user mapping, budgets, rpm/tpm, spend |
| Redis               | Rate-limit counters (TTL-based)                        |
| Langfuse            | Per-request traces, model costs, latency               |
| **Admin app**       | **Nothing — stateless**                                |

## Repo layout

```
admin-app/
├── Dockerfile                  multi-stage; Vite build → Node runtime
├── package.json
├── vite.config.ts
├── tsconfig.json
├── tailwind.config.ts
├── index.html
├── src/                        React SPA
│   ├── main.tsx
│   ├── routes/
│   │   ├── __root.tsx
│   │   ├── index.tsx            redirect → /keys
│   │   ├── keys.tsx             3.1 — list / create / revoke keys
│   │   ├── usage.tsx            placeholder for W4
│   │   └── unauthorized.tsx
│   ├── components/
│   │   ├── KeyTable.tsx
│   │   ├── KeyGenerateModal.tsx
│   │   ├── KeyRevealOnceModal.tsx
│   │   └── ui/                  shadcn primitives
│   ├── lib/
│   │   ├── api.ts               TanStack Query hooks → /api/*
│   │   └── format.ts            key masking, currency, dates
│   └── stores/
│       └── ui.ts                Zustand store: modals, toasts, transient flags
└── server/                     Hono + oRPC BFF
    ├── index.ts                 Hono app; mounts oRPC handler + SPA fallback
    ├── orpc.ts                  oRPC instance, base middleware (auth, role)
    ├── router/
    │   ├── index.ts             root router (composes resource routers)
    │   ├── me.ts                procedure: me.get
    │   ├── keys.ts              procedures: keys.list / create / delete / info
    │   └── usage.ts             procedure: usage.get (W4 stub)
    └── lib/
        ├── litellm.ts           thin client around LiteLLM admin API
        └── jit-provision.ts     POST /user/new on first encounter
```

The oRPC router type is exported from `server/router/index.ts` and imported by the React side as `type AppRouter`. All client hooks (`api.keys.list.useQuery()`, `api.keys.create.useMutation()`, …) are inferred from this single type — no hand-written client types.

## BFF surface (W3 scope)

Defined as oRPC procedures in `server/router/`; mounted by Hono at `/api/*`.

| Procedure          | Calls on LiteLLM                | Notes                                      |
| ------------------ | ------------------------------- | ------------------------------------------ |
| `me.get`           | `/user/info` (+JIT `/user/new`) | Auto-provisions on first call              |
| `keys.list`        | `/key/list`                     | Filtered by `user_id` for non-admins       |
| `keys.create`      | `/key/generate`                 | Body: alias, budget, duration, tpm/rpm     |
| `keys.delete`      | `/key/delete`                   | Idempotent; returns 200 even if not found  |
| `keys.info`        | `/key/info?keys=…`              | Remaining budget, last used                |
| `usage.get`        | (W4 — placeholder)              | Stub returns `{ comingInWeek: 4 }`         |
| `_health` (Hono)   | —                                | Liveness; bypasses oRPC                    |

Six procedures plus an auth middleware on the oRPC base. The matching client hooks (`api.me.get.useQuery`, `api.keys.create.useMutation`, …) are inferred from the exported router type.

## UI — pages delivered in W3

### `/keys` — API Key List

- Table columns: alias, masked key (`sk-...abc4`), budget remaining (% bar), expires, created, actions
- Header button: "Generate Key" → opens the modal below
- Per-row "Revoke" with confirm dialog
- Empty state with CTA when the user has no keys yet

### Generate Key modal

Form fields (all with sensible defaults from `.env`):

- Key alias (string, required)
- Team / project (dropdown — MVP hardcodes `default-team`)
- Max budget (USD)
- Budget period — `24h` / `7d` / `30d`
- TPM limit (tokens per minute)
- RPM limit (requests per minute)
- Expires — `30d` / `90d` / `never`

After generation: a **reveal-once modal** shows the full `sk-...` value with a Copy-to-Clipboard button + warning that it won't be shown again. Click "Done" → key joins the table (masked).

### `/usage` — placeholder for W4

Card stating "Usage analytics arriving in W4." Wires the route now so the app shape is stable when W4 lands.

## Defaults (`admin-app/.env`)

```
DEFAULT_USER_BUDGET=10           # USD per period
DEFAULT_BUDGET_DURATION=30d
DEFAULT_TPM_LIMIT=10000
DEFAULT_RPM_LIMIT=60
KEY_DEFAULT_DURATION=90d
LITELLM_BASE_URL=http://litellm-proxy:4000
LITELLM_MASTER_KEY=…             # never sent to browser
JWT_SECRET=…                     # SAME value as LibreChat's
PORT=3000
```

Changing a default = redeploy. No UI for editing defaults in W3.

## Docker integration

- Add `admin-app` service to `docker-compose.yml`
- Network: shared `npuops`
- Image: built from `admin-app/Dockerfile` (no public registry yet)
- Port: `3001:3000` (browser hits `http://localhost:3001`)
- Depends on: `litellm-proxy` (healthy)
- Mounts: none — fully image-baked, stateless
- Env: pass-through from root `.env`

## Implementation checklist

### Day 1 (Mon 2026-05-12) — scaffolding

- [ ] `admin-app/` skeleton: Vite + React 19 + TS template
- [ ] Add Tailwind + shadcn/ui
- [ ] Add TanStack Router (file-based routes)
- [ ] Hono server stub with `_health` route
- [ ] Add oRPC + Zod; create empty router with one ping procedure
- [ ] Wire build pipeline: Vite → `dist/`, Hono serves `dist/` as fallback
- [ ] Wire client: oRPC client + TanStack Query provider, importing `AppRouter` type
- [ ] Multi-stage `Dockerfile`
- [ ] `docker-compose.yml` integration
- [ ] Bring stack up; hit `http://localhost:3001/_health` → 200, `api.ping.useQuery` → "pong"

### Day 2 (Tue 2026-05-13) — auth & JIT provisioning

- [ ] `auth` middleware (Hono) — verify JWT with shared secret, attach `c.var.user`
- [ ] `LiteLLMClient` wrapper using master key
- [ ] `GET /api/me` route + first-call JIT-provisioning to LiteLLM `/user/new`
- [ ] React: `useMe()` hook, redirect to `/unauthorized` on 401
- [ ] Verify end-to-end: log into LibreChat → open admin app → see profile data

### Day 3 (Wed 2026-05-14) — key CRUD

- [ ] `keys.list` procedure (filtered by `user_id` via role middleware)
- [ ] `keys.create` procedure with Zod input (budget + limit fields)
- [ ] `keys.delete` procedure
- [ ] `keys.info` procedure
- [ ] Export `AppRouter` type from `server/router/index.ts`
- [ ] React: KeyTable, KeyGenerateModal, KeyRevealOnceModal — wired via auto-generated `api.keys.*` hooks

### Day 4 (Thu 2026-05-15) — role filtering + polish

- [ ] `role` middleware: ADMIN bypass; USER filtered by their `user_id`
- [ ] Empty / loading / error states
- [ ] Copy-to-clipboard for full key
- [ ] Key masking utility (`sk-...{last4}`)
- [ ] Update root `README.md`: how to access admin app, default URL

### Day 5 (Fri 2026-05-16) — verification + demo

- [ ] End-to-end script: generate → use vs LiteLLM → exceed `rpm_limit` → revoke
- [ ] Add e2e to `scripts/` for regression
- [ ] Internal demo

## Acceptance criteria

- [ ] Logged in via LibreChat → open admin app → already authenticated (no second login)
- [ ] Generate a key → reveal-once modal shows full `sk-…` → copy to clipboard
- [ ] Use the key against `POST /v1/chat/completions` on LiteLLM → 200
- [ ] Spam past `rpm_limit` → 429 with the LiteLLM error message
- [ ] Burn `max_budget` → 403
- [ ] Revoke key from the UI → next request returns 401 within seconds
- [ ] Key list shows all of the user's keys, never anyone else's
- [ ] Admin role can list and revoke any user's key
- [ ] `docker compose up -d` brings up admin-app cleanly with no manual steps

## Out of scope (W3)

- Usage charts / monthly dashboard → **W4**
- Team management UI → W4 if needed; MVP hardcodes `default-team`
- LibreChat in-app link injection → revisit in W4 if click-out friction is a real complaint; users bookmark `http://localhost:3001` for now
- LibreChat fork → architecturally rejected
- Custom auth / login UI → uses LibreChat's JWT
- Audit log → LiteLLM and Langfuse already log every key action and request
- Cost-calculation logic → LiteLLM uses `model_info.input_cost_per_token` already populated in `litellm/config.yaml`

## Pre-W3 verifications (resolved 2026-05-05)

### 1. LibreChat 0.7.5 passes `user` field to LiteLLM — ✅ confirmed

- Static: `OpenAIClient.js:607` — `this.modelOptions.user = this.user` set before every chat completion
- Live: existing Langfuse traces show `userId: 69f86488d98fee9e8b8d0452` (a 24-char hex matching LibreChat's MongoDB `_id` shape)
- Implication: W4 per-user dashboard will work without modifying LibreChat or issuing per-user LiteLLM keys for chat

### 2. Admin link injection into LibreChat — partial

- The `interface` schema in v0.7.5 is strict: only `privacyPolicy`, `termsOfService`, and visibility toggles. **No `customWelcome`, `customLinks`, or `customFooter` exists.**
- W3 MVP path: separate URL bookmark, link from root `README.md`. Revisit a tiny ~20-LOC LibreChat fork (one header button) only if click-out friction proves to be a real complaint.

## Risks

| Risk | Impact | Mitigation |
| --- | --- | --- |
| LiteLLM admin API shape changes between versions | All BFF routes break | Pin LiteLLM image version; smoke-test on every upgrade |
| JWT cookie not sent cross-port in dev | Auth fails locally | Cookie domain = parent (`.localhost` won't work — use a `localtest.me` style trick or run both behind a single-port reverse proxy in dev) |
| LiteLLM `/user/new` with existing email collides | JIT provisioning errors out | Use LibreChat `_id` as `user_id` (guaranteed unique); treat 409 as idempotent |
| TanStack Router file-based routing learning curve | Day-1 scaffold slips | Fallback to code-based routing if file-based is fighting us |
