"""`nufi-box invite | members | revoke` against a stdlib fake headscale API.

The fake speaks just enough of headscale v0.29.3's REST surface
(gen/openapiv2/headscale/v1/headscale.swagger.json, confirmed live) for
lib/mesh.sh to drive: GET /api/v1/user?name=... (resolve the box's headscale
user to its numeric id — CreatePreAuthKeyRequest.user is a uint64, not the
username, despite the plan brief's literal `{"user":"box",...}`), POST
/api/v1/preauthkey, GET /api/v1/node, DELETE /api/v1/node/{id}.
"""
import base64
import http.server
import json
import os
import pathlib
import subprocess
import threading
import urllib.parse

import pytest

BOX = pathlib.Path(__file__).resolve().parents[1]


class Handler(http.server.BaseHTTPRequestHandler):
    def _authorized(self):
        return self.headers.get("Authorization") == "Bearer %s" % self.server.valid_key

    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not self._authorized():
            return self._json(401, {"message": "unauthorized"})
        path, _, query = self.path.partition("?")
        self.server.requests.append(("GET", self.path))
        if path == "/api/v1/user":
            qs = urllib.parse.parse_qs(query)
            name = (qs.get("name") or [None])[0]
            users = [u for u in self.server.users if not name or u["name"] == name]
            return self._json(200, {"users": users})
        if path == "/api/v1/node":
            return self._json(200, {"nodes": self.server.nodes})
        self._json(404, {"message": "not found"})

    def do_POST(self):
        if not self._authorized():
            return self._json(401, {"message": "unauthorized"})
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        body = json.loads(raw) if raw else {}
        self.server.requests.append(("POST", self.path, body, dict(self.headers)))
        if self.path == "/api/v1/preauthkey":
            return self._json(200, {"preAuthKey": {
                "id": "9",
                "key": self.server.preauth_key,
                "user": self.server.users[0],
                "reusable": body.get("reusable"),
                "ephemeral": body.get("ephemeral"),
                "expiration": body.get("expiration"),
                "aclTags": body.get("aclTags"),
            }})
        self._json(404, {"message": "not found"})

    def do_DELETE(self):
        if not self._authorized():
            return self._json(401, {"message": "unauthorized"})
        self.server.requests.append(("DELETE", self.path))
        if self.path.startswith("/api/v1/node/"):
            return self._json(200, {})
        self._json(404, {"message": "not found"})

    def log_message(self, *_a, **_k):
        pass  # keep test output quiet


@pytest.fixture
def fake_headscale():
    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    server.valid_key = "k"
    server.users = [{"id": "1", "name": "box"}]
    server.nodes = [
        {"id": "1", "name": "bob", "ipAddresses": ["100.64.0.5"], "online": True,
         "lastSeen": "2026-09-08T00:00:00Z", "user": {"name": "box"}},
        {"id": "2", "name": "alice", "ipAddresses": ["100.64.0.6"], "online": False,
         "lastSeen": "2026-09-07T00:00:00Z", "user": {"name": "box"}},
    ]
    server.preauth_key = "test-preauth-key-abc123"
    server.requests = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def cli(*args, env=None, cwd=None):
    e = dict(os.environ)
    e.pop("NUFI_BOX_DRY_RUN", None)
    if env:
        e.update(env)
    return subprocess.run(
        ["/bin/bash", str(BOX / "nufi-box"), *args],
        cwd=str(cwd or BOX), env=e, capture_output=True, text=True,
    )


def make_env(tmp_path, server, **overrides):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "nufi-box-ca.crt").write_bytes(
        b"-----BEGIN CERTIFICATE-----\nFAKECAFAKECAFAKECA==\n-----END CERTIFICATE-----\n"
    )
    values = {
        "NUFI_DATA_DIR": str(data_dir),
        "BOX_NAME": "nufi",
        "MESH_SERVER_URL": "http://127.0.0.1:%d" % server.server_port,
        "MESH_API_KEY": "k",
        "BOX_MESH_HOST": "nufi.box.lab",
        "DEPARTMENTS": "legal,hr",
    }
    values.update(overrides)
    envf = tmp_path / ".env"
    envf.write_text("".join("%s=%s\n" % (k, v) for k, v in values.items()))
    return envf, data_dir


