#!/usr/bin/env python3
"""Stdlib test for the adapter's identity federation (CMP-509, no deps, no Docker).

Stands up two fakes and drives the REAL adapter between them:

  - a fake nufi-app Console `/oidc/userinfo` that "verifies" a token and returns
    its subject (mirrors the real console, which does the RS256/JWKS check), and
  - a fake litellm `/v1/chat/completions` that RECORDS the litellm key and the
    `user` field of every request it receives (the audit trail).

Then it sends chat turns carrying different members' identities and asserts each
turn reached litellm under that member's own virtual key + `user` — i.e. the
per-user audit trail is preserved end to end. It also asserts the honest
boundary: a required-but-missing identity is refused (401), and a tampered
audience is refused before the console is even asked.

Run:  python3 test_federation.py     (exit 0 = PASS)
"""
import base64
import json
import socket
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import nufi_chat_adapter as A


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _mk_token(sub, aud="nufi-chat", email=None):
    """A JWT-shaped opaque token our fake console recognises (not RS256-real).

    The adapter only base64-decodes the payload locally to check `aud`; real
    signature verification is delegated to the console, which here is the fake.
    """
    header = base64.urlsafe_b64encode(b'{"alg":"RS256"}').rstrip(b"=").decode()
    claims = {"sub": sub, "aud": aud, "email": email or sub}
    payload = base64.urlsafe_b64encode(
        json.dumps(claims).encode()).rstrip(b"=").decode()
    return f"{header}.{payload}.sig-{sub}"


# Members the fake console will vouch for, and the token each one presents.
_MEMBERS = {
    _mk_token("alice@dept.local"): {"sub": "alice@dept.local",
                                    "email": "alice@dept.local",
                                    "access": "editor"},
    _mk_token("bob@dept.local"): {"sub": "bob@dept.local",
                                  "email": "bob@dept.local",
                                  "access": "viewer"},
}

# What litellm recorded: list of {"key", "user"} in arrival order.
_AUDIT = []


class _FakeConsole(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path == "/oidc/userinfo":
            auth = self.headers.get("Authorization", "")
            token = auth[7:] if auth.startswith("Bearer ") else ""
            member = _MEMBERS.get(token)
            if not member:
                return self._json(401, {"error": "invalid_token"})
            return self._json(200, member)
        return self._json(404, {"error": "nope"})

    def _json(self, code, obj):
        raw = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


class _FakeLitellm(BaseHTTPRequestHandler):
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
            return self._json(200, {"data": [{"id": "nufi-local"}]})
        return self._json(404, {"error": "nope"})

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        body = json.loads(self.rfile.read(n) or "{}")
        if self.path == "/v1/chat/completions":
            auth = self.headers.get("Authorization", "")
            key = auth[7:] if auth.startswith("Bearer ") else ""
            _AUDIT.append({"key": key, "user": body.get("user"),
                           "actor_hdr": self.headers.get("X-MeshBox-Actor")})
            last = body["messages"][-1]["content"]
            return self._json(200, {"model": "nufi-local", "choices": [
                {"message": {"role": "assistant", "content": f"ok: {last}"}}]})
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


def _chat(adapter_url, message, identity_token=None):
    headers = {"Content-Type": "application/json"}
    if identity_token:
        headers["X-MeshBox-Identity"] = identity_token
    req = urllib.request.Request(
        adapter_url + "/v1/chat", data=json.dumps({"message": message}).encode(),
        method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def main():
    con_port, lit_port, ad_port = _free_port(), _free_port(), _free_port()
    con = _serve(_FakeConsole, con_port)
    lit = _serve(_FakeLitellm, lit_port)

    cfg = A.Config()
    cfg.upstream = f"http://127.0.0.1:{lit_port}"
    cfg.api_key = "sk-default"
    cfg.model = ""
    cfg.host = "127.0.0.1"
    cfg.port = ad_port
    cfg.console_url = f"http://127.0.0.1:{con_port}"
    cfg.fed_aud = "nufi-chat"
    cfg.fed_required = True
    cfg.keymap = {"alice@dept.local": "sk-alice", "bob@dept.local": "sk-bob"}
    A.Handler.cfg = cfg
    adapter = _serve(A.Handler, ad_port)
    base = f"http://127.0.0.1:{ad_port}"
    _wait(base + "/healthz")

    alice = _mk_token("alice@dept.local")
    bob = _mk_token("bob@dept.local")

    # 1) alice's turn is attributed to alice's virtual key + user
    code, out = _chat(base, "회의록 요약", alice)
    assert code == 200, (code, out)
    # 2) bob's turn, then alice again — interleaved members must not bleed
    assert _chat(base, "규정 확인", bob)[0] == 200
    assert _chat(base, "다시 요약", alice)[0] == 200

    assert len(_AUDIT) == 3, _AUDIT
    assert _AUDIT[0] == {"key": "sk-alice", "user": "alice@dept.local",
                         "actor_hdr": "alice@dept.local"}, _AUDIT[0]
    assert _AUDIT[1] == {"key": "sk-bob", "user": "bob@dept.local",
                         "actor_hdr": "bob@dept.local"}, _AUDIT[1]
    assert _AUDIT[2]["user"] == "alice@dept.local", _AUDIT[2]

    # 3) honest boundary: required identity missing -> 401, nothing forwarded
    before = len(_AUDIT)
    code, out = _chat(base, "익명 요청")
    assert code == 401, (code, out)
    assert len(_AUDIT) == before, "an unidentified request must not reach litellm"

    # 4) tampered audience -> refused locally (before the console is asked)
    wrong_aud = _mk_token("mallory@dept.local", aud="some-other-app")
    code, out = _chat(base, "권한 없는 청중", wrong_aud)
    assert code == 401, (code, out)
    assert "audience" in out.get("error", ""), out

    adapter.shutdown()
    lit.shutdown()
    con.shutdown()
    print("PASS: adapter identity federation — per-user audit + honest boundary")


if __name__ == "__main__":
    main()
