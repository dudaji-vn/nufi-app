#!/usr/bin/env python3
"""The registrar against a fake box: chat, console, Works and LiteLLM on one
http.server. What is asserted is the calls it makes, in the shape the real
services answer -- and that a second run makes none of the ones that create.

Run:  python3 deploy/box/works/test_register_works.py     (exit 0 = PASS)
"""
import http.server
import json
import os
import pathlib
import subprocess
import sys
import threading
import urllib.parse

HERE = pathlib.Path(__file__).resolve().parent
SCRIPT = HERE / "register_works.py"
ADMIN = "admin@nufi.local"
PLUGIN = "@nufi/plugin-docker-sandbox"


def fresh_state():
    return {
        "calls": [],
        "claimed_by": None,           # None | "me" | "other"
        "plugins": [],                # {id, packageName, status}
        "companies": [],              # {id, name}
        "environments": [{"id": "env-local", "name": "Local", "driver": "local",
                          "status": "active", "config": {}}],
        "default_env": None,
        "keys_minted": 0,
        "plugin_polls": 0,
        "chat_logins": 0,
        "fail_plugin_install": False,
        "sso_error": False,        # True: the OAuth callback lands on /error
    }


class Fake(http.server.BaseHTTPRequestHandler):
    state = fresh_state()

    def log_message(self, *a):
        pass

    # -- helpers --
    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}") if n else {}

    def send(self, code, obj=None, headers=()):
        data = json.dumps(obj if obj is not None else {}).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        for k, v in headers:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def send_html(self, code, html):
        """Works' SPA answers text/html, not JSON -- the shape that crashed
        the registrar's Content-Type-blind json.loads before the fix."""
        data = html.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def cookie(self, name):
        raw = self.headers.get("Cookie") or ""
        for part in raw.split(";"):
            k, _, v = part.strip().partition("=")
            if k == name:
                return v
        return None

    def bearer(self):
        a = self.headers.get("Authorization") or ""
        return a[7:] if a.lower().startswith("bearer ") else None

    def as_admin(self):
        st = Fake.state
        if self.bearer() == "bk-1":
            return st["claimed_by"] == "me"
        if self.cookie("session") == "sess-1":
            return st["claimed_by"] == "me"
        return False

    def record(self):
        Fake.state["calls"].append((self.command, urllib.parse.urlparse(self.path).path))

    # -- routes --
    def do_GET(self):
        self.record()
        st = Fake.state
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        if u.path == "/oidc/authorize":                       # the console
            assert self.cookie("refreshToken") == "rt-1", "no chat session at the console"
            assert q["client_id"] == ["nufi-works"]
            target = q["redirect_uri"][0] + "?code=code-1&state=" + q["state"][0]
            self.send_response(302); self.send_header("Location", target); self.end_headers(); return
        if u.path == "/api/auth/oauth2/callback/nufi":         # Works, the far end of SSO
            if st.get("sso_error"):
                # better-auth renders a 200 error PAGE for a mismatched state
                # rather than a non-200 status -- redirect there, same as the
                # real thing, instead of asserting the happy-path cookies.
                self.send_response(302); self.send_header("Location", "/error?error=state_mismatch"); self.end_headers(); return
            assert self.cookie("better-auth.state") == "st-1", "state cookie did not travel"
            assert q["code"] == ["code-1"]
            self.send_response(302); self.send_header("Set-Cookie", "session=sess-1; Path=/")
            self.send_header("Location", "/"); self.end_headers(); return
        if u.path == "/":                                       # Works' SPA -- HTML, not JSON
            self.send_html(200, "<!doctype html><title>Works</title>"); return
        if u.path == "/error":                                  # better-auth's error page -- HTML too
            self.send_html(200, "<!doctype html><title>Works</title>"); return
        if u.path == "/api/auth/get-session":
            if self.cookie("session") != "sess-1":
                self.send(200, None); return
            self.send(200, {"user": {"email": ADMIN, "id": "u-1"}}); return
        if u.path == "/api/health":
            self.send(200, {"status": "ok"}); return
        if u.path == "/api/cli-auth/me":                       # says isInstanceAdmin outright
            if self.bearer() == "bk-1":
                self.send(200, {"userId": "u-1", "isInstanceAdmin": st["claimed_by"] == "me",
                                "companyIds": [c["id"] for c in st["companies"]], "source": "board_key"}); return
            if self.cookie("session") == "sess-1":
                self.send(200, {"userId": "u-1", "isInstanceAdmin": st["claimed_by"] == "me",
                                "companyIds": [c["id"] for c in st["companies"]], "source": "session"}); return
            self.send(401, {"error": "unauthenticated"}); return
        if u.path == "/api/instance/settings":
            # assertBoardOrgAccess: any company member reads this, not only
            # the instance admin -- the real looseness register_works.py must
            # not use to decide "am I admin" (it asks /api/cli-auth/me for
            # that instead).
            if self.cookie("session") == "sess-1":
                self.send(200, {"defaultEnvironmentId": st["default_env"]}); return
            if not self.as_admin():
                self.send(403, {"error": "Instance admin access required"}); return
            self.send(200, {"defaultEnvironmentId": st["default_env"]}); return
        if u.path == "/api/plugins":
            if not self.bearer() == "bk-1": self.send(401); return
            st["plugin_polls"] += 1
            # The worker takes a moment after install: first listing says
            # installed, the next says ready. The registrar must wait for ready.
            for p in st["plugins"]:
                if p["status"] == "installed" and st["plugin_polls"] > p["installed_at_poll"]:
                    p["status"] = "ready"
            self.send(200, st["plugins"]); return
        if u.path == "/api/companies":
            self.send(200, st["companies"]); return
        if u.path.startswith("/api/companies/") and u.path.endswith("/environments"):
            self.send(200, st["environments"]); return
        self.send(404, {"error": "no route " + u.path})

    def do_POST(self):
        self.record()
        st = Fake.state
        u = urllib.parse.urlparse(self.path)
        b = self.body()
        if u.path == "/api/auth/login":                          # chat
            assert "Mozilla" in (self.headers.get("User-Agent") or ""), "chat needs a browser UA"
            assert b == {"email": ADMIN, "password": "pw-1"}, b
            st["chat_logins"] += 1
            self.send(200, {"user": {"email": ADMIN}}, [("Set-Cookie", "refreshToken=rt-1; Path=/; HttpOnly")]); return
        if u.path == "/api/auth/sign-in/oauth2":                 # Works starts SSO
            assert self.headers.get("Origin") == self.works_origin(), self.headers.get("Origin")
            assert b["providerId"] == "nufi"
            url = (self.works_origin() + "/oidc/authorize?client_id=nufi-works&state=st-1&redirect_uri="
                   + urllib.parse.quote(self.works_origin() + "/api/auth/oauth2/callback/nufi", safe=""))
            self.send(200, {"url": url, "redirect": True}, [("Set-Cookie", "better-auth.state=st-1; Path=/")]); return
        if u.path == "/api/bootstrap/claim":
            assert self.cookie("session") == "sess-1"
            assert self.headers.get("Origin") == self.works_origin()
            if st["claimed_by"] is None:
                st["claimed_by"] = "me"; self.send(200, {"claimed": True}); return
            self.send(409, {"error": "Someone else has already claimed this instance"}); return
        if u.path == "/api/board-api-keys":
            assert self.cookie("session") == "sess-1" and st["claimed_by"] == "me"
            st["keys_minted"] += 1
            self.send(201, {"id": "k-1", "name": b["name"], "token": "bk-1"}); return
        if u.path == "/key/generate":                            # LiteLLM, not Works: master key, no session
            assert self.bearer() == "sk-master", "the virtual key is minted with the master key"
            self.send(200, {"key": "sk-virtual-1"}); return
        if not self.as_admin():
            self.send(403, {"error": "Instance admin required"}); return
        if u.path == "/api/plugins/install":
            if st["fail_plugin_install"]:
                self.send(500, {"error": "the worker is not answering"}); return
            assert b == {"packageName": "/app/packages/plugins/sandbox-providers/docker", "isLocalPath": True}, b
            st["plugins"].append({"id": "p-1", "packageName": PLUGIN, "status": "installed",
                                  "installed_at_poll": st["plugin_polls"]})
            self.send(201, st["plugins"][-1]); return
        if u.path == "/api/companies":
            st["companies"].append({"id": "c-1", "name": b["name"]}); self.send(201, st["companies"][-1]); return
        if u.path == "/api/companies/c-1/environments":
            assert b["driver"] == "sandbox" and b["config"]["provider"] == "docker", b
            env = {"id": "env-docker", "name": b["name"], "driver": "sandbox", "status": "active", "config": b["config"]}
            st["environments"].append(env); self.send(201, env); return
        self.send(404, {"error": "no route " + u.path})

    def do_PATCH(self):
        self.record()
        st = Fake.state
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        b = self.body()
        if not self.as_admin():
            self.send(403); return
        if u.path == "/api/instance/settings":
            st["default_env"] = b["defaultEnvironmentId"]; self.send(200, {"defaultEnvironmentId": st["default_env"]}); return
        if u.path.startswith("/api/environments/"):
            env_id = u.path.rsplit("/", 1)[1]
            if "config" in b:
                # A config PATCH resolves a secret context company and 400s
                # without ?companyId= unless the actor is in exactly one
                # company -- pin that the registrar always sends it.
                assert "companyId" in q, ("companyId missing from a config PATCH", self.path)
            (env,) = [e for e in st["environments"] if e["id"] == env_id]
            env.update(b); self.send(200, env); return
        self.send(404)

    def works_origin(self):
        return "http://127.0.0.1:%d" % self.server.server_address[1]


