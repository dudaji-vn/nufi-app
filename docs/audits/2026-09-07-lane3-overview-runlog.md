# Lane 3 (Overview + Reference) run log — 2026-09-07

Branch `docs/audit-overview` from origin/main b5b5a9df9 (after lane 2 merged).

These nine pages describe the system rather than tell the reader to run
things, so the verification was reading and probing rather than executing:
a claim inventory of every page against the repository, then the facts below
checked by hand on the running compose stack and the live services.

## Checked

| # | Claim | How | Result |
|---|---|---|---|
| 1 | which hostnames exist | Railway domains over the API; `deploy/platform/docs/cloudflare-tunnel-setup.md`; `apps/console/server/*` defaults | `chat.nufi.me`, `console.nufi.me`, `agents.nufi.me`, `studio.nufi.me`, `works.nufi.me`, `admin.app.nufi.me`, `docs.app.nufi.me`; the gateway and the stack's own surfaces under `codechi.me`. `api.nufi.me`, `admin.nufi.me`, `langfuse.nufi.me`, `grafana.nufi.me` exist nowhere (**F18**) |
| 2 | what the gateway serves | `/v1/models` on the local stack; `litellm/config.yaml` comments | `gemini`, `nufi-agent`, `claude-sonnet-4-5`, `claude-haiku-4-5`, `gpt-5`, `gpt-5-mini` all Gemini (`hardware_id: gemini-cloud`), plus three added through the UI |
| 3 | the app attaches the user to each request | `apps/chat/api/server/controllers/agents/client.js:763` (`user: this.user ?? req.user.id`) | yes; the trace can name the user although the key is shared |
| 4 | the app's endpoint key | `deploy/platform/librechat.yaml:44` (`${LITELLM_MASTER_KEY}`), `deploy/railway/docker-compose.yml` (`BACKEND_API_KEY`) | one key per deployment; per-user budgets apply to console keys only |
| 5 | input PII is logged, not masked | `policy.yaml` G2a `mode: logging_only`, `action: log` | the old data-flow and glossary pages said "masked" |
| 6 | tool results and the model's turns need two detectors | `policy.yaml` `require_corroboration` incl. `tool` (added `a3ee40e85`, 2026-09-04) | security page corrected |
| 7 | agents in the app | `deploy/platform/librechat.yaml:25` `agents: false`; `deploy/railway/librechat.yaml:20` `agents: true` | on hosted, off on the shipped compose stack (**F14**) |
| 8 | app-layer guardrails are gone | `deploy/railway/.env.example:76-85` | removed 2026-07-29; gateway only |
| 9 | alert routing | `monitoring/alertmanager.yml` | default `noop`, critical → `slack` receiver that needs a webhook file; nobody is "paged within five minutes" by default |
| 10 | the one Grafana dashboard | `monitoring/grafana/dashboards/` | `litellm-overview.json` only; no "Errors by reason" panel |
| 11 | host ports and internal ports | `deploy/platform/docker-compose.yml`, `deploy/railway/docker-compose.yml`, app Dockerfiles | tables regenerated; Studio 7860, Works 3100, admin panel 3000 added |
| 12 | `.env.example` values | the files | `DATABASE_URL` db is `npuops` (page said `litellm`); `APP_TITLE=NPUOps` (page said `Nufi Chat`); `GEMINI_API_KEY` required; generators per `bootstrap.sh:520-539` |
| 13 | image pinning claim on the security page | compose files | `nufichat:main`, `librechat-rag-api-dev-lite:latest` float; infrastructure images pinned |
| 14 | branding on the compose stack | `.env.example`, `librechat.yaml` | still "NPUOps" throughout (**F17**) |

## Not executed

Nothing on these pages is a command. The Langfuse trace fields were read
from the gateway's callback code and a dump of the local Langfuse Postgres
was not inspected.
