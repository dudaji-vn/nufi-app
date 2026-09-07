# Lane 6 (NUFI Studio and NUFI Works) run log — 2026-09-07

Branch `docs/audit-agents` from origin/main 4b6ce8ff5 (after lane 4 merged).

Studio claims were checked against `apps/nufi-agent` (the vendored
Langflow: `src/frontend/src/utils/styleUtils.ts` for the palette,
`src/lfx/src/lfx/base/agents/agent.py` for the agent's inputs,
`src/backend/base/langflow/api/v1/endpoints.py` for the run endpoint,
`services/database/models/api_key/crud.py` and
`lfx/services/settings/auth.py` for the API-key rule) and against
`deploy/railway/agents.md` for what the hosted instance enables. Works
claims against `apps/agents` (`ui/src/adapters/adapter-display-registry.ts`,
`ui/src/pages/Inbox.tsx`, `ui/src/components/access/CompanySettingsNav.tsx`,
`server/src/services/heartbeat.ts` for the wake reasons) and
`apps/console/server/router/connect.ts` for the key the console issues.
Both products were run locally in lane 1; no new screenshots were taken,
but four already-captured ones that no page used are now placed.

## Checked

| # | Claim | Result |
|---|---|---|
| 1 | palette groups | nine plus **Saved** and **Prototypes** (`styleUtils.ts:314-366`); the pages said eight |
| 2 | agent tool input | display name **Tools** (`agent.py:352`), not `Toolset` |
| 3 | MCP servers pre-registered | none; the docs said "a couple" |
| 4 | built-in global variables | `FLOW_ID`, `COMPONENT_ID`, `FIELD_NAME` (`lfx/services/settings/constants.py:59-61`) |
| 5 | run endpoint | `POST /api/v1/run/{flow_id_or_name}` with `x-api-key`; body `input_value`, `input_type`, `output_type` default `chat` (`schemas/__init__.py:351-354`) |
| 6 | Studio API keys for NUFI-signed-in members | refused when the access ceiling is on, which `deploy/railway/agents.md:65` sets (**F24**) |
| 7 | console key masking | first three and last four characters (`apps/console/src/lib/format.ts`) |
| 8 | Works wizard adapter order | `nufi_agent` recommended since `25fd2149d`; coding adapters behind **More Agent Adapter Types** (**F25**) |
| 9 | NUFI adapter label | **NUFI Agent** (`adapter-display-registry.ts:85`) |
| 10 | instance admin tab | **Instance access** (`CompanySettingsNav.tsx:15`) |
| 11 | first-admin banner | "This NUFI Works is waiting on its first admin" |
| 12 | escalation wording | the product is NUFI Works, not "NUFI Agents" |
| 13 | agent wake reasons | assignment, comment, mention, approval granted, blockers resolved, children completed (`heartbeat.ts:524-540`) |
| 14 | Inbox categories | My recent tasks, Join requests, Approvals, Failed runs, Alerts (`Inbox.tsx:2472-2477`) |
| 15 | company budget | **Costs → Budgets**; card reads **Open** / "No monthly cap configured" until set (screenshot `works-costs.png`) |
| 16 | console key expiry | `KEY_DEFAULT_DURATION` defaults to `90d` (`connect.ts:27`) |
| 17 | allowed origin example | the Works origin (`https://works.nufi.me`), not the chooser |
| 18 | scenarios: model URL, adapter URL, fields | `host.docker.internal:11434` (`build_flows.py:341`), `http://nufi-agent:7860` (adapter README), six fields per entry |

## Screenshots

Placed: `works-onboarding.png` (getting started), `works-agents.png`
(agents), `works-org.png` (concepts), `works-costs.png` (costs).
Removed: `works-tasks.png`, which had captured a "Page not found" screen.

## Not executed

Recapturing Studio and Works screenshots against the hosted instances
(they need the shared test account), and a live check that **Share → API
access** on `studio.nufi.me` shows the run endpoint for a NUFI-signed-in
member who cannot hold a key for it.
