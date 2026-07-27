"""LiteLLM CustomGuardrail entrypoints. Wiring only — no policy, no detection."""

from __future__ import annotations

import os
import time
from typing import Any

from guardrails import audit
from guardrails.canonical import canonicalize
from guardrails.policy import ControlConfig, Policy, decide
from guardrails.scanners.injection import InjectionScanner
from guardrails.spans import extract_spans
from guardrails.types import Action
from litellm._logging import verbose_proxy_logger
from litellm.integrations.custom_guardrail import CustomGuardrail

# Verified against the installed litellm==1.83.10 source
# (litellm/proxy/common_request_processing.py::_handle_llm_api_exception,
# which both /v1/chat/completions and /v1/completions route through): the
# call_type LiteLLM actually hands a pre_call hook is the CallTypes enum
# value, and for a chat request that is "acompletion" (async) or
# "completion" (sync) — never "chat_completion"/"achat_completion". Those
# two strings appear in no CallTypes member and would never match a real
# request; kept out rather than carried forward from the brief unverified.
_CHAT_CALL_TYPES = frozenset({"completion", "acompletion"})

POLICY_PATH = os.environ.get("GUARDRAIL_POLICY_PATH", "/app/guardrails/policy.yaml")
SCANNER_API_BASE = os.environ.get("SCANNER_API_BASE", "http://nufi-scanner:8000")
# Measured: ~200 ms per 450-token window, and the scanner caps a request at
# _MAX_WINDOWS_PER_REQUEST windows, so a full scan lands near 5 s worst case.
# G1 fails closed, so a timeout is a 503 for the user — leave headroom.
SCANNER_TIMEOUT_S = float(os.environ.get("SCANNER_TIMEOUT_S", "8.0"))

# Where the pre_call phase records its verdict on the client's grounded hint,
# for post_call controls to read. Namespaced so a client cannot forge it: the
# resolver overwrites this key on every request before anything reads it.
VERIFIED_GROUNDED_KEY = "nufi_grounded_verified"


class GuardrailBlocked(Exception):
    """Raised to stop a request. LiteLLM surfaces this to the caller.

    Carries `status_code` (plain attribute, not an `HTTPException`
    subclass) because LiteLLM's own exception-to-response mapping reads
    `status_code` off whatever a guardrail hook raises — verified directly
    against the installed litellm==1.83.10 source, in BOTH exception paths
    a chat completion can take:
      - the legacy `completion()` endpoint's inline
        `except Exception as e: raise ProxyException(...,
        code=getattr(e, "status_code", 500))`;
      - `chat_completion()`'s route through
        `ProxyBaseLLMRequestProcessing._handle_llm_api_exception`, whose
        final fallback (reached by anything that is not an `HTTPException`
        or `httpx.HTTPStatusError`) is the identical
        `code=getattr(e, "status_code", 500)`.
    A bare `Exception` has neither attribute, so every block would surface
    to the caller — and to any 5xx-based alerting — as a 500 server error
    indistinguishable from an outage. This module's own comment above
    `SCANNER_TIMEOUT_S` already promises the caller a 503 on a scanner
    timeout; the brief's `class GuardrailBlocked(Exception)` did not
    deliver that promise, defaulting every raise to 500. `status_code`
    closes that gap without adding a `fastapi` dependency this package does
    not otherwise need (it is not installed in this venv or in CI's
    `litellm` — only bare `pip install litellm` — and is only present at
    runtime because the proxy's own base image bundles it).

    Not subclassing `fastapi.HTTPException`: doing so would let LiteLLM's
    `_serialize_http_exception_detail` unpack a structured dict `detail`
    into `ProxyException.provider_specific_fields`, which is the most
    promising carrier for `code`/`event_id` to survive to the client
    verbatim — but confirming that shape requires `fastapi` importable,
    which is a dependency decision (and the empirical wire-format check)
    the plan explicitly reserves for Task 15 Step 9. Recorded here so that
    task does not have to rediscover it.
    """

    def __init__(
        self, code: str, event_id: str, detail: str, status_code: int = 400
    ) -> None:
        self.code = code
        self.event_id = event_id
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)

    def to_body(self) -> dict[str, Any]:
        return {
            "error": {
                "type": "nufi_guardrail_blocked",
                "code": self.code,
                "event_id": self.event_id,
                "detail": self.detail,
            }
        }


