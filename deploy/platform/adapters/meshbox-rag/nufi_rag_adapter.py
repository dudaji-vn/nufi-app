#!/usr/bin/env python3
"""MeshBox ⇄ nufi-app RAG adapter — feasibility gap G1 (CMP-510, sibling of chat).

MeshBox (appliance) ``portal/ai.py`` fronts a department RAG backend through two
sockets (see appliance portal/ai.py :163-204):

  POST $MESHBOX_RAG_URL/v1/documents  {"name","text"}      -> {"id","chunks"}
  POST $MESHBOX_RAG_URL/v1/query      {"question"}         -> {"answer","sources"}

nufi-app does NOT speak that contract. Its real RAG engine is the one the chat
app (LibreChat fork) already integrates: **rag_api** (``RAG_API_URL``, default
``rag_api:8000`` — see apps/chat .../app/checks.ts). rag_api is a *retriever*: it
embeds/stores documents and returns matching chunks; it does NOT synthesize a
grounded answer. So this adapter, like a real RAG pipeline, does the two hops:

    laptop ─mesh─▶ MeshBox portal/ai.py ─/v1/query─▶ [THIS ADAPTER]
                   ├─ retrieve ─▶ rag_api  /query           (grounding chunks)
                   └─ generate ─▶ litellm  /v1/chat/completions (grounded answer)

The generation upstream is the very same OpenAI-compatible litellm-proxy the chat
adapter drives, reused deliberately (one model surface for the appliance).

Honest boundary (the product's central principle, mirrored from the chat adapter):
it NEVER fabricates. If retrieval is unreachable, or the model returns an empty
completion, it answers ``502`` so MeshBox's ``AiError(.., 502)`` surfaces a real
failure as a real failure. A missing ``question``/``name``/``text`` is ``400``.

Upstream contract this adapter tolerates (so a plain G1 backend OR rag_api both
work): ``POST {RAG}/query`` may return EITHER a synthesized ``{"answer","sources"}``
(then we pass it straight through — no second hop) OR raw chunks as a list / under
``documents``/``data``/``results`` (then we ground-and-generate here). Likewise
``POST {RAG}/documents`` returns ``{"id"/"file_id","chunks"}``.

Contract exposed to MeshBox
---------------------------
  GET  /healthz          -> 200 {"status":"ok","rag_upstream":..,"model":..}
                            502 {"status":"error","detail":..} if RAG down
  POST /v1/documents      body  {"name": str, "text": str}
                          -> 200 {"id": str, "chunks": int}
                             400 {"error": ..} (missing name/text)
                             502 {"error": ..} (upstream unreachable)
  POST /v1/query          body  {"question": str}
                          -> 200 {"answer": str, "sources": [str, ...]}
                             400 {"error": ..} (missing question)
                             502 {"error": ..} (upstream unreachable / empty)

Config (env)
------------
  NUFI_RAG_URL           base URL of nufi-app RAG retriever
                         (default http://rag_api:8000)
  NUFI_RAG_API_KEY       optional bearer for the RAG retriever
  NUFI_RAG_K             top-k chunks to retrieve (default 4)
  NUFI_UPSTREAM_URL      OpenAI-compatible generation base (litellm-proxy)
                         (default http://litellm-proxy:4000)
  NUFI_UPSTREAM_API_KEY  bearer key (also accepts LITELLM_MASTER_KEY)
  NUFI_MODEL             model for generation; empty => first from /v1/models
  NUFI_SYSTEM_PROMPT     grounding system prompt (has a sensible Korean default)
  ADAPTER_HOST/ADAPTER_PORT   bind address (default 0.0.0.0 / 8901)
  NUFI_UPSTREAM_TIMEOUT  per-request timeout seconds (default 30)

Run
---
  python3 nufi_rag_adapter.py            # serves on 0.0.0.0:8901
"""
import contextlib
import json
import os
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# Korean-by-design default: the appliance ships to Korean-speaking departments, so
# the grounded RAG answer defaults to Korean. Override with NUFI_SYSTEM_PROMPT.
# English meaning of the default: "You are an in-house document QA assistant. Answer
# concisely in Korean, grounded ONLY in the '문맥' (context) below; if the context
# does not support an answer, say you don't know — never fabricate." The Korean label
# '문맥' (context) / '질문' (question) below is kept consistent with this prompt.
DEFAULT_SYSTEM_PROMPT = (
    "당신은 사내 문서 기반 질의응답 도우미입니다. 아래 '문맥'에 있는 내용만 근거로 "
    "한국어로 간결히 답하세요. 문맥에 근거가 없으면 모른다고 답하고 지어내지 마세요."
)


