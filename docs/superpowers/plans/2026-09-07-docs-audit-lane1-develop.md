# Docs audit, lane 1 (Develop) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the twelve Develop pages, organised by archived repository, with eight pages organised by what a developer is doing, every command in them executed on this machine against the real stack.

**Architecture:** Content lives in `apps/docs/content/docs/developer/*.mdx` with order in `meta.json`; old URLs redirect from `apps/docs/next.config.mjs`. Ground truth comes from running things (`deploy/platform`, the three app dev servers) and from the two research reports in the scratchpad. Anything wrong in code rather than docs goes to `docs/audits/2026-09-07-docs-audit-findings.md`, not into a fix.

**Tech Stack:** Fumadocs (MDX, `meta.json`), Next 15 redirects, Playwright (`scripts/check-nav.mjs`), Docker Compose stack in `deploy/platform`, Bun (console, admin panel), npm (chat).

**Spec:** `docs/superpowers/specs/2026-09-07-docs-audit-design.md`

## Global Constraints

- Product names: NUFI app, NUFI Console, NUFI Admin Panel, NUFI Studio, NUFI Works, NUFI AI Gateway. Never "NuFi", never "NUFI Chat" as the product.
- Every command in a page was run on 2026-09-07 or is marked "not run here" with the reason.
- Repo paths are monorepo paths (`deploy/platform`, `apps/console`, …). No `git clone` of `npuops-platform`, `nufi-chat`, `nufi-console`, `LibreChat`.
- Package managers as they are: Bun for console, admin panel, docs; npm for chat; `pnpm --node-linker=isolated` for Works; `uv`/`make` for Studio.
- Every old Develop URL keeps resolving (redirects in `next.config.mjs`).
- No prose that reads as AI-authored, no "boss", no references to this audit inside the pages.
- Each task ends with `bun run build` passing in `apps/docs` and a commit.

---

### Task 1: New Develop index and section order

**Files:**
- Modify: `apps/docs/content/docs/developer/index.mdx`
- Modify: `apps/docs/content/docs/developer/meta.json`
- Create: placeholder-free stubs are NOT allowed; the index links only to pages that exist by the end of this task, so it is written last in this task after the meta order is set.

**Interfaces:**
- Produces: the page slugs the rest of the lane uses: `run-locally`, `work-on-chat`, `work-on-console`, `work-on-admin-panel`, `work-on-agents`, `models`, `release`, `rag-integration`.

- [ ] **Step 1: Set the order**

`apps/docs/content/docs/developer/meta.json`:

```json
{
  "title": "Develop",
  "icon": "Code",
  "pages": [
    "run-locally",
    "---Work on one app---",
    "work-on-chat",
    "work-on-console",
    "work-on-admin-panel",
    "work-on-agents",
    "---Ship---",
    "models",
    "release",
    "---Design notes---",
    "rag-integration"
  ]
}
```

- [ ] **Step 2: Write the index**

`index.mdx` frontmatter `title: Develop`, `description: Run NUFI on your machine, change one app, ship it.` Body, in this order:

