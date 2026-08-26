# nufi-app ⇄ MeshBox appliance — the nufi-app side of the contract

> **Status:** W0 foundation (CMP-507). This is nufi-app's half of the productized
> `nufi-app × MeshBox` appliance. The **authoritative** design (HTTP contract, env,
> network, tiers, gaps) lives in the appliance repo: `appliance/docs/INTEGRATION.md`.
> This note records what **nufi-app** must provide, so nufi-app changes don't break
> the appliance orchestration.

## What nufi-app provides

The appliance does **not** fork nufi-app. Its tiered compose
(`appliance/deploy/docker-compose.{base,standard,full}.yml`) orchestrates
**our** images and builds from **this** checkout (`${NUFI_APP_DIR}`). nufi-app is the
single source of truth for images and config; the appliance owns topology + the
MeshBox wiring.

| nufi-app artifact | Consumed by the appliance as | Keep stable |
|-------------------|------------------------------|-------------|
| `adapters/meshbox-chat/` (Dockerfile + `nufi_chat_adapter.py`) | built into `nufi/meshbox-chat-adapter:local` | the `/v1/chat` ⇄ `/v1/chat/completions` translation + `502` honest boundary |
| `litellm/` (Dockerfile + config + guardrails) | built into `nufi/litellm:local`, `:4000` | OpenAI-compatible `/v1/*`, `/health/liveliness`, `guardrails/policy.yaml` mount path |
| `scanner/` (Dockerfile) | built into `nufi/scanner:local`, `/healthz` on `:8000` | `SCANNER_API_BASE` contract |
| `librechat.yaml`, `scripts/postgres-init.sh`, `monitoring/` | mounted read-only from `${NUFI_APP_DIR}` | these relative paths |
| GHCR images `nufichat`, `nufi-console`, `nufichat-admin-panel` | pulled by tier | image names + ports (3080 / 3000 / 3000) |

If you move any of the mounted paths above, or rename an image/port, update
`appliance/docs/INTEGRATION.md` §5 and the tier compose in the same change.

## The adapter is the seam (chat)

MeshBox `portal/ai.py` POSTs `{"message","history"}` to `/v1/chat` and expects
`{"reply","model"}`. nufi-app speaks OpenAI `/v1/chat/completions`. The adapter
(`adapters/meshbox-chat/nufi_chat_adapter.py`) bridges the two and — like the rest of
the honest-boundary design — returns `502` rather than fabricating a reply when the
upstream is empty/unreachable. Config: `NUFI_UPSTREAM_URL`, `NUFI_UPSTREAM_API_KEY`
(falls back to `LITELLM_MASTER_KEY`), `NUFI_MODEL` (empty ⇒ auto-pick).

## Tier → nufi-app service map

The appliance packages this stack in three footprints (see INTEGRATION.md §5):

- **minimal (5):** pgvector(postgres) · mongodb · litellm-proxy · librechat · adapter
- **standard (13):** + redis · console · admin-panel · langfuse(web+worker+clickhouse+minio+minio-init)
- **full (21):** + presidio-analyzer · presidio-anonymizer · nufi-scanner · prometheus · grafana · alertmanager · postgres/redis exporters

Guardrail detectors (presidio, scanner) exist **only at full tier**; minimal/standard
run litellm without them. If `litellm/config.yaml` ever hard-requires a detector at
load time, gate it so the proxy still boots detector-less (appliance gap **G4**).

## Forward work owned by nufi-app (from INTEGRATION.md §7)

- **G1 RAG:** MeshBox expects `/v1/documents` + `/v1/query`; nufi-app has no RAG
  service yet. Needs a RAG backend + a `meshbox-rag` adapter + a pgvector store
  (minimal tier already provisions `pgvector/pgvector:pg16`).
- **G2 Agent:** MeshBox expects `/v1/run`; wire `apps/nufi-agent` behind a
  `meshbox-agent` adapter mapping routine templates → runs.
- **G5 admin-panel:** not in this platform compose yet; the appliance wires
  `API_SERVER_URL` to console best-effort — confirm the real contract.