def _env(*names, default=""):
    for n in names:
        v = os.environ.get(n)
        if v:
            return v
    return default


class Config:
    def __init__(self):
        self.rag_url = _env("NUFI_RAG_URL",
                            default="http://rag_api:8000").rstrip("/")
        self.rag_key = _env("NUFI_RAG_API_KEY")
        self.k = int(os.environ.get("NUFI_RAG_K", "4") or "4")
        self.upstream = _env("NUFI_UPSTREAM_URL",
                             default="http://litellm-proxy:4000").rstrip("/")
        self.api_key = _env("NUFI_UPSTREAM_API_KEY", "LITELLM_MASTER_KEY")
        self.model = os.environ.get("NUFI_MODEL", "").strip()
        self.system_prompt = (os.environ.get("NUFI_SYSTEM_PROMPT", "").strip()
                              or DEFAULT_SYSTEM_PROMPT)
        self.host = os.environ.get("ADAPTER_HOST", "0.0.0.0")
        self.port = int(os.environ.get("ADAPTER_PORT", "8901"))
        self.timeout = float(os.environ.get("NUFI_UPSTREAM_TIMEOUT", "30"))


class UpstreamError(Exception):
    """Upstream (rag_api or litellm) failed. Always mapped to HTTP 502 downstream."""


def _request(base, path, payload=None, method="GET", key="", timeout=30.0):
    """Call a JSON HTTP upstream; return parsed JSON or raise UpstreamError.

    Any transport/HTTP/JSON failure becomes UpstreamError so we answer the
    MeshBox gateway with an honest 502 rather than a fabricated result.
    """
    url = base + path
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Accept", "application/json")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if key:
        req.add_header("Authorization", "Bearer " + key)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        body = ""
        with contextlib.suppress(Exception):
            body = exc.read().decode("utf-8")[:300]
        raise UpstreamError(f"upstream HTTP {exc.code}: {body}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise UpstreamError(
            f"upstream unreachable: {getattr(exc, 'reason', exc)}") from exc
    except json.JSONDecodeError as exc:
        raise UpstreamError(f"upstream returned non-JSON: {exc}") from exc


def resolve_model(cfg):
    """Return the generation model: configured one, else first advertised."""
    if cfg.model:
        return cfg.model
    data = _request(cfg.upstream, "/v1/models", method="GET",
                    key=cfg.api_key, timeout=cfg.timeout)
    models = data.get("data") or []
    if not models:
        raise UpstreamError("generation upstream advertises no models")
    model = models[0].get("id") or models[0].get("model")
    if not model:
        raise UpstreamError("generation upstream /v1/models entry has no id")
    return model


def upload_document(cfg, name, text):
    """Hand a document to the RAG retriever; return {id, chunks} for MeshBox."""
    resp = _request(cfg.rag_url, "/documents",
                    {"name": name, "text": text}, method="POST",
                    key=cfg.rag_key, timeout=cfg.timeout) or {}
    doc_id = resp.get("id") or resp.get("file_id") or resp.get("document_id")
    if not doc_id:
        raise UpstreamError("RAG upstream did not return a document id")
    chunks = resp.get("chunks", resp.get("chunk_count", 0))
    try:
        chunks = int(chunks or 0)
    except (TypeError, ValueError):
        chunks = 0
    return {"id": str(doc_id), "chunks": chunks}


def _chunk_text(c):
    """Pull the text out of one retrieved chunk (tolerant of shapes)."""
    if isinstance(c, str):
        return c
    if isinstance(c, dict):
        return (c.get("page_content") or c.get("text") or c.get("content")
                or c.get("chunk") or "")
    return ""


def _chunk_source(c, idx):
    """Pull a human source label out of one retrieved chunk."""
    if isinstance(c, dict):
        meta = c.get("metadata") or {}
        src = (meta.get("source") or meta.get("name") or meta.get("file")
               or c.get("source") or c.get("name") or c.get("id"))
        page = meta.get("page") or meta.get("loc")
        if src and page not in (None, ""):
            return f"{src}#{page}"
        if src:
            return str(src)
    return f"chunk-{idx + 1}"


def _extract_chunks(resp):
    """Normalize a retriever response into a list of chunk dicts/strings."""
    if isinstance(resp, list):
        # rag_api returns [[Document, score], ...] or [Document, ...]
        out = []
        for item in resp:
            if isinstance(item, list | tuple) and item:
                out.append(item[0])
            else:
                out.append(item)
        return out
    if isinstance(resp, dict):
        for key in ("documents", "data", "results", "chunks", "matches"):
            val = resp.get(key)
            if isinstance(val, list):
                return val
    return []


