# NPUOps Platform

Self-hosted AI platform that routes LLM workloads across GPU and NPU backends.
Q2 2026 deliverable: complete GPU platform with NPU integration ready.

## Stack

| Component         | Role                                       |
| ----------------- | ------------------------------------------ |
| LiteLLM Proxy     | Gateway, routing, virtual keys             |
| Langfuse          | Observability, tracing, cost tracking      |
| Open WebUI        | Chat interface for end users               |
| LLM Guard         | PII / prompt-injection scanner (W5)        |
| Prometheus + Grafana | Monitoring dashboards (W5)              |
| PostgreSQL        | State store (LiteLLM keys, Langfuse data)  |
| Redis             | Rate limiting + cache                      |

Everything runs in Docker Compose. See `docs/roadmap.md` for the weekly plan.

## Prerequisites

- Docker Engine 24+ and Docker Compose v2
- A reachable GPU inference server exposing an OpenAI-compatible API
  (e.g. vLLM, TGI, Ollama). Set `GPU_BACKEND_BASE_URL` in `.env`.
- ~10 GB free disk for Postgres / Langfuse / Open WebUI volumes

## Quick start

```bash
# 1. Clone and enter the repo
git clone git@github.com:DudajiVN/npuops-platform.git
cd npuops-platform

# 2. Create your local env file
cp .env.example .env
# then edit .env and replace every `replace-me` value

# 3. Start the stack
docker compose up -d

# 4. Tail logs
docker compose logs -f litellm-proxy

# 5. Smoke test
./scripts/smoke-test.sh
```

### Local dev backend (free, no GPU server)

For local development on Mac, point `GPU_BACKEND_BASE_URL` at host-installed
Ollama. It uses Metal acceleration and is fast on any Apple Silicon Mac.

```bash
brew install ollama
brew services start ollama        # or: ollama serve
ollama pull qwen2.5:3b            # ~2 GB; swap for any model you prefer
```

The defaults in `.env.example` are already set up for this:

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
| Open WebUI     | http://localhost:3001     |
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
├── open-webui/       # branding + custom pages
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
- Open WebUI: https://docs.openwebui.com
