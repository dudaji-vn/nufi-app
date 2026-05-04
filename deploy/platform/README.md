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

- Docker Engine 24+ and Docker Compose v2
- A reachable GPU inference server exposing an OpenAI-compatible API
  (e.g. vLLM, TGI, Ollama). Set `GPU_BACKEND_BASE_URL` in `.env`.
- ~10 GB free disk for Postgres / MongoDB / Langfuse / LibreChat volumes

## Quick start (recommended)

```bash
# 1. One-time install on your machine:
#    Docker Desktop  https://www.docker.com  (give it ≥4 GB RAM)
#    Ollama          brew install ollama && brew services start ollama
#                    (Linux: curl -fsSL https://ollama.com/install.sh | sh)

# 2. Clone and bootstrap — one command does everything:
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
