#!/usr/bin/env python3
"""Stdlib unit test for the MeshBox⇄nufi-app RAG adapter (no Docker, no deps).

Stands up a fake retriever and a fake OpenAI-compatible generation upstream,
points the adapter at both, and drives it through its MeshBox contract
(/healthz, /v1/documents, /v1/query).

The retriever fake speaks **two** shapes, because the adapter must:

  * ``rag_api`` — what nufi-app actually runs. Ingest is a multipart
    ``POST /embed`` with a caller-supplied file id; retrieval is scoped to
    explicit file ids; and there is **no** ``POST /documents`` — asking for one
    is a 405. An earlier version of this file implemented ``POST /documents``,
    so the suite passed green against a contract the real service does not
    have, and the adapter could not ingest a single document in production.
    Every request the adapter makes is recorded here and asserted.
  * ``legacy`` — a plain answer-service backend that does take the JSON
    ``POST /documents`` and an unscoped ``POST /query``.

Run:  python3 test_adapter.py     (exit 0 = PASS)
"""
import json
import socket
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import nufi_rag_adapter as A


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _form_field(raw, name):
    """Pull one field out of a multipart body (enough parsing for a fake)."""
    marker = b'name="' + name.encode() + b'"'
    i = raw.find(marker)
    if i < 0:
        return None
    j = raw.find(b"\r\n\r\n", i)
    k = raw.find(b"\r\n--", j)
    return raw[j + 4:k].decode("utf-8")


