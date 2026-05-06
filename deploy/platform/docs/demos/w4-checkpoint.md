---
marp: true
title: NPUOps W4 Checkpoint
date: 2026-05-08
---

# NPUOps — W3 + W4 Checkpoint

Self-service is live · 2026-05-08 · sun

---

## Where we are vs. roadmap calendar

Today is week 2 by calendar (May 5–9). Work-wise we're ~one week ahead:

- **W1** ✅ — LiteLLM proxy + Langfuse v3 stack (`v0.1.0-alpha`)
- **W2** ✅ — LibreChat + automated e2e smoke test (7/7)
- **W3** ✅ — Console: API key CRUD, budget / rpm / tpm, JWT SSO
- **W4** 🟢 — Self-service usage dashboard (today)
- **W2.5** ✅ — `hardware_id` propagation gap closed; e2e is now 7/7 hard checks

Effective buffer: ~5 working days going into W5 (LLM Guard).

---

## What ships this checkpoint

- **`/usage` route on the console** — dedicated dashboard, separate from the profile mini-chart
  - Period selector: 7d / 30d / 90d
  - 4 summary cards: total cost, requests, models used, primary hardware
  - Daily-spend bar chart (UsageChart)
  - Per-model + per-hardware breakdown (side-by-side)
  - Last 50 requests, newest-first, with chat / key source tag
- **Two data sources, one cache:**
  - LiteLLM `/spend/logs` for cost + per-model (authoritative for spend)
  - Langfuse `/api/public/traces` for per-`hardware_id` (LiteLLM doesn't carry it)
  - 60s in-memory trace cache → `summary` + `byHardware` share one round-trip per tick
- **W2.5 hook** — `litellm/callbacks/hardware_metadata.py` stamps every
  request with `hardware_id` + `backend_type` as Langfuse tags (queryable)
  and `trace_metadata` (structured)

---

## Live demo (≤5 min)

1. `./scripts/console-smoke-test.sh` — 14/14 hard checks ✓
2. Browser → `http://localhost:3080` → login → chat one prompt
3. Browser → `http://localhost:3001` (console) — already authenticated
   - **Profile** — combined spend (chat + issued keys), 7-day mini chart
   - **API keys** — generate a key, reveal-once modal, copy → curl works
   - **Usage** — switch 7 → 30 → 90, scroll the breakdown
     - Note the `mac-local (gpu)` row in **By hardware**
     - Mention: when gom's NPU lands in W8, that'll become a second row
       and the migration story becomes visible immediately
4. Browser → Langfuse → filter `tags=hardware_id:mac-local` → live data

---

## What's next · risks · asks

**W5 (May 26–30, but pulled forward):**
- Task 5.1 — LLM Guard inline integration (PII + prompt injection)
- Task 5.2 — Prometheus + Grafana + Slack alerts

**Discovered this week:**
1. LiteLLM logs the same model under two names (`openai/qwen2.5:3b` for
   chat traffic, `qwen2.5-3b` for issued-key traffic). Stripped the
   `openai/` prefix for now; full alias-vs-id collapse needs round-tripping
   through `/model/info` and is deferred — Langfuse-backed views already
   record the configured name correctly, so the smell is bounded.
2. Pre-W2.5 traces show as an `unknown` hardware bucket — they age out of
   the 7-day window naturally; no backfill needed.

**Asks:**
- gom: ETA on NPU backend connection (W8 dependency).
- gom: lock cost-saving API contract by end-W6 (W8.2 dependency).
- All: feedback on the LibreChat branding (logo / favicon still pending).
