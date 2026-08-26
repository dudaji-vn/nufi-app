#!/usr/bin/env python3
"""MeshBox ⇄ nufi-app Agent adapter — feasibility gap G2 (CMP-510, sibling of chat).

MeshBox (appliance) ``portal/ai.py`` fronts an agent backend with one socket
(see appliance portal/ai.py :212-233): it POSTs a routine trigger to
``$MESHBOX_AGENT_URL/v1/run`` and expects a run record back:

  POST $MESHBOX_AGENT_URL/v1/run  {"routine_id","routine"}  -> {"status","output"}

nufi-app's real agent engine is **nufi-agent** (``apps/nufi-agent`` — a Langflow-based
flow runtime). Its native service API runs a *flow* by id:

  POST {AGENT}/api/v1/run/{flow}   header: x-api-key
       body {"input_value","output_type":"chat","input_type":"chat"}
    -> nested {"outputs":[{"outputs":[{"results":{"message":{"text": ...}}}]}]}

This adapter is the seam: it maps a MeshBox *routine* to a nufi-agent *flow*, runs
it, and normalizes the nested Langflow result down to the ``{status, output}`` MeshBox
expects.

    laptop ─mesh─▶ MeshBox portal/ai.py ─/v1/run─▶ [THIS ADAPTER]
                   └─ run flow ─▶ nufi-agent /api/v1/run/{flow}

Two upstream modes (auto-selected):
  * **flow mode** (default when a flow is mapped): drive nufi-agent's Langflow run
    API and walk the nested outputs for the message text.
  * **clean mode** (no flow mapped): POST ``{routine_id,routine}`` to
    ``{AGENT}{NUFI_AGENT_RUN_PATH}`` and expect a plain ``{status,output}`` — for a
    future G2 service that already speaks the MeshBox shape.

Honest boundary (mirrored from the chat adapter): it NEVER fabricates a run result.
Unreachable backend, an errored run, or an empty output => ``502`` so MeshBox's
``AiError(.., 502)`` surfaces a real failure. A routine with no wired flow AND no
clean-mode endpoint is honestly ``502`` ("not wired"), never a fake "completed".

Contract exposed to MeshBox
---------------------------
  GET  /healthz          -> 200 {"status":"ok","agent_upstream":..,"mode":..}
                            502 {"status":"error","detail":..} if backend down
  POST /v1/run            body  {"routine_id": str, "routine": str}
                          -> 200 {"status": str, "output": str}
                             400 {"error": ..} (missing routine_id)
                             502 {"error": ..} (unreachable / errored / empty / unwired)

Config (env)
------------
  NUFI_AGENT_URL         base URL of nufi-agent (default http://nufi-agent:7860)
  NUFI_AGENT_API_KEY     x-api-key for nufi-agent (also accepts LANGFLOW_API_KEY)
  NUFI_AGENT_FLOW_MAP    JSON {routine_id: flow_id} routing map (optional)
  NUFI_AGENT_DEFAULT_FLOW  flow id used for any routine not in the map (optional)
  NUFI_AGENT_RUN_PATH    run path prefix (default /api/v1/run); flow appended in
                         flow mode, used as-is in clean mode
  NUFI_AGENT_INPUT_TEMPLATE  input_value template, {routine}/{routine_id} expanded
                             (default "'{routine}' 루틴을 실행하세요.")
  ADAPTER_HOST/ADAPTER_PORT  bind address (default 0.0.0.0 / 8902)
  NUFI_AGENT_TIMEOUT     run timeout seconds (default 120 — agent runs are slow)

Run
---
  python3 nufi_agent_adapter.py            # serves on 0.0.0.0:8902
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
        self.agent_url = _env("NUFI_AGENT_URL",
                              default="http://nufi-agent:7860").rstrip("/")
        self.api_key = _env("NUFI_AGENT_API_KEY", "LANGFLOW_API_KEY")
        self.default_flow = os.environ.get("NUFI_AGENT_DEFAULT_FLOW", "").strip()
        self.run_path = os.environ.get("NUFI_AGENT_RUN_PATH",
                                       "/api/v1/run").rstrip("/") or "/api/v1/run"
        self.input_template = os.environ.get(
            "NUFI_AGENT_INPUT_TEMPLATE", "'{routine}' 루틴을 실행하세요.")
        self.host = os.environ.get("ADAPTER_HOST", "0.0.0.0")
        self.port = int(os.environ.get("ADAPTER_PORT", "8902"))
        self.timeout = float(os.environ.get("NUFI_AGENT_TIMEOUT", "120"))
        raw = os.environ.get("NUFI_AGENT_FLOW_MAP", "").strip()
        self.flow_map = {}
        if raw:
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    self.flow_map = {str(k): str(v) for k, v in parsed.items()}
            except json.JSONDecodeError:
                sys.stderr.write(
                    "[agent-adapter] WARN: NUFI_AGENT_FLOW_MAP is not valid JSON;"
                    " ignoring\n")

    def flow_for(self, routine_id):
        """Resolve the flow id for a routine, or "" if this routine is unwired."""
        return self.flow_map.get(routine_id) or self.default_flow


class UpstreamError(Exception):
    """Upstream (nufi-agent) failed. Always mapped to HTTP 502 downstream."""


def _request(base, path, payload=None, method="GET", api_key="", timeout=120.0):
    """Call nufi-agent; return parsed JSON or raise UpstreamError.

    nufi-agent (Langflow) authenticates the service API with the ``x-api-key``
    header. Any transport/HTTP/JSON failure becomes UpstreamError -> honest 502.
    """
    url = base + path
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Accept", "application/json")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if api_key:
        req.add_header("x-api-key", api_key)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
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


# Keys under which Langflow (and lookalikes) stash the human-readable message text.
_TEXT_KEYS = ("text", "message", "result", "output", "answer", "content")


def extract_output(resp):
    """Walk a nufi-agent/Langflow run response for the message text.

    Langflow nests results deeply and inconsistently across component types, so we
    recursively search for the first non-empty message text rather than hard-coding
    one path. Also handles a clean ``{status,output}`` shape directly.
    """
    if isinstance(resp, dict):
        # clean-mode shortcut
        out = resp.get("output")
        if isinstance(out, str) and out.strip():
            return out.strip()
        # Langflow: results.message.text | results.message.data.text | artifacts.message
        msg = resp.get("message")
        if isinstance(msg, str) and msg.strip():
            return msg.strip()
        if isinstance(msg, dict):
            found = extract_output(msg)
            if found:
                return found
        for key in _TEXT_KEYS:
            val = resp.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
        # recurse into the structural containers Langflow uses
        for key in ("outputs", "results", "data", "artifacts", "message",
                    "messages", "outputs_dict"):
            if key in resp:
                found = extract_output(resp[key])
                if found:
                    return found
        # last resort: any nested dict/list value
        for val in resp.values():
            if isinstance(val, (dict, list)):
                found = extract_output(val)
                if found:
                    return found
    elif isinstance(resp, list):
        for item in resp:
            found = extract_output(item)
            if found:
                return found
    return ""


def _run_status(resp):
    """Best-effort run status; treat explicit failures as failures."""
    if isinstance(resp, dict):
        for key in ("status", "state"):
            v = resp.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip().lower()
    return "completed"


def run(cfg, routine_id, routine):
    """Trigger one routine on nufi-agent and return {status, output} for MeshBox."""
    flow = cfg.flow_for(routine_id)
    input_value = cfg.input_template.format(routine=routine or routine_id,
                                            routine_id=routine_id)

    if flow:
        # flow mode — Langflow service API
        path = f"{cfg.run_path}/{flow}"
        payload = {"input_value": input_value,
                   "output_type": "chat", "input_type": "chat"}
    else:
        if not cfg.api_key and cfg.run_path == "/api/v1/run":
            # No flow mapped and no clean endpoint configured: honestly unwired.
            raise UpstreamError(
                f"routine '{routine_id}' is not wired to a nufi-agent flow "
                f"(set NUFI_AGENT_FLOW_MAP or NUFI_AGENT_DEFAULT_FLOW)")
        # clean mode — a G2 service that already speaks {status,output}
        path = cfg.run_path
        payload = {"routine_id": routine_id, "routine": routine,
                   "input_value": input_value}

    resp = _request(cfg.agent_url, path, payload, method="POST",
                    api_key=cfg.api_key, timeout=cfg.timeout) or {}

    status = _run_status(resp)
    if status in ("error", "failed", "failure"):
        detail = extract_output(resp) or "agent run reported failure"
        raise UpstreamError(f"agent run failed: {detail}")

    output = extract_output(resp)
    if not output:
        # Honest boundary: an empty run output is a failure, not a result.
        raise UpstreamError("agent run returned no output")
    return {"status": "completed" if status not in ("running", "pending")
            else status, "output": output}


class Handler(BaseHTTPRequestHandler):
    cfg = None  # injected by serve()

    def log_message(self, fmt, *args):
        sys.stderr.write("[agent-adapter] " + (fmt % args) + "\n")

    def _json(self, code, obj):
        raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _mode(self):
        return "flow" if (self.cfg.flow_map or self.cfg.default_flow) else "clean"

    def do_GET(self):
        if self.path in ("/healthz", "/health"):
            try:
                # nufi-agent exposes /health_check (Langflow); tolerate /health too.
                try:
                    _request(self.cfg.agent_url, "/health_check", method="GET",
                             api_key=self.cfg.api_key, timeout=self.cfg.timeout)
                except UpstreamError:
                    _request(self.cfg.agent_url, "/health", method="GET",
                             api_key=self.cfg.api_key, timeout=self.cfg.timeout)
                return self._json(200, {"status": "ok",
                                        "agent_upstream": self.cfg.agent_url,
                                        "mode": self._mode()})
            except UpstreamError as exc:
                return self._json(502, {"status": "error", "detail": str(exc)})
        return self._json(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/v1/run":
            return self._json(404, {"error": "not found"})
        try:
            n = int(self.headers.get("Content-Length", 0) or 0)
            body = json.loads(self.rfile.read(n) or "{}")
        except (ValueError, json.JSONDecodeError):
            return self._json(400, {"error": "invalid JSON body"})
        routine_id = (body.get("routine_id") or "").strip()
        if not routine_id:
            return self._json(400, {"error": "routine_id is required"})
        routine = (body.get("routine") or "").strip()
        try:
            return self._json(200, run(self.cfg, routine_id, routine))
        except UpstreamError as exc:
            return self._json(502, {"error": str(exc)})


def serve(cfg=None):
    cfg = cfg or Config()
    Handler.cfg = cfg
    httpd = ThreadingHTTPServer((cfg.host, cfg.port), Handler)
    mode = "flow" if (cfg.flow_map or cfg.default_flow) else "clean"
    sys.stderr.write(
        f"[agent-adapter] listening on {cfg.host}:{cfg.port} -> "
        f"{cfg.agent_url} (mode={mode})\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    serve()