1. One paragraph: everything is in `dudaji-vn/nufi-app`; one clone is the whole system. Table mapping directory → product → dev guide link: `deploy/platform` → the stack → Run the stack locally; `apps/chat` → NUFI app → Work on the chat app; `apps/console` → NUFI Console; `apps/admin-panel` → NUFI Admin Panel; `apps/nufi-agent` → NUFI Studio and `apps/agents` → NUFI Works → Work on Studio and Works; `apps/docs` → this site → its README.
2. "Three ways to have a NUFI to develop against": (a) the hosted staging (`chat.nufi.me`, `console.nufi.me`) for UI-only work; (b) the local stack from `deploy/platform` (recommended, ~10 GB); (c) one app's dev server against the local stack. Two sentences each.
3. Prerequisites table with exact versions from source: Docker Desktop with Compose v2 (`bootstrap.sh` checks `docker compose`), `yq` (Mike Farah's), `openssl`, `curl`, `git`, Bun 1.3 (`console-ci.yml`, `apps/console/README.md`), Node 20.19+ / 22.12+ (`apps/chat/CLAUDE.md:146`, Dockerfile `node:20-alpine`), pnpm for Works, `uv` + Python 3.12 for Studio, Ollama optional.
4. "Which package manager where" table (Bun / npm / pnpm / uv) with one line on why (each app keeps its own lockfile; root README: "no root package manager on purpose").

- [ ] **Step 3: Build**

Run from `apps/docs`: `bun run build`. Expected: build fails on the dangling links until Tasks 2–8 exist? No: Fumadocs does not validate internal links at build time. Expected: `✓ Generating static pages`. The dangling links are closed by the tasks below; `scripts/check-nav.mjs` runs in Task 9 after all pages exist.

- [ ] **Step 4: Commit**

```bash
git add apps/docs/content/docs/developer/index.mdx apps/docs/content/docs/developer/meta.json
git commit -m "docs(develop): index by what you are doing, not by which repo it used to be"
```

### Task 2: Run the stack locally

**Files:**
- Create: `apps/docs/content/docs/developer/run-locally.mdx`
- Delete: `quick-start.mdx`, `prerequisites.mdx`, `verify-install.mdx`, `local-stack.mdx`
- Modify: `apps/docs/next.config.mjs` (redirects)

**Verified on this machine (run log in scratchpad `lane1-runlog.md`):** stack up, 18 services, ports 3080/3001/3000/3030/4000/9090/9093; gateway needed `docker compose build litellm-proxy` after pulling (finding F1); `./scripts/smoke-test.sh` 8/8; `bootstrap.sh --help` flags.

- [ ] **Step 1: Write the page**

Frontmatter: `title: Run the stack locally`, `description: The whole platform on your laptop with one script, and what to do when it does not come up.`

Sections and their required content:

1. **What comes up** — table of the 18 services from `docker-compose.yml` with host port and purpose (postgres, redis, clickhouse, minio, langfuse-web :3000, langfuse-worker, litellm-proxy :4000, mongodb, librechat :3080 "the NUFI app", console :3001, prometheus :9090, grafana :3030, alertmanager :9093, presidio ×2, nufi-scanner, exporters). Note `mongo:4.4` and why (target VM lacks AVX, compose comment).
2. **Before you start** — Docker Desktop with ≥4 GB RAM; `docker login ghcr.io` with a PAT scoped `read:packages` (the `nufichat` and `nufi-console` images); `yq`; Ollama optional. **Apple Silicon**: the two GHCR images are amd64-only; create `deploy/platform/docker-compose.override.yml` (gitignored) with `platform: linux/amd64` for `librechat` and `console` — show the 6-line file (finding F3).
3. **Bring it up**:
   ```bash
   cd deploy/platform
   ./scripts/bootstrap.sh --backend ollama --model qwen2.5:3b   # local model
   ./scripts/bootstrap.sh --backend cloud                       # OpenAI/Anthropic/... key
   ./scripts/bootstrap.sh --backend skip                        # stack only
   ```
   What the script does, from `bootstrap.sh:359-760`: checks tools, fills every `replace-me` secret in `.env`, pulls the chat image, `docker compose up -d`, waits up to 5 min for the gateway to be healthy, registers the model with `add-model.sh`, runs the smoke test. What it prints (URLs; note it still prints Grafana on 3002 "not yet deployed", which is wrong: Grafana is on 3030, finding).
4. **After `git pull`** — the gateway and scanner are built locally from `litellm/` and `scanner/`; compose does not rebuild them on `up`. Exact commands:
   ```bash
   docker compose build litellm-proxy nufi-scanner
   docker compose up -d
   ```
   with the crash signature to recognise (`unknown threshold key(s)`), from F1.
5. **Check it works** — the five URLs table (chat 3080 register first user = ADMIN; console 3001; Langfuse 3000 with `admin@npuops.local` + password from `.env`; Grafana 3030 `GRAFANA_ADMIN_*`; gateway `/ui` 4000 master key) and `./scripts/smoke-test.sh` with the 8 lines it prints.
6. **Day to day** — `docker compose ps|logs -f <svc>|restart <svc>|down|down -v`, and what to edit where: `litellm/config.yaml` (rebuild + restart litellm), `librechat.yaml` (restart librechat), `litellm/guardrails/policy.yaml` (mounted, restart only), `monitoring/rules/*.yml` (`curl -X POST localhost:9090/-/reload`).
7. **Variables the stack reads that `.env.example` does not list** — `AGENTS_URL`, `NUFI_CONSOLE_TAG`, `DEFAULT_USER_BUDGET`, `DEFAULT_BUDGET_DURATION`, `DEFAULT_TPM_LIMIT`, `DEFAULT_RPM_LIMIT`, one line each with default.
8. **When it does not come up** — gateway crash loop (rebuild), `no matching manifest for linux/arm64/v8` (override), `LiteLLM refuses to start without GEMINI_API_KEY` (`.env.example:120-125`: set it or remove the two gemini entries), scanner takes up to 5 min on first start (700 MB model).

- [ ] **Step 2: Redirects**

Add to `redirects()` in `apps/docs/next.config.mjs`:

```js
{ source: '/docs/developer/quick-start', destination: '/docs/developer/run-locally', permanent: true },
{ source: '/docs/developer/prerequisites', destination: '/docs/developer', permanent: true },
{ source: '/docs/developer/verify-install', destination: '/docs/developer/run-locally', permanent: true },
{ source: '/docs/developer/local-stack', destination: '/docs/developer/run-locally', permanent: true },
```

- [ ] **Step 3: Delete the four old pages, build, commit**

```bash
git rm apps/docs/content/docs/developer/{quick-start,prerequisites,verify-install,local-stack}.mdx
(cd apps/docs && bun run build)
git add -A apps/docs
git commit -m "docs(develop): run the stack locally, as it actually runs"
```

### Task 3: Work on the chat app

**Files:**
- Create: `work-on-chat.mdx`
- Delete: `nufi-chat.mdx`, `librechat-fork.mdx`
- Redirects: both → `/docs/developer/work-on-chat`

**Verify first (this task's run):** in `apps/chat`, `npm ci`; start a throwaway Mongo (`docker run -d --name nufi-dev-mongo -p 27018:27017 mongo:4.4`); `.env` with `MONGO_URI=mongodb://127.0.0.1:27018/LibreChat`, `JWT_SECRET`, `JWT_REFRESH_SECRET`, `CREDS_KEY`, `CREDS_IV` (openssl), `ENDPOINTS=custom`; a `librechat.yaml` with the gateway endpoint (`baseURL: http://localhost:4000/v1`, `apiKey: <LITELLM_MASTER_KEY>`, `models.fetch: true`, `default: ["_no-model-registered"]`); `npm run backend:dev` then `npm run frontend:dev`; confirm the login page on 3090 and that the model list shows the gateway's models. Record what failed.

- [ ] **Step 1: Write the page** with: where the code is (`apps/chat`, `api/`, `client/`, `packages/*`), the rule from the root README (no upstream, hand-port only), Node version, `npm ci`, the `.env` keys above, the `librechat.yaml` excerpt, the two dev commands, ports (API 3080, Vite 3090), tests (`npm run test:api`, `test:client`, `lint`), and "which deployment config carries the gateway endpoint" (`deploy/platform/librechat.yaml`, `deploy/railway/librechat.yaml`).
- [ ] **Step 2: Redirects, delete old pages, build, commit** (`docs(develop): work on the chat app`).

### Task 4: Work on the console

**Files:** Create `work-on-console.mdx`; delete `console-dev.mdx`; redirect.

**Verified:** run log items 10; `bun run dev` = Vite 5173 + server 3000 (`SERVER_PORT` to move it); env names from source.

- [ ] **Step 1: Write the page** with the env table (every variable the server reads, grouped: gateway, chat identity, Langfuse, defaults, OIDC, chooser), the exact `bun --env-file=.env.local run server/index.ts` / `bun run dev` commands, the port collision with the stack's console on 3001 (dev server default 3000 collides with Langfuse: set `SERVER_PORT`), the identity handoff (`CHAT_BASE_URL`, browser UA), tests (`bun test`, `typecheck`, `lint`).
- [ ] **Step 2: Redirect `/docs/developer/console-dev` → `/docs/developer/work-on-console`; delete; build; commit.**

### Task 5: Work on the admin panel

**Files:** Create `work-on-admin-panel.mdx`; delete `admin-panel-dev.mdx`; redirect.

**Verified:** run log item 11.

- [ ] **Step 1: Write the page**: `bun install`, `.env` (`SESSION_SECRET` optional in dev, `VITE_API_BASE_URL=http://localhost:3080`), `bun run dev -- --port 3003` because 3000 is Langfuse, how it talks to the app (HTTP API, not the database: `src/server/utils/url.ts`), sign in with the ADMIN user created in the chat, tests/lint.
- [ ] **Step 2: Redirect, delete, build, commit.**

### Task 6: Work on NUFI Studio and NUFI Works

**Files:** Create `work-on-agents.mdx`; delete `agent-forks.mdx`; redirect.

**Verify:** Studio: `apps/nufi-agent/nufi/init.sh` then `.venv/bin/langflow run --host 127.0.0.1 --port 7860 --no-open-browser` (DEVELOPING.md:224); confirm 7860 answers. Works: `pnpm install --frozen-lockfile --node-linker=isolated` and `pnpm run dev:server` with `PAPERCLIP_ADAPTERS_FILE=nufi/adapters.json`, a Postgres (`docker run -d -p 5433:5432 postgres:16-alpine`), `DATABASE_URL`; confirm 3100 answers. If either cannot be completed in 30 minutes, the page says "run the container" for that product with the exact `docker build` from its `nufi/Dockerfile` header, and the run log says why.

- [ ] **Step 1: Write the page**: the two forks (upstream, tag, license, from each `nufi/upstream.json`), the allowlist rule and the CI jobs that enforce it (`nufi-agent-ci.yml`, `agents-ci.yml`), how to run each, the `LANGFLOW_AUTO_LOGIN=false` warning, `PAPERCLIP_ADAPTERS_FILE`, where the production env is documented (`deploy/railway/agents.md`).
- [ ] **Step 2: Redirect `/docs/developer/agent-forks` → `/docs/developer/work-on-agents`; delete; build; commit.**

### Task 7: Add or change a model

**Files:** Create `models.mdx` from `adding-models.mdx` (rename); redirect old slug.

**Verify:** `./scripts/add-model.sh --help`; register `qwen2.5:0.5b` from Ollama with the non-interactive flags from `bootstrap.sh:654-661`; confirm it appears in `/v1/models` and the chat dropdown; remove it again (edit `litellm/config.yaml` + `librechat.yaml`, restart).

- [ ] **Step 1: Rewrite** with the real flag forms (`add-model.sh:7-44`), what it edits (`litellm/config.yaml`, `librechat.yaml`), the rebuild rule (config.yaml is baked into the image: rebuild), and the admin-panel alternative for chat-side model presets.
- [ ] **Step 2: Redirect `/docs/developer/adding-models` → `/docs/developer/models`; build; commit.**

### Task 8: Release and deploy

**Files:** Create `release.mdx` from `release-flow.mdx`; redirect old slug.

**Verify against** `.github/workflows/*.yml` (table in the research report) and the Railway services (`nufi-chat`, `nufi-console` pinned to a tag, `nufi-studio`, `nufi-works`, `nufi-docs` track `main`).

- [ ] **Step 1: Rewrite**: one table: product → tag pattern → workflow → image → what Railway does with it. `nufi-v*` chat, `nufi-console-v*`, `nufi-admin-v*`, `nufi-studio-v*`, `nufi-works-v*`; docs deploy on merge to `main`. The `/nufi-release` skill note stays out (internal tooling).
- [ ] **Step 2: Redirect, build, commit.**

### Task 9: READMEs, findings, navigation check, PR

**Files:**
- Modify: `deploy/platform/README.md` (Quick start, Console, LibreChat customization sections), `deploy/platform/scripts/bootstrap.sh` header lines 22-23 and the Grafana line 774 (comment/print text only), `deploy/railway/README.md` (title, clone lines), `apps/console/README.md` (lines 8-10, 82-84, 132-133), `apps/admin-panel/README.md:3`, root `README.md` (add Studio and Works rows).
- Modify: `docs/audits/2026-09-07-docs-audit-findings.md` (F4+ from the stale-statements list and anything the runs turned up).

- [ ] **Step 1: README fixes** — only statements the research report marked stale, replaced with the monorepo truth; no restructuring.
- [ ] **Step 2: Findings** — add: `.env.example` missing six variables; `bootstrap.sh` prints Grafana :3002; `apps/admin-panel/docker-compose.yml` pulls the upstream ClickHouse image; admin panel README claims a shared database; `apps/console` has no `.env.example`; `apps/agents/nufi/README.md` names a workflow that does not exist; `docs-ci` has no push trigger; chat `package.json` still named LibreChat with upstream repository links.
- [ ] **Step 3: Full check**

```bash
cd apps/docs && rm -rf .next && bun run build
bun run start -- -p 3123 &   # then
bun run check:nav http://localhost:3123
# and every old Develop URL:
for p in prerequisites quick-start verify-install local-stack nufi-chat librechat-fork agent-forks admin-panel-dev console-dev adding-models release-flow; do
  curl -s -o /dev/null -w "$p %{http_code} %{redirect_url}\n" http://localhost:3123/docs/developer/$p; done
```
Expected: 9/9, and eleven 308s to existing pages.

- [ ] **Step 4: Screenshots** of `/docs/developer` and `/docs/developer/run-locally` for the PR.
- [ ] **Step 5: Commit, push, PR** titled `docs(develop): the developer lane, rewritten from running it`, body listing what was executed (run log) and what was read only; link the findings file.
