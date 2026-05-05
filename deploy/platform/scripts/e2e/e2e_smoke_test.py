#!/usr/bin/env python3
"""End-to-end smoke test for the NPUOps platform (W2 Task 2.2).

Drives the full user-visible flow:

    User → LibreChat → LiteLLM → GPU backend → Langfuse trace

Sectioned output mirrors `scripts/smoke-test.sh`. Designed to run inside the
compose network (service `e2e-test`, profile `e2e`) so it can address services
by their internal hostnames and so we never run Python on the host (per
CLAUDE.md). Exits non-zero on the first failed assertion.
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from typing import Any

import httpx

LIBRECHAT_URL = os.environ.get("LIBRECHAT_URL", "http://librechat:3080")
LANGFUSE_URL = os.environ.get("LANGFUSE_URL", "http://langfuse-web:3000")
LANGFUSE_PUBLIC_KEY = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
LANGFUSE_SECRET_KEY = os.environ.get("LANGFUSE_SECRET_KEY", "")
USER_EMAIL = os.environ.get("E2E_USER_EMAIL", "e2e@npuops.local")
USER_PASSWORD = os.environ.get("E2E_USER_PASSWORD", "")
USER_NAME = os.environ.get("E2E_USER_NAME", "E2E Bot")
MODEL = os.environ.get("E2E_MODEL", "qwen2.5-3b")
EXPECTED_HARDWARE_ID = os.environ.get("E2E_EXPECTED_HARDWARE_ID", "mac-local")
ENDPOINT_NAME = os.environ.get("E2E_ENDPOINT_NAME", "NPUOps")

# ---- ANSI helpers (match scripts/smoke-test.sh look) -----------------------
_TTY = sys.stdout.isatty()
BOLD = "\033[1m" if _TTY else ""
GREEN = "\033[32m" if _TTY else ""
RED = "\033[31m" if _TTY else ""
CYAN = "\033[36m" if _TTY else ""
DIM = "\033[2m" if _TTY else ""
RESET = "\033[0m" if _TTY else ""


def step(msg: str) -> None:
    print(f"{CYAN}==>{RESET} {BOLD}{msg}{RESET}", flush=True)


def ok(msg: str) -> None:
    print(f"    {GREEN}✓{RESET} {msg}", flush=True)


YELLOW = "\033[33m" if _TTY else ""


def warn(msg: str) -> None:
    print(f"    {YELLOW}!{RESET} {msg}", flush=True)


def fail(msg: str) -> None:
    print(f"{RED}error:{RESET} {msg}", file=sys.stderr, flush=True)
    sys.exit(1)


def require(cond: bool, msg: str) -> None:
    if not cond:
        fail(msg)


# ---- 1/6 LibreChat liveness ------------------------------------------------
def assert_librechat_up(client: httpx.Client) -> None:
    step("1/7 LibreChat liveness")
    deadline = time.time() + 30
    last_err = ""
    while time.time() < deadline:
        try:
            # /api/config returns JSON with `appTitle` etc; a 200 here means
            # both the proxy *and* the React app have booted (the docker-level
            # /api/health hits the SPA fallback and is too lenient).
            r = client.get(f"{LIBRECHAT_URL}/api/config", timeout=5)
            if r.status_code == 200 and "appTitle" in r.text:
                ok(f"LibreChat reachable ({LIBRECHAT_URL})")
                return
            last_err = f"HTTP {r.status_code}"
        except httpx.HTTPError as e:
            last_err = str(e)
        time.sleep(2)
    fail(f"LibreChat not reachable after 30s: {last_err}")


# ---- 2/6 Auth (register-or-login) ------------------------------------------
def get_jwt(client: httpx.Client) -> str:
    step("2/7 Auth (register-or-login)")
    require(
        bool(USER_PASSWORD),
        "E2E_USER_PASSWORD is empty — set it in .env (see .env.example)",
    )

    # Try register first. LibreChat returns 422 with "already exists" on
    # duplicate emails; treat that as a soft success and fall through to login.
    register_body = {
        "email": USER_EMAIL,
        "password": USER_PASSWORD,
        "confirm_password": USER_PASSWORD,
        "name": USER_NAME,
        "username": USER_EMAIL.split("@")[0] + "-" + uuid.uuid4().hex[:6],
    }
    r = client.post(f"{LIBRECHAT_URL}/api/auth/register", json=register_body, timeout=15)
    if r.status_code in (200, 201):
        ok(f"registered new user {USER_EMAIL}")
    elif r.status_code in (409, 422):
        ok(f"user {USER_EMAIL} already exists — falling through to login")
    elif r.status_code == 429:
        # LibreChat rate-limits registration; treat as "user probably exists,
        # let login decide". If login also fails, the error there will be the
        # actionable one.
        ok(f"register rate-limited — falling through to login ({r.status_code})")
    else:
        fail(f"register failed: HTTP {r.status_code} body={r.text[:300]}")

    # Login. LibreChat sets refreshToken as an httpOnly cookie and returns
    # the access token in the JSON body as `token`.
    r = client.post(
        f"{LIBRECHAT_URL}/api/auth/login",
        json={"email": USER_EMAIL, "password": USER_PASSWORD},
        timeout=15,
    )
    require(r.status_code == 200, f"login failed: HTTP {r.status_code} body={r.text[:300]}")
    body = r.json()
    token = body.get("token") or ""
    require(bool(token), f"login response missing 'token': {json.dumps(body)[:300]}")
    ok("got JWT")
    return token


# ---- 3/6 Chat round-trip ---------------------------------------------------
def send_chat(client: httpx.Client, token: str) -> tuple[str, float]:
    """POST /api/ask/<endpoint> and consume the SSE stream.

    Returns (assistant_text, request_timestamp_ms) — the timestamp is the
    moment we sent the request and is used to scope the Langfuse trace lookup.
    """
    # In LibreChat 0.7.5 the URL component is the *endpoint type* (`custom`,
    # `openai`, `anthropic`, …), while the body's `endpoint` field carries the
    # configured name (e.g. "NPUOps") that LibreChat resolves against
    # endpoints.custom[] in librechat.yaml.
    step(f"3/7 Chat via /api/ask/custom (endpoint={ENDPOINT_NAME!r})")
    convo_id = str(uuid.uuid4())
    parent_id = "00000000-0000-0000-0000-000000000000"
    user_msg_id = str(uuid.uuid4())
    prompt = "say hi in 5 words"

    body: dict[str, Any] = {
        "endpoint": ENDPOINT_NAME,
        "endpointType": "custom",
        "model": MODEL,
        "text": prompt,
        "conversationId": convo_id,
        "parentMessageId": parent_id,
        "messageId": user_msg_id,
        "isCreatedByUser": True,
        "sender": "User",
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "text/event-stream",
        "Content-Type": "application/json",
    }

    request_started_ms = int(time.time() * 1000)
    assistant_text = ""
    final_payload: dict[str, Any] = {}
    last_data_line = ""

    with client.stream(
        "POST",
        f"{LIBRECHAT_URL}/api/ask/custom",
        json=body,
        headers=headers,
        timeout=120,
    ) as r:
        require(
            r.status_code == 200,
            f"/api/ask returned HTTP {r.status_code}: {r.read().decode('utf-8', 'replace')[:300]}",
        )
        for line in r.iter_lines():
            if not line:
                continue
            if not line.startswith("data:"):
                continue
            data = line[len("data:"):].strip()
            if not data or data == "[DONE]":
                continue
            last_data_line = data
            try:
                event = json.loads(data)
            except json.JSONDecodeError:
                continue
            # The final event includes the full assistant message under
            # `responseMessage` (LibreChat 0.7.x). Earlier events stream
            # incremental text under `text`.
            if "responseMessage" in event:
                final_payload = event
            if isinstance(event.get("text"), str):
                assistant_text = event["text"]

    if final_payload.get("responseMessage", {}).get("text"):
        assistant_text = final_payload["responseMessage"]["text"]

    require(
        bool(assistant_text.strip()),
        f"empty assistant response — last SSE data line: {last_data_line[:300]}",
    )
    ok(f"got reply ({len(assistant_text)} chars): {assistant_text[:80]!r}")
    return assistant_text, request_started_ms


# ---- 4/6 Langfuse trace surfaces -------------------------------------------
def find_trace(from_ts_ms: int) -> dict[str, Any]:
    step("4/7 Langfuse trace surfaces")
    require(
        bool(LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY),
        "LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY not set in env",
    )
    auth = (LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY)
    # Langfuse expects ISO 8601. Use UTC, ms precision.
    from_ts_iso = (
        time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(from_ts_ms / 1000))
        + f".{from_ts_ms % 1000:03d}Z"
    )
    deadline = time.time() + 30
    with httpx.Client(auth=auth, timeout=10) as c:
        while time.time() < deadline:
            r = c.get(
                f"{LANGFUSE_URL}/api/public/traces",
                params={"limit": 5, "fromTimestamp": from_ts_iso},
            )
            if r.status_code == 200:
                data = r.json().get("data", [])
                if data:
                    trace_id = data[0]["id"]
                    # The list endpoint returns observation IDs only — fetch
                    # the full trace so downstream assertions can read
                    # observation.model and friends.
                    full = c.get(f"{LANGFUSE_URL}/api/public/traces/{trace_id}")
                    if full.status_code == 200:
                        trace = full.json()
                        ok(f"trace surfaced: id={trace.get('id')}")
                        return trace
            time.sleep(1)
    fail(f"no trace surfaced within 30s (since {from_ts_iso})")
    raise SystemExit(1)  # for type-checker; fail() already exits


# ---- 5/6 Cost populated ----------------------------------------------------
def assert_cost(trace: dict[str, Any]) -> None:
    step("5/7 Trace cost is populated")
    cost = trace.get("totalCost")
    if cost is None:
        cost = trace.get("calculatedTotalCost")
    require(
        cost is not None,
        f"trace.totalCost / calculatedTotalCost both None — check langfuse_default_tags + model_info costs in litellm/config.yaml. trace={json.dumps(trace)[:400]}",
    )
    ok(f"cost = {cost}")


# ---- 6/7 Trace records the configured model -------------------------------
def assert_trace_model(trace: dict[str, Any]) -> None:
    step(f"6/7 Trace records the configured model ({MODEL!r})")
    # LiteLLM stores the resolved model on the GENERATION observation under
    # `.model`. Top-level trace doesn't carry it directly. Find the first
    # generation-type observation and check.
    observations = trace.get("observations") or []
    gen_models = [
        o.get("model")
        for o in observations
        if isinstance(o, dict) and o.get("type") == "GENERATION"
    ]
    require(
        bool(gen_models),
        f"trace had no GENERATION observation — observations={observations!r}",
    )
    # LiteLLM's normalised model name strips the `openai/` prefix, so the
    # observation's `.model` may be either the model_name from config.yaml
    # (e.g. `qwen2.5-3b`) or the upstream id (`qwen2.5:3b`). Accept either.
    expected_aliases = {MODEL, MODEL.replace("-", ":")}
    require(
        any(m and any(alias in m for alias in expected_aliases) for m in gen_models),
        f"observation.model {gen_models!r} does not match expected {MODEL!r}",
    )
    ok(f"observation.model = {gen_models[0]!r}")


# ---- 7/7 hardware_id propagation (soft check — known gap) ------------------
def soft_check_hardware_id(trace: dict[str, Any]) -> bool:
    step(f"7/7 hardware_id propagates (soft check, expecting {EXPECTED_HARDWARE_ID!r})")
    # KNOWN GAP discovered during W2.2: LiteLLM's `langfuse_default_tags` only
    # natively resolves `cache_hit` / `cache_key` — custom strings like
    # `hardware_id` and `backend_type` are silently ignored
    # (litellm/integrations/langfuse/langfuse.py::add_default_langfuse_tags).
    # Surfacing model_info.hardware_id on every trace requires a small custom
    # callback (or a `pre_call_hook` that injects metadata). Tracked as a W2.5
    # follow-up so the W6 NPU utilisation report can aggregate by hardware.
    #
    # We still check both tags and metadata so this assertion auto-promotes
    # to "passing" once the follow-up lands.
    tags = trace.get("tags") or []
    metadata = trace.get("metadata") or {}
    hw_in_tags = EXPECTED_HARDWARE_ID in tags or any(
        EXPECTED_HARDWARE_ID in str(t) for t in tags
    )
    hw_in_meta = (
        metadata.get("hardware_id") == EXPECTED_HARDWARE_ID
        if isinstance(metadata, dict)
        else False
    )
    if hw_in_tags or hw_in_meta:
        ok(f"hardware_id present in {'tags' if hw_in_tags else 'metadata'}")
        return True
    warn(
        f"hardware_id={EXPECTED_HARDWARE_ID!r} not propagated — "
        f"tags={tags}, metadata.hardware_id={metadata.get('hardware_id') if isinstance(metadata, dict) else None!r}. "
        "Known gap, see scripts/e2e/e2e_smoke_test.py docstring."
    )
    return False


def main() -> None:
    # LibreChat's `uaParser` middleware rejects any request whose User-Agent
    # ua-parser-js doesn't recognise as a browser (and increments a violation
    # counter that can rate-limit us). Send a realistic Firefox UA so we look
    # like a real client; the alternative would be NON_BROWSER_VIOLATION_SCORE=0
    # in compose, but that weakens prod-like behaviour for everyone.
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) "
            "Gecko/20100101 Firefox/128.0"
        ),
    }
    with httpx.Client(follow_redirects=True, headers=headers) as client:
        assert_librechat_up(client)
        token = get_jwt(client)
        _, request_started_ms = send_chat(client, token)

    trace = find_trace(request_started_ms)
    assert_cost(trace)
    assert_trace_model(trace)
    hw_ok = soft_check_hardware_id(trace)

    print()
    if hw_ok:
        print(f"{GREEN}all checks passed{RESET}")
    else:
        print(f"{GREEN}all hard checks passed{RESET} ({YELLOW}1 soft warning above{RESET})")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
