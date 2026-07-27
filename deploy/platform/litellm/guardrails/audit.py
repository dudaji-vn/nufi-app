"""Normalised guardrail events and Prometheus instrumentation.

Events never carry the matched text — only offsets, scores and entity types —
so the audit trail cannot itself become a disclosure channel. `build_event`
reads `request_context` through a fixed key allow-list (never `**spread`), so
an unexpected key a caller passes in — a prompt, a user message — cannot ride
along into the audit trail either. `Finding.entity`, `Finding.detector` and
`Canonical.transforms` are all fixed category/evidence labels supplied by the
scanners and `guardrails.canonical` — never spans of user text — which is
what makes copying them into an event safe; see the task report for how that
is proven against each scanner, not merely assumed here. `decision.reason`
is the one field this module does NOT trust verbatim: `_safe_reason`
rebuilds it from the top finding's structured fields, because `reason`
staying text-free today is a property of `policy.decide()`'s current
implementation, not a constraint this module enforces on its own — the
guarantee must not depend on a fact that lives somewhere else.

`record` raises `AuditRecordError` rather than silently discarding an event
it cannot attach to request metadata. A dropped audit event that raises
nothing looks, from the caller's side, identical to a clean write — the same
invisible-failure shape this whole pipeline exists to prevent, one layer up,
in the audit trail itself.
"""

from __future__ import annotations

import base64
import os
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


class AuditRecordError(RuntimeError):
    """`record` could not instrument or attach an event.

    Raised — never swallowed — so a broken metadata shape or a garbage
    hand-built event surfaces to the caller instead of vanishing as a
    successful-looking no-op.
    """


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
    """
    if not decision.findings:
        return decision.reason
    top = max(decision.findings, key=lambda f: f.score)
    return f"{top.detector}={top.score:.2f} on {top.source.value} span"


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
    """
    return {
        "event_id": new_event_id(),
        "control": decision.control,
        "risk": decision.risk,
        "action": decision.action.value,
        "reason": _safe_reason(decision),
        "enforced": enforced,
        "transforms": list(transforms),
        "findings": [
            {
                "detector": finding.detector,
                "score": finding.score,
                "source": finding.source.value,
                "start": finding.start,
                "end": finding.end,
                "entity": finding.entity,
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
