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
    # the headscale node name must match NAME, or `nufi-box revoke alice`
    # has nothing to resolve — the laptop's OS hostname is not "alice".
    assert "--hostname=alice" in content
    # headscale v0.29.3 rejects a pre-auth-key registration that carries
    # RequestTags, regardless of tagOwners — tag:member must come only from
    # the pre-auth key's own aclTags (asserted above), never a login flag.
    # (Check the actual login invocation, not the whole file, so the
    # explanatory comment next to it — which necessarily names the flag —
    # can't make this assertion pass or fail on its own wording.)
    login_line = next(l for l in content.splitlines() if "--hostname=" in l)
    assert "--advertise-tags" not in login_line


def test_invite_windows_uses_certutil_and_net_use(tmp_path, fake_headscale):
    envf, data_dir = make_env(tmp_path, fake_headscale)
    r = cli("invite", "bob2", "--os", "windows", env={"NUFI_BOX_ENV": str(envf)})
    assert r.returncode == 0, r.stdout + r.stderr
    content = (data_dir / "invites" / "nufi-join-bob2.cmd").read_text()
    assert "certutil" in content
    assert "net use Z:" in content
    assert ca_b64(data_dir) in content
    assert "--hostname=bob2" in content
    login_line = next(l for l in content.splitlines() if "--hostname=" in l)
    assert "--advertise-tags" not in login_line  # see the macOS test for why


def test_invite_linux_uses_update_ca_certificates(tmp_path, fake_headscale):
    envf, data_dir = make_env(tmp_path, fake_headscale)
    r = cli("invite", "carol", "--os", "linux", env={"NUFI_BOX_ENV": str(envf)})
    assert r.returncode == 0, r.stdout + r.stderr
    content = (data_dir / "invites" / "nufi-join-carol.sh").read_text()
    assert "update-ca-certificates" in content
    assert ca_b64(data_dir) in content
    assert "--hostname=carol" in content
    login_line = next(l for l in content.splitlines() if "--hostname=" in l)
    assert "--advertise-tags" not in login_line  # see the macOS test for why


def test_invite_windows_drive_letters_do_not_run_off_the_alphabet(tmp_path, fake_headscale):
    depts = ",".join("dept%d" % i for i in range(28))  # more than 26 drives
    envf, data_dir = make_env(tmp_path, fake_headscale, DEPARTMENTS=depts)
    r = cli("invite", "hank", "--os", "windows", env={"NUFI_BOX_ENV": str(envf)})
    assert r.returncode == 0, r.stdout + r.stderr
    content = (data_dir / "invites" / "nufi-join-hank.cmd").read_text()
    assert "net use Z:" in content
    # the 27th and 28th drives can't get a unique letter; must not render a
    # broken "net use : ..." line -- a clear fallback instead.
    assert "net use : " not in content
    assert "Too many drives" in content


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


def test_revoke_with_an_ambiguous_name_refuses_and_names_both_ids(tmp_path, fake_headscale):
    """Two laptops can legitimately report the same node name (headscale
    keeps `givenName` precisely because raw hostnames collide) -- revoke
    must never guess which one to delete."""
    fake_headscale.nodes = [
        {"id": "5", "name": "dup", "ipAddresses": ["100.64.0.9"], "online": True,
         "lastSeen": "2026-09-08T00:00:00Z", "user": {"name": "box"}},
        {"id": "6", "name": "dup", "ipAddresses": ["100.64.0.10"], "online": True,
         "lastSeen": "2026-09-08T00:00:00Z", "user": {"name": "box"}},
    ]
    envf, _ = make_env(tmp_path, fake_headscale)
    r = cli("revoke", "dup", env={"NUFI_BOX_ENV": str(envf)})
    assert r.returncode != 0
    assert "5" in r.stderr
    assert "6" in r.stderr
    assert "--id" in r.stderr
    deletes = [req for req in fake_headscale.requests if req[0] == "DELETE"]
    assert deletes == [], "an ambiguous name must not delete anything"


def test_revoke_by_id_deletes_directly_without_resolving_a_name(tmp_path, fake_headscale):
    envf, _ = make_env(tmp_path, fake_headscale)
    r = cli("revoke", "--id", "2", env={"NUFI_BOX_ENV": str(envf)})
    assert r.returncode == 0, r.stdout + r.stderr
    deletes = [req for req in fake_headscale.requests if req[0] == "DELETE"]
    assert deletes == [("DELETE", "/api/v1/node/2")]
    # --id must not even fetch the node list to resolve a name
    gets = [req for req in fake_headscale.requests if req[0] == "GET"]
    assert gets == []


def test_revoke_id_requires_a_value(tmp_path, fake_headscale):
    envf, _ = make_env(tmp_path, fake_headscale)
    r = cli("revoke", "--id", env={"NUFI_BOX_ENV": str(envf)})
    assert r.returncode == 2


# --- help ------------------------------------------------------------------

def test_help_lists_the_mesh_verbs():
    r = cli("--help")
    assert r.returncode == 0
    for verb in ("invite", "members", "revoke"):
        assert verb in r.stdout


# --- Task 6: a coordinator on its own CA (MESH_CA_FILE) ----------------------


