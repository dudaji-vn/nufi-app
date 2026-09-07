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

## Lane 2: Deploy & operate

### F10. The end-to-end smoke test calls an endpoint the app no longer has — blocks

**Seen:** `./scripts/e2e-smoke-test.sh --rebuild` on the running stack
passes liveness and registration, then stops:

```
==> 3/7 Chat via /api/ask/custom (endpoint='NPUOps')
error: /api/ask returned HTTP 404: {"message":"Endpoint not found"}
```

**Why:** the test was written against the LibreChat 0.7 API; the NUFI app is
at 0.8.6, where the chat route moved. The unit smoke test (`smoke-test.sh`,
gateway only) still passes, so the failure is specific to the chat leg, which
is the leg the test exists to cover. Every page that points at the e2e test
as the way to prove a deployment works is pointing at a test that cannot
pass.

**Proposed fix:** update `scripts/e2e/` to the current chat API (the agents
route), keep the Langfuse `hardware_id` assertion, and run it in
`platform-ci` against a real stack or delete it from the documented path.

### F11. The compose stack cannot share the session cookie across subdomains — misleads

**Seen:** the app honours `COOKIE_DOMAIN` and `COOKIE_SAMESITE`
(`apps/chat/api/server/utils/sessionCookies.js`), and the wrapper stack
passes them (`deploy/railway/docker-compose.yml:33-35`). The platform
stack's `librechat` service passes neither, so the documented
`COOKIE_DOMAIN=.example.com` in `.env` has no effect there; the console on
a sibling subdomain stays at `/unauthorized`.

**Proposed fix:** add `COOKIE_DOMAIN: ${COOKIE_DOMAIN:-}` and
`COOKIE_SAMESITE: ${COOKIE_SAMESITE:-strict}` to the `librechat` service in
`deploy/platform/docker-compose.yml`, and the two names to `.env.example`.

### F12. The documented MongoDB backup cannot run — blocks

**Seen:** `docker compose exec -T mongodb mongodump --archive --gzip`, as
the backup page had it, stops with `(Unauthorized) command listDatabases
requires authentication`; the stack's MongoDB is created with a root user.
The page now shows the authenticated form. Nothing in `scripts/` schedules
or performs a backup; an operator following the old page had none.

**Proposed fix:** a `scripts/backup.sh` that runs the two authenticated
dumps and the two volume snapshots, so the documented path is a script
that CI can at least lint.

### F13. The "Agents" entry in the app can never appear on either compose stack — misleads

**Seen:** both `librechat.yaml` files add an **Agents** entry from
`${AGENTS_URL}` (`deploy/platform/librechat.yaml:37`,
`deploy/railway/librechat.yaml:31`) and say an empty value hides it. Neither
compose file passes `AGENTS_URL` to the app: the platform stack hands the
`librechat` service an explicit environment list without it
(`docker-compose.yml:358-378`), and the wrapper stack likewise. The variable
is in no `.env.example`. So on any compose deployment the link that leads
members to NUFI Studio and NUFI Works is hidden, whatever the operator sets.
It shows on Railway only because Railway injects every service variable.

**Proposed fix:** `AGENTS_URL: ${AGENTS_URL:-}` on the `librechat` service in
both compose files, and the variable in both `.env.example` files.

### F14. The gateway's shipped models are Gemini aliases, and the on-prem app has agents off — misleads

**Seen:** `deploy/platform/litellm/config.yaml:81-86` says in its own
comments that `claude-sonnet-4-5`, `claude-haiku-4-5`, `gpt-5` and
`gpt-5-mini` are answered by Gemini, and that cost reports carry the alias.
`deploy/platform/librechat.yaml:25` sets `interface.agents: false`. The
Overview pages describe a multi-provider platform with agents; the shipped
on-prem configuration is neither.

**Proposed fix:** either rename the aliases to what they are, or register
the real providers behind them; and decide whether agents are on for the
on-prem stack. Lane 3 rewrites the Overview to say what ships.

### F15. The staging readiness check fails on `main` — blocks

**Seen:** `./scripts/staging-readiness.sh` on the running stack:
`passed 28 failed 3`, `NOT READY for staging`. With
`PYTHON=.venv/bin/python3`: `passed 29 failed 2`. The two that remain:

```
FAIL: could not read controls from policy.yaml (is PyYAML available to python3?)
FAIL: tool-result injection returned 200, expected 400
```