class BaseNufiGuardrail(CustomGuardrail):
    control_id: str = ""

    def __init__(self, policy: Policy | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._policy = policy or Policy.load(POLICY_PATH)
        self._control = self._policy.control(self.control_id)
        audit.GUARDRAIL_ENABLED.labels(
            control=self.control_id, mode=self._control.mode
        ).set(1 if self._control.enabled else 0)

    @property
    def control(self) -> ControlConfig:
        return self._control

    def _enforcing(self) -> bool:
        return self._control.enabled and self._control.mode != "logging_only"

    def _context(self, data: dict[str, Any], key: Any) -> dict[str, Any]:
        """Build `audit.build_event`'s `request_context`.

        `audit.build_event` documents that a key ABSENT from this dict is
        omitted from the event entirely, never defaulted to `None` — "a
        None copied into every event looks, on the reading side, identical
        to 'we checked and there wasn't one'". Setting every key
        unconditionally (including `None` when a key/model attribute is
        missing) would silently defeat that contract at the one call site
        that actually supplies it, so each optional field is included only
        when it has a real value.
        """
        context: dict[str, Any] = {"policy_digest": self._policy.digest()}
        key_alias = getattr(key, "key_alias", None)
        if key_alias is not None:
            context["key_alias"] = key_alias
        team_id = getattr(key, "team_id", None)
        if team_id is not None:
            context["team_id"] = team_id
        model = data.get("model")
        if model is not None:
            context["model"] = model
        return context

    def resolve_grounded(self, data: dict[str, Any], key: Any) -> bool:
        """Evaluate the grounded hint against the calling key and record the verdict.

        Only callable from a pre_call hook, which is the only place LiteLLM
        hands us the API key object. Post-call controls read the verdict via
        `verified_grounded` — they must never re-read the raw client hint,
        which is attacker-controllable.
        """
        key_metadata = getattr(key, "metadata", None)
        if not isinstance(key_metadata, dict):
            key_metadata = {}
        request_metadata = data.setdefault("metadata", {})
        if not isinstance(request_metadata, dict):
            return False

        granted = bool(key_metadata.get("allow_grounded_hint"))
        claimed = bool(request_metadata.get("nufi_grounded"))
        verdict = granted and claimed
        request_metadata[VERIFIED_GROUNDED_KEY] = verdict
        return verdict

    @staticmethod
    def verified_grounded(request_data: dict[str, Any] | None) -> bool:
        metadata = (request_data or {}).get("metadata") or {}
        if not isinstance(metadata, dict):
            return False
        return metadata.get(VERIFIED_GROUNDED_KEY) is True

    def _emit(
        self,
        data: dict[str, Any],
        decision: Any,
        transforms: tuple[str, ...],
        key: Any,
        enforced: bool,
    ) -> dict[str, Any]:
        event = audit.build_event(
            decision, transforms, self._context(data, key), enforced
        )
        try:
            audit.record(data, event)
        except audit.AuditRecordError:
            # `event["event_id"]` above is already valid regardless — only
            # the metadata ATTACH (and this one event's entry in
            # `guardrail_information`) failed, not the decision itself.
            # `audit.record` increments GUARDRAIL_DECISIONS before it ever
            # touches `data["metadata"]` (see audit.py), so the decision is
            # still visible in Prometheus even though this call raised.
            #
            # Swallowed here rather than re-raised: re-raising would let a
            # malformed `data["metadata"]` shape (e.g. a client sending
            # `"metadata": "not-a-dict"`) turn into an uncaught exception
            # from THIS hook regardless of mode — including logging_only,
            # where it must never break traffic. The caller can still raise
            # the correct `GuardrailBlocked` when enforcing, since it reads
            # `event["event_id"]`, not this method's return value's
            # persistence. Logged, not silent — the request-level count is
            # covered by Prometheus, but this surfaces the anomaly itself.
            verbose_proxy_logger.error(
                "guardrail %s: audit.record failed to attach event %s: "
                "malformed request metadata shape",
                self.control_id,
                event.get("event_id"),
            )
        return event


class G1Injection(BaseNufiGuardrail):
    control_id = "G1"

    def __init__(
        self, policy: Policy | None = None, scanner: Any | None = None, **kwargs: Any
    ) -> None:
        super().__init__(policy=policy, **kwargs)
        self._scanner = scanner or InjectionScanner(
            base_url=SCANNER_API_BASE, timeout_s=SCANNER_TIMEOUT_S
        )

    async def async_pre_call_hook(
        self, user_api_key_dict: Any, cache: Any, data: dict[str, Any], call_type: str
    ) -> dict[str, Any]:
        if call_type not in _CHAT_CALL_TYPES:
            return data

        # Runs before every early return below, so post_call controls always
        # see an authoritative verdict. If G1 is disabled the key is never set
        # and `verified_grounded` returns False — which redacts more, not less.
        grounded = self.resolve_grounded(data, user_api_key_dict)

        if not self._control.enabled:
            return data

        messages = data.get("messages")
        if messages is not None and (
            not isinstance(messages, list)
            or any(not isinstance(message, dict) for message in messages)
        ):
            # `extract_spans` assumes a list of dict messages and is off
            # limits to modify here; a malformed shape would otherwise raise
            # AttributeError deep inside it — an exception type nothing in
            # this hook expects. Treated the same as a scanner outage: we
            # cannot certify a request we cannot even parse, so the same
            # enforced/fail-open-by-mode branching applies.
            return self._on_outage(
                data, user_api_key_dict, TypeError("'messages' is not a list of dicts")
            )

        spans = extract_spans(messages)
        if not spans:
            return data

        started = time.perf_counter()
        try:
            findings = await self._scanner.scan(spans)
        except Exception as exc:
            # Caught broadly, not just `ScannerUnavailable`: a scanner that
            # raises a type this hook does not recognise must still respect
            # logging_only's never-break-traffic guarantee (and enforcing's
            # fail-closed guarantee) rather than escape as an exception type
            # nothing here expects. `Scanner.scan` is documented to raise
            # only `ScannerUnavailable`, but a hook that trusts that
            # contract absolutely is one bug away from either breaking
            # shadow-mode traffic or bypassing enforcement, depending on
            # where a future scanner implementation's bug happens to sit.
            return self._on_outage(data, user_api_key_dict, exc)
        finally:
            audit.GUARDRAIL_LATENCY.labels(control=self.control_id).observe(
                time.perf_counter() - started
            )

        audit.GUARDRAIL_DEGRADED.labels(control=self.control_id).set(0)

        transforms = audit.canonical_transforms(
            [canonicalize(span.text) for span in spans]
        )
        decision = decide(self._control, findings, grounded)
        if decision.action is Action.ALLOW:
            return data

        enforced = self._enforcing()
        event = self._emit(data, decision, transforms, user_api_key_dict, enforced)
        if not enforced:
            return data

        raise GuardrailBlocked(
            code="LLM01_INJECTION",
            event_id=event["event_id"],
            detail=decision.reason,
            status_code=400,
        )

    def _on_outage(
        self, data: dict[str, Any], key: Any, exc: Exception
    ) -> dict[str, Any]:
        verbose_proxy_logger.warning(
            "guardrail %s could not certify request (%s): %s",
            self.control_id,
            type(exc).__name__,
            exc,
        )
        audit.GUARDRAIL_DEGRADED.labels(control=self.control_id).set(1)
        if self._control.fails_closed and self._enforcing():
            raise GuardrailBlocked(
                code="GUARDRAIL_UNAVAILABLE",
                event_id=audit.new_event_id(),
                detail=str(exc),
                status_code=503,
            )
        return data


g1_injection = G1Injection()
