---
marp: true
title: NPUOps W2 Checkpoint
date: 2026-05-08
---

# NPUOps — W2 Checkpoint

End-to-end GPU flow is live · 2026-05-08 · sun

---

## Architecture (W2)

```
   ┌──────────┐    ┌──────────┐    ┌──────────────┐    ┌──────────┐
   │   User   │───▶│LibreChat │───▶│ LiteLLM Proxy│───▶│  Ollama  │
   │ (browser)│    │  :3080   │    │     :4000    │    │  (GPU)   │
   └──────────┘    └────┬─────┘    └──────┬───────┘    └──────────┘
                        │                 │
                        └─MongoDB         └─Postgres + Redis
                                          │
                                          ▼
                                  ┌────────────────┐
                                  │   Langfuse     │
                                  │  v3 stack      │  (Postgres +
                                  │     :3000      │   ClickHouse +
                                  └────────────────┘   MinIO + worker)
```

Every request carries a `hardware_id` so W6 reports can aggregate per hardware
unit. (The propagation path needs one small follow-up — see slide 5.)

---

## What's new this week

- **LibreChat** at `:3080` — single "NPUOps" custom endpoint pointed at LiteLLM
  - Apache-2.0; replaced Open WebUI (license drift in 2025)
  - Model dropdown auto-populates from LiteLLM `/v1/models` (`fetch: true`)
  - MongoDB persistence verified; conversations survive restart
- **Automated end-to-end smoke test** — `./scripts/e2e-smoke-test.sh`
  - Containerised (no Python on host, per CLAUDE.md)
  - 7 sectioned assertions: liveness, register-or-login, `/api/ask/custom`
    SSE round-trip, Langfuse trace surfaces, cost populated, model recorded,
    hardware_id propagates (soft check)
- **Hygiene** — fixed a SIGPIPE bug in `add-model.sh` / `bootstrap.sh` that
  silently let the dedup check fall through; cleaned 6 duplicate entries from
  `litellm/config.yaml` and dropped a `__dedup_test` artefact

---

## Live demo (≤5 min)

1. `./scripts/e2e-smoke-test.sh` — green output ✓
2. Browser → `http://localhost:3080`
   - Login as `e2e@npuops.local`
   - Pick `qwen2.5-3b`, send "say hi in 5 words"
   - Reply streams back
3. Browser → `http://localhost:3000` (Langfuse)
   - Filter by latest trace
   - Show: `output.content`, `latency`, `cost = 7.4e-06`,
     `observation.model = openai/qwen2.5:3b`
4. (Optional) `docker compose ps` — every service `healthy`

---

## What's next · risks · asks

**W3 (May 12–16):**
- Task 3.1 — API Key Issuance UI (Next.js admin app)
- Task 3.2 — Budget & rate limit management

**Discovered this week (file as W2.5 / early-W3 follow-ups):**
1. **`hardware_id` propagation gap** — `langfuse_default_tags` only resolves
   `cache_hit`/`cache_key` natively; custom keys are silently ignored. Need a
   small LiteLLM `pre_call_hook` (or callback) that injects
   `model_info.hardware_id` into request metadata. Blocks W6 reports
   long-term but not W3.
2. **`smoke-test.sh` default model** is the stale `llama-3-gpu`; use
   `MODEL=qwen2.5-3b ./scripts/smoke-test.sh` until we config-drive it.

**Asks:**
- gom: ETA on NPU backend connection (W8 dependency).
- gom: lock cost-saving API contract by end-W6 (W8.2 dependency).
- All: feedback on the LibreChat branding (logo / favicon still pending).
