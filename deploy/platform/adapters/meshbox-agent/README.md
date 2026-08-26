# MeshBox ⇄ nufi-app Agent adapter (CMP-510, gap G2)

Thin, stdlib-only shim that lets a **MeshBox (appliance)** portal trigger
**nufi-app** agent routines over the mesh. Sibling of the
[chat adapter](../meshbox-chat/README.md); resolves forward gap **G2** from
`deploy/platform/docs/meshbox-appliance-integration.md`.

```
laptop ─mesh─▶ MeshBox portal/ai.py ─/v1/run─▶ [adapter] ─▶ nufi-agent /api/v1/run/{flow}
```

MeshBox's `portal/ai.py` triggers a routine by POSTing `{routine_id, routine}` to
`/v1/run` and expects a run record `{status, output}`. nufi-app's real agent engine
is **nufi-agent** (`apps/nufi-agent`, a Langflow-based flow runtime) whose service API
runs a *flow* by id and returns a deeply-nested result. This adapter maps a routine to
a flow, runs it, and normalizes the nested output down to `{status, output}`.

Like the chat adapter it **never fabricates**: an unreachable backend, an errored run,
an empty output, or a routine with no wired flow all become `502`, so MeshBox's honest
boundary reports a real failure as a failure — never a fake "completed".

## Contract exposed to MeshBox

| Method + path | Request | Response |
|---|---|---|
| `GET /healthz` | – | `200 {status:"ok",agent_upstream,mode}` / `502 {status:"error",detail}` |
| `POST /v1/run` | `{routine_id, routine}` | `200 {status, output}` / `400` / `502` |

## Two upstream modes (auto-selected)

- **flow mode** *(a flow is mapped)* — drives nufi-agent's Langflow run API:
  `POST {AGENT}/api/v1/run/{flow}` with `x-api-key`, body
  `{input_value, output_type:"chat", input_type:"chat"}`; the nested
  `outputs[].outputs[].results.message.text` is walked out robustly.
- **clean mode** *(no flow mapped)* — `POST {AGENT}{NUFI_AGENT_RUN_PATH}` with
  `{routine_id, routine}` and expects a plain `{status, output}` — for a future G2
  service that already speaks the MeshBox shape.

If neither a flow nor a clean endpoint is configured, a routine is **honestly
unwired** → `502` (never a fabricated result).

## Config (env)

| Var | Default | Purpose |
|---|---|---|
| `NUFI_AGENT_URL` | `http://nufi-agent:7860` | nufi-agent base URL |
| `NUFI_AGENT_API_KEY` (or `LANGFLOW_API_KEY`) | – | `x-api-key` for nufi-agent |
| `NUFI_AGENT_FLOW_MAP` | – | JSON `{routine_id: flow_id}` routing map |
| `NUFI_AGENT_DEFAULT_FLOW` | – | flow for routines not in the map |
| `NUFI_AGENT_RUN_PATH` | `/api/v1/run` | run path (flow appended in flow mode) |
| `NUFI_AGENT_INPUT_TEMPLATE` | `'{routine}' 루틴을 실행하세요.` (Korean-by-design; means "Run the '{routine}' routine.") | `input_value` template |
| `ADAPTER_HOST` / `ADAPTER_PORT` | `0.0.0.0` / `8902` | bind address |
| `NUFI_AGENT_TIMEOUT` | `120` | run timeout (s) — agent runs are slow |
| `NUFI_EGRESS_MODE` | `audit` | `enforce` = refuse to dial an off-mesh `NUFI_AGENT_URL` (`403`); `audit` records only |
| `NUFI_EGRESS_ALLOW` | – | comma/space list of extra allow-listed agent hosts |
| `NUFI_MESH_CIDR` | – | mesh CIDR(s) counted as on-mesh (e.g. `192.168.99.0/24`) |
| `NUFI_MESH_DOMAIN` | `mesh` | mesh DNS suffix counted as on-mesh |

**Egress guard (CMP-511 W4, gap #6).** Before a routine run dials nufi-agent, the
adapter confirms `NUFI_AGENT_URL` is on the mesh (loopback / private / `.mesh` /
mesh CIDR / allow-list). A public target is denied `403` in `enforce` mode (never
dialed), recorded only in `audit` (default). See `nufi_egress.py`, `test_egress.py`.

MeshBox routine ids (`r1`…`r6`) come from `appliance/portal/catalog.py :ROUTINES`.
Map each to a nufi-agent flow, e.g.:

```bash
NUFI_AGENT_FLOW_MAP='{"r1":"dept-qa","r2":"meeting-minutes","r3":"morning-mail"}'
```

## Run / verify

```bash
# unit test — fake nufi-agent, no Docker, no deps (exit 0 = PASS)
python3 test_adapter.py

# run against a live nufi-agent
NUFI_AGENT_URL=http://nufi-agent:7860 \
NUFI_AGENT_API_KEY=$LANGFLOW_API_KEY \
NUFI_AGENT_DEFAULT_FLOW=dept-qa \
python3 nufi_agent_adapter.py
```

The **full mesh end-to-end proof** (laptop → MeshBox `ai.py` → adapter → nufi-agent)
lives in the appliance repo: `appliance/scripts/demo_nufi_agent.sh`.

## Known PoC limits

- Routine→flow mapping is operator-provided (`NUFI_AGENT_FLOW_MAP`); auto-provisioning
  flows from the routine catalog is out of scope.
- Async/long runs are handled synchronously within `NUFI_AGENT_TIMEOUT`; streaming and
  run polling are out of scope for the PoC.
- Auth federation (gap #3): a single `x-api-key`, not per-user portal identity.
