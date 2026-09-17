#!/usr/bin/env python3
"""Register the box's Docker sandbox environment in NUFI Works.

Runs inside the box network (`nufi-box works install` starts it with
`docker compose run`), where the box's name resolves to Caddy and the box's CA
is on the volume. Stdlib only.

How it gets to be an instance admin without a human step: it signs in AS THE
BOX ADMIN through the same door a browser takes -- the chat login, then the
console's /oidc/authorize, then Works' OAuth callback -- and that session
claims first admin (Works is in private exposure) and mints one board API key.
Every later run uses the key and never signs in again. There is no service
account and no database write, and the admin's own browser lands on the same
account, because it is the same identity.

Exit codes: 0 registered (or already so); 1 a step failed (the response is on
stderr); 3 the instance was claimed by someone else -- say who to promote.

Secrets arrive in the environment, never in an argument:
  ADMIN_PASSWORD, LITELLM_MASTER_KEY, and the two this script may mint and
  prints back on stdout as KEY=VALUE for the caller to keep: WORKS_BOX_KEY,
  WORKS_MODEL_KEY.
"""
import argparse
import http.cookiejar
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

PLUGIN_PACKAGE = "@nufi/plugin-docker-sandbox"
PLUGIN_PATH = "/app/packages/plugins/sandbox-providers/docker"
ENV_NAME = "Box sandboxes"
ENV_DESC = "Every run on this box: a gVisor container on the works-sandbox network, behind the egress proxy."
# LibreChat's user-agent parser rejects unknown callers; the ingest daemon
# carries the same disguise for the same reason.
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


def say(msg):
    print("works: " + msg, file=sys.stderr, flush=True)


