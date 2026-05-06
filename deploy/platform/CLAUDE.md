# NPUOps Platform

## WHY (Goal)

Build a self-hosted AI platform to migrate LLM workloads from GPU to NPU.
Q2 2026 deliverable: complete GPU platform with NPU integration ready.
Current phase: W5 — LLM Guard inline + Prometheus/Grafana (W1–W4 complete; standalone `console/` ships keys + budget/rate-limit + `/usage` dashboard)

## WHAT (Stack & Structure)

**Core stack:**

- LiteLLM Proxy — gateway, routing, virtual keys
- Langfuse — observability, tracing, cost tracking
- LibreChat — chat interface for end users (Apache-2.0; replaced Open WebUI in W1 due to license restrictions)
- LLM Guard — PII / prompt injection scanner
- Prometheus + Grafana — monitoring
- PostgreSQL — state store (LiteLLM keys, Langfuse)
- MongoDB — LibreChat app data
- Redis — cache + rate limiting
- Docker Compose — local orchestration

**Directory layout:**

- `litellm/` — config.yaml and customization
- `langfuse/` — Langfuse setup
- `librechat/` — LibreChat config (`librechat.yaml`) + branding assets
- `monitoring/` — Prometheus, Grafana, alert rules
- `scripts/` — helper scripts
- `docs/` — internal documentation

## HOW (Workflow)

**Common commands:**

- Start stack: `docker compose up -d`
- Tail logs: `docker compose logs -f <service>`
- Run smoke test: `./scripts/smoke-test.sh`

**Project conventions:**

- All services run in Docker Compose; do not run Python/Node directly on host
- Pin every Docker image version (never use `:latest`)
- Secrets only via `.env`; never hardcoded
- LiteLLM `config.yaml` must include `backend_type: gpu | npu` field from W1
  so that W8 NPU integration does not require a refactor
- All request logs must include `hardware_id` so W6 reports can aggregate by hardware

**Workflow rules:**

- Research before coding: read official docs, understand the component
- Plan before implementing: confirm approach before writing large files
- Test after writing: smoke test with curl or a Python script

**When uncertain:**

- LiteLLM: docs.litellm.ai
- Langfuse: langfuse.com/docs
- LibreChat: docs.librechat.ai
