#!/usr/bin/env python3
"""Stdlib unit test for the MeshBox⇄nufi-app chat adapter (no Docker, no deps).

Stands up a fake nufi-app OpenAI-compatible upstream (/v1/models +
/v1/chat/completions), points the adapter at it, and drives the adapter through
its MeshBox contract (/healthz + /v1/chat), asserting the request/response
translation both ways — including the honest-boundary 502 on an empty completion.

Run:  python3 test_adapter.py     (exit 0 = PASS)
"""
import json
import socket
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import nufi_chat_adapter as A


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class _FakeUpstream(BaseHTTPRequestHandler):
    """Minimal OpenAI-compatible stand-in for nufi-app litellm-proxy."""
    empty_reply = False  # flipped by a test to exercise the 502 path

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
            last = body["messages"][-1]["content"]
            content = "" if _FakeUpstream.empty_reply else f"reply to: {last}"
            return self._json(200, {
                "model": body.get("model", "nufi-local-qwen"),
                "choices": [{"message": {"role": "assistant",
                                         "content": content}}],
            })
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
    up_port = _free_port()
    ad_port = _free_port()
    up = _serve(_FakeUpstream, up_port)

    cfg = A.Config()
    cfg.upstream = f"http://127.0.0.1:{up_port}"
    cfg.api_key = "test-key"
    cfg.model = ""          # force /v1/models discovery
    cfg.host = "127.0.0.1"
    cfg.port = ad_port
    A.Handler.cfg = cfg
    adapter = _serve(A.Handler, ad_port)
    base = f"http://127.0.0.1:{ad_port}"
    _wait(base + "/healthz")

    # 1) healthz reflects discovered model
    with urllib.request.urlopen(base + "/healthz", timeout=5) as r:
        health = json.loads(r.read())
    assert health["status"] == "ok", health
    assert health["model"] == "nufi-local-qwen", health

    # 2) chat translates the MeshBox contract to OpenAI and back
    code, out = _post(base + "/v1/chat",
                      {"message": "안녕", "history": [
                          {"role": "user", "text": "이전"},
                          {"role": "assistant", "text": "네"}]})
    assert code == 200, (code, out)
    assert out["reply"] == "reply to: 안녕", out
    assert out["model"] == "nufi-local-qwen", out

    # 3) missing message -> 400
    code, out = _post(base + "/v1/chat", {"message": "  "})
    assert code == 400, (code, out)

    # 4) empty completion -> honest 502 (never fabricate)
    _FakeUpstream.empty_reply = True
    code, out = _post(base + "/v1/chat", {"message": "x"})
    assert code == 502, (code, out)
    _FakeUpstream.empty_reply = False

    adapter.shutdown()
    up.shutdown()
    print("PASS: nufi_chat_adapter contract translation + honest-boundary")


if __name__ == "__main__":
    main()