def ca_b64(data_dir):
    return base64.b64encode((data_dir / "nufi-box-ca.crt").read_bytes()).decode()


# --- invite ------------------------------------------------------------

def test_invite_macos_posts_preauthkey_and_writes_the_join_file(tmp_path, fake_headscale):
    envf, data_dir = make_env(tmp_path, fake_headscale)
    r = cli("invite", "alice", "--os", "macos", "--drives", "legal,hr", env={"NUFI_BOX_ENV": str(envf)})
    assert r.returncode == 0, r.stdout + r.stderr

    posts = [req for req in fake_headscale.requests if req[0] == "POST"]
    assert len(posts) == 1
    _, path, body, headers = posts[0]
    assert path == "/api/v1/preauthkey"
    assert headers.get("Authorization") == "Bearer k"
    # confirmed against headscale v0.29.3's swagger: user is a numeric id
    # (uint64-as-string), resolved from the headscale user "box" — not the
    # literal string "box".
    assert body["user"] == "1"
    assert body["reusable"] is False
    assert body["ephemeral"] is False
    assert body["aclTags"] == ["tag:member"]
    assert "expiration" in body and body["expiration"].endswith("Z")

    # the "box" user must have been resolved by name first
    gets = [req for req in fake_headscale.requests if req[0] == "GET"]
    assert any(g[1].startswith("/api/v1/user") for g in gets)

    out_file = data_dir / "invites" / "nufi-join-alice.command"
    assert out_file.exists()
    mode = oct(out_file.stat().st_mode)[-3:]
    assert mode == "600", mode
    content = out_file.read_text()
    assert fake_headscale.preauth_key in content
    assert ca_b64(data_dir) in content
    assert "/Applications/Tailscale.app/Contents/MacOS/Tailscale" in content
    assert "smb://nufi.box.lab/legal" in content
    assert "smb://nufi.box.lab/hr" in content
    assert "https://nufi.box.lab:3080" in content
    assert "single-use" in content


def test_invite_windows_uses_certutil_and_net_use(tmp_path, fake_headscale):
    envf, data_dir = make_env(tmp_path, fake_headscale)
    r = cli("invite", "bob2", "--os", "windows", env={"NUFI_BOX_ENV": str(envf)})
    assert r.returncode == 0, r.stdout + r.stderr
    content = (data_dir / "invites" / "nufi-join-bob2.cmd").read_text()
    assert "certutil" in content
    assert "net use Z:" in content
    assert ca_b64(data_dir) in content


def test_invite_linux_uses_update_ca_certificates(tmp_path, fake_headscale):
    envf, data_dir = make_env(tmp_path, fake_headscale)
    r = cli("invite", "carol", "--os", "linux", env={"NUFI_BOX_ENV": str(envf)})
    assert r.returncode == 0, r.stdout + r.stderr
    content = (data_dir / "invites" / "nufi-join-carol.sh").read_text()
    assert "update-ca-certificates" in content
    assert ca_b64(data_dir) in content


def test_invite_defaults_to_macos_and_all_departments(tmp_path, fake_headscale):
    envf, data_dir = make_env(tmp_path, fake_headscale, DEPARTMENTS="legal,hr,ga")
    r = cli("invite", "dana", env={"NUFI_BOX_ENV": str(envf)})
    assert r.returncode == 0, r.stdout + r.stderr
    content = (data_dir / "invites" / "nufi-join-dana.command").read_text()
    for dept in ("legal", "hr", "ga"):
        assert "smb://nufi.box.lab/%s" % dept in content


