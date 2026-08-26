# MeshBox ⇄ nufi-app Chat adapter (CMP-505 PoC)

Thin, stdlib-only shim that lets a **MeshBox (appliance)** portal drive
**nufi-app** Chat inference over the mesh. It resolves feasibility gap **#1**
(API-contract mismatch) from `plan/docs/CMP-503-nufi-app-appliance-merge-feasibility.md`.

```
laptop ──mesh──▶ MeshBox portal/ai.py ──POST /v1/chat──▶ [adapter] ──▶
                 nufi-app litellm-proxy /v1/chat/completions ──▶ model
```

MeshBox's `portal/ai.py` is a pure forwarding gateway. For a chat turn it POSTs
`{"message","history"}` to `$MESHBOX_CHAT_URL/v1/chat` and expects `{"reply","model"}`.
nufi-app does not speak that shape — its real Chat inference is the
OpenAI-compatible litellm-proxy on `:4000/v1` (the same endpoint LibreChat's custom
endpoint drives, see `../../librechat.yaml`). This adapter translates both ways and
**never fabricates**: an empty/failed upstream becomes a `502`, so MeshBox's honest
boundary reports a real failure as a failure.

## Contract exposed to MeshBox

| Method + path | Request | Response |
|---|---|---|
| `GET /healthz` | – | `200 {status:"ok",upstream,model}` / `502 {status:"error",detail}` |
| `POST /v1/chat` | `{message, history:[{role,text}...]}` | `200 {reply, model}` / `400` / `502` |

## Config (env)

| Var | Default | Purpose |
|---|---|---|
| `NUFI_UPSTREAM_URL` | `http://litellm-proxy:4000` | nufi-app OpenAI-compatible chat base URL |
| `NUFI_UPSTREAM_API_KEY` (or `LITELLM_MASTER_KEY`) | – | bearer key for litellm |
| `NUFI_MODEL` | *auto* | model to request; if unset, first from `/v1/models` |
| `NUFI_SYSTEM_PROMPT` | – | optional system message |
| `ADAPTER_HOST` / `ADAPTER_PORT` | `0.0.0.0` / `8900` | bind address |
| `NUFI_UPSTREAM_TIMEOUT` | `30` | upstream timeout (s) |
| `NUFI_CONSOLE_URL` | `http://console:3000` | Console base URL used to verify a federated identity token |
| `NUFI_FEDERATION_AUD` | `nufi-chat` | audience the identity token must carry (checked locally) |
| `NUFI_FEDERATION_REQUIRED` | `0` | `1` = refuse requests without a valid identity |
| `NUFI_LITELLM_KEYMAP` | `{}` | JSON `{subject: litellm virtual key}` for per-user attribution |

## Identity federation (CMP-509)

The MeshBox portal carries a member's identity as a nufi-app **Console-signed**
token (from the Console `/oidc/federated-token` grant) in `X-MeshBox-Identity`
(or `Authorization: Bearer`). The adapter checks the token audience locally, then
confirms authenticity via the Console's `/oidc/userinfo` (the Console owns the
signing key, so the adapter keeps no crypto dep). The verified subject is mapped
to a **per-user litellm virtual key** (`NUFI_LITELLM_KEYMAP`) and stamped onto the
OpenAI request as `user` + `metadata` + `X-MeshBox-Actor`, so litellm's audit
trail attributes the call to the real member instead of one shared key. With
`NUFI_FEDERATION_REQUIRED=1` an unidentified request is refused (`401`) — the
adapter never impersonates. See appliance `docs/INTEGRATION.md` §9.

## Run / verify

```bash
# contract translation — fake upstream, no Docker, no deps (exit 0 = PASS)
python3 test_adapter.py

# identity federation — fake Console + fake litellm, per-user audit (exit 0 = PASS)
python3 test_federation.py

# run against a live nufi-app litellm-proxy
NUFI_UPSTREAM_URL=http://litellm-proxy:4000 \
NUFI_UPSTREAM_API_KEY=$LITELLM_MASTER_KEY \
python3 nufi_chat_adapter.py
```

The **full mesh end-to-end proof** (laptop → MeshBox `ai.py` → adapter → nufi chat)
lives in the appliance repo: `appliance/scripts/demo_nufi_chat.sh`.

## Known limits (follow-up issues per CMP-503)

- Auth federation (gap #3/#6): **DONE (CMP-509)** — per-user identity is verified
  and mapped to a per-user litellm key (see above).
- Domain/TLS termination (gap #2): **DONE (CMP-508)** — HTTPS over mesh via Caddy
  (`nufichat.mesh`). At PoC level the adapter can still bind to a mesh IP/mDNS alias.
- Chat only. RAG (`/v1/query`) and Agent (`/v1/run`) are not adapted here (G1/G2).
