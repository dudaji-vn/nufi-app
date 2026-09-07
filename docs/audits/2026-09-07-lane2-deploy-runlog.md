# Lane 2 (Deploy & operate) run log — 2026-09-07

Branch `docs/audit-deploy` from origin/main 686229c57 (after lane 1 merged). Same machine and stack as lane 1.

## Executed

| # | Command / action | Result |
|---|---|---|
| 1 | `./scripts/e2e-smoke-test.sh --rebuild` (deploy/platform) | builds the e2e image; 1/7 liveness ok, 2/7 register + JWT ok, 3/7 `POST /api/ask/custom` → 404 `Endpoint not found` → **F10** (test written for LibreChat 0.7 API; app is 0.8.6) |
| 2 | backup page: `docker compose exec -T postgres pg_dumpall -U npuops > pg.sql` | ok, 6.6 MB, databases `langfuse` and `npuops` |
| 3 | backup page: `docker compose exec -T mongodb mongodump --archive --gzip` as written | **fails**: `(Unauthorized) command listDatabases requires authentication`. The stack's Mongo has a root user; the page omits `-u/-p --authenticationDatabase admin` |
| 4 | `docker volume ls` | `npuops_{clickhouse,grafana,minio,mongodb,postgres,prometheus,redis}-data` — names on the page are right |
| 5 | troubleshooting page: `docker compose exec librechat wget -qO- http://litellm-proxy:4000/health/liveliness` | `"I'm alive!"` |
| 6 | troubleshooting page: `curl localhost:9090/api/v1/alerts \| jq` | works; no alerts firing |
| 8 | `docker compose exec -T mongodb sh -c 'mongodump --archive --gzip -u "$MONGO_INITDB_ROOT_USERNAME" -p "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin' > mongo.gz` | ok, 115 KB, every LibreChat collection; this is the form the page must show (credentials come from the container's own env, nothing on the host) |
| 9 | `docker compose exec -T postgres sh -c 'pg_dumpall -U "$POSTGRES_USER"'` | ok, same 6.6 MB / 2 databases; the form the page now shows |
| 10 | monitoring config read (`monitoring/rules/*.yml`, `prometheus.yml`, `alertmanager.yml`, grafana dashboards) | real alert names are LiteLLM* (3) + Guardrail*/MandatoryControl* (6); scrape jobs litellm/postgres/redis/prometheus; retention 15d; one dashboard "LiteLLM Overview"; default receiver noop but critical → slack |
| 11 | Studio health endpoints on the user's running instance (7860) | `/health`, `/health_check`, `/api/v1/version` all 200 |
| 12 | greps: COOKIE_* passthrough, `env_file`, AGENTS_URL, DOMAIN_* | app honours COOKIE_DOMAIN/SAMESITE (`sessionCookies.js`); railway compose passes them, platform compose does not (**F11**); only litellm-proxy has `env_file`; AGENTS_URL passed by neither compose (**F13**); platform compose hardcodes DOMAIN_CLIENT/SERVER=http://localhost:3080 |
| 13 | tags | latest: nufi-v0.1.12, nufi-console-v0.1.7, nufi-admin-v0.0.5; no studio/works tags |
| 14 | Railway service sources (MCP) | nufi-chat builds deploy/railway (BASE var); console v0.1.7; admin v0.0.5; studio :main; works :main; docs builds apps/docs |
| 15 | `./scripts/check-guardrails-wired.sh` | bare python3: refuses (no PyYAML). `PYTHON=<repo>/deploy/platform/.venv/bin/python3 ./scripts/check-guardrails-wired.sh` → "all 5 declared controls are wired and able to run: G1, G2a, G2b, G3, G4" |
| 16 | `./scripts/staging-readiness.sh` | 28/31, NOT READY: wiring reconciliation (no PyYAML), "could not read controls from policy.yaml" (no PyYAML), 6e tool-result injection 200 instead of 400. With `PYTHON=<venv>`: 29/31, the PyYAML failure remains in one check that ignores `$PYTHON`, and 6e remains → **F15**, **F16** |
| 18 | screenshots of /docs/deployment and /docs/deployment/guardrails-ops on the rebuilt site | fine; 19 Deploy pages 200, check:nav 9/9 |

## Not executed

- Cloudflare tunnel, Access policies, Caddy/Traefik configs: no public host here; checked against `deploy/platform/docs/cloudflare-tunnel-setup.md`, `docs/sso-and-reverse-proxy.md` and the compose ports.
- Restore paths (`psql`, `mongorestore --drop`, volume extraction): destructive on the user's data; forms derived from the dump commands that were run.
- Studio egress check (`verify-egress.sh`): needs a Kubernetes cluster.
- Running the admin panel and Works images from `docker run`: env and ports taken from the Dockerfiles and `deploy/railway/agents.md`.
| 17 | `deploy/railway/README.md` Verify section said `curl localhost:3081/api/health` | 404 on this app version (only `/health` is registered); fixed to `/health` |
| 7 | greps | `SCANNER_API_BASE` is in compose (ok); `spend_logs_max_size` is not in `litellm/config.yaml` (page tells you to set it — fine); `COOKIE_DOMAIN`/`COOKIE_SAMESITE` exist only in `deploy/railway/docker-compose.yml`, not the platform stack — the SSO troubleshooting item applies to the Railway wrapper; `docker compose logs chat` on the page names a service that does not exist (`librechat`) |