@pytest.fixture
def fake_headscale_tls(tmp_path_factory):
    """The same fake behind HTTPS with a self-signed certificate — the shape of
    the Docker lab and of a dev coordinator on TLS_MODE=internal, where the
    box has to be told which CA to trust."""
    import ssl

    d = tmp_path_factory.mktemp("hs-tls")
    key, crt = d / "server.key", d / "server.crt"
    gen = subprocess.run(
        ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
         "-keyout", str(key), "-out", str(crt), "-subj", "/CN=localhost",
         "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1"],
        capture_output=True, text=True)
    if gen.returncode != 0:
        pytest.skip("openssl cannot make a self-signed certificate here")

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    server.valid_key = "k"
    server.users = [{"id": "1", "name": "box"}]
    server.nodes = [{"id": "1", "name": "bob", "ipAddresses": ["100.64.0.5"],
                     "online": True, "lastSeen": "2026-09-08T00:00:00Z",
                     "user": {"name": "box"}}]
    server.preauth_key = "test-preauth-key-abc123"
    server.requests = []
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(str(crt), str(key))
    server.socket = ctx.wrap_socket(server.socket, server_side=True)
    server.ca_file = crt
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_members_trusts_the_coordinators_own_ca_when_mesh_ca_file_names_it(tmp_path, fake_headscale_tls):
    envf, _ = make_env(tmp_path, fake_headscale_tls,
                       MESH_SERVER_URL="https://localhost:%d" % fake_headscale_tls.server_port,
                       MESH_CA_FILE=str(fake_headscale_tls.ca_file))
    r = cli("members", env={"NUFI_BOX_ENV": str(envf)})
    assert r.returncode == 0, r.stderr
    assert "bob" in r.stdout


def test_members_against_an_untrusted_coordinator_fails_loudly(tmp_path, fake_headscale_tls):
    """Without MESH_CA_FILE the same call must not quietly succeed: the box
    would be talking to a coordinator it cannot authenticate."""
    envf, _ = make_env(tmp_path, fake_headscale_tls,
                       MESH_SERVER_URL="https://localhost:%d" % fake_headscale_tls.server_port)
    r = cli("members", env={"NUFI_BOX_ENV": str(envf)})
    assert r.returncode != 0
    assert "bob" not in r.stdout


def test_a_mesh_ca_file_that_is_not_there_is_ignored_not_fatal(tmp_path, fake_headscale):
    """The default value names the host's system bundle, which does not exist
    on macOS — that must not stop a plain HTTP or public-CA coordinator."""
    envf, _ = make_env(tmp_path, fake_headscale,
                       MESH_CA_FILE="/etc/ssl/certs/ca-certificates.crt")
    r = cli("members", env={"NUFI_BOX_ENV": str(envf)})
    assert r.returncode == 0, r.stderr
    assert "bob" in r.stdout


# --- secrets never reach argv ------------------------------------------------
#
# lib/flows.sh:12-15 states the rule and cites THIS file as its precedent, and
# `test_flows_install_never_puts_the_key_in_an_argument` pins the flows half.
# These two are the mesh half, and they are not hypothetical: both keys used to
# be handed to python3 as arguments — the coordinator API key to build curl's
# config file, the freshly minted pre-auth key to render the join file. On
# Linux /proc/<pid>/cmdline is world-readable, so any local user polling `ps`
# during `nufi-box invite` or `members` read a credential that lists and
# deletes every node on the coordinator.


def argv_recorder(tmp_path):
    """A `python3` on PATH that records the argv it is handed, then execs the
    real one — what lands in argv is exactly what `ps` shows another user."""
    import sys
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    log = tmp_path / "python3.argv"
    shim = bin_ / "python3"
    shim.write_text('#!/bin/sh\nprintf \'%s\\n\' "$@" >> "{log}"\nexec {py} "$@"\n'
                    .format(log=log, py=sys.executable))
    shim.chmod(0o755)
    return bin_, log


def test_the_coordinator_api_key_never_reaches_argv(tmp_path, fake_headscale):
    secret = "hs-api-key-that-must-not-reach-ps"
    fake_headscale.valid_key = secret
    bin_, log = argv_recorder(tmp_path)
    envf, _ = make_env(tmp_path, fake_headscale, MESH_API_KEY=secret)
    r = cli("members", env={"NUFI_BOX_ENV": str(envf),
                            "PATH": "%s:%s" % (bin_, os.environ["PATH"])})
    assert r.returncode == 0, r.stdout + r.stderr
    assert "bob" in r.stdout, "the call still has to work with the key in the environment"
    assert log.exists(), "the recording shim was never used — check PATH"
    assert secret not in log.read_text()


def test_the_minted_preauth_key_never_reaches_argv(tmp_path, fake_headscale):
    secret = "tskey-auth-that-must-not-reach-ps"
    fake_headscale.preauth_key = secret
    bin_, log = argv_recorder(tmp_path)
    envf, data_dir = make_env(tmp_path, fake_headscale)
    r = cli("invite", "alice", "--os", "macos",
            env={"NUFI_BOX_ENV": str(envf), "PATH": "%s:%s" % (bin_, os.environ["PATH"])})
    assert r.returncode == 0, r.stdout + r.stderr
    # It reached the join file, which is the only place it belongs...
    assert secret in (data_dir / "invites" / "nufi-join-alice.command").read_text()
    # ...and no argument on the way there.
    assert log.exists(), "the recording shim was never used — check PATH"
    assert secret not in log.read_text()


def test_a_join_file_is_never_rendered_without_a_key(tmp_path):
    """The renderer takes @AUTH_KEY@ from the environment, so an unset one has
    to be fatal: a join file with an empty key is a file that cannot work and
    does not say why."""
    script = (
        'set -e\nHERE=%s\n. "$HERE/lib/mesh.sh"\n'
        'mesh_render_template "$HERE/lib/join-templates/linux.sh" %s MEMBER=x\n'
        % (BOX, tmp_path / "join.sh")
    )
    e = dict(os.environ)
    e.pop("MESH_JOIN_AUTH_KEY", None)
    r = subprocess.run(["/bin/bash", "-c", script], capture_output=True, text=True, env=e)
    assert r.returncode != 0
    assert "MESH_JOIN_AUTH_KEY" in r.stderr
    assert not (tmp_path / "join.sh").exists()
