#!/usr/bin/env python3
"""Egress guard unit test for the MeshBox⇄nufi-app chat adapter (CMP-511 W4).

Two layers, no Docker / no deps:

  * pure EgressGuard logic — audit never raises; enforce denies a public upstream
    (403) but allows loopback / private / mesh / allow-listed targets.
  * adapter integration — an enforcing adapter pointed at a PUBLIC upstream
    refuses POST /v1/chat with 403 BEFORE any network dial (member data never
    leaves the mesh); the same adapter in audit mode does not block on policy.

Run:  python3 test_egress.py     (exit 0 = PASS)
"""
import json
import socket
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import nufi_chat_adapter as A
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
    allow = E.EgressGuard(mode=E.MODE_ENFORCE, mesh_cidrs=["192.168.99.0/24"],
                          allow_hosts=["trusted.partner"], mesh_domain="mesh")
    for url in ("http://127.0.0.1:4000", "http://localhost:4000",
                "http://192.168.99.5:4000", "http://10.0.0.9",
                "http://nufichat.mesh/v1", "http://trusted.partner/v1"):
        # loopback / private / mesh / allow-listed => allowed, never raises
        assert allow.classify(url)["allowed"] is True, url
        allow.check(url)  # no raise

    for url in ("https://evil.example.com/v1", "http://8.8.8.8/v1",
                "http://api.openai.com/v1/chat/completions"):
        assert allow.classify(url)["allowed"] is False, url
        try:
            allow.check(url)
            raise AssertionError(f"enforce did not raise for {url}")
        except E.EgressError as ex:
            assert ex.code == 403

    # audit records but NEVER raises
    audit = E.EgressGuard(mode=E.MODE_AUDIT)
    d = audit.check("https://evil.example.com/v1")
    assert d["allowed"] is False and d["enforcing"] is False

    # bad mode rejected
    try:
        E.EgressGuard(mode="whatever")
        raise AssertionError("bad mode accepted")
    except ValueError:
        pass

    # from_env parsing
    g = E.from_env({"NUFI_EGRESS_MODE": "enforce",
                    "NUFI_EGRESS_ALLOW": "a.host, b.host",
                    "NUFI_MESH_CIDR": "192.168.50.0/24"})
    assert g.enforcing is True
    assert g.classify("http://a.host/x")["allowed"] is True
    assert g.classify("http://192.168.50.9/x")["allowed"] is True
    # unknown mode falls back to audit (never crashes the adapter)
    assert E.from_env({"NUFI_EGRESS_MODE": "nonsense"}).mode == E.MODE_AUDIT
    print("  [ok] pure EgressGuard: enforce denies public / allows mesh; audit no-raise")


def _boot_adapter(mode, upstream):
    cfg = A.Config()
    cfg.upstream = upstream
    cfg.api_key = "test-key"
    cfg.model = "m"          # skip /v1/models discovery
    cfg.host = "127.0.0.1"
    cfg.port = _free_port()
    cfg.egress = E.EgressGuard(mode=mode)
    A.Handler.cfg = cfg
    httpd = ThreadingHTTPServer(("127.0.0.1", cfg.port), A.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{cfg.port}"
    for _ in range(50):
        try:
            urllib.request.urlopen(base + "/healthz", timeout=0.5)
            break
        except Exception:
            time.sleep(0.05)
    return base, httpd


def test_adapter_enforce_refuses_public_upstream():
    # enforce + a PUBLIC upstream -> 403, and the target is never dialed.
    base, httpd = _boot_adapter(E.MODE_ENFORCE, "https://evil.example.com")
    code, out = _post(base + "/v1/chat", {"message": "leak this"})
    assert code == 403, (code, out)
    assert "egress denied" in out.get("error", ""), out
    httpd.shutdown()
    print("  [ok] enforce mode refuses forwarding chat to an off-mesh upstream (403)")

    # audit + same public upstream -> policy does NOT block (it tries to dial and
    # fails with an honest 502; the point is: not a 403 policy block).
    base, httpd = _boot_adapter(E.MODE_AUDIT, "http://off-mesh.invalid:9")
    code, out = _post(base + "/v1/chat", {"message": "hi"})
    assert code != 403, (code, out)
    httpd.shutdown()
    print("  [ok] audit mode does not block on policy (backward compatible)")


def main():
    print("== test_egress :: nufi-chat adapter egress guard (#6) ==")
    test_pure_guard()
    test_adapter_enforce_refuses_public_upstream()
    print("PASS: nufi_chat_adapter egress enforcement")


if __name__ == "__main__":
    main()
