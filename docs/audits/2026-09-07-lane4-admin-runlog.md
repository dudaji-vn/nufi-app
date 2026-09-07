# Lane 4 (Administer) run log — 2026-09-07

Branch `docs/audit-admin` from origin/main 5e4c04d3f (after lane 3 merged).

The admin panel's labels, tabs and behaviours were checked against
`apps/admin-panel/src` (components, routes, `locales/en/translation.json`)
and the app's admin API (`apps/chat/api/server/routes/admin/*`,
`packages/data-schemas/src/admin/capabilities.ts`); the observability
pages against `deploy/platform/monitoring/*`; the gateway page against
`deploy/platform/litellm/config.yaml`; the Works page against
`apps/agents/nufi/*` and `apps/agents/server/src/services/budgets.ts`.
No live admin session: the shared test account's password was not
available, so the six existing screenshots stay and no new ones were
taken.

## Checked

| # | Claim | Result |
|---|---|---|
| 1 | admin panel hostname | `admin.app.nufi.me` (Railway custom domain, read over the API); `admin.nufi.me` never existed |
| 2 | sign-in gate | the capability `access:admin` (`routes/admin/auth.js:40,77`), not the role name |
| 3 | sidebar | seven entries: Dashboard, Configuration, Access, Grants, Audit log, Security, Help (`Sidebar.tsx:37-65`) |
| 4 | the Security page | its own notice says the app-layer guardrails feeding it were removed 2026-07-29 (**F20**) |
| 5 | capabilities | 21 defined and seeded on ADMIN; 20 in the Grants grid; 18 labelled (**F21**); Permissions tab = 14 feature toggles, not capabilities |
| 6 | Configuration tabs | eight incl. **Other**; no field search; Import YAML has no diff step; field modes Simple/Advanced/i18n/Multi |
| 7 | profiles | UI vocabulary is profile / profile value / scope; priorities role 10, group 20, user 100, reorderable on Access; per-field Profiles popover; Users page disabled so user profiles cannot be created (**F22**) |
| 8 | Registration setting | System tab (**F23**) |
| 9 | LiteLLM sync | `POST /api/admin/litellm/resync`, badge Synced/Syncing/Sync failed/Not synced; separate from the app's model-list cache, which needs a restart (memory: no TTL) |
| 10 | gateway routing | `simple-shuffle`, no fallbacks, canary slider not enabled (config comment says "later") |
| 11 | Langfuse sign-in | org/project/admin seeded from `.env` (`docker-compose.yml:179-187`) |
| 12 | Grafana | one dashboard "LiteLLM Overview" with the listed panels; nine alerts; retention deletes |
| 13 | Works budgets | per company and per agent (`budgets.ts:40,83,104`), enforcement cancels work (`cancelWorkForScope`); Costs → Budgets tab; adapter config fields incl. `gatewayUrl`, `maxTokens` |
| 14 | Help page links | point at LibreChat's docs and Discord (**F19**) |

## Not executed

Everything that needs a signed-in admin: recapturing the six screenshots,
confirming the Audit log columns on screen, the Profiles popover, the
drag-to-reorder. Those wait for the test-account password.