def serve():
    srv = http.server.HTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, "http://127.0.0.1:%d" % srv.server_address[1]


def run(base, **env_extra):
    env = {k: v for k, v in os.environ.items() if not k.startswith("WORKS_") and k not in ("ADMIN_PASSWORD", "LITELLM_MASTER_KEY")}
    env.update({"ADMIN_PASSWORD": "pw-1", "LITELLM_MASTER_KEY": "sk-master"})
    env.update(env_extra)
    return subprocess.run([sys.executable, str(SCRIPT), "--works", base, "--chat", base, "--litellm", base,
                           "--login", ADMIN, "--company", "nufi", "--image", "ghcr.io/dudaji-vn/nufi-sandbox@sha256:" + "0" * 64],
                          env=env, capture_output=True, text=True, timeout=60)


def keys(stdout):
    return dict(l.split("=", 1) for l in stdout.splitlines() if l and l[0].isupper() and "=" in l)


def test_first_run_signs_in_as_the_admin_claims_and_registers_everything():
    Fake.state = fresh_state()
    srv, base = serve()
    try:
        r = run(base)
        assert r.returncode == 0, r.stderr
        assert "Traceback" not in r.stderr, r.stderr
        st = Fake.state
        assert st["chat_logins"] == 1, "signed in to chat once, with the admin's password"
        assert st["claimed_by"] == "me", "the admin's SSO session claimed first admin"
        assert keys(r.stdout) == {"WORKS_BOX_KEY": "bk-1", "WORKS_MODEL_KEY": "sk-virtual-1"}, r.stdout
        assert [p["packageName"] for p in st["plugins"]] == [PLUGIN]
        assert st["plugins"][0]["status"] == "ready", "waited for the worker"
        assert [c["name"] for c in st["companies"]] == ["nufi"]
        docker = [e for e in st["environments"] if e["driver"] == "sandbox"]
        assert len(docker) == 1 and docker[0]["config"]["image"].startswith("ghcr.io/dudaji-vn/nufi-sandbox@sha256:")
        assert st["default_env"] == "env-docker", "the docker environment is the instance default"
        local = [e for e in st["environments"] if e["driver"] == "local"][0]
        assert local["status"] == "archived", "upstream's Local -- plain Docker, no gVisor -- is archived"
        print("PASS: first run signs in as the admin, claims, installs, registers, pins, archives Local")
    finally:
        srv.shutdown()


