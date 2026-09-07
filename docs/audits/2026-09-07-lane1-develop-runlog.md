# Lane 1 (Develop) run log — 2026-09-07

Machine: macOS, 24 GB RAM, Docker Desktop 27.4.1 / Compose 2.39.2, Bun 1.3.1, Node 24.18, Ollama (qwen2.5:7b, qwen2.5:0.5b, nomic-embed-text).
Worktree: .claude/worktrees/docs-audit on branch docs/audit-develop (from origin/main 4db7ed1d8).
Prior state: deploy/platform/.env dated 2026-07-28; compose project `npuops` auto-started with Docker Desktop (restart policy); 46 volumes; local images nufi/litellm:local + nufi/scanner:local built 2026-07-30.

## Executed

| # | Command / action | Result |
|---|---|---|
| 1 | `open -a Docker`; wait for daemon | ready in ~1 min; the npuops stack came up by itself |
| 2 | `docker compose -p npuops ps` | 18 containers up; chat 3080, console 3001, langfuse 3000, grafana 3030, litellm 4000, prometheus 9090, alertmanager 9093 |
| 3 | curl 3080 / 3001 / 3000 / 9090 | 200 200 200 200; grafana 3030 → 302 (login) |
| 4 | curl 4000/ui, 4000/health/liveliness | 000 — gateway not answering |
| 5 | `docker logs npuops-litellm` | crash loop, 8 restarts: `G1: unknown threshold key(s) ['tool']` → **Finding F1** (stale local image, nothing rebuilds it) |
| 6 | `docker compose build litellm-proxy && up -d litellm-proxy` (from worktree deploy/platform, .env copied) | built in ~3 min; container healthy; 4000/health/liveliness 200, /ui 307 (login), /v1/models 401 without key |
| 7 | `./scripts/smoke-test.sh` | 8/8 pass (liveness, model list → gemini, completion, streaming, 4xx on unknown model, Langfuse trace, Prometheus counter, G1 decision) |
| 8 | `./scripts/bootstrap.sh --help` | flags: --backend ollama/remote/cloud/mock-npu/skip, --model, --domain, --skip-pull, --skip-smoke-test. Header still says chat image is `ghcr.io/dudaji-vn/librechat` (private); compose pulls `ghcr.io/dudaji-vn/nufichat:main` → finding (misleads) |
| 9 | `git ls-files deploy/platform/litellm/nufi-security` | 425 tracked files, vendored, no submodule → fresh clone builds the gateway image |
| 10 | console: `bun install --frozen-lockfile` (251 pkgs, <1s) then `bun --env-file=<env> run server/index.ts` with LITELLM_BASE_URL=http://localhost:4000, LITELLM_MASTER_KEY, JWT_SECRET, JWT_REFRESH_SECRET, LANGFUSE_HOST=http://localhost:3000, LANGFUSE_PUBLIC/SECRET_KEY, CHAT_BASE_URL=http://localhost:3080, PORT=3002 | listening on :3002, `/_health` 200. No `.env.example` exists to tell a dev these names → finding. Compose passes `LIBRECHAT_URL`, code reads `CHAT_BASE_URL` (defaults to prod) → **F2** |
| 11 | admin panel: `bun install --frozen-lockfile` (780 pkgs, 3s) then `VITE_API_BASE_URL=http://localhost:3080 bunx vite dev --port 3003` (script's default port 3000 collides with Langfuse) | Vite ready in 2.3s; `/` 200, `/login` 307 |
| 12 | `docker manifest inspect ghcr.io/dudaji-vn/nufichat:main` | amd64 only → **F3**; the local gitignored override pins `platform: linux/amd64` for librechat + console |
| 13 | `grep -c replace-me deploy/platform/.env` | 19 placeholders incl. LITELLM_MASTER_KEY=sk-replace-me; stack runs and smoke test passes on them → **F4** |
| 14 | `/v1/models` on the gateway | gemini, nufi-agent, claude-sonnet-4-5, claude-haiku-4-5, gpt-5, gpt-5-mini (config.yaml) + gemini-2.5-flash/pro/-title (added via UI, store_model_in_db) |
| 15 | `add-model.sh` apply step (`:602-607`) | `docker compose up -d --force-recreate litellm-proxy` only; config.yaml is baked into the image (compose:250) → a model added after the image was built never reaches the running gateway unless you `docker compose build litellm-proxy` first → finding |
| 16 | chat: `npm ci` (ok) then `npm run backend:dev` | crashed: `Cannot find module @librechat/data-schemas/dist/index.cjs`. Workspace packages must be built first: `npm run build:packages` (~2 min), then backend:dev. Neither CLAUDE.md's table nor the old page says so (CLAUDE.md's `smart-reinstall` implies it) |
| 17 | console: `.env.local` + plain `bun run dev` | API on 3002 OK, but Vite proxied `/_health` to Langfuse (3000): Bun's automatic .env.local does not reach the Node child. `bun --env-file=.env.local run dev` → 5173/_health = {"ok":true}. Documented that form |
| 18 | admin panel: `bun run dev -- --port 3003` while the console dev server was up | exit 1, `EADDRINUSE :::42069` = @tanstack/devtools event bus; both apps use it. Re-tested alone below |
| 19 | works: `pnpm install --frozen-lockfile --node-linker=isolated` (ok, ~1 min) then `pnpm run dev:server` with DATABASE_URL (throwaway postgres:16 on 5433), PORT=3100, PAPERCLIP_ADAPTERS_FILE | exit 1: `@paperclipai/plugin-sdk/dist/index.js` missing → `pnpm run build` first |
| 20 | works: `pnpm run build` (ok, ~3 min) → `pnpm db:migrate` (182 migrations) → `pnpm run dev:server` with the same env | listening on 127.0.0.1:3100; `/api/health` status ok, version 0.3.1, adapters enabled incl. `nufi_agent`; `/` 200 |
| 21 | admin panel alone: `bun run dev -- --port 3003` | vite on 3003, `/` 200 (the earlier EADDRINUSE 42069 was the console's devtools) |
| 22 | chat: `npm run build:packages` (~2 min) then backend:dev | crashed again: `ENOENT client/dist/index.html` — the API serves the built client and refuses to start without it → `npm run build:client` (~4 min) |
| 23 | chat: backend:dev after both builds; `BACKEND_PORT=3081 npm run frontend:dev` | API `/health` OK on 3081; Vite 3090 `/` 200, `/api/config` via proxy 200; register + login via API 200; `/api/models` lists the gateway's 9 models under "NUFI" |
| 24 | add-model.sh experiment (`--name qwen-audit-test ... --no-test`) | script: "is now registered"; `/v1/models` unchanged → **F5**. Reverted config.yaml + librechat.yaml in the worktree, restarted librechat |
| 25 | studio: `nufi/init.sh` (ok, fast with warm caches) then `.venv/bin/langflow run --port 7860` | exit 1: `Static files directory .../langflow/frontend does not exist` — needs `make build_frontend` first. Port 7860 was already held by the user's own Studio (python -m langflow run), which is what answered health/version; `make backend`/`make frontend` would `kill -9` whatever holds 7860/3000 (DEVELOPING.md), so neither was run |
| 26 | studio: `.venv/bin/langflow run --backend-only --host 127.0.0.1 --port 7861 --no-open-browser` | `/health` ok, `/api/v1/version` 1.11.2 |
| 27 | studio UI: `cd src/frontend && VITE_PORT=3005 VITE_PROXY_TARGET=http://127.0.0.1:7861 npm start` | Vite ready; binds `[::1]:3005` so use http://localhost:3005 (127.0.0.1 refuses); `/api/v1/version` through the proxy answers |
| 28 | README fixes via scratchpad/fix-readmes.py | deploy/platform/README.md (8 + the LibreChat customization section), bootstrap.sh (3 comment/print strings), deploy/railway/README.md (2), apps/console/README.md (3), apps/admin-panel/README.md (1), root README (Studio + Works rows) |

## Cleanup owed at the end

- `docker rm -f nufi-dev-mongo nufi-dev-pg`
- `litellm-proxy` and `librechat` containers were recreated from the worktree's compose file (bind mounts point into `.claude/worktrees/docs-audit/deploy/platform`). Recreate them from the main checkout before the worktree goes: `cd deploy/platform && docker compose up -d --force-recreate litellm-proxy librechat` (main checkout, its own .env and override).
- The rebuilt `nufi/litellm:local` image stays; it is what the user needs anyway (F1).
- Throwaway users `audit-<ts>@example.com` exist only in the throwaway Mongo.

## Not executed / limitations

- Did not run a from-scratch bootstrap (`down -v`) because the existing volumes hold the user's local data. Fresh-install steps (secret generation, image pulls) verified by reading bootstrap.sh and by re-running it non-destructively.
