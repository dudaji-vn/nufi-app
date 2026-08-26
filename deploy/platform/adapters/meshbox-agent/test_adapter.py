#!/usr/bin/env python3
"""Stdlib unit test for the MeshBox⇄nufi-app agent adapter (no Docker, no deps).

Stands up a fake nufi-agent (Langflow-shaped run API + health) and drives the
adapter through its MeshBox contract (/healthz, /v1/run), asserting:

  * flow mode: routine -> flow run, nested Langflow output normalized to {status,output}
  * clean mode: plain {status,output} upstream passed through
  * honest boundary: errored run -> 502, empty output -> 502, unwired routine -> 502
  * missing routine_id -> 400

Run:  python3 test_adapter.py     (exit 0 = PASS)
"""
import json
import socket
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import nufi_agent_adapter as A


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class _FakeAgent(BaseHTTPRequestHandler):
    """Stand-in for nufi-agent. Serves Langflow-shaped run output by default."""
    mode = "flow"     # "flow" (nested Langflow) | "clean" | "error" | "empty"
    last_path = None

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
        if self.path == "/health_check":
            return self._json(200, {"status": "ok"})
        return self._json(404, {"error": "nope"})

    def do_POST(self):
        _FakeAgent.last_path = self.path
        n = int(self.headers.get("Content-Length", 0) or 0)
        _ = self.rfile.read(n)
        if _FakeAgent.mode == "clean":
            return self._json(200, {"status": "completed",
                                    "output": "메일 5건 요약 완료"})
        if _FakeAgent.mode == "error":
            return self._json(200, {"outputs": [], "status": "error",
                                    "message": "flow build failed"})
        if _FakeAgent.mode == "empty":
            return self._json(200, {"outputs": [{"outputs": [{"results": {}}]}]})
        # default: Langflow nested success shape
        return self._json(200, {"outputs": [{"outputs": [
            {"results": {"message": {
                "text": "회의록 요약: 액션아이템 3건 정리했습니다."}}}]}]})


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


def _make_cfg(agent_port, ad_port, **over):
    cfg = A.Config()
    cfg.agent_url = f"http://127.0.0.1:{agent_port}"
    cfg.api_key = "test-key"
    cfg.host = "127.0.0.1"
    cfg.port = ad_port
    cfg.default_flow = over.get("default_flow", "flow-abc")
    cfg.flow_map = over.get("flow_map", {"r2": "flow-minutes"})
    cfg.run_path = over.get("run_path", "/api/v1/run")
    return cfg


def main():
    agent_port = _free_port()
    agent = _serve(_FakeAgent, agent_port)

    # ---- flow mode --------------------------------------------------------
    ad_port = _free_port()
    A.Handler.cfg = _make_cfg(agent_port, ad_port)
    adapter = _serve(A.Handler, ad_port)
    base = f"http://127.0.0.1:{ad_port}"
    _wait(base + "/healthz")

    # 1) healthz reports flow mode + reachable backend
    with urllib.request.urlopen(base + "/healthz", timeout=5) as r:
        health = json.loads(r.read())
    assert health["status"] == "ok" and health["mode"] == "flow", health

    # 2) mapped routine hits the mapped flow; nested output normalized
    _FakeAgent.mode = "flow"
    code, out = _post(base + "/v1/run", {"routine_id": "r2",
                                         "routine": "회의록 요약·액션아이템"})
    assert code == 200, (code, out)
    assert out["status"] == "completed", out
    assert "액션아이템" in out["output"], out
    assert _FakeAgent.last_path == "/api/v1/run/flow-minutes", _FakeAgent.last_path

    # 3) unmapped routine falls back to default flow
    _post(base + "/v1/run", {"routine_id": "r9", "routine": "기타"})
    assert _FakeAgent.last_path == "/api/v1/run/flow-abc", _FakeAgent.last_path

    # 4) missing routine_id -> 400
    assert _post(base + "/v1/run", {"routine": "x"})[0] == 400

    # 5) errored run -> honest 502
    _FakeAgent.mode = "error"
    assert _post(base + "/v1/run", {"routine_id": "r2", "routine": "x"})[0] == 502

    # 6) empty output -> honest 502 (never fabricate a "completed")
    _FakeAgent.mode = "empty"
    assert _post(base + "/v1/run", {"routine_id": "r2", "routine": "x"})[0] == 502

    adapter.shutdown()

    # ---- clean mode -------------------------------------------------------
    _FakeAgent.mode = "clean"
    ad_port2 = _free_port()
    A.Handler.cfg = _make_cfg(agent_port, ad_port2, default_flow="",
                              flow_map={}, run_path="/v1/run")
    adapter2 = _serve(A.Handler, ad_port2)
    base2 = f"http://127.0.0.1:{ad_port2}"
    _wait(base2 + "/healthz")
    with urllib.request.urlopen(base2 + "/healthz", timeout=5) as r:
        assert json.loads(r.read())["mode"] == "clean"
    code, out = _post(base2 + "/v1/run", {"routine_id": "r3", "routine": "메일 요약"})
    assert code == 200 and out["output"] == "메일 5건 요약 완료", (code, out)
    assert _FakeAgent.last_path == "/v1/run", _FakeAgent.last_path

    adapter2.shutdown()

    # ---- unwired routine (no flow, default run path, no key) -> 502 -------
    ad_port3 = _free_port()
    cfg3 = _make_cfg(agent_port, ad_port3, default_flow="", flow_map={})
    cfg3.api_key = ""      # no clean endpoint, default run path -> unwired
    A.Handler.cfg = cfg3
    adapter3 = _serve(A.Handler, ad_port3)
    base3 = f"http://127.0.0.1:{ad_port3}"
    _wait(base3 + "/healthz")
    assert _post(base3 + "/v1/run", {"routine_id": "r5", "routine": "x"})[0] == 502
    adapter3.shutdown()

    agent.shutdown()
    print("PASS: nufi_agent_adapter flow+clean modes + honest-boundary")


if __name__ == "__main__":
    main()
