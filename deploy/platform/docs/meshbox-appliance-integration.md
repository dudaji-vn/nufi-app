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

## The adapters are the seam (RAG, Agent) — CMP-510

Two more adapters extend the chat pattern to the remaining MeshBox sockets:

- `adapters/meshbox-rag/` bridges MeshBox `/v1/documents` + `/v1/query` to nufi-app's
  RAG retriever (**rag_api**, `RAG_API_URL`) and grounds the answer via litellm
  (`/v1/chat/completions`). Two-hop RAG (retrieve → generate); `502` on empty. Built
  into `nufi/meshbox-rag-adapter:local`, `:8901`.
- `adapters/meshbox-agent/` bridges MeshBox `/v1/run` to nufi-agent's Langflow run API
  (`/api/v1/run/{flow}`, `x-api-key`), mapping a routine → flow and normalizing the
  nested output to `{status,output}`; `502` on empty/errored/unwired. Built into
  `nufi/meshbox-agent-adapter:local`, `:8902`.

Keep stable for the appliance: the `/v1/documents`·`/v1/query`·`/v1/run` ⇄ upstream
translations + the `502` honest boundary, and the `:8901`/`:8902` ports.

## Identity federation (chat) — CMP-509

nufi-app's **Console is the identity authority** for the appliance. Two console
endpoints + the adapter form the federation seam (appliance gap **G6**, done):

- `POST /oidc/federated-token` (in `apps/console/server/oidc.ts`) — a token-exchange
  grant for a **trusted upstream IdP**. The MeshBox portal, registered in
  `OIDC_CLIENTS` with `federation:true`, authenticates by client credentials and
  asserts a subject it already signed in; the console mints an RS256 identity
  scoped to `audience` (e.g. `nufi-chat`). Gated on the flag: a plain
  authorization-code client can never mint by assertion.
- `GET /oidc/userinfo` — unchanged; verifies the RS256 signature/issuer/expiry and
  returns `{sub,email,access}`. The chat adapter calls this to verify a forwarded
  token, so **the signing key never leaves the console** and the adapter keeps no
  crypto dependency.
- `adapters/meshbox-chat/nufi_chat_adapter.py` — reads `X-MeshBox-Identity`, checks
  audience locally, verifies via `/oidc/userinfo`, then maps the subject to a
  **per-user litellm virtual key** (`NUFI_LITELLM_KEYMAP`) and stamps
  `user`/`metadata`/`X-MeshBox-Actor` so litellm's audit trail is per-user.
  `NUFI_FEDERATION_REQUIRED=1` refuses unidentified requests.

Keep stable for the appliance: the `/oidc/federated-token` request/response shape,
the `federation`+`audience` client fields, and `/oidc/userinfo`'s claim set.

## Forward work owned by nufi-app (from INTEGRATION.md §7)

- **G1 RAG:** ✅ delivered (CMP-510) — `meshbox-rag` adapter above. Still needs the
  real RAG backend deployed in the tier: rag_api + a pgvector store (minimal tier
  already provisions `pgvector/pgvector:pg16`) and a JSON `/documents` ingest (rag_api
  native `/embed` is multipart — a small ingest shim closes that).
- **G2 Agent:** ✅ delivered (CMP-510) — `meshbox-agent` adapter above. Still needs
  nufi-agent deployed in the tier and per-routine `NUFI_AGENT_FLOW_MAP` flows built.
- **G5 admin-panel:** not in this platform compose yet; the appliance wires
  `API_SERVER_URL` to console best-effort — confirm the real contract.