def test_second_run_with_the_keys_creates_nothing_and_never_signs_in():
    Fake.state = fresh_state()
    srv, base = serve()
    try:
        first = run(base)
        assert first.returncode == 0, first.stderr
        Fake.state["calls"].clear()
        r = run(base, WORKS_BOX_KEY="bk-1", WORKS_MODEL_KEY="sk-virtual-1")
        assert r.returncode == 0, r.stderr
        writes = [c for c in Fake.state["calls"] if c[0] in ("POST", "PATCH")]
        assert writes == [], writes
        assert Fake.state["chat_logins"] == 1, "a working box key means no second sign-in"
        assert keys(r.stdout) == {}, "nothing minted, nothing printed"
        print("PASS: a second run is reads only")
    finally:
        srv.shutdown()


def test_an_instance_claimed_by_someone_else_is_named_not_worked_around():
    Fake.state = fresh_state()
    Fake.state["claimed_by"] = "other"
    # The admin also happens to be a member of the existing company -- which
    # is exactly the case /api/instance/settings alone would get wrong: that
    # route answers 200 to any company member (assertBoardOrgAccess), not
    # only an instance admin. The fake mirrors that looseness here so this
    # test would fail if the registrar were still asking it "am I admin".
    Fake.state["companies"] = [{"id": "c-1", "name": "nufi"}]
    srv, base = serve()
    try:
        r = run(base)
        assert r.returncode == 3, (r.returncode, r.stderr)
        assert "claimed" in r.stderr and "promote" in r.stderr, r.stderr
        assert not [c for c in Fake.state["calls"] if c[1] in ("/api/plugins/install", "/api/companies") and c[0] == "POST"]
        print("PASS: someone else's instance is reported with the fix, not taken over")
    finally:
        srv.shutdown()


def test_a_minted_key_is_printed_before_a_later_step_can_fail():
    """A board key is minted the moment first admin is claimed; if the next
    step -- installing the provider plugin -- then fails, the key must not be
    lost. It is only good on Works, and a run that dies without printing it
    leaves an orphan key nothing on this side has a record of."""
    Fake.state = fresh_state()
    Fake.state["fail_plugin_install"] = True
    srv, base = serve()
    try:
        r = run(base)
        assert r.returncode == 1, (r.returncode, r.stderr)
        assert "WORKS_BOX_KEY=bk-1" in r.stdout, r.stdout
        print("PASS: a minted key is printed before a later step can fail")
    finally:
        srv.shutdown()


