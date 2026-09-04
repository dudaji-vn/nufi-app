# MeshBox ⇄ nufi-app RAG adapter (CMP-510, gap G1)

Thin, stdlib-only shim that lets a **MeshBox (appliance)** portal drive
**nufi-app** RAG (department document Q&A) over the mesh. Sibling of the
[chat adapter](../meshbox-chat/README.md); resolves forward gap **G1** from
`plan/docs/CMP-503-…` / `deploy/platform/docs/meshbox-appliance-integration.md`.

```
laptop ─mesh─▶ MeshBox portal/ai.py ─/v1/query─▶ [adapter]
               ├─ retrieve ─▶ rag_api /query             (grounding chunks)
               └─ generate ─▶ litellm /v1/chat/completions (grounded answer)
```

MeshBox's `portal/ai.py` fronts a RAG backend with two sockets: `POST /v1/documents`
`{name,text}` → `{id,chunks}` and `POST /v1/query` `{question}` → `{answer,sources}`.
nufi-app's real RAG engine is **rag_api** (`RAG_API_URL`, the retriever the chat app
already integrates) — it returns *chunks*, not a synthesized answer. So this adapter
does the two hops a real RAG pipeline does: **retrieve** from rag_api, then **generate**
a grounded answer with the same OpenAI-compatible litellm-proxy the chat adapter uses.

Like the chat adapter it **never fabricates**: an unreachable retriever or an empty
completion becomes a `502`, so MeshBox's honest boundary reports a real failure as a
failure.

## Contract exposed to MeshBox

| Method + path | Request | Response |
|---|---|---|
| `GET /healthz` | – | `200 {status:"ok",rag_upstream,model}` / `502 {status:"error",detail}` |
| `POST /v1/documents` | `{name, text}` | `200 {id, chunks}` / `400` / `502` |
| `POST /v1/query` | `{question}` | `200 {answer, sources:[...]}` / `400` / `502` |

## Upstream RAG contract (tolerant)

`POST {NUFI_RAG_URL}/query` may return **either**:
- a synthesized `{answer, sources}` (a plain G1 answer-service) → passed straight
  through, no second hop; **or**
- raw chunks — a list `[{page_content, metadata}...]` (rag_api native) or under
  `documents`/`data`/`results`/`chunks`/`matches` → grounded-and-generated here.

`GET /health` → 200.

### Ingest, and the socket that does not exist

The real **rag_api** has **no `POST /documents`** — it answers `405`. Ingest is
`POST /embed`, a *multipart* upload carrying a caller-supplied `file_id`, and
retrieval is scoped: `POST /query` without a `file_id` is a `422`. So the adapter
reads `GET /ids` and asks `POST /query_multiple` across everything the store
holds, which keeps it stateless.

`/embed` **appends**, so re-ingesting under the same id would leave a superseded
revision in the index; the adapter deletes first, making a re-upload behave like
saving over a file on the drive. The document id is `sha256(name)[:16]`, so the
same document name always lands on the same id.

A plain answer-service backend that *does* take JSON `POST /documents` and an
unscoped `POST /query` is still supported — as the **fallback**, chosen only on a
`404`/`405`, never to paper over a real failure.

> This is worth stating plainly because the adapter shipped calling
> `POST /documents` as its primary path and could not ingest a single document
> against the service nufi-app actually runs. Its suite passed because the fake
> implemented the imagined contract. `test_adapter.py` now drives **both**
> shapes, and the rag_api fake answers `405` there exactly like the real one.

## Config (env)

| Var | Default | Purpose |
|---|---|---|
| `NUFI_RAG_URL` | `http://rag_api:8000` | nufi-app RAG retriever base URL |
| `NUFI_RAG_API_KEY` | – | optional bearer for the retriever |
| `NUFI_RAG_K` | `4` | top-k chunks to retrieve |
| `NUFI_UPSTREAM_URL` | `http://litellm-proxy:4000` | OpenAI-compatible generation base |
| `NUFI_UPSTREAM_API_KEY` (or `LITELLM_MASTER_KEY`) | – | bearer key for litellm |
| `NUFI_MODEL` | *auto* | generation model; if unset, first from `/v1/models` |
| `NUFI_SYSTEM_PROMPT` | *(Korean grounding prompt)* | system message for generation |
| `ADAPTER_HOST` / `ADAPTER_PORT` | `0.0.0.0` / `8901` | bind address |
| `NUFI_UPSTREAM_TIMEOUT` | `30` | per-request timeout (s) |

## Run / verify

```bash
# unit test — fake rag_api + fake litellm, no Docker, no deps (exit 0 = PASS)
python3 test_adapter.py

# run against a live nufi-app stack
NUFI_RAG_URL=http://rag_api:8000 \
NUFI_UPSTREAM_URL=http://litellm-proxy:4000 \
NUFI_UPSTREAM_API_KEY=$LITELLM_MASTER_KEY \
python3 nufi_rag_adapter.py
```

The **full mesh end-to-end proof** (laptop → MeshBox `ai.py` → adapter → nufi RAG)
lives in the appliance repo: `appliance/scripts/demo_nufi_rag.sh`.

## Known PoC limits

- Corpus scoping: `/v1/query` retrieves across the corpus the retriever exposes; per-user
  / per-department document ACLs (auth federation, gap #3) are out of scope here.
- rag_api's native `/embed` is multipart; this adapter targets a JSON `/documents` ingest
  (a small G1 ingest endpoint or rag_api-compat shim). Retrieval `/query` is already JSON.
