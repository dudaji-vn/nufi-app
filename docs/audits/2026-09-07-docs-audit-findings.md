# Docs audit, 2026-09-07: what was wrong in the code, not the docs

Companion to `docs/superpowers/specs/2026-09-07-docs-audit-design.md`. Each
entry is something a documented path ran into that a doc rewrite cannot fix.
Nothing here has been changed; each item is a proposal.

Severity: **blocks** a documented path · **misleads** a reader or operator ·
**cosmetic**.

## Lane 1: Develop

### F1. The gateway image goes stale silently, and nothing rebuilds it — blocks

**Seen:** on a machine that had run the stack in July, `docker compose up -d`
after pulling `main` brought up every service except the gateway.
`npuops-litellm` restarted 8 times with

```
ValueError: G1: unknown threshold key(s) ['tool'], expected ['assistant', 'system', 'untrusted', 'user']
ERROR:    Application startup failed. Exiting.
```

**Why:** `litellm-proxy` is a derived image (`deploy/platform/docker-compose.yml:193`,
`build: ./litellm`, `image: nufi/litellm:local`) with the guardrail package
baked in, while the policy it loads comes from the checkout. The local image
was built 2026-07-30; `litellm/guardrails/policy.yaml` gained the `tool` span
source on 2026-09-04 (`a3ee40e85`). Compose does not rebuild a `build:` service
on `up -d`, `scripts/bootstrap.sh` never runs `docker compose build`, and
`README.md` never says to. Every developer who pulls a guardrail change gets a
gateway that will not start, with an error that names a policy key rather than
the cause.

**Proposed fix:** make the build part of the documented path and the script:
`bootstrap.sh` runs `docker compose build litellm-proxy nufi-scanner` (or
`up -d --build`) before `up`, and the "Run the stack locally" page says the
same for `git pull`. Longer term, publish `nufi/litellm` to GHCR from CI like
the other images so the checkout and the image cannot drift.

### F2. The local console talks to production chat for identity — misleads

**Seen:** `deploy/platform/docker-compose.yml:415` hands the console
`LIBRECHAT_URL`. Nothing in `apps/console/server` reads that name. The
identity resolver reads `CHAT_BASE_URL`
(`apps/console/server/lib/chat-identity.ts:19`) and, when it is unset, falls
back to `https://chat.nufi.me`.

**Effect:** on the local stack every console feature that needs the member's
email and role (the handoff into NUFI Studio and NUFI Works) asks production
chat about a locally issued cookie. It cannot succeed, and the failure surfaces
inside Studio or Works as a missing email rather than in the console. A
developer working on the handoff locally cannot reproduce production.

**Proposed fix:** pass `CHAT_BASE_URL: http://librechat:3080` (the in-network
address) in the compose service, drop the unread `LIBRECHAT_URL` line, and make
the resolver refuse to start without an explicit value instead of defaulting to
a production host.

### F3. The published chat and console images are amd64-only — blocks (Apple Silicon)

**Seen:** `ghcr.io/dudaji-vn/nufichat:main` and `nufi-console:main` publish a
single `linux/amd64` manifest. On an arm64 Mac `docker compose up` fails with
`no matching manifest for linux/arm64/v8`, and because the pull is one
transaction it takes the already-running services down with it. The developer
who hit this keeps a gitignored `docker-compose.override.yml` pinning
`platform: linux/amd64` for both services, which nothing in the repo or the
docs mentions.

**Proposed fix:** build the two images for `linux/amd64,linux/arm64` in
`chat-release.yml` and `console-image.yml` (`docker/build-push-action` with
`platforms:`). Until then, the "Run the stack locally" page tells Apple Silicon
developers to add the override, and ships it as
`docker-compose.override.example.yml`.

### F4. The stack runs happily on placeholder secrets — misleads (locally), blocks (anywhere else)

**Seen:** the `.env` of a stack that has been in daily use since July still
holds 19 `replace-me` values, among them `LITELLM_MASTER_KEY=sk-replace-me`,
`POSTGRES_PASSWORD=replace-me`, `JWT_SECRET=replace-me`,
`GRAFANA_ADMIN_PASSWORD=replace-me`. Every service started, the smoke test
passed 8/8, and `/v1/models` answered to the placeholder master key.

**Why:** `README.md` documents a "Manual quick start" (`cp .env.example .env`,
edit, `docker compose up -d`) beside the scripted one, and nothing between the
copy and the `up` checks that a secret was actually set. `bootstrap.sh` fills
placeholders (`:517-575`), but only if it is the path the developer took.

**Also:** once volumes exist, filling the placeholders later is not safe
either. Postgres and MongoDB take their password from the environment only
on first initialisation, so a later `bootstrap.sh` run that rewrites
`POSTGRES_PASSWORD` and `MONGO_INITDB_ROOT_PASSWORD` leaves the databases on
the old value and the gateway, Langfuse and the app unable to connect.

**Proposed fix:** `docker-compose.yml` fails fast on a placeholder
(`${LITELLM_MASTER_KEY:?set in .env}` is not enough, since the value is set;
a one-line `scripts/check-env.sh` run by `bootstrap.sh` and documented for the
manual path does it). Drop the manual quick start from the README, or make it
`bootstrap.sh --backend skip`. Document that changing a database password
after first start means `docker compose down -v`.