def test_a_new_image_digest_repins_the_existing_environment():
    Fake.state = fresh_state()
    Fake.state["companies"] = [{"id": "c-1", "name": "nufi"}]
    Fake.state["environments"].append({"id": "env-docker", "name": "Box sandboxes", "driver": "sandbox",
                                       "status": "active", "config": {"provider": "docker", "image": "ghcr.io/dudaji-vn/nufi-sandbox@sha256:" + "f" * 64}})
    Fake.state["plugins"] = [{"id": "p-1", "packageName": PLUGIN, "status": "ready", "installed_at_poll": 0}]
    Fake.state["claimed_by"] = "me"
    Fake.state["default_env"] = "env-docker"
    srv, base = serve()
    try:
        r = run(base, WORKS_BOX_KEY="bk-1", WORKS_MODEL_KEY="x")
        assert r.returncode == 0, r.stderr
        (env,) = [e for e in Fake.state["environments"] if e["driver"] == "sandbox"]
        assert env["config"]["image"].endswith("0" * 64), env
        posts = [c for c in Fake.state["calls"] if c[0] == "POST"]
        assert posts == [], posts
        print("PASS: an installer that pulled a new digest re-pins the environment in place")
    finally:
        srv.shutdown()


def test_check_mode_reads_only_and_says_what_is_missing():
    Fake.state = fresh_state()
    Fake.state["claimed_by"] = "me"
    Fake.state["companies"] = [{"id": "c-1", "name": "nufi"}]
    srv, base = serve()
    try:
        env = dict(os.environ, WORKS_BOX_KEY="bk-1")
        r = subprocess.run([sys.executable, str(SCRIPT), "--works", base, "--check", "--image", "x@sha256:" + "0" * 64],
                           env=env, capture_output=True, text=True, timeout=60)
        assert r.returncode == 1, (r.returncode, r.stderr)
        for missing in ("plugin", "default", "Local"):
            assert missing in r.stderr, (missing, r.stderr)
        assert not [c for c in Fake.state["calls"] if c[0] != "GET"]
        print("PASS: --check is reads only and names each missing piece")
    finally:
        srv.shutdown()


def test_check_mode_passes_after_a_first_run():
    """The negative test above proves --check complains; this proves it stops
    complaining once `install` has actually run, and catches a re-pin."""
    Fake.state = fresh_state()
    srv, base = serve()
    try:
        first = run(base)
        assert first.returncode == 0, first.stderr
        image = "ghcr.io/dudaji-vn/nufi-sandbox@sha256:" + "0" * 64
        env = dict(os.environ, WORKS_BOX_KEY="bk-1")
        r = subprocess.run([sys.executable, str(SCRIPT), "--works", base, "--check", "--image", image],
                           env=env, capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, r.stderr
        assert "missing:" not in r.stderr, r.stderr
        other_image = "ghcr.io/dudaji-vn/nufi-sandbox@sha256:" + "1" * 64
        r2 = subprocess.run([sys.executable, str(SCRIPT), "--works", base, "--check", "--image", other_image],
                            env=env, capture_output=True, text=True, timeout=60)
        assert r2.returncode == 1, (r2.returncode, r2.stderr)
        assert "pinned" in r2.stderr, r2.stderr
        print("PASS: --check passes after a first run, and catches a re-pinned image")
    finally:
        srv.shutdown()


def test_a_better_auth_error_page_is_named_not_parsed():
    """The Critical this round fixed: the SSO callback can land on an HTML
    error page instead of the JSON the old code assumed everywhere. This must
    become a named, one-line failure -- not a JSONDecodeError traceback."""
    Fake.state = fresh_state()
    Fake.state["sso_error"] = True
    srv, base = serve()
    try:
        r = run(base)
        assert r.returncode == 1, (r.returncode, r.stderr)
        assert "state_mismatch" in r.stderr, r.stderr
        assert "Traceback" not in r.stderr, r.stderr
        print("PASS: better-auth's error page is named, not parsed as JSON")
    finally:
        srv.shutdown()


if __name__ == "__main__":
    test_first_run_signs_in_as_the_admin_claims_and_registers_everything()
    test_second_run_with_the_keys_creates_nothing_and_never_signs_in()
    test_an_instance_claimed_by_someone_else_is_named_not_worked_around()
    test_a_minted_key_is_printed_before_a_later_step_can_fail()
    test_a_new_image_digest_repins_the_existing_environment()
    test_check_mode_reads_only_and_says_what_is_missing()
    test_check_mode_passes_after_a_first_run()
    test_a_better_auth_error_page_is_named_not_parsed()
