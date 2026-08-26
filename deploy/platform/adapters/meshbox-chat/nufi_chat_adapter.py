#!/usr/bin/env python3
"""MeshBox ⇄ nufi-app Chat adapter — the wiring for feasibility gap #1 (CMP-505).

MeshBox (appliance) `portal/ai.py` is a pure forwarding gateway: for a chat turn
it POSTs ``{"message", "history"}`` to ``$MESHBOX_CHAT_URL/v1/chat`` and expects
``{"reply", "model"}`` back (see appliance portal/ai.py :138-157). nufi-app does
NOT speak that contract — its real Chat inference is an OpenAI-compatible endpoint
(litellm-proxy on :4000/v1, the very endpoint LibreChat's custom endpoint drives,
see deploy/platform/librechat.yaml). This adapter is the thin shim between the two.

    laptop ──mesh──▶ MeshBox portal/ai.py ──/v1/chat──▶ [THIS ADAPTER] ──▶
                     nufi-app litellm-proxy /v1/chat/completions ──▶ model

It is deliberately stdlib-only (no deps, ~tiny image) to mirror MeshBox's portal
principle and keep the appliance footprint small. It translates in BOTH directions
and never fabricates: if the upstream returns no usable content it answers 502, so
MeshBox's honest-boundary (`AiError(..., 502)`) surfaces a real failure as a real
failure — matching portal/ai.py's own contract.

Contract exposed to MeshBox
---------------------------
  GET  /healthz            -> 200 {"status":"ok","upstream":..,"model":..}
                              502 {"status":"error","detail":..} if upstream down
  POST /v1/chat            body  {"message": str, "history": [{"role","text"}...]}
                           -> 200 {"reply": str, "model": str}
                              502 {"error": str}  (upstream unreachable / empty)
                              400 {"error": str}  (missing message)

Identity federation (CMP-509 / gap #6)
--------------------------------------
The MeshBox portal carries an authenticated member's identity to this adapter as
a nufi-app **Console-signed** identity token (RS256, minted by the console's
/oidc/federated-token grant). The adapter reads it from ``X-MeshBox-Identity``
(or ``Authorization: Bearer``), checks the token audience locally, then confirms
its authenticity by calling the console's ``/oidc/userinfo`` — the console owns
the signing key, so verification stays there and this adapter keeps NO crypto
dependency. The verified subject is then mapped to a **per-user litellm virtual
key** (``NUFI_LITELLM_KEYMAP``) and stamped onto the OpenAI request as ``user`` +
``metadata`` + ``X-MeshBox-Actor``, so litellm attributes the call to the real
member and the audit trail is preserved instead of collapsing to one master key.

Honest boundary: with ``NUFI_FEDERATION_REQUIRED=1`` a request that carries no
valid identity is refused (401) rather than served anonymously — the adapter
never impersonates. Left off (default) it stays backward compatible with the
CMP-505 PoC path that sends no identity.

Config (env)
------------
  NUFI_UPSTREAM_URL      base URL of nufi-app OpenAI-compatible chat
                         (default http://litellm-proxy:4000)
  NUFI_UPSTREAM_API_KEY  bearer key (litellm master/virtual key). Also accepts
                         LITELLM_MASTER_KEY for drop-in use in the platform compose.
  NUFI_MODEL             model name to request. If unset, the adapter fetches
                         /v1/models and uses the first one it advertises.
  NUFI_SYSTEM_PROMPT     optional system message prepended to every conversation.
  ADAPTER_HOST           bind address (default 0.0.0.0)
  ADAPTER_PORT           bind port    (default 8900)
  NUFI_UPSTREAM_TIMEOUT  upstream request timeout seconds (default 30)
  NUFI_CONSOLE_URL       nufi-app Console base URL used to verify a federated
                         identity token (default http://console:3000).
  NUFI_FEDERATION_AUD    audience the identity token must carry (default
                         nufi-chat). Checked locally before the console call.
  NUFI_FEDERATION_REQUIRED  "1" to refuse requests without a valid identity
                         (default "0" = serve anonymously, PoC-compatible).
  NUFI_LITELLM_KEYMAP    JSON object mapping a verified subject to a litellm
                         virtual key, e.g. {"alice@x":"sk-alice"}. A subject not
                         in the map falls back to NUFI_UPSTREAM_API_KEY.

Run
---
  python3 nufi_chat_adapter.py            # serves on 0.0.0.0:8900
"""
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import nufi_egress


def _env(*names, default=""):
    for n in names:
        v = os.environ.get(n)
        if v:
            return v
    return default