def query(cfg, question):
    """Answer a question against the RAG corpus. Returns {answer, sources}.

    Two-hop RAG: retrieve grounding chunks from the RAG upstream, then generate a
    grounded answer via litellm. If the retriever already synthesizes an answer
    (a plain G1 backend), we pass it straight through — no second hop, no
    duplicate work. Empty either way -> honest 502.
    """
    resp = _request(cfg.rag_url, "/query",
                    {"query": question, "question": question, "k": cfg.k},
                    method="POST", key=cfg.rag_key, timeout=cfg.timeout) or {}

    # Path A: retriever already produced a grounded answer -> pass through.
    if isinstance(resp, dict) and (resp.get("answer") or "").strip():
        sources = list(resp.get("sources", []) or [])
        return {"answer": resp["answer"].strip(), "sources": sources}

    # Path B: retriever returned raw chunks -> ground-and-generate here.
    chunks = _extract_chunks(resp)
    context_parts, sources = [], []
    for i, c in enumerate(chunks):
        txt = _chunk_text(c).strip()
        if not txt:
            continue
        src = _chunk_source(c, i)
        sources.append(src)
        context_parts.append(f"[{src}]\n{txt}")
    context = "\n\n".join(context_parts) if context_parts else "(관련 문서 없음)"

    model = resolve_model(cfg)
    messages = [
        {"role": "system", "content": cfg.system_prompt},
        {"role": "user",
         "content": f"문맥:\n{context}\n\n질문: {question}"},
    ]
    gen = _request(cfg.upstream, "/v1/chat/completions",
                   {"model": model, "messages": messages, "stream": False},
                   method="POST", key=cfg.api_key, timeout=cfg.timeout)
    choices = gen.get("choices") or []
    answer = ""
    if choices:
        answer = ((choices[0].get("message") or {}).get("content") or "").strip()
    if not answer:
        # Honest boundary: an empty completion is a failure, not an answer.
        raise UpstreamError("generation upstream returned an empty completion")
    # De-dup sources, keep order.
    seen, uniq = set(), []
    for s in sources:
        if s not in seen:
            seen.add(s)
            uniq.append(s)
    return {"answer": answer, "sources": uniq}


class Handler(BaseHTTPRequestHandler):
    cfg = None  # injected by serve()

    def log_message(self, fmt, *args):
        sys.stderr.write("[rag-adapter] " + (fmt % args) + "\n")

    def _json(self, code, obj):
        raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _body(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        return json.loads(self.rfile.read(n) or "{}")

    def do_GET(self):
        if self.path in ("/healthz", "/health"):
            try:
                # A reachable retriever is the hard dependency; the model is
                # resolved lazily but we surface it when we can.
                _request(self.cfg.rag_url, "/health", method="GET",
                         key=self.cfg.rag_key, timeout=self.cfg.timeout)
                model = ""
                try:
                    model = resolve_model(self.cfg)
                except UpstreamError:
                    model = "unknown"
                return self._json(200, {"status": "ok",
                                        "rag_upstream": self.cfg.rag_url,
                                        "model": model})
            except UpstreamError as exc:
                return self._json(502, {"status": "error", "detail": str(exc)})
        return self._json(404, {"error": "not found"})

    def do_POST(self):
        try:
            body = self._body()
        except (ValueError, json.JSONDecodeError):
            return self._json(400, {"error": "invalid JSON body"})

        if self.path == "/v1/documents":
            name = (body.get("name") or "").strip()
            text = body.get("text") or ""
            if not name:
                return self._json(400, {"error": "name is required"})
            if not text.strip():
                return self._json(400, {"error": "text is required"})
            try:
                return self._json(200, upload_document(self.cfg, name, text))
            except UpstreamError as exc:
                return self._json(502, {"error": str(exc)})

        if self.path == "/v1/query":
            question = (body.get("question") or "").strip()
            if not question:
                return self._json(400, {"error": "question is required"})
            try:
                return self._json(200, query(self.cfg, question))
            except UpstreamError as exc:
                return self._json(502, {"error": str(exc)})

        return self._json(404, {"error": "not found"})


def serve(cfg=None):
    cfg = cfg or Config()
    Handler.cfg = cfg
    httpd = ThreadingHTTPServer((cfg.host, cfg.port), Handler)
    sys.stderr.write(
        f"[rag-adapter] listening on {cfg.host}:{cfg.port} -> "
        f"rag={cfg.rag_url} gen={cfg.upstream} (model={cfg.model or 'auto'})\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    serve()