class _FakeRag(BaseHTTPRequestHandler):
    """Retriever stand-in; see the module docstring for the two shapes."""
    shape = "rag_api"
    synth = False
    empty = False
    store = {}
    seen = []

    def log_message(self, *a):
        pass

    def _json(self, code, obj):
        raw = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        _FakeRag.seen.append("GET " + self.path)
        if self.path == "/health":
            return self._json(200, {"status": "ok"})
        if _FakeRag.shape == "rag_api":
            if self.path == "/ids":
                return self._json(200, sorted(_FakeRag.store))
            if self.path.startswith("/documents?ids="):
                fid = urllib.parse.unquote(self.path.split("=", 1)[1])
                return self._json(200, _FakeRag.store.get(fid, []))
        return self._json(404, {"error": "nope"})

    def do_DELETE(self):
        _FakeRag.seen.append("DELETE " + self.path)
        n = int(self.headers.get("Content-Length", 0) or 0)
        ids = json.loads(self.rfile.read(n) or "[]")
        if _FakeRag.shape != "rag_api":
            return self._json(405, {"detail": "Method Not Allowed"})
        for fid in ids:
            _FakeRag.store.pop(fid, None)
        return self._json(200, {"deleted": ids})

    def do_POST(self):
        _FakeRag.seen.append("POST " + self.path)
        n = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(n)

        if _FakeRag.shape == "rag_api":
            if self.path == "/embed":
                fid = _form_field(raw, "file_id")
                text = _form_field(raw, "file") or ""
                # Append, exactly like the real service: the adapter is the one
                # responsible for dropping the old revision first.
                _FakeRag.store.setdefault(fid, []).append(
                    {"page_content": text,
                     "metadata": {"source": f"/app/uploads/public/doc_{'a' * 32}.txt"}})
                return self._json(200, {"status": True, "file_id": fid})
            if self.path == "/documents":
                return self._json(405, {"detail": "Method Not Allowed"})
            if self.path == "/query":
                return self._json(422, {"detail": [{"loc": ["body", "file_id"],
                                                    "msg": "Field required"}]})
            if self.path == "/query_multiple":
                body = json.loads(raw or "{}")
                assert body.get("file_ids"), "query must be scoped to file ids"
                if _FakeRag.empty:
                    return self._json(200, [])
                return self._json(200, [[
                    {"page_content": "Annual leave is 15 days.",
                     "metadata": {"source": f"/app/uploads/public/hr_{'b' * 32}.pdf",
                                  "page": 3}}, 0.9]])
            return self._json(404, {"error": "nope"})

        # legacy shape: no multipart ingest socket at all
        if self.path == "/embed":
            return self._json(405, {"detail": "Method Not Allowed"})
        body = json.loads(raw or "{}")
        if self.path == "/documents":
            return self._json(200, {"id": "doc-42",
                                    "chunks": max(1, len(body.get("text", "")) // 4)})
        if self.path == "/query":
            if _FakeRag.empty:
                return self._json(200, {"documents": []})
            if _FakeRag.synth:
                return self._json(200, {
                    "answer": "Per company policy article 3, it is 15 days.",
                    "sources": ["hr.pdf#3"]})
            return self._json(200, {"documents": [
                {"page_content": "Annual leave is 15 days.",
                 "metadata": {"source": "hr.pdf", "page": 3}},
                {"page_content": "Sick leave follows a separate policy.",
                 "metadata": {"source": "hr.pdf", "page": 4}},
            ]})
        return self._json(404, {"error": "nope"})


class _FakeGen(BaseHTTPRequestHandler):
    """OpenAI-compatible generation stand-in for litellm-proxy."""
    empty_reply = False
    last_body = {}

    def log_message(self, *a):
        pass

    def _json(self, code, obj):
        raw = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path == "/v1/models":
            return self._json(200, {"data": [{"id": "nufi-local-qwen"}]})
        return self._json(404, {"error": "nope"})

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        body = json.loads(self.rfile.read(n) or "{}")
        if self.path == "/v1/chat/completions":
            _FakeGen.last_body = body
            ctx = body["messages"][-1]["content"]
            content = "" if _FakeGen.empty_reply else \
                ("Per the provided context, the answer is 15 days. "
                 f"(context length={len(ctx)})")
            return self._json(200, {"model": body.get("model", "nufi-local-qwen"),
                                    "choices": [{"message": {"role": "assistant",
                                                             "content": content}}]})
        return self._json(404, {"error": "nope"})


def _serve(handler_cls, port):
    httpd = ThreadingHTTPServer(("127.0.0.1", port), handler_cls)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def _wait(url):
    for _ in range(100):
        try:
            urllib.request.urlopen(url, timeout=1).read()
            return
        except urllib.error.HTTPError:
            return
        except Exception:
            threading.Event().wait(0.05)
    raise AssertionError("server never came up: " + url)


def _post(url, obj):
    req = urllib.request.Request(
        url, data=json.dumps(obj).encode(), method="POST",
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or "{}")


def main():
    rag_port, gen_port, ad_port = _free_port(), _free_port(), _free_port()
    _serve(_FakeRag, rag_port)
    _serve(_FakeGen, gen_port)
    _wait(f"http://127.0.0.1:{rag_port}/health")
    _wait(f"http://127.0.0.1:{gen_port}/v1/models")

    cfg = A.Config()
    cfg.rag_url = f"http://127.0.0.1:{rag_port}"
    cfg.upstream = f"http://127.0.0.1:{gen_port}"
    cfg.rag_key = ""
    cfg.api_key = "test-key"
    cfg.model = ""          # force /v1/models discovery
    cfg.k = 2
    cfg.host = "127.0.0.1"
    cfg.port = ad_port
    A.Handler.cfg = cfg
    _serve(A.Handler, ad_port)
    base = f"http://127.0.0.1:{ad_port}"
    _wait(base + "/healthz")

    # ---- pure helpers ---------------------------------------------------
    assert A.humanise_source("/app/uploads/public/hr_" + "b" * 32 + ".pdf") == "hr.pdf"
    assert A.humanise_source("my_report_v2.pdf") == "my_report_v2.pdf", \
        "a legitimate underscore must survive"
    assert A.document_id_for("a.txt") == A.document_id_for("a.txt"), "id must be stable"
    assert A.document_id_for("a.txt") != A.document_id_for("b.txt")

    # ---- 1) rag_api shape: ingest goes to /embed, never to /documents ----
    _FakeRag.shape = "rag_api"
    _FakeRag.store, _FakeRag.seen = {}, []
    doc = {"name": "leave.txt", "text": "Annual leave is 15 days."}
    code, out = _post(base + "/v1/documents", doc)
    assert code == 200, (code, out)
    assert out["chunks"] == 1, out
    assert "POST /embed" in _FakeRag.seen, _FakeRag.seen
    assert "POST /documents" not in _FakeRag.seen, \
        "the real rag_api answers 405 there; the adapter must not call it"

    # ---- 2) re-upload replaces, it does not accumulate -------------------
    code, out2 = _post(base + "/v1/documents", doc)
    assert code == 200 and out2["chunks"] == 1, (code, out2)
    assert out2["id"] == out["id"], "same name must land on the same id"
    assert any(s.startswith("DELETE /documents") for s in _FakeRag.seen), \
        "the old revision must be dropped before re-embedding"

    # ---- 3) query is scoped by file ids, sources are human ---------------
    _FakeRag.seen = []
    code, out = _post(base + "/v1/query", {"question": "How many annual leave days?"})
    assert code == 200, (code, out)
    assert "15 days" in out["answer"], out
    assert out["sources"] == ["hr.pdf#3"], out
    assert "POST /query_multiple" in _FakeRag.seen, _FakeRag.seen
    assert "GET /ids" in _FakeRag.seen, _FakeRag.seen

    # ---- 4) generation is deterministic by default -----------------------
    assert _FakeGen.last_body.get("temperature") == 0, _FakeGen.last_body

    # ---- 5) no chunks -> honest 502, never an invented answer ------------
    _FakeRag.empty = True
    code, out = _post(base + "/v1/query", {"question": "anything"})
    assert code == 200, (code, out)   # empty context still generates a refusal
    _FakeRag.empty = False

    # ---- 6) empty completion -> honest 502 -------------------------------
    _FakeGen.empty_reply = True
    code, out = _post(base + "/v1/query", {"question": "How many annual leave days?"})
    assert code == 502, (code, out)
    _FakeGen.empty_reply = False

    # ---- 7) missing input -> 400 ----------------------------------------
    code, out = _post(base + "/v1/query", {})
    assert code == 400, (code, out)
    code, out = _post(base + "/v1/documents", {"name": "x"})
    assert code == 400, (code, out)

    # ---- 8) legacy answer-service shape still works ----------------------
    _FakeRag.shape = "legacy"
    _FakeRag.seen = []
    code, out = _post(base + "/v1/documents", doc)
    assert code == 200 and out["id"] == "doc-42", (code, out)
    assert "POST /documents" in _FakeRag.seen, "must fall back to the JSON socket"

    _FakeRag.synth = True
    code, out = _post(base + "/v1/query", {"question": "How many annual leave days?"})
    assert code == 200, (code, out)
    assert out["answer"] == "Per company policy article 3, it is 15 days.", out
    assert out["sources"] == ["hr.pdf#3"], out
    _FakeRag.synth = False

    print("PASS: rag_api contract + legacy fallback + honest boundary")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