class Config:
    def __init__(self):
        self.upstream = _env("NUFI_UPSTREAM_URL",
                             default="http://litellm-proxy:4000").rstrip("/")
        self.api_key = _env("NUFI_UPSTREAM_API_KEY", "LITELLM_MASTER_KEY")
        self.model = os.environ.get("NUFI_MODEL", "").strip()
        self.system_prompt = os.environ.get("NUFI_SYSTEM_PROMPT", "").strip()
        self.host = os.environ.get("ADAPTER_HOST", "0.0.0.0")
        self.port = int(os.environ.get("ADAPTER_PORT", "8900"))
        self.timeout = float(os.environ.get("NUFI_UPSTREAM_TIMEOUT", "30"))
        # --- identity federation (CMP-509) ---
        self.console_url = _env("NUFI_CONSOLE_URL",
                                default="http://console:3000").rstrip("/")
        self.fed_aud = os.environ.get("NUFI_FEDERATION_AUD", "nufi-chat").strip()
        self.fed_required = _env("NUFI_FEDERATION_REQUIRED", default="0").lower() \
            in ("1", "true", "yes", "on")
        try:
            self.keymap = json.loads(_env("NUFI_LITELLM_KEYMAP", default="") or "{}")
            if not isinstance(self.keymap, dict):
                self.keymap = {}
        except json.JSONDecodeError:
            # A malformed map disables per-user keys rather than crashing the
            # adapter; every subject then falls back to the default key.
            self.keymap = {}
        # --- egress guard (CMP-511 W4): refuse to dial an off-mesh upstream ---
        self.egress = nufi_egress.from_env()


class UpstreamError(Exception):
    """Upstream (nufi-app chat) failed. Always mapped to HTTP 502 downstream."""


class IdentityError(Exception):
    """A federated identity token was missing, malformed or not authentic.

    Mapped to HTTP 401 downstream when identity is required — the adapter refuses
    rather than serving an unattributable request under a shared key.
    """


