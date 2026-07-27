"""Block prompt-injection attempts via the LLM Guard sidecar.

Pre-call hook that POSTs each user prompt to llm-guard-api before LiteLLM
forwards it upstream. On `is_valid: false`, returns HTTP 400 to the caller
and skips the model call entirely. Fail-closed by design — see W5.1's
"prompt-injection is a security control, not UX" decision.

Scanner scores are stamped onto Langfuse trace metadata (tags +
trace_metadata) so Grafana / Langfuse can aggregate guardrail trigger
rates over time without us shipping a custom Prometheus exporter.

Network errors / timeouts against llm-guard-api also fail-closed (HTTP
503): if we can't verify the prompt is safe, we don't forward it.
Better a 503 than a poisoned prompt slipping through during an outage.
"""

from __future__ import annotations

import os
from typing import Any

import httpx
from fastapi import HTTPException

from litellm.integrations.custom_logger import CustomLogger

LLM_GUARD_API_BASE = os.environ.get("LLM_GUARD_API_BASE", "http://llm-guard-api:8000")
LLM_GUARD_AUTH_TOKEN = os.environ.get("LLM_GUARD_AUTH_TOKEN", "")
LLM_GUARD_TIMEOUT_S = float(os.environ.get("LLM_GUARD_TIMEOUT_S", "5.0"))

# Module-level client — avoids per-call TLS/connection setup.
# Bearer header is set unconditionally; LLM Guard's auth.type: http_bearer
# rejects empty/missing tokens with 403 even on healthcheck-style endpoints.
_client = httpx.AsyncClient(
    base_url=LLM_GUARD_API_BASE,
    timeout=LLM_GUARD_TIMEOUT_S,
    headers={"Authorization": f"Bearer {LLM_GUARD_AUTH_TOKEN}"},
)

# Restrict scanning to chat completions; embeddings, image generation, etc.
# don't carry user prompts in the same shape.
_SCANNED_CALL_TYPES = frozenset({
    "completion", "acompletion", "chat_completion", "achat_completion",
})


def _extract_user_prompt(messages: list[dict[str, Any]] | None) -> str:
    """Concatenate user-role message contents into a single prompt string.

    System and assistant messages are operator-controlled, not user input,
    so they're trusted and skipped. Multimodal content (vision) only contributes
    its text parts.
    """
    parts: list[str] = []
    for m in messages or []:
        if m.get("role") != "user":
            continue
        content = m.get("content")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            for chunk in content:
                if isinstance(chunk, dict) and chunk.get("type") == "text":
                    parts.append(str(chunk.get("text", "")))
    return "\n".join(parts).strip()


class PromptInjectionLogger(CustomLogger):
    """Pre-call hook: scan user prompts via LLM Guard, block on injection."""

    async def async_pre_call_hook(
        self,
        user_api_key_dict: Any,
        cache: Any,
        data: dict[str, Any],
        call_type: str,
    ) -> dict[str, Any]:
        if call_type not in _SCANNED_CALL_TYPES:
            return data
        prompt = _extract_user_prompt(data.get("messages"))
        if not prompt:
            return data

        try:
            resp = await _client.post(
                "/scan/prompt",
                json={"prompt": prompt, "scanners_suppress": []},
            )
            resp.raise_for_status()
            body = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise HTTPException(
                status_code=503,
                detail=f"prompt-injection guardrail unavailable: {exc!s}",
            ) from exc

        is_valid = bool(body.get("is_valid", False))
        scanners: dict[str, float] = body.get("scanners") or {}

        meta = data.setdefault("metadata", {})
        if isinstance(meta, dict):
            tags = meta.setdefault("tags", [])
            if isinstance(tags, list):
                tags.append(
                    f"guardrail:injection_{'pass' if is_valid else 'block'}"
                )
            trace_meta = meta.setdefault("trace_metadata", {})
            if isinstance(trace_meta, dict):
                trace_meta["guardrail_injection_scores"] = scanners

        if not is_valid:
            top_scanner, top_score = max(
                scanners.items(), key=lambda kv: kv[1], default=("?", 0.0),
            )
            raise HTTPException(
                status_code=400,
                detail=(
                    f"prompt rejected by guardrail "
                    f"(top scanner: {top_scanner}={top_score:.2f})"
                ),
            )
        return data


proxy_handler_instance = PromptInjectionLogger()