### F5. `add-model.sh` says "registered" and the gateway never sees the model — blocks

**Seen:** `./scripts/add-model.sh --name qwen-audit-test --model
'openai/qwen2.5:0.5b' --base-url-env GPU_BACKEND_BASE_URL --api-key-env
GPU_BACKEND_API_KEY --backend-type gpu --hardware-id mac-local --no-test`
finished with "'qwen-audit-test' is now registered" and a pointer to the
dropdown. `/v1/models` on the gateway afterwards: the same nine models as
before. The entry is in `litellm/config.yaml`; the gateway is running the
config that was baked into `nufi/litellm:local` when it was last built.

**Why:** `config.yaml` is copied into the image (`litellm/Dockerfile:94`) and
not mounted (`docker-compose.yml:250-253`). The script's apply step is
`docker compose up -d --force-recreate litellm-proxy` (`add-model.sh:607`),
which recreates the container from the existing image. `bootstrap.sh` calls
the same script, so the model it registers on first run is served only
because the image happens to be built after the file was written; on every
later run the script's success message is false.

**Proposed fix:** either mount `config.yaml` the way `policy.yaml` is mounted
(then a recreate is enough), or have the script run
`docker compose build litellm-proxy` before the recreate. The models page now
tells the reader to rebuild by hand.

### F6. The chat app does not start from a fresh checkout without two builds nobody names — misleads

**Seen:** `npm ci && npm run backend:dev` in `apps/chat` crashes twice in a
row: first `Cannot find module @librechat/data-schemas/dist/index.cjs`, then,
after `npm run build:packages`, `ENOENT ... client/dist/index.html`. The API
imports the built workspace packages and serves the built client for every
non-API route, and refuses to start when either is missing.
`apps/chat/CLAUDE.md`'s command table lists `backend:dev` and `frontend:dev`
as the development commands and never says a build must come first; only
`smart-reinstall`'s one-line description ("install + build") implies it.

**Proposed fix:** a `predev` step, or a `dev` script that runs
`build:packages` when `packages/*/dist` is missing, and a line in
`apps/chat/CLAUDE.md`. The docs page now lists the two builds.

### F7. `apps/console` has no `.env.example`, and reads 29 variables — misleads

Every other app ships one. A developer starting the console from source
finds the variable names only by grepping `server/` (or on the docs page,
which now lists them). `deploy/platform/docker-compose.yml:406-419` is the
closest thing to a template and, per F2, passes one variable the code does
not read.

**Proposed fix:** commit `apps/console/.env.example` with the table from the
docs page, defaults included, secrets blank.

### F8. Two TanStack apps, one devtools port — cosmetic

The console and the admin panel both ship `@tanstack/devtools`, whose event
bus listens on 42069. Starting the second app's dev server while the first
runs exits with `EADDRINUSE :::42069`, a port that appears nowhere in either
app's configuration. Documented on the admin panel page; a fix is setting the
devtools port per app in each `vite.config`.

### F9. Smaller stale statements found in the repository, not the docs — misleads

| Where | Says | Is |
|---|---|---|
| `deploy/platform/scripts/bootstrap.sh:774` | prints `Grafana http://localhost:3002 (not yet deployed)` | Grafana is deployed on 3030 (`docker-compose.yml:475`) |
| `deploy/platform/scripts/bootstrap.sh:22-23`, `:604-607`; `README.md:27-28` | the chat image is `ghcr.io/dudaji-vn/librechat` (private) | it is `ghcr.io/dudaji-vn/nufichat:main` (`docker-compose.yml:348`) |
| `deploy/platform/.env.example` | (absent) | compose reads `AGENTS_URL`, `NUFI_CONSOLE_TAG`, `DEFAULT_USER_BUDGET`, `DEFAULT_BUDGET_DURATION`, `DEFAULT_TPM_LIMIT`, `DEFAULT_RPM_LIMIT` |
| `apps/admin-panel/README.md:3`, `CLAUDE.md:5-6` | "connects to the same database as the main application" | it calls the app's HTTP API; no Mongo client in `src/` |
| `apps/admin-panel/docker-compose.yml:3` | `image: ghcr.io/clickhouse/librechat-admin-panel:latest` | CI publishes `ghcr.io/dudaji-vn/nufichat-admin-panel` |
| `apps/admin-panel/README.md:31` | `docker compose up -d` "builds and starts" | the compose file has no `build:` |
| `apps/agents/nufi/README.md:8` | the guard is `.github/workflows/agents-fork-guard.yml` | it is the `fork-guard` job in `agents-ci.yml` |
| `apps/chat/package.json:2-3`, `api/package.json`, `client/package.json` | name `LibreChat`, repository and homepage `danny-avila/LibreChat` | the app has no upstream relationship (root `README.md:20`) |
| `apps/chat/README.md`, `apps/chat/CLAUDE.md:16` | upstream's marketing README; a maintainer's local path `/home/danny/agentus` | |
| `.github/workflows/docs-ci.yml` | runs on `pull_request` only | a docs change pushed straight to `main` is never built or checked before Railway deploys it |
| `deploy/railway/bootstrap.sh:159-164` | auto-detects the gateway key from `~/npuops-platform/.env` or `../npuops-platform/.env` | both are archived checkouts; the stack is `deploy/platform` |

The README lines among these are corrected in this lane; the script, package
and workflow items are left for a decision.
