#!/usr/bin/env python3
"""Egress guard unit test for the MeshBox⇄nufi-app agent adapter (CMP-511 W4).

Mirrors the chat adapter's egress test: pure EgressGuard logic plus an adapter
integration check that an enforcing agent adapter pointed at a PUBLIC nufi-agent
upstream refuses POST /v1/run with 403 before any network dial.

Run:  python3 test_egress.py     (exit 0 = PASS)
"""
import json
import socket
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import nufi_agent_adapter as A
import nufi_egress as E


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _post(url, obj):
    req = urllib.request.Request(
        url, data=json.dumps(obj).encode(), method="POST",
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_pure_guard():
    g = E.EgressGuard(mode=E.MODE_ENFORCE, mesh_cidrs=["192.168.99.0/24"],
                      mesh_domain="mesh")
    assert g.classify("http://nufi-agent:7860")["allowed"] is False  # bare name
    for url in ("http://127.0.0.1:7860", "http://192.168.99.7:7860",
                "http://agent.mesh/api"):
        assert g.classify(url)["allowed"] is True, url
        g.check(url)
    try:
        g.check("https://exfil.example.com/api/v1/run/flow")
        raise AssertionError("enforce did not raise for public agent")
    except E.EgressError as ex:
        assert ex.code == 403
    # audit never raises
    assert E.EgressGuard(mode=E.MODE_AUDIT).check(
        "https://exfil.example.com")["enforcing"] is False
    print("  [ok] pure EgressGuard: enforce denies public agent / allows mesh")


def test_adapter_enforce_refuses_public_agent():
    cfg = A.Config()
    cfg.agent_url = "https://exfil.example.com"
    cfg.api_key = "test-key"
    cfg.default_flow = "flow-abc"
    cfg.host = "127.0.0.1"
    cfg.port = _free_port()
    cfg.timeout = 2.0            # keep the (doomed) off-mesh dial fast
    cfg.egress = E.EgressGuard(mode=E.MODE_ENFORCE)
    A.Handler.cfg = cfg
    httpd = ThreadingHTTPServer(("127.0.0.1", cfg.port), A.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{cfg.port}"
    for _ in range(50):
        try:
            # healthz dials the (public) upstream and 502s; ANY HTTP response
            # means the adapter socket is up and ready for the /v1/run check.
            urllib.request.urlopen(base + "/healthz", timeout=2)
            break
        except urllib.error.HTTPError:
            break
        except Exception:
            time.sleep(0.05)
    code, out = _post(base + "/v1/run", {"routine_id": "r1", "routine": "meeting-notes"})
    assert code == 403, (code, out)
    assert "egress denied" in out.get("error", ""), out
    httpd.shutdown()
    print("  [ok] enforce mode refuses running a routine against an off-mesh agent (403)")


def main():
    print("== test_egress :: nufi-agent adapter egress guard (#6) ==")
    test_pure_guard()
    test_adapter_enforce_refuses_public_agent()
    print("PASS: nufi_agent_adapter egress enforcement")


if __name__ == "__main__":
    main()
