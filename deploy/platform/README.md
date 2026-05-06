# NPUOps Platform

Self-hosted AI platform that routes LLM workloads across GPU and NPU backends.
Q2 2026 deliverable: complete GPU platform with NPU integration ready.

## Stack

| Component         | Role                                       |
| ----------------- | ------------------------------------------ |
| LiteLLM Proxy     | Gateway, routing, virtual keys             |
| Langfuse          | Observability, tracing, cost tracking      |
| LibreChat         | Chat interface for end users               |
| Console           | Self-service API key + usage UI (W3)       |
| LLM Guard         | PII / prompt-injection scanner (W5)        |
| Prometheus + Grafana | Monitoring dashboards (W5)              |
| PostgreSQL        | State store (LiteLLM keys, Langfuse data)  |
| MongoDB           | LibreChat app data                         |
| Redis             | Rate limiting + cache                      |

Everything runs in Docker Compose. See `docs/roadmap.md` for the weekly plan.

## Prerequisites

- Docker Engine 24+ and Docker Compose v2 (Docker Desktop on macOS / Windows)
- `git` (with the LibreChat submodule fetched — `--recurse-submodules` on
  clone, or `git submodule update --init` inside an existing checkout)
- `yq` (Mike Farah's Go-based one — bootstrap and `add-model.sh` use it):
  - macOS — `brew install yq`
  - Linux — `sudo snap install yq` or download the binary from
    https://github.com/mikefarah/yq/releases
  - Windows (Git Bash / WSL2) — `winget install MikeFarah.yq` or the
    Linux binary above
  - **Not** Ubuntu's `apt install yq` — that's a different Python tool
- A reachable GPU inference server exposing an OpenAI-compatible API
  (e.g. vLLM, TGI, Ollama). Set `GPU_BACKEND_BASE_URL` in `.env`.
- ~10 GB free disk for Postgres / MongoDB / Langfuse / LibreChat volumes
- A POSIX shell to run the helper scripts:
  - macOS / Linux — built-in
  - Windows — Git Bash (ships with Git for Windows) or WSL2. Do **not** run
    `*.sh` scripts from cmd.exe or PowerShell.

## Quick start (recommended)

### 1. One-time install on your machine

Docker is required. Ollama is **optional** — only install it if you want to
run models locally on your laptop. If you'll point the stack at a remote
GPU/NPU box (vLLM, TGI, custom OpenAI-compatible server) or a cloud
provider (OpenAI, Anthropic, Together, …), skip Ollama entirely.

| OS      | Docker (required)                                      | Ollama (optional, local backend)                                        |
| ------- | ------------------------------------------------------ | ----------------------------------------------------------------------- |
| macOS   | Docker Desktop — https://www.docker.com (≥4 GB RAM)    | `brew install ollama && brew services start ollama`                    |
| Linux   | Docker Engine + Compose v2                             | `curl -fsSL https://ollama.com/install.sh \| sh` then `ollama serve &`  |
| Windows | Docker Desktop + WSL2 backend (≥4 GB RAM)              | `winget install Ollama.Ollama` (or installer from https://ollama.com)   |

Windows users also need **Git for Windows** (which provides Git Bash) or
**WSL2** to run the bootstrap and smoke-test scripts.

### 2. Clone and bootstrap

```bash
# macOS / Linux: open Terminal.
# Windows:       open Git Bash (right-click → "Git Bash Here") or a WSL2 shell.

git clone --recurse-submodules  git@github.com:dudaji-vn/npuops-platform.git
or git clone --recurse-submodules  https://github.com/dudaji-vn/npuops-platform.git
cd npuops-platform
./scripts/bootstrap.sh
#   → initializes the LibreChat submodule if you forgot --recurse-submodules
#   → asks which backend to use:
#       • ollama     — local Ollama on this machine (auto-pulls + registers)
#       • remote     — vLLM / TGI / custom OpenAI-compatible server on the network
#       • cloud      — OpenAI / Anthropic / Together / Groq / etc. (needs an API key)
#       • mock-npu   — clone an existing model entry, tag as backend_type=npu
#       • skip       — bring the stack up only, register models later
#   → fills in random secrets in .env
#   → builds the LibreChat custom image (~5-10 min first run, cached after)
#   → docker compose up -d
#   → runs the smoke test (skipped if no model was registered)
#   → prints URLs and the Langfuse admin password
```

Re-run `./scripts/bootstrap.sh` anytime — it's idempotent. Non-interactive flags:

```bash
./scripts/bootstrap.sh --backend ollama --model qwen2.5:3b   # CI / one-liner
./scripts/bootstrap.sh --backend remote                       # → add-model.sh prompts
./scripts/bootstrap.sh --backend skip                         # stack only, no model
```

### Manual quick start (if you want to do it yourself)

```bash
git submodule update --init      # populate librechat/source (LibreChat soft fork)
cp .env.example .env
# edit .env: replace every `replace-me` value (see comments in the file for
# how to generate each one — e.g. `openssl rand -hex 32`)

docker compose build librechat   # ~5-10 min first time, cached after
docker compose up -d
docker compose logs -f litellm-proxy   # wait for "Application startup complete"

# Register a model (pick one path):
./scripts/add-model.sh           # interactive — works for Ollama, vLLM, TGI,
                                 # OpenAI, Anthropic, Together, custom servers
# (or, if you'll use local Ollama: `ollama pull qwen2.5:3b` first, then run
#  add-model.sh and point it at http://host.docker.internal:11434/v1)

./scripts/smoke-test.sh
```

### Local dev backend (Ollama)

LiteLLM treats Ollama as just another OpenAI-compatible server. `.env.example`
ships with the host-Ollama defaults already set:

```env
GPU_BACKEND_BASE_URL=http://host.docker.internal:11434/v1
GPU_BACKEND_API_KEY=ollama
```

`./scripts/bootstrap.sh` pulls a model and registers it for you. To swap to
a real GPU server later: change the two lines above, then `add-model.sh`
again pointing at the same env vars.

## Adding a new model

Use `./scripts/add-model.sh` (interactive or via flags) to register any
OpenAI-compatible model — Ollama, vLLM, OpenAI, Together, Anthropic, your
teammate's custom server, etc. The script edits `litellm/config.yaml`
and `librechat/librechat.yaml`, restarts the proxy + chat UI, and runs a
test chat completion against the new model.

```bash
# Interactive — prompts you for each field
./scripts/add-model.sh

# Or non-interactive (CI / one-liner)
./scripts/add-model.sh \
  --name mixtral-8x7b \
  --model 'openai/mistralai/Mixtral-8x7B-Instruct-v0.1' \
  --base-url https://api.together.xyz/v1 \
  --api-key-env TOGETHER_API_KEY \
  --backend-type cloud \
  --hardware-id together-cloud
```

Requires `yq` (Mike Farah's — see [Prerequisites](#prerequisites) for cross-platform install). Run `./scripts/add-model.sh --help` for all flags.

## End-to-end smoke test

`./scripts/e2e-smoke-test.sh` drives the full user flow
(LibreChat → LiteLLM → GPU backend → Langfuse trace) inside the compose
network. Useful as a regression check after touching any of those services.

```bash
./scripts/e2e-smoke-test.sh             # ~10s after the image is built
./scripts/e2e-smoke-test.sh --rebuild   # rebuild the e2e image first
```

`./scripts/console-smoke-test.sh` is a faster, host-side regression
check for the W3 console specifically — drives the full happy path
(login → JIT-provision → generate key → use vs LiteLLM → 429 on
rate-limit → revoke → 401 on revoked) in under a second:

```bash
./scripts/console-smoke-test.sh
```

Same `E2E_*` env vars; requires the stack to already be running.

Required env (auto-set by `./scripts/bootstrap.sh`, otherwise fill in `.env`
from the new `E2E_*` block in `.env.example`): `E2E_USER_EMAIL`,
`E2E_USER_PASSWORD`, `E2E_MODEL`, `E2E_EXPECTED_HARDWARE_ID`.

Production deployments that disable `ALLOW_REGISTRATION` must pre-create the
e2e user — the test only auto-registers when registration is open.

## Service endpoints (local defaults)

| Service        | URL                       |
| -------------- | ------------------------- |
| LiteLLM Proxy  | http://localhost:4000     |
| LibreChat      | http://localhost:3080     |
| Console        | http://localhost:3001     |
| Langfuse       | http://localhost:3000     |
| Grafana        | http://localhost:3002     |
| Prometheus     | http://localhost:9090     |

## Project conventions

- All services run in Docker Compose. Do not run Python / Node directly on host.
- Pin every Docker image version. Never use `:latest`.
- Secrets only via `.env`. Never hardcode.
- LiteLLM `config.yaml` must include `model_info.backend_type: gpu | npu` from
  W1 onward, so W8 NPU integration does not require a refactor.
- Every request must log `hardware_id` so W6 reports can aggregate by hardware.

## Layout

```
npuops-platform/
├── docker-compose.yml
├── litellm/          # config.yaml + Dockerfile
├── langfuse/         # Langfuse setup
├── librechat/        # soft fork of LibreChat — see "LibreChat customization"
│   ├── librechat.yaml  # runtime config (mounted into the container)
│   ├── Dockerfile      # builds npuops/librechat:v0.7.5-custom
│   ├── source/         # git submodule, pinned to upstream v0.7.5
│   └── patches/        # *.patch files applied before npm install
├── console/          # self-service UI (Bun + Hono + Vite + React)
├── monitoring/       # Prometheus, Grafana, alert rules
├── scripts/          # helper scripts (smoke test, backups)
└── docs/             # internal documentation (roadmap.md)
```

## Console (self-service UI)

The console at `http://localhost:3001` is where users self-issue LiteLLM API
keys and view their own usage. It's a single Bun container — Hono serves
both the React SPA and the oRPC API at one origin.

**SSO**: the console verifies the LibreChat-issued JWT (shared `JWT_SECRET`)
out of the cookie jar — sign in once at LibreChat, then open the console in
the same browser. No second login.

**Pages**:

- `/` — profile + this-period spend (combined chat + issued-key usage)
- `/keys` — list / generate / revoke API keys with budgets and rpm/tpm limits

**Develop locally** (without rebuilding the image on every change):

```bash
cd console
bun install
bun run dev          # Vite at :5173, Hono at :3000, proxied for you
```

Set the same `JWT_SECRET` / `JWT_REFRESH_SECRET` / `LITELLM_MASTER_KEY` as
the running stack so auth and admin calls work in dev. See
`docs/w3-console-plan.md` for the full implementation plan.

## LibreChat customization (soft fork)

LibreChat ships as a custom image (`npuops/librechat:v0.7.5-custom`) built
from upstream v0.7.5 with a stack of small patches in `librechat/patches/`.
Each patch is one reviewable diff against upstream — the source itself
lives in the `librechat/source/` submodule, which we never edit directly.

**Add a new patch:**

```bash
cd librechat/source

# 1. Edit the upstream files locally (e.g. add a menu item).
$EDITOR client/src/components/Nav/AccountSettings.tsx

# 2. Capture the diff into a numbered patch file.
git diff > ../patches/0002-something-descriptive.patch

# 3. Revert the submodule so it stays clean against upstream.
git checkout -- .

# 4. Build to verify the patch applies cleanly.
cd ../..
docker compose build librechat
docker compose up -d librechat
```

Patches are applied in lexicographic order during the Docker build. Names
should start with a zero-padded number — `0001-`, `0002-`, etc.

**Upgrade the upstream LibreChat version:**

```bash
cd librechat/source
git fetch --tags
git checkout v0.7.6   # or whatever the new tag is

# Dry-run every patch; any "REBASE" line means manual fix-up needed.
cd ..
for p in patches/*.patch; do
  git -C source apply --check "../$p" || echo "REBASE: $p"
done

# After fixing conflicts (re-do the edit against the new source, regenerate
# the patch), rebuild and commit the new submodule SHA.
docker compose build librechat
git add source patches/
git commit -m "chore(librechat): bump to v0.7.6"
```

CI (`.github/workflows/ci.yml`) rebuilds the image on every PR — if a patch
stops applying after an upstream bump, CI fails before it bites locally.

## Documentation

- `docs/roadmap.md` — weekly plan (W1–W9), acceptance criteria, risks
- `CLAUDE.md` — guidance for AI-assisted contributions

## Useful references

- LiteLLM: https://docs.litellm.ai
- Langfuse: https://langfuse.com/docs
- LibreChat: https://docs.librechat.ai