class Box:
    def __init__(self, works, cacert):
        self.works = works.rstrip("/")
        self.jar = http.cookiejar.CookieJar()
        handlers = [urllib.request.HTTPCookieProcessor(self.jar)]
        if cacert:
            handlers.append(urllib.request.HTTPSHandler(context=ssl.create_default_context(cafile=cacert)))
        self.opener = urllib.request.build_opener(*handlers)
        self.token = None
        self.last_url = None

    def call(self, method, url, body=None, token=None, origin=False, ua=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Accept", "application/json")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        if token or self.token:
            req.add_header("Authorization", "Bearer " + (token or self.token))
        if origin:
            # better-auth and the board-mutation guard check Origin on a
            # session-authenticated POST; a bearer key needs none.
            req.add_header("Origin", self.works)
        req.add_header("User-Agent", ua or "nufi-box/register_works")
        self.last_url = url
        try:
            with self.opener.open(req, timeout=60) as r:
                self.last_url = r.geturl()
                raw = r.read()
                # Only a JSON body is ever ours to parse. The SSO round trip
                # can land on Works' own SPA (its index.html, or an error
                # page) -- text/html, 200 -- and json.loads on that is an
                # uncaught traceback on every fresh box, not a status a
                # caller can react to.
                if "json" in r.headers.get("Content-Type", ""):
                    return r.status, (json.loads(raw) if raw.strip() else None)
                return r.status, raw.decode(errors="replace")
        except urllib.error.HTTPError as e:
            self.last_url = e.geturl() if hasattr(e, "geturl") else url
            raw = e.read()
            if "json" in (e.headers.get("Content-Type", "") if e.headers is not None else ""):
                try:
                    return e.code, json.loads(raw)
                except ValueError:
                    return e.code, raw.decode(errors="replace")
            return e.code, raw.decode(errors="replace")
        except urllib.error.URLError as e:
            # Connection refused, TLS failure, DNS -- not an HTTP status, and
            # a traceback here is not something an installer's stderr should
            # ever have to be read past.
            say("%s %s: %s" % (method, url, e.reason))
            sys.exit(1)

    def must(self, method, path, body=None, ok=(200, 201), **kw):
        status, out = self.call(method, self.works + path, body, **kw)
        if status not in ok:
            say("%s %s -> %s %s" % (method, path, status, json.dumps(out)[:400] if not isinstance(out, str) else out[:400]))
            sys.exit(1)
        return out


def sign_in_as_admin(box, chat, login, password):
    """The browser's path, without the browser."""
    status, out = box.call("POST", chat.rstrip("/") + "/api/auth/login", {"email": login, "password": password}, ua=UA)
    if status != 200:
        say("chat login as %s failed: %s %s" % (login, status, out)); sys.exit(1)
    out = box.must("POST", "/api/auth/sign-in/oauth2", {"providerId": "nufi", "callbackURL": "/"}, origin=True)
    url = out.get("url") if isinstance(out, dict) else None
    if not url:
        say("Works did not return an SSO redirect: %s" % json.dumps(out)[:300]); sys.exit(1)
    # Console -> code -> Works callback -> session cookie; urllib follows the
    # redirects and the jar carries the chat cookie, the state and the session.
    status, _ = box.call("GET", url)
    if status != 200:
        say("the SSO round trip ended with %s (is the console's OIDC_CLIENTS carrying nufi-works, and PAPERCLIP_PUBLIC_URL the name the box announces?)" % status)
        sys.exit(1)
    # better-auth renders a 200 error PAGE for some failures (a mismatched
    # state, a provider it does not recognize) rather than a non-200 status,
    # so the status check above passes and the only tell is the URL urllib
    # actually landed on.
    landed = urllib.parse.urlparse(box.last_url or "")
    if landed.path.endswith("/error"):
        say("Works refused the sign-in: %s" % (landed.query or "(no details)"))
        sys.exit(1)
    session = box.must("GET", "/api/auth/get-session")
    email = ((session or {}).get("user") or {}).get("email", "")
    if email.lower() != login.lower():
        say("signed in as %r, expected %s" % (email, login)); sys.exit(1)
    say("signed in to Works as %s through the console" % login)


def claim_or_confirm(box):
    status, out = box.call("POST", box.works + "/api/bootstrap/claim", {}, origin=True)
    if status == 200:
        say("claimed instance admin")
    elif status != 409:
        say("bootstrap claim -> %s %s" % (status, out)); sys.exit(1)
    # Not /api/instance/settings: that answers 200 to any company member
    # (assertBoardOrgAccess), so a box admin someone else later added to a
    # company would sail through this check and only fail, confusingly, at
    # plugin install. /api/cli-auth/me says isInstanceAdmin outright.
    status, out = box.call("GET", box.works + "/api/cli-auth/me")
    if status != 200 or not (out or {}).get("isInstanceAdmin"):
        say("this Works instance was claimed by someone else, and %s is not an instance admin." % "the box admin")
        say("In Works: Instance access -> promote the box admin to instance admin, then run: nufi-box works install")
        sys.exit(3)


def stored_key_works(box, existing):
    """A key from an earlier run means no sign-in at all this time."""
    if not existing:
        return False
    status, out = box.call("GET", box.works + "/api/cli-auth/me", token=existing)
    if status == 200 and (out or {}).get("isInstanceAdmin"):
        box.token = existing
        return True
    say("the stored WORKS_BOX_KEY no longer works; signing in to mint a new one")
    return False


def mint_key(box):
    """Needs the admin's session (a bearer key cannot mint another)."""
    out = box.must("POST", "/api/board-api-keys", {"name": "nufi-box"}, origin=True)
    box.token = out["token"]
    say("minted a board API key for the box")
    return out["token"]


def plugin_ready(box, path, wait_s=90):
    def find():
        for p in box.must("GET", "/api/plugins"):
            if p.get("packageName") == PLUGIN_PACKAGE and p.get("status") != "uninstalled":
                return p
        return None
    p = find()
    if p is None:
        status, out = box.call("POST", box.works + "/api/plugins/install", {"packageName": path, "isLocalPath": True})
        if status not in (200, 201):
            text = out if isinstance(out, str) else json.dumps(out or {})
            if status == 400 and "manifest" in text.lower():
                # Upstream's own message names a path nobody on this side can
                # act on. The box's own image is the thing to fix: an older
                # `nufi-box works install` (before the provider was built into
                # it) leaves a Works image with no manifest at PLUGIN_PATH.
                say("the Works image on this box predates the sandbox provider (no built manifest at %s); "
                    "pull the current image: docker compose pull works && nufi-box works install" % path)
            else:
                say("POST /api/plugins/install -> %s %s" % (status, text[:400]))
            sys.exit(1)
        say("installed the Docker sandbox provider from %s" % path)
    deadline = time.time() + wait_s
    while True:
        p = find()
        if p and p.get("status") == "ready":
            return p
        if p and p.get("status") == "error":
            say("the provider plugin is in error -- check: nufi-box logs works"); sys.exit(1)
        if time.time() > deadline:
            say("the provider plugin is %s, not ready, after %ss -- check: nufi-box logs works" % (p and p.get("status"), wait_s))
            sys.exit(1)
        time.sleep(2)


def company(box, name):
    companies = box.must("GET", "/api/companies")
    if companies:
        return companies[0]
    c = box.must("POST", "/api/companies", {"name": name})
    say("created the company %r; the box admin is its owner" % name)
    return c


def environment(box, company_id, image):
    envs = box.must("GET", "/api/companies/%s/environments" % company_id)
    docker = [e for e in envs if e.get("driver") == "sandbox" and (e.get("config") or {}).get("provider") == "docker"]
    if docker:
        env = docker[0]
        if (env.get("config") or {}).get("image") != image:
            cfg = dict(env.get("config") or {}); cfg["image"] = image
            # A config PATCH resolves a secret context company and 400s
            # ("requires a companyId context") unless the actor is in exactly
            # one company; the box admin usually is, but say which one rather
            # than lean on that.
            env = box.must("PATCH", "/api/environments/%s?companyId=%s" % (env["id"], company_id), {"config": cfg})
            say("re-pinned the sandbox image to %s" % image)
    else:
        env = box.must("POST", "/api/companies/%s/environments" % company_id, {
            "name": ENV_NAME, "description": ENV_DESC, "driver": "sandbox",
            "config": {"provider": "docker", "image": image}})
        say("registered the Docker sandbox environment (%s)" % image)
    settings = box.must("GET", "/api/instance/settings")
    if settings.get("defaultEnvironmentId") != env["id"]:
        box.must("PATCH", "/api/instance/settings", {"defaultEnvironmentId": env["id"]})
        say("made it the instance default")
    for e in envs:
        if e.get("driver") == "local" and e.get("status") == "active":
            # No config body here, so no companyId context to resolve -- but
            # the query does no harm, and it is one less thing to remember if
            # this PATCH ever grows a config field.
            box.must("PATCH", "/api/environments/%s?companyId=%s" % (e["id"], company_id), {"status": "archived"})
            say("archived %r: it would run agent code inside the works container under plain Docker" % e.get("name"))
    return env


def model_key(box, litellm, existing, master):
    if existing:
        return None
    if not master:
        say("no LITELLM_MASTER_KEY in the environment; cannot mint the model key"); sys.exit(1)
    status, out = box.call("POST", litellm.rstrip("/") + "/key/generate",
                           {"key_alias": "works-box-%d" % int(time.time()), "metadata": {"box": "works"}}, token=master)
    if status != 200 or not isinstance(out, dict) or not out.get("key"):
        say("LiteLLM /key/generate -> %s %s" % (status, out)); sys.exit(1)
    say("minted a LiteLLM virtual key for Works; the master key never reaches a sandbox")
    return out["key"]


def check(box, image):
    """Reads only. Exit 0 when the box is registered as `install` leaves it."""
    box.token = os.environ.get("WORKS_BOX_KEY") or None
    if not box.token:
        say("no WORKS_BOX_KEY -- run: nufi-box works install"); sys.exit(1)
    missing = []
    plugins = box.must("GET", "/api/plugins")
    if not any(p.get("packageName") == PLUGIN_PACKAGE and p.get("status") == "ready" for p in plugins):
        missing.append("the Docker sandbox provider plugin is not ready")
    companies = box.must("GET", "/api/companies")
    if not companies:
        missing.append("no company yet (works install creates the box's)")
    envs = box.must("GET", "/api/companies/%s/environments" % companies[0]["id"]) if companies else []
    settings = box.must("GET", "/api/instance/settings")
    default = next((e for e in envs if e.get("id") == settings.get("defaultEnvironmentId")), None)
    if not default or (default.get("config") or {}).get("provider") != "docker":
        missing.append("the instance default environment is not the Docker sandbox one")
    elif image and (default.get("config") or {}).get("image") != image:
        missing.append("the default environment's image is not the pinned %s" % image)
    if any(e.get("driver") == "local" and e.get("status") == "active" for e in envs):
        missing.append("upstream's Local environment is still active")
    for m in missing:
        say("missing: " + m)
    sys.exit(1 if missing else 0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--works", required=True)
    ap.add_argument("--chat")
    ap.add_argument("--litellm")
    ap.add_argument("--cacert")
    ap.add_argument("--login")
    ap.add_argument("--company", default="nufi")
    ap.add_argument("--image", required=True)
    ap.add_argument("--plugin-path", default=PLUGIN_PATH)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    box = Box(a.works, a.cacert)
    if a.check:
        check(box, a.image)
    # Printed the moment each exists, not batched at the end: a later step
    # (the plugin install, the environment registration) can still fail, and
    # a key minted just before that and never handed back is an orphan on
    # Works with nothing on this side to show for it. `minted` is kept only
    # for the closing summary line, not to decide what reaches stdout.
    minted = {}
    if not stored_key_works(box, os.environ.get("WORKS_BOX_KEY") or None):
        if not (a.chat and a.login and os.environ.get("ADMIN_PASSWORD")):
            say("no working WORKS_BOX_KEY and no way to sign in (--chat, --login, ADMIN_PASSWORD)"); sys.exit(1)
        sign_in_as_admin(box, a.chat, a.login, os.environ["ADMIN_PASSWORD"])
        claim_or_confirm(box)
        minted["WORKS_BOX_KEY"] = mint_key(box)
        print("WORKS_BOX_KEY=%s" % minted["WORKS_BOX_KEY"], flush=True)
    plugin_ready(box, a.plugin_path)
    c = company(box, a.company)
    environment(box, c["id"], a.image)
    if a.litellm:
        mk = model_key(box, a.litellm, os.environ.get("WORKS_MODEL_KEY"), os.environ.get("LITELLM_MASTER_KEY"))
        if mk:
            minted["WORKS_MODEL_KEY"] = mk
            print("WORKS_MODEL_KEY=%s" % mk, flush=True)
    if minted:
        say("minted: " + ", ".join(minted))
    say("registered")


if __name__ == "__main__":
    main()