def _upstream_request(cfg, path, payload=None, method="GET", api_key=None,
                      extra_headers=None):
    """Call the nufi-app OpenAI-compatible chat API; return parsed JSON.

    Any transport/HTTP/JSON failure becomes UpstreamError so we can answer the
    MeshBox gateway with an honest 502 rather than a fabricated reply.

    ``api_key`` overrides the default litellm key for this call (per-user virtual
    key); ``extra_headers`` carries the actor attribution stamped on the request.
    """
    url = cfg.upstream + path
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Accept", "application/json")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    key = api_key if api_key is not None else cfg.api_key
    if key:
        req.add_header("Authorization", "Bearer " + key)
    for name, value in (extra_headers or {}).items():
        if value:
            req.add_header(name, value)
    try:
        with urllib.request.urlopen(req, timeout=cfg.timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8")[:300]
        except Exception:
            pass
        raise UpstreamError(f"upstream HTTP {exc.code}: {body}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise UpstreamError(
            f"upstream unreachable: {getattr(exc, 'reason', exc)}") from exc
    except json.JSONDecodeError as exc:
        raise UpstreamError(f"upstream returned non-JSON: {exc}") from exc


def _jwt_claims_unverified(token):
    """Base64url-decode a JWT payload WITHOUT verifying the signature.

    Used only for a fail-fast audience check; authenticity is established
    separately by the console (see verify_identity). Never trust a value read
    here to *grant* access.
    """
    try:
        payload_b64 = token.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        return json.loads(base64.urlsafe_b64decode(payload_b64))
    except (IndexError, ValueError, json.JSONDecodeError):
        return {}


# Short-lived cache of verified tokens so a burst of turns from one member does
# not hit the console on every request. Keyed by the raw token; value is
# (claims, expiry_epoch).
_IDENTITY_CACHE = {}
_IDENTITY_CACHE_TTL = 60


def verify_identity(cfg, token, now=None):
    """Verify a federated identity token; return {sub, email, access}.

    1. Local audience check (cheap, unverified) — a token minted for another
       resource is rejected before any network call.
    2. Authenticity + canonical claims from the console's /oidc/userinfo, which
       holds the signing key and checks the RS256 signature, issuer and expiry.

    Raises IdentityError on any problem.
    """
    if not token:
        raise IdentityError("no identity token")
    now = int(now if now is not None else time.time())
    cached = _IDENTITY_CACHE.get(token)
    if cached and cached[1] > now:
        return cached[0]

    if cfg.fed_aud:
        aud = _jwt_claims_unverified(token).get("aud")
        auds = aud if isinstance(aud, list) else [aud]
        if cfg.fed_aud not in auds:
            raise IdentityError(f"audience mismatch (want {cfg.fed_aud})")

    req = urllib.request.Request(
        cfg.console_url + "/oidc/userinfo",
        headers={"Authorization": "Bearer " + token, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=cfg.timeout) as resp:
            info = json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        raise IdentityError(f"console rejected token (HTTP {exc.code})") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise IdentityError(
            f"console unreachable: {getattr(exc, 'reason', exc)}") from exc
    except json.JSONDecodeError as exc:
        raise IdentityError(f"console returned non-JSON: {exc}") from exc

    sub = info.get("sub")
    if not sub:
        raise IdentityError("console returned no subject")
    identity = {"sub": sub, "email": info.get("email"),
                "access": info.get("access")}
    _IDENTITY_CACHE[token] = (identity, now + _IDENTITY_CACHE_TTL)
    return identity


def key_for(cfg, identity):
    """Per-user litellm virtual key for a verified subject, else the default."""
    if identity:
        mapped = cfg.keymap.get(identity["sub"])
        if mapped:
            return mapped
    return cfg.api_key


def resolve_model(cfg):
    """Return the model to use: configured one, else first advertised by upstream."""
    if cfg.model:
        return cfg.model
    data = _upstream_request(cfg, "/v1/models", method="GET")
    models = data.get("data") or []
    if not models:
        raise UpstreamError("upstream advertises no models (/v1/models empty)")
    model = models[0].get("id") or models[0].get("model")
    if not model:
        raise UpstreamError("upstream /v1/models entry has no id")
    return model


def build_messages(cfg, message, history):
    """Map MeshBox history ({role,text}) + new message to OpenAI messages."""
    messages = []
    if cfg.system_prompt:
        messages.append({"role": "system", "content": cfg.system_prompt})
    for turn in history or []:
        role = turn.get("role")
        text = turn.get("text") or turn.get("content") or ""
        # MeshBox stores 'user'/'assistant'; anything else we coerce to user.
        if role not in ("user", "assistant", "system"):
            role = "user"
        if text:
            messages.append({"role": role, "content": text})
    messages.append({"role": "user", "content": message})
    return messages


def chat(cfg, message, history, identity=None):
    """Forward one chat turn to nufi-app and return the MeshBox {reply,model}.

    When ``identity`` is present the turn is attributed to that member: it uses
    the member's litellm virtual key and stamps ``user``/``metadata``/header so
    litellm's audit trail records who actually asked.
    """
    # Egress guard: before any member data leaves for the upstream, confirm the
    # target is on the mesh. In enforce mode an off-mesh upstream raises
    # EgressError(403); in audit mode this is a no-op (decision recorded only).
    if cfg.egress is not None:
        cfg.egress.check(cfg.upstream)
    model = resolve_model(cfg)
    payload = {
        "model": model,
        "messages": build_messages(cfg, message, history),
        "stream": False,
    }
    api_key = key_for(cfg, identity)
    extra_headers = None
    if identity:
        payload["user"] = identity["sub"]
        payload["metadata"] = {
            "meshbox_actor": identity["sub"],
            "meshbox_email": identity.get("email") or "",
            "meshbox_access": identity.get("access") or "",
        }
        extra_headers = {"X-MeshBox-Actor": identity["sub"]}
    resp = _upstream_request(cfg, "/v1/chat/completions", payload, method="POST",
                             api_key=api_key, extra_headers=extra_headers)
    choices = resp.get("choices") or []
    reply = ""
    if choices:
        reply = (choices[0].get("message") or {}).get("content") or ""
    reply = reply.strip()
    if not reply:
        # Honest boundary: an empty completion is a backend failure, not a reply.
        raise UpstreamError("upstream returned an empty completion")
    return {"reply": reply, "model": resp.get("model", model)}


class Handler(BaseHTTPRequestHandler):
    cfg = None  # injected by serve()

    def log_message(self, fmt, *args):  # keep the demo output clean
        sys.stderr.write("[adapter] " + (fmt % args) + "\n")

    def _json(self, code, obj):
        raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path in ("/healthz", "/health"):
            try:
                model = resolve_model(self.cfg)
                return self._json(200, {"status": "ok",
                                        "upstream": self.cfg.upstream,
                                        "model": model})
            except UpstreamError as exc:
                return self._json(502, {"status": "error", "detail": str(exc)})
        return self._json(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/v1/chat":
            return self._json(404, {"error": "not found"})
        try:
            n = int(self.headers.get("Content-Length", 0) or 0)
            body = json.loads(self.rfile.read(n) or "{}")
        except (ValueError, json.JSONDecodeError):
            return self._json(400, {"error": "invalid JSON body"})
        message = (body.get("message") or "").strip()
        if not message:
            return self._json(400, {"error": "message is required"})
        history = body.get("history") or []

        # Federated identity: X-MeshBox-Identity, else a bearer token.
        token = self.headers.get("X-MeshBox-Identity", "").strip()
        if not token:
            auth = self.headers.get("Authorization", "")
            if auth.startswith("Bearer "):
                token = auth[7:].strip()
        identity = None
        if token:
            try:
                identity = verify_identity(self.cfg, token)
            except IdentityError as exc:
                # An offered-but-invalid identity is always refused, whether or
                # not federation is required: it signals tampering, not absence.
                return self._json(401, {"error": str(exc)})
        elif self.cfg.fed_required:
            return self._json(401, {"error": "identity required"})

        try:
            return self._json(200, chat(self.cfg, message, history, identity))
        except nufi_egress.EgressError as exc:
            # Enforcing egress refused an off-mesh upstream: member data must not
            # leave the mesh. Answer 403 (never forwarded, never fabricated).
            return self._json(exc.code, {"error": str(exc)})
        except UpstreamError as exc:
            # MeshBox portal/ai.py maps any non-2xx here to AiError(.., 502).
            return self._json(502, {"error": str(exc)})


def serve(cfg=None):
    cfg = cfg or Config()
    Handler.cfg = cfg
    httpd = ThreadingHTTPServer((cfg.host, cfg.port), Handler)
    sys.stderr.write(
        f"[adapter] listening on {cfg.host}:{cfg.port} -> {cfg.upstream} "
        f"(model={cfg.model or 'auto'})\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    serve()