**Why:** the first is the script itself: one of its checks calls `python3`
directly instead of `$PYTHON`, so it fails on any machine whose system
Python lacks PyYAML even when the caller pointed `PYTHON` at the venv, as
the wiring check asks. The second is a real disagreement between the
policy and the test: `policy.yaml` added `tool` to `require_corroboration`
on 2026-09-04 (`a3ee40e85`, "close the G1 agent hole with a tool span
source"), so an injection in a tool result now needs both detectors to
agree before it blocks; check 6e still expects a single-detector block and
its own comment says what that means ("four of six measured
indirect-injection payloads would be log-only"). Either the policy change
regressed the guarantee the check protects, or the check is stale. The
docs cannot say which; whoever made the policy change can.

**Proposed fix:** make every Python call in `staging-readiness.sh` use
`$PYTHON`; then decide 6e: restore single-detector blocking for `tool`
spans, or change the check and the security page to say tool results are
corroborated. Until then the "ready for staging" gate cannot pass.

### F16. The wiring check silently depends on a venv that nothing creates — misleads

**Seen:** `./scripts/check-guardrails-wired.sh` refuses to run without
PyYAML and names the fix (`python3 -m venv .venv && .venv/bin/pip install
-r litellm/requirements.txt`). `bootstrap.sh` never creates that venv, the
README does not mention it, and `platform-ci` installs its own. On a fresh
host the documented pre-promotion check therefore fails before it starts.

**Proposed fix:** `bootstrap.sh` creates `.venv` when it is missing, or
the wiring check runs inside the gateway container, which already has
PyYAML.

## Lane 3: Overview and Reference

### F17. The compose stack still brands itself "NPUOps" — cosmetic

`deploy/platform/.env.example` ships `APP_TITLE=NPUOps`, `CUSTOM_FOOTER='©
NPUOps'`, `HELP_AND_FAQ_URL=https://npuops.local/docs`,
`LANGFUSE_INIT_USER_EMAIL=admin@npuops.local`; `librechat.yaml` names the
one endpoint `NPUOps` and greets with "Welcome to NPUOps — chat routes
through LiteLLM to GPU/NPU backends"; the Railway copy says `Nufi Chat` and
`Nufi`. A self-hosted install therefore presents a product name that is
neither NUFI nor consistent with the hosted one. **Proposed fix:** `NUFI`
for the title, the endpoint and the footer in both stacks; `HELP_AND_FAQ_URL`
to `https://docs.app.nufi.me`.

### F18. Four `*.nufi.me` hostnames in the docs did not exist — docs only, fixed

`api.nufi.me`, `admin.nufi.me`, `langfuse.nufi.me` and `grafana.nufi.me`
appeared across the Overview and Reference pages and resolve nowhere. The
gateway and the compose stack's own surfaces are under `codechi.me`; the
admin panel is `admin.app.nufi.me`. Recorded here so the next person who
finds an old link knows it never worked.

## Lane 4: Administer

### F19. The admin panel still calls itself LibreChat, and its Help page links there — misleads

**Seen:** `apps/admin-panel/src/locales/en/translation.json` carries
"for LibreChat" in `com_users_subtitle` and `com_dash_subtitle`; the Help
page (`src/components/help/HelpPage.tsx:9-27`) links to `librechat.ai/docs`,
the upstream GitHub repository and its Discord. An admin who clicks Help
lands in another product's manual.

**Proposed fix:** the four Help links to `https://docs.app.nufi.me/docs/admin`
and the repository's issues; the two subtitles to "for NUFI".

### F20. The Security page in the admin panel has had no data source since 2026-07-29 — misleads

**Seen:** the page is still in the sidebar (`Sidebar.tsx:58-63`). Its own
notice (`com_security_moved_body`) says the app-layer guardrails that fed it
were removed and that an empty table means no source, not no blocks. The
gateway's decisions, which replaced them, are not shown anywhere in the
panel.

**Proposed fix:** either point the page at the gateway (the
`nufi_guardrail_decisions_total` counters, or the audit events) or remove
it from the sidebar. The docs now say what the empty table means.

### F21. Capability arithmetic does not add up — cosmetic

21 capabilities are defined and seeded onto `ADMIN`
(`packages/data-schemas/src/admin/capabilities.ts:22-44`); the Grants grid
shows 20 (`manage:files` is in no category) and 18 have an English label
(`read:skills`, `manage:skills`, `manage:files` have no `com_cap_*` key).
The docs now say "every capability" instead of a number.

### F22. The Users page exists, is wired to an API, and is disabled — cosmetic

`apps/admin-panel/src/routes/_app/users.tsx:4-6` redirects to `/`; the
components and `POST /api/admin/users` exist. It is also the only place a
user-scoped configuration profile can be created, so user profiles are
listed by the scope selector but cannot be made. Decide whether the page
ships; the docs describe the panel as it is.

### F23. The Registration setting is under System, not Features — docs only, fixed

The old users page sent admins to Features → Registration. `configMeta.ts`
puts the section on the System tab.

## Lane 6: NUFI Studio and NUFI Works

### F24. A member who signs in through NUFI cannot publish a Studio flow — misleads

**Seen:** `apps/nufi-agent/src/backend/base/langflow/services/database/models/api_key/crud.py:83-92` refuses API-key creation for externally authenticated users when the access ceiling is on, and `deploy/railway/agents.md:65` turns the ceiling on for the hosted Studio. `EXTERNAL_AUTH_DISABLE_API_KEYS_FOR_EXTERNAL_USERS` defaults to `true` (`lfx/services/settings/auth.py:255`). Every member reaches Studio through NUFI, so **Add New** under NUFI Studio API Keys fails for all of them with *"API key creation is disabled for externally authenticated users"*, and the run endpoint the Publish page describes has no key anyone can hold.

**Why it matters:** the product pitch for Studio is "a pipeline you can call from code". On the hosted instance nobody can, short of an administrator with a local Studio account. The old Publish page did not say so.

**Proposed fix:** decide which. Either (a) keep the ceiling and give administrators a documented way to issue a key for a flow on a member's behalf, or (b) set `LANGFLOW_EXTERNAL_AUTH_DISABLE_API_KEYS_FOR_EXTERNAL_USERS=false` on the hosted Studio and accept that a key carries the access the member had when it was minted. The docs now state the restriction and both routes.

### F25. The Works wizard and docs disagreed about the recommended adapter — docs only, fixed

Commit `25fd2149d` moved `nufi_agent` to the top of the wizard and put Claude Code and Codex behind **More Agent Adapter Types**; the docs still told members the opposite. `deploy/platform/adapters/meshbox-agent/README.md` says `NUFI_AGENT_URL=http://nufi-agent:7860`; the scenarios page said `http://studio:7860`, which is not a service name in any compose file. Both corrected.

## Lane 5: Using the app

### F26. The hosted app calls itself "Nufi Chat" — cosmetic

`https://chat.nufi.me/api/config` returns `appTitle: "Nufi Chat"`, from `APP_TITLE` in `deploy/railway/docker-compose.yml:24`, and `deploy/railway/librechat.yaml:5` sets `customWelcome: "Welcome to Nufi Chat."`, which is baked into three screenshots. The product is the NUFI app; chat is one of its features. Set `APP_TITLE=NUFI` and change the welcome line, then recapture the screenshots.

### F27. Nobody can reset a password on chat.nufi.me — blocks

**Seen:** `/api/config` reports `emailEnabled: false` and `passwordResetEnabled: false`, so the sign-in screen has no reset link. The admin panel's Users page, the one place an administrator could reset a password, is disabled (**F22**). A member with a password account who forgets it has no path back except creating a new account.

**Proposed fix:** either configure email on the Railway service (`EMAIL_*` variables) so self-service reset works, or ship the Users page with a reset action. The docs now say to ask an administrator, which is true only once one of those exists.

### F28. Help & FAQ in the account menu opens LibreChat's site — cosmetic

`helpAndFaqURL` is `https://librechat.ai` (`/api/config`). `interface.helpAndFaqURL` in `librechat.yaml` can point it at `https://docs.app.nufi.me` instead. Same family as **F19**.

### F29. The repo's seed config no longer describes production — misleads

`deploy/railway/librechat.yaml:40-42` scopes agent capabilities to `file_search` only, but the screenshots taken on `chat.nufi.me` show Web Search, Skills, Run Code and Artifacts in the Tools menu: the admin panel's stored configuration overrides the file, and nothing in the repo records what production actually enables. An operator reading the yaml, or a docs author, gets the wrong answer. Export the live configuration from the admin panel and commit it as the seed, or state in `deploy/railway/README.md` that the panel is authoritative and the yaml is only the first boot.
