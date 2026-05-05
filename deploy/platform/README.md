# NPUOps Platform

Self-hosted AI platform that routes LLM workloads across GPU and NPU backends.
Q2 2026 deliverable: complete GPU platform with NPU integration ready.

## Stack

| Component         | Role                                       |
| ----------------- | ------------------------------------------ |
| LiteLLM Proxy     | Gateway, routing, virtual keys             |
| Langfuse          | Observability, tracing, cost tracking      |
| LibreChat         | Chat interface for end users (Apache-2.0)  |
| LLM Guard         | PII / prompt-injection scanner (W5)        |
| Prometheus + Grafana | Monitoring dashboards (W5)              |
| PostgreSQL        | State store (LiteLLM keys, Langfuse data)  |
| MongoDB           | LibreChat app data                         |
| Redis             | Rate limiting + cache                      |

Everything runs in Docker Compose. See `docs/roadmap.md` for the weekly plan.

## Prerequisites

- Docker Engine 24+ and Docker Compose v2 (Docker Desktop on macOS / Windows)
- A reachable GPU inference server exposing an OpenAI-compatible API
  (e.g. vLLM, TGI, Ollama). Set `GPU_BACKEND_BASE_URL` in `.env`.
- ~10 GB free disk for Postgres / MongoDB / Langfuse / LibreChat volumes
- A POSIX shell to run the helper scripts:
  - macOS / Linux — built-in
  - Windows — Git Bash (ships with Git for Windows) or WSL2. Do **not** run
    `*.sh` scripts from cmd.exe or PowerShell.

## Quick start (recommended)

### 1. One-time install on your machine

| OS      | Docker                                                | Ollama                                                                |
| ------- | ----------------------------------------------------- | --------------------------------------------------------------------- |
| macOS   | Docker Desktop — https://www.docker.com (≥4 GB RAM)   | `brew install ollama && brew services start ollama`                   |
| Linux   | Docker Engine + Compose v2                            | `curl -fsSL https://ollama.com/install.sh \| sh` then `ollama serve &` |
| Windows | Docker Desktop + WSL2 backend (≥4 GB RAM)             | `winget install Ollama.Ollama` (or installer from https://ollama.com) |

Windows users also need **Git for Windows** (which provides Git Bash) or
**WSL2** to run the bootstrap and smoke-test scripts.

### 2. Clone and bootstrap

```bash
# macOS / Linux: open Terminal.
# Windows:       open Git Bash (right-click → "Git Bash Here") or a WSL2 shell.

git clone git@github.com:DudajiVN/npuops-platform.git
cd npuops-platform
./scripts/bootstrap.sh
#   → prompts for which Ollama model to use (default qwen2.5:3b)
#   → fills in random secrets in .env
#   → docker compose up -d
#   → runs the smoke test
#   → prints URLs and the Langfuse admin password
```

Re-run `./scripts/bootstrap.sh` anytime — it's idempotent. To pick a model
non-interactively: `./scripts/bootstrap.sh --model llama3.2:3b`.

### Manual quick start (if you want to do it yourself)

```bash
cp .env.example .env
# edit .env: replace every `replace-me` value (see comments in the file for
# how to generate each one — e.g. `openssl rand -hex 32`)

ollama pull qwen2.5:3b            # or any model from https://ollama.com/library
docker compose up -d
docker compose logs -f litellm-proxy   # wait for "Application startup complete"
./scripts/smoke-test.sh
```

### Local dev backend (Ollama)

LiteLLM treats Ollama as just another OpenAI-compatible server. The defaults
in `.env.example` are already set up to point at host-installed Ollama:

```env
GPU_MODEL=openai/qwen2.5:3b
GPU_BACKEND_BASE_URL=http://host.docker.internal:11434/v1
GPU_BACKEND_API_KEY=ollama
GPU_HARDWARE_ID=mac-local
```

When the real GPU server is provisioned, change those four lines — no
code edit needed.

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

Requires `yq` (mikefarah's: `brew install yq`). Run `./scripts/add-model.sh --help` for all flags.

## Service endpoints (local defaults)

| Service        | URL                       |
| -------------- | ------------------------- |
| LiteLLM Proxy  | http://localhost:4000     |
| LibreChat      | http://localhost:3080     |
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
├── librechat/        # librechat.yaml + branding assets
├── monitoring/       # Prometheus, Grafana, alert rules
├── scripts/          # helper scripts (smoke test, backups)
└── docs/             # internal documentation (roadmap.md)
```

## Documentation

- `docs/roadmap.md` — weekly plan (W1–W9), acceptance criteria, risks
- `CLAUDE.md` — guidance for AI-assisted contributions

## Useful references

- LiteLLM: https://docs.litellm.ai
- Langfuse: https://langfuse.com/docs
- LibreChat: https://docs.librechat.ai
