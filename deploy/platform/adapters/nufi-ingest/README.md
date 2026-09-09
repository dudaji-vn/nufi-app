# nufi-ingest — a drive folder becomes an agent's Knowledge

Stdlib-only daemon. Sibling of the [RAG adapter](../meshbox-rag/README.md) and
the [chat adapter](../meshbox-chat/README.md) under `deploy/platform/adapters/`.

Watches `NUFI_DRIVES_DIR/<dept>/` (polling; no inotify, so it works on a bind
mount from any host OS). For every department folder it ensures one team
(`"<Dept>"`), one agent (`"<Dept> assistant"`, author = this service account)
and a viewer grant of the agent to the team. Every stable, supported file is
uploaded through `POST /api/files` with `agent_id` + `tool_resource=file_search`,
which embeds it in rag_api and attaches it to the agent in one call. A changed
file is deleted and re-uploaded; a removed file is deleted. State lives in
`NUFI_STATE_DIR/state.json` so a restart does not re-embed the world.

Auth: one login to learn the service account's id, then self-minted HS256 JWTs
signed with `JWT_SECRET` (the app's strategy checks only `payload.id`). Every
call to `/api/files` and `/api/agents` carries a Chrome User-Agent — a single
bare UA bans the account for two hours. `file_ids` are never managed through
`PATCH /api/agents/:id`; the upload/delete endpoints own that relationship.

## Config (env)

| Var | Default | Purpose |
|---|---|---|
| `NUFI_APP_URL` | *(required)* | Base URL of the NuFi app (e.g. `http://librechat:3080`) |
| `NUFI_INGEST_EMAIL` | *(required)* | Service account email used for the one-time login |
| `NUFI_INGEST_PASSWORD` | *(required)* | Service account password |
| `JWT_SECRET` | *(required)* | Shared secret used to self-mint HS256 JWTs after login |
| `NUFI_DRIVES_DIR` | `/drives` | Root folder; one subfolder per department |
| `NUFI_STATE_DIR` | `/state` | Where `state.json` is persisted |
| `NUFI_MODEL` | *(required)* | Model used when creating a department's agent |
| `NUFI_PROVIDER` | `NuFi` | Provider used when creating a department's agent |
| `NUFI_INGEST_INTERVAL` | `20` | Seconds between scans |
| `NUFI_INGEST_SHARE` | `team` | How a department's agent is shared: `team` \| `public` \| `none` |

## State file

`<NUFI_STATE_DIR>/state.json`:

```json
{
  "departments": {
    "legal": {"team_id": "t1", "agent_id": "agent_1", "agent_oid": "oid1"}
  },
  "files": {
    "legal/policy.txt": {
      "file_id": "srv-1", "filepath": "vectordb",
      "size": 123, "mtime": 1717000000, "sha256": "...", "embedded": true
    }
  }
}
```

`departments` maps a drive subfolder name to the team/agent it was provisioned
into. `files` maps a `dept/relative/path` to the last-uploaded file's server
id and the size/mtime/sha256 used to detect a change on the next scan.
`embedded` echoes the app's `POST /api/files` response (`true` once rag_api
has confirmed the embedding); it is informational only and not read back by
the daemon.

## Run / verify

```bash
# unit test — fake NuFi app, temp drives dir, no Docker, no deps (exit 0 = PASS)
python3 test_ingest.py

# run against a live nufi-app stack
NUFI_APP_URL=http://librechat:3080 \
NUFI_INGEST_EMAIL=ingest@box NUFI_INGEST_PASSWORD=*** \
JWT_SECRET=$JWT_SECRET NUFI_MODEL=qwen2.5-7b \
python3 nufi_ingest.py
```