def test_invite_prints_the_path_and_a_sentence_to_send(tmp_path, fake_headscale):
    envf, data_dir = make_env(tmp_path, fake_headscale)
    r = cli("invite", "erin", "--os", "macos", env={"NUFI_BOX_ENV": str(envf)})
    assert r.returncode == 0, r.stderr
    assert str(data_dir / "invites" / "nufi-join-erin.command") in r.stdout
    assert "erin" in r.stdout


def test_invite_without_box_mesh_host_dies_with_the_hint(tmp_path, fake_headscale):
    envf, _ = make_env(tmp_path, fake_headscale, BOX_MESH_HOST="")
    r = cli("invite", "frank", "--os", "macos", env={"NUFI_BOX_ENV": str(envf)})
    assert r.returncode == 2, r.stdout + r.stderr
    assert "nufi-box mesh up" in r.stderr


def test_invite_with_bad_api_key_exits_3_naming_mesh_api_key(tmp_path, fake_headscale):
    envf, _ = make_env(tmp_path, fake_headscale, MESH_API_KEY="wrong")
    r = cli("invite", "grace", "--os", "macos", env={"NUFI_BOX_ENV": str(envf)})
    assert r.returncode == 3, r.stdout + r.stderr
    assert "MESH_API_KEY" in r.stderr


def test_invite_rejects_an_unknown_os(tmp_path, fake_headscale):
    envf, _ = make_env(tmp_path, fake_headscale)
    r = cli("invite", "henry", "--os", "plan9", env={"NUFI_BOX_ENV": str(envf)})
    assert r.returncode == 2
    assert "--os" in r.stderr


def test_invite_requires_a_name(tmp_path, fake_headscale):
    envf, _ = make_env(tmp_path, fake_headscale)
    r = cli("invite", env={"NUFI_BOX_ENV": str(envf)})
    assert r.returncode == 2


# --- members -------------------------------------------------------------

def test_members_renders_the_fakes_two_nodes(tmp_path, fake_headscale):
    envf, _ = make_env(tmp_path, fake_headscale)
    r = cli("members", env={"NUFI_BOX_ENV": str(envf)})
    assert r.returncode == 0, r.stdout + r.stderr
    assert "bob" in r.stdout
    assert "alice" in r.stdout
    assert "100.64.0.5" in r.stdout
    assert "100.64.0.6" in r.stdout


def test_members_with_bad_api_key_exits_3(tmp_path, fake_headscale):
    envf, _ = make_env(tmp_path, fake_headscale, MESH_API_KEY="wrong")
    r = cli("members", env={"NUFI_BOX_ENV": str(envf)})
    assert r.returncode == 3, r.stdout + r.stderr
    assert "MESH_API_KEY" in r.stderr


# --- revoke ----------------------------------------------------------------

def test_revoke_resolves_the_name_and_deletes_the_node(tmp_path, fake_headscale):
    envf, _ = make_env(tmp_path, fake_headscale)
    r = cli("revoke", "alice", env={"NUFI_BOX_ENV": str(envf)})
    assert r.returncode == 0, r.stdout + r.stderr
    deletes = [req for req in fake_headscale.requests if req[0] == "DELETE"]
    assert deletes == [("DELETE", "/api/v1/node/2")]
    assert "alice" in r.stdout


def test_revoke_unknown_name_fails_cleanly(tmp_path, fake_headscale):
    envf, _ = make_env(tmp_path, fake_headscale)
    r = cli("revoke", "nobody", env={"NUFI_BOX_ENV": str(envf)})
    assert r.returncode != 0
    assert "nobody" in r.stderr
    deletes = [req for req in fake_headscale.requests if req[0] == "DELETE"]
    assert deletes == []


def test_revoke_requires_a_name(tmp_path, fake_headscale):
    envf, _ = make_env(tmp_path, fake_headscale)
    r = cli("revoke", env={"NUFI_BOX_ENV": str(envf)})
    assert r.returncode == 2


# --- help ------------------------------------------------------------------

def test_help_lists_the_mesh_verbs():
    r = cli("--help")
    assert r.returncode == 0
    for verb in ("invite", "members", "revoke"):
        assert verb in r.stdout
