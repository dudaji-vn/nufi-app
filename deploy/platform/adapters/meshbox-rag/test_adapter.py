#!/usr/bin/env python3
"""Stdlib unit test for the MeshBox⇄nufi-app RAG adapter (no Docker, no deps).

Stands up a fake nufi-app RAG retriever (/health, /documents, /query) and a fake
OpenAI-compatible generation upstream (/v1/models, /v1/chat/completions), points
the adapter at both, and drives it through its MeshBox contract (/healthz,
/v1/documents, /v1/query), asserting:

  * document upload translation ({name,text} -> {id,chunks})
  * two-hop RAG: retriever chunks -> grounded generation -> {answer, sources}
  * pass-through when the retriever itself already synthesizes an answer
  * honest-boundary 502 on an empty completion, 400 on missing input

Run:  python3 test_adapter.py     (exit 0 = PASS)
"""
import json
import socket
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import nufi_rag_adapter as A


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class _FakeRag(BaseHTTPRequestHandler):
    """Stand-in for nufi-app rag_api. Returns raw chunks (retriever mode) by
    default; flip synth=True to return a pre-synthesized answer (G1 mode)."""
    synth = False
    empty = False  # no chunks / no answer at all

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
        if self.path == "/health":
            return self._json(200, {"status": "ok"})
        return self._json(404, {"error": "nope"})

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        body = json.loads(self.rfile.read(n) or "{}")
        if self.path == "/documents":
            return self._json(200, {"id": "doc-42",
                                    "chunks": max(1, len(body.get("text", "")) // 4)})
        if self.path == "/query":
            if _FakeRag.empty:
                return self._json(200, {"documents": []})
            if _FakeRag.synth:
                return self._json(200, {"answer": "Per company policy article 3, it is 15 days.",
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
    for _ in range(50):
        try:
            urllib.request.urlopen(url, timeout=0.5)
            return
        except Exception:
            time.sleep(0.1)
    raise RuntimeError(f"{url} never came up")


def _post(url, obj):
    req = urllib.request.Request(
        url, data=json.dumps(obj).encode(), method="POST",
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def main():
    rag_port, gen_port, ad_port = _free_port(), _free_port(), _free_port()
    rag = _serve(_FakeRag, rag_port)
    gen = _serve(_FakeGen, gen_port)

    cfg = A.Config()
    cfg.rag_url = f"http://127.0.0.1:{rag_port}"
    cfg.upstream = f"http://127.0.0.1:{gen_port}"
    cfg.rag_key = ""
    cfg.api_key = "test-key"
    cfg.model = ""          # force /v1/models discovery
    cfg.host = "127.0.0.1"
    cfg.port = ad_port
    A.Handler.cfg = cfg
    adapter = _serve(A.Handler, ad_port)
    base = f"http://127.0.0.1:{ad_port}"
    _wait(base + "/healthz")

    # 1) healthz reflects a reachable retriever + discovered model
    with urllib.request.urlopen(base + "/healthz", timeout=5) as r:
        health = json.loads(r.read())
    assert health["status"] == "ok", health
    assert health["model"] == "nufi-local-qwen", health

    # 2) document upload translates {name,text} -> {id,chunks}
    code, out = _post(base + "/v1/documents",
                      {"name": "hr.pdf", "text": "Annual leave is 15 days."})
    assert code == 200, (code, out)
    assert out["id"] == "doc-42" and out["chunks"] >= 1, out

    # 3) missing name/text -> 400
    assert _post(base + "/v1/documents", {"text": "x"})[0] == 400
    assert _post(base + "/v1/documents", {"name": "x"})[0] == 400

    # 4) two-hop RAG: retriever chunks -> grounded answer + sources
    code, out = _post(base + "/v1/query", {"question": "How many annual leave days?"})
    assert code == 200, (code, out)
    assert "15 days" in out["answer"], out
    assert out["sources"] == ["hr.pdf#3", "hr.pdf#4"], out

    # 5) missing question -> 400
    assert _post(base + "/v1/query", {"question": "   "})[0] == 400

    # 6) retriever that already synthesizes an answer -> pass-through (no gen)
    _FakeRag.synth = True
    code, out = _post(base + "/v1/query", {"question": "How many annual leave days?"})
    assert code == 200, (code, out)
    assert out["answer"] == "Per company policy article 3, it is 15 days." and out["sources"] == ["hr.pdf#3"], out
    _FakeRag.synth = False

    # 7) empty completion -> honest 502 (never fabricate)
    _FakeGen.empty_reply = True
    assert _post(base + "/v1/query", {"question": "How many annual leave days?"})[0] == 502
    _FakeGen.empty_reply = False

    adapter.shutdown()
    gen.shutdown()
    rag.shutdown()
    print("PASS: nufi_rag_adapter two-hop RAG + pass-through + honest-boundary")


if __name__ == "__main__":
    main()
