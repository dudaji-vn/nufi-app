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

Run
---
  python3 nufi_chat_adapter.py            # serves on 0.0.0.0:8900
"""
import json
import os
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


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


class UpstreamError(Exception):
    """Upstream (nufi-app chat) failed. Always mapped to HTTP 502 downstream."""


def _upstream_request(cfg, path, payload=None, method="GET"):
    """Call the nufi-app OpenAI-compatible chat API; return parsed JSON.

    Any transport/HTTP/JSON failure becomes UpstreamError so we can answer the
    MeshBox gateway with an honest 502 rather than a fabricated reply.
    """
    url = cfg.upstream + path
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Accept", "application/json")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if cfg.api_key:
        req.add_header("Authorization", "Bearer " + cfg.api_key)
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


def chat(cfg, message, history):
    """Forward one chat turn to nufi-app and return the MeshBox {reply,model}."""
    model = resolve_model(cfg)
    payload = {
        "model": model,
        "messages": build_messages(cfg, message, history),
        "stream": False,
    }
    resp = _upstream_request(cfg, "/v1/chat/completions", payload, method="POST")
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
        try:
            return self._json(200, chat(self.cfg, message, history))
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
