"""Normalised guardrail events and Prometheus instrumentation.

Events never carry the matched text — only offsets, scores and entity types —
so the audit trail cannot itself become a disclosure channel. `build_event`
reads `request_context` through a fixed key allow-list (never `**spread`), so
an unexpected key a caller passes in — a prompt, a user message — cannot ride
along into the audit trail either. `decision.reason` is rebuilt from
structured `Finding` fields by `_safe_reason` rather than copied verbatim.
`control`, `risk`, each `transforms` entry, and each finding's
`detector`/`entity` are all meant to be fixed, closed-set labels — every
current producer honours that (verified by reading each scanner and
`policy.py` directly; see the task report) — but that is a fact about
today's producers, not a guarantee this module enforced on its own until
`_safe_label` was added: every one of those five routes is now checked
against an identifier shape (`^[A-Za-z0-9_.:-]{1,64}$`) and replaced with
`"UNSAFE_LABEL"` if it fails, so a future producer that regresses — a
scanner that puts the matched substring into `entity` instead of its
category, say — cannot leak through this module even though nothing here
controls that producer. The guarantee must not depend on a fact that lives
somewhere else.

`record` raises `AuditRecordError` rather than silently discarding an event
it cannot attach to request metadata. A dropped audit event that raises
nothing looks, from the caller's side, identical to a clean write — the same
invisible-failure shape this whole pipeline exists to prevent, one layer up,
in the audit trail itself.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import sys
from collections.abc import Callable
from typing import Any, TypeVar

from prometheus_client import REGISTRY, Counter, Gauge, Histogram
from prometheus_client.metrics import MetricWrapperBase

from guardrails.types import Canonical, Decision

_M = TypeVar("_M", bound=MetricWrapperBase)


def _register(
    factory: Callable[..., _M],
    name: str,
    documentation: str,
    labelnames: tuple[str, ...] = (),
    **kwargs: Any,
) -> _M:
    """Create a collector, tolerating a second execution of this module.

    `Counter`/`Gauge`/`Histogram` register themselves with the process-global
    default registry at construction time, which raises `ValueError:
    Duplicated timeseries...` if a collector with the same name is already
    registered — verified directly against a live `CollectorRegistry`. That
    happens whenever this module's top level runs twice: a duplicate import
    under a different qualified name (this package imported both as
    `guardrails.audit` and, say, `litellm.guardrails.audit`), or a
    dev-server reload. An unguarded second import would then raise at
    *import time*, crashing whatever imported `guardrails.audit` — every
    guardrail's audit trail and metrics would go down together, an
    availability incident far worse than the metric collision itself.
    Reusing the already-registered collector keeps the metric singular
    (matching every earlier import's effect) and makes a second import a
    no-op instead of a crash.
    """
    try:
        return factory(name, documentation, labelnames, **kwargs)
    except ValueError:
        existing = REGISTRY._names_to_collectors.get(name)
        if existing is None:
            raise
        return existing  # type: ignore[return-value]


GUARDRAIL_DECISIONS = _register(
    Counter,
    "nufi_guardrail_decisions_total",
    "Guardrail decisions by control and action.",
    ("control", "risk", "action", "enforced"),
)
GUARDRAIL_LATENCY = _register(
    Histogram,
    "nufi_guardrail_latency_seconds",
    "Time spent inside a guardrail control.",
    ("control",),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0),
)
GUARDRAIL_ENABLED = _register(
    Gauge,
    "nufi_guardrail_enabled",
    "1 when a control is enabled and enforcing, 0 otherwise.",
    ("control", "mode"),
)
GUARDRAIL_DEGRADED = _register(
    Gauge,
    "nufi_guardrail_degraded",
    "1 while a control is failing open because its detector is unavailable.",
    ("control",),
)

_CONTEXT_KEYS = ("key_alias", "team_id", "model", "policy_digest")
_LABEL_KEYS = ("control", "risk", "action")
_LABEL_SHAPE = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")


class AuditRecordError(RuntimeError):
    """`record` could not instrument or attach an event.

    Raised — never swallowed — so a broken metadata shape or a garbage
    hand-built event surfaces to the caller instead of vanishing as a
    successful-looking no-op.
    """


# Metadata key carrying the guardrail audit trail to the callback loggers.
# Namespaced with `nufi_` deliberately: litellm consumes or filters keys it
# recognises, and both `guardrail_information` and
# `standard_logging_guardrail_information` were measured absent from
# `litellm_params["metadata"]` downstream. A key litellm has no meaning for
# survives — this is the same mechanism `nufi_grounded_verified` already
# relies on.
NUFI_EVENTS_KEY = "nufi_guardrail_events"


def _build_audit_logger() -> logging.Logger:
    """A logger the audit trail owns, independent of litellm's verbosity.

    `verbose_proxy_logger.info` is swallowed unless `LITELLM_LOG=INFO`, which
    is unset by default — measured: the decision counter incremented while no
    line reached the container log. Hanging the audit trail off the proxy's
    global log level means a routine verbosity change silently deletes it,
    which is the failure this subsystem exists to prevent.

    `propagate = False` so litellm's root configuration cannot re-suppress it,
    and the level is pinned to INFO here rather than inherited.
    """
    log = logging.getLogger("nufi.guardrail.audit")
    log.setLevel(logging.INFO)
    log.propagate = False
    if not log.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(message)s"))
        log.addHandler(handler)
    return log


AUDIT_LOG = _build_audit_logger()


def log_event(event: dict[str, Any]) -> None:
    """Emit one event as single-line JSON, prefixed for grepping by event_id.

    This is the only route measured to reach a durable store. Request metadata
    does not carry a guardrail event to any logging backend in litellm
    1.83.10 — three separate keys were tried and all were absent downstream
    (see the comment at the call site in entrypoints._emit).
    """
    AUDIT_LOG.info("nufi_guardrail_event %s", json.dumps(event, sort_keys=True))


def new_event_id() -> str:
    """`grd_` + 26 lowercase base32 characters, drawn from 128 bits of
    `os.urandom`.

    16 random bytes is 128 bits; base32 (5 bits/char) needs ceil(128/5) = 26
    data characters, padded to the next multiple of 8 with 6 trailing `=`
    (verified: `base64.b32encode(os.urandom(16))` is always exactly 32 chars,
    26 of them data). `[:26]` is therefore a no-op on every real call — kept
    as an explicit guarantee of the documented shape rather than an implicit
    one.
    """
    raw = base64.b32encode(os.urandom(16)).decode("ascii").rstrip("=").lower()
    return f"grd_{raw[:26]}"


def _safe_label(value: str | None) -> str | None:
    """Refuse to copy a string into the event unless it is identifier-shaped.

    `control`, `risk`, each `transforms` entry, and each finding's
    `detector`/`entity` are all meant to be fixed, closed-set labels —
    control ids from `policy.yaml`, risk codes, obfuscation-evidence tags,
    detector names, entity-type categories — never matched text. Every
    current producer of these values happens to honour that (every scanner
    and `policy.py` were read directly to confirm it; see the task report),
    but `_safe_reason` below exists precisely because "no producer
    currently violates this" is not the same claim as "this module
    enforces it". Patching each of these routes individually would repeat
    the mistake `_safe_reason` was written to fix — a guard placed next to
    today's known-safe producers survives only until a sixth route is
    added, or a scanner starts putting the matched substring into `entity`
    instead of its category, and nothing here would notice.

    A matched secret is not identifier-shaped: an email address has an
    `@`, a quoted span has spaces, an API key or a decoded payload can
    carry arbitrary Unicode. None of that survives
    `^[A-Za-z0-9_.:-]{1,64}$`, so replacing anything that fails the check
    with the literal `"UNSAFE_LABEL"` closes every one of these routes at
    once — including the one nobody has written a producer for yet —
    rather than trusting each individual producer never to regress.

    `None` passes through unchanged: it is `Finding.entity`'s legitimate
    "no entity classified" value (injection and coverage_gap findings never
    set one), not a value to sanitise.
    """
    if value is None:
        return None
    if _LABEL_SHAPE.match(value):
        return value
    return "UNSAFE_LABEL"


def _safe_reason(decision: Decision) -> str:
    """Rebuild `reason` from structured `Finding` fields rather than trusting
    `decision.reason` verbatim.

    `policy.decide()` today only ever formats `reason` from
    `detector`/`score`/`source` — verified by reading `policy.py` directly —
    so the two currently agree. But nothing in THIS module enforces that
    agreement: a guard that lives only in the module that happens not to
    violate it survives exactly until someone edits the OTHER module to add
    a more descriptive reason (naming an entity value, quoting a span). That
    coupling — a constraint stated in one place, relied on from another —
    is the same shape that cost two fix rounds in Task 8. Rebuilding here
    means the no-text guarantee holds even if `policy.decide`'s `reason`
    format later changes to something less careful.

    `top` is picked the same way `policy.decide()` picks it — `max` over the
    same `findings` tuple `decide()` already narrowed to `crossed` before
    constructing the `Decision` — so this reproduces an identical string in
    the case that matters today, while no longer trusting the string itself.

    A `Decision` with no findings (the ALLOW paths in `policy._allow`) has
    its reason drawn from a closed set of literals — "control disabled", "no
    finding crossed threshold", "grounded hint honoured" — none of which can
    contain matched text, so those pass through unchanged.

    `top.detector` is passed through `_safe_label` before it goes into the
    string — rebuilding the reason from structured fields does not help if
    one of those fields is itself untrusted free text (caught by this
    module's own test suite: a smuggled `Finding.detector` leaked straight
    through an earlier version of this function that skipped the sanitise
    step). `top.source.value` needs no such check: `Finding.source` is a
    `SpanSource` enum with exactly three members (user/untrusted/system),
    assigned from message role by `extract_spans`, never attacker-influenced
    text.
    """
    if not decision.findings:
        return decision.reason
    top = max(decision.findings, key=lambda f: f.score)
    return f"{_safe_label(top.detector)}={top.score:.2f} on {top.source.value} span"


def build_event(
    decision: Decision,
    transforms: tuple[str, ...],
    request_context: dict[str, Any],
    enforced: bool,
) -> dict[str, Any]:
    """Turn a `Decision` into a JSON-serialisable audit event.

    `request_context` is read through the fixed `_CONTEXT_KEYS` allow-list —
    never `**request_context` — so a key a caller did not intend to publish
    cannot ride along. A key absent from `request_context` is OMITTED from
    the event entirely rather than defaulted to `None`: a `None` copied into
    every event looks, on the reading side, identical to "we checked and
    there wasn't one", which is not the same claim as "we never looked".

    `reason` is rebuilt by `_safe_reason` rather than copied from
    `decision.reason` directly — see that function's docstring for why.
    `control`, `risk`, each `transforms` entry, and each finding's
    `detector`/`entity` are passed through `_safe_label` for the same
    reason — see its docstring.
    """
    return {
        "event_id": new_event_id(),
        "control": _safe_label(decision.control),
        "risk": _safe_label(decision.risk),
        "action": decision.action.value,
        "reason": _safe_reason(decision),
        "enforced": enforced,
        "transforms": [_safe_label(t) for t in transforms],
        "findings": [
            {
                "detector": _safe_label(finding.detector),
                "score": finding.score,
                "source": finding.source.value,
                "start": finding.start,
                "end": finding.end,
                "entity": _safe_label(finding.entity),
            }
            for finding in decision.findings
        ],
        **{key: request_context[key] for key in _CONTEXT_KEYS if key in request_context},
    }


def record(data: dict[str, Any], event: dict[str, Any]) -> None:
    """Attach `event` to `data["metadata"]["guardrail_information"]` and
    increment `GUARDRAIL_DECISIONS`.

    Never returns having silently failed to do either. `control`/`risk`/
    `action` are validated as non-empty strings and `enforced` as an actual
    bool before either lands in a Prometheus label — `None` is silently
    accepted by `prometheus_client` and rendered as the literal string
    "None" (verified against a live `Counter`), which would otherwise be a
    garbage series that looks like a real decision. The counter is
    incremented BEFORE the metadata attach is attempted, so a malformed
    `data["metadata"]` shape still leaves an accurate trace in Grafana even
    though this function goes on to raise for it — visibility must not
    depend on the caller's dict being well-formed.
    """
    if not isinstance(data, dict):
        raise AuditRecordError(f"record: data must be a dict, got {type(data).__name__}")

    for key in _LABEL_KEYS:
        value = event.get(key)
        if not isinstance(value, str) or not value:
            raise AuditRecordError(
                f"record: event[{key!r}] must be a non-empty str, got {value!r}"
            )

    enforced = event.get("enforced")
    if not isinstance(enforced, bool):
        raise AuditRecordError(f"record: event['enforced'] must be a bool, got {enforced!r}")

    GUARDRAIL_DECISIONS.labels(
        control=event["control"],
        risk=event["risk"],
        action=event["action"],
        enforced=str(enforced).lower(),
    ).inc()

    metadata = data.setdefault("metadata", {})
    if not isinstance(metadata, dict):
        raise AuditRecordError(
            f"record: data['metadata'] must be a dict, got {type(metadata).__name__}"
        )

    bucket = metadata.setdefault("guardrail_information", [])
    if not isinstance(bucket, list):
        raise AuditRecordError(
            "record: metadata['guardrail_information'] must be a list, "
            f"got {type(bucket).__name__}"
        )
    bucket.append(event)

    # Second, namespaced copy. `guardrail_information` above is OURS but shares
    # a name with keys litellm recognises, and neither it nor
    # `standard_logging_guardrail_information` survives into
    # `litellm_params["metadata"]` — measured on the live stack, both absent
    # from the spend-log row and from the Langfuse observation, while
    # `nufi_grounded_verified` (a key litellm has no meaning for, written to
    # the same dict from the same hook) arrives intact.
    #
    # So the trail is carried on a key litellm cannot claim. This is the only
    # copy proven to reach a durable store; the two above are kept because
    # in-process consumers and the LiteLLM helper read them.
    mirror = metadata.setdefault(NUFI_EVENTS_KEY, [])
    if not isinstance(mirror, list):
        raise AuditRecordError(
            f"record: metadata[{NUFI_EVENTS_KEY!r}] must be a list, "
            f"got {type(mirror).__name__}"
        )
    mirror.append(event)


def canonical_transforms(items: list[Canonical]) -> tuple[str, ...]:
    """Dedup transform labels across every span's `Canonical`, preserving
    the order each first appeared in.

    `Canonical.transforms` carries only evidence-of-obfuscation labels (see
    `canonical.py` — "unicode_tags", "bidi", "invisible", "nfkc",
    "homoglyph", "base64"), never decoded text, so this stays a label-only
    aggregation the same way the rest of this module is.
    """
    seen: list[str] = []
    for item in items:
        for transform in item.transforms:
            if transform not in seen:
                seen.append(transform)
    return tuple(seen)
