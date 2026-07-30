"""Tests for guardrails.audit: event shape, the no-leak guarantee, and the
Prometheus/metadata instrumentation `record` performs.

The brief's own five tests are kept (some strengthened) plus tests for every
failure mode named in the task brief's mandatory enumeration: a Decision with
no findings, a finding whose entity is None, `data["metadata"]` missing/None/
non-dict, `guardrail_information` present but non-list, a None Prometheus
label value, and duplicate metric registration on a second module import.
"""

from __future__ import annotations

import importlib.util
import json

import pytest
from guardrails.audit import (
    GUARDRAIL_DECISIONS,
    GUARDRAIL_DEGRADED,
    GUARDRAIL_ENABLED,
    GUARDRAIL_LATENCY,
    AuditRecordError,
    build_event,
    canonical_transforms,
    new_event_id,
    record,
)
from guardrails.types import Action, Canonical, Decision, Finding, SpanSource


def _decision(action: Action = Action.BLOCK) -> Decision:
    finding = Finding(
        risk="LLM01", detector="injection", score=0.97,
        source=SpanSource.UNTRUSTED, start=0, end=10,
    )
    return Decision(
        action=action, control="G1", risk="LLM01",
        findings=(finding,), reason="injection=0.97 on untrusted span",
    )


def _counter_value(control: str, risk: str, action: str, enforced: bool) -> float:
    return GUARDRAIL_DECISIONS.labels(
        control=control, risk=risk, action=action, enforced=str(enforced).lower()
    )._value.get()


# ---------------------------------------------------------------------------
# new_event_id
# ---------------------------------------------------------------------------


def test_event_id_has_the_expected_shape():
    event_id = new_event_id()

    assert event_id.startswith("grd_")
    assert len(event_id) == 30
    assert event_id[4:].islower()


def test_event_id_is_unique_across_many_calls():
    # A hardcoded or low-entropy tail would still satisfy the shape test
    # above. Generating a large batch and requiring them all distinct proves
    # os.urandom is actually being consumed, not a fixed string truncated.
    ids = {new_event_id() for _ in range(2000)}
    assert len(ids) == 2000


# ---------------------------------------------------------------------------
# build_event — happy path and request-context handling
# ---------------------------------------------------------------------------


def test_event_records_the_decision_and_context():
    event = build_event(
        _decision(),
        transforms=("homoglyph",),
        request_context={
            "key_alias": "chat-app", "team_id": "t1", "model": "nufi",
            "policy_digest": "abc123",
        },
        enforced=True,
    )

    assert event["control"] == "G1"
    assert event["risk"] == "LLM01"
    assert event["action"] == "block"
    assert event["reason"] == "injection=0.97 on untrusted span"
    assert event["enforced"] is True
    assert event["transforms"] == ["homoglyph"]
    assert event["key_alias"] == "chat-app"
    assert event["team_id"] == "t1"
    assert event["model"] == "nufi"
    assert event["policy_digest"] == "abc123"
    assert event["event_id"].startswith("grd_")


def test_event_omits_absent_request_context_keys_rather_than_defaulting_to_none():
    # A key request_context never supplied must not appear at all — not even
    # as an explicit `None` — so a downstream reader cannot mistake "we
    # looked and there wasn't one" for "we never checked".
    event = build_event(_decision(), transforms=(), request_context={}, enforced=False)

    for key in ("key_alias", "team_id", "model", "policy_digest"):
        assert key not in event


def test_event_never_leaks_arbitrary_request_context_keys():
    # The allow-list must be read explicitly, never `**request_context`. A
    # regression to full-dict spread would smuggle any key a caller passes —
    # including, worst case, raw prompt text under an unexpected key — into
    # the audit trail this module exists to keep clean.
    canary = "CANARY-do-not-leak-a92f1c"
    event = build_event(
        _decision(),
        transforms=(),
        request_context={"key_alias": "chat-app", "prompt": canary, "user_id": "u1"},
        enforced=True,
    )

    assert "prompt" not in event
    assert "user_id" not in event
    assert canary not in json.dumps(event)


def test_event_with_no_findings_has_an_empty_findings_list():
    decision = Decision(
        action=Action.ALLOW, control="G2", risk="LLM02",
        findings=(), reason="no finding crossed threshold",
    )

    event = build_event(decision, transforms=(), request_context={}, enforced=True)

    assert event["findings"] == []
    assert event["control"] == "G2"
    assert event["action"] == "allow"


def test_event_finding_with_none_entity_serialises_as_null():
    # Finding.entity defaults to None for detectors that don't classify an
    # entity type (injection, coverage_gap). The event must carry that
    # through as JSON null, not crash and not silently invent a value.
    event = build_event(_decision(), transforms=(), request_context={}, enforced=True)

    assert event["findings"][0]["entity"] is None
    # And the event must still round-trip through JSON with that None in it.
    reloaded = json.loads(json.dumps(event))
    assert reloaded["findings"][0]["entity"] is None


# ---------------------------------------------------------------------------
# build_event — the no-leak guarantee, proven against a fully-populated event
# ---------------------------------------------------------------------------


def test_event_records_finding_detail_without_the_raw_text():
    event = build_event(
        _decision(), transforms=(), request_context={}, enforced=False,
    )

    finding = event["findings"][0]
    assert finding["detector"] == "injection"
    assert finding["score"] == 0.97
    assert finding["source"] == "untrusted"
    assert finding["start"] == 0
    assert finding["end"] == 10
    assert finding["entity"] is None
    assert "text" not in finding


def test_build_event_signature_has_no_channel_for_raw_span_text():
    """Structural proof, not an assertion about behaviour: `build_event`
    takes `decision`, `transforms`, `request_context` and `enforced` — no
    `span`, `text`, or `spans` parameter — so there is no argument through
    which a caller could hand it raw prompt/response text even by mistake.
    Combined with `Finding` and `Decision` themselves carrying no text field
    (see guardrails/types.py — Finding has no `text` attribute at all), the
    only remaining channel for a leak is `request_context`, which is what
    `test_event_never_leaks_arbitrary_request_context_keys` closes.
    """
    import inspect

    params = set(inspect.signature(build_event).parameters)
    assert params == {"decision", "transforms", "request_context", "enforced"}
    assert not hasattr(Finding, "text")
    assert not hasattr(Decision, "text")


def test_no_span_text_or_decoded_payload_anywhere_in_a_fully_populated_event():
    """The trap this test is written to avoid: a bare `"text" not in event`
    assertion passes trivially against a stub that returns an empty dict.
    So first prove the event is genuinely populated (every expected field,
    non-empty, matching the fixture) and only then prove that a canary
    string standing in for matched PII text — placed only where a caller
    could plausibly smuggle it in, `request_context`, since `Finding` and
    `Decision` have no text field for it to ride in on — appears nowhere in
    the serialised event, checked as JSON text rather than one field at a
    time so no nesting could hide a leak.
    """
    canary = "sun@dudaji.com-SECRET-PAYLOAD"
    finding = Finding(
        risk="LLM02", detector="presidio", score=0.95,
        source=SpanSource.USER, start=11, end=25, entity="EMAIL_ADDRESS",
    )
    decision = Decision(
        action=Action.REDACT, control="G2a", risk="LLM02",
        findings=(finding,), reason="presidio=0.95 on user span",
    )

    event = build_event(
        decision,
        transforms=("base64",),
        request_context={"key_alias": "chat-app", "model": "nufi", "note": canary},
        enforced=True,
    )

    # Prove completeness first — every expected field is present and correct.
    assert event["control"] == "G2a"
    assert event["risk"] == "LLM02"
    assert event["action"] == "redact"
    assert event["reason"] == "presidio=0.95 on user span"
    assert event["enforced"] is True
    assert event["transforms"] == ["base64"]
    assert event["key_alias"] == "chat-app"
    assert event["model"] == "nufi"
    assert len(event["findings"]) == 1
    f = event["findings"][0]
    assert (f["detector"], f["score"], f["source"], f["start"], f["end"], f["entity"]) == (
        "presidio", 0.95, "user", 11, 25, "EMAIL_ADDRESS",
    )

    # Only now check the canary — smuggled in under an unlisted
    # request_context key — is not present anywhere in the serialised event.
    assert "note" not in event
    assert canary not in json.dumps(event)


def test_event_reason_never_carries_matched_text_even_if_decisions_reason_did():
    """`policy.decide()` today only ever formats `reason` from
    detector/score/source — but nothing in `build_event` enforced that on
    its own until now. Build a `Decision` whose `reason` DOES carry a raw
    secret (standing in for a future, more descriptive `policy.decide()`
    that names an entity value or quotes a span) and prove `build_event`
    rebuilds `reason` from the finding's structured fields instead of
    trusting the string verbatim.

    Checked against completeness first, same as every other no-leak test in
    this file: an implementation that returns an empty dict — or one that
    merely deletes the `reason` key — would pass a bare "secret not in
    event" check trivially, so the full expected shape is asserted before
    the secret's absence is.
    """
    secret = "sun@dudaji.com"
    finding = Finding(
        risk="LLM02", detector="presidio", score=0.97,
        source=SpanSource.USER, start=11, end=25, entity="EMAIL_ADDRESS",
    )
    decision = Decision(
        action=Action.REDACT, control="G2a", risk="LLM02",
        findings=(finding,), reason=f"presidio=0.97 matched {secret} verbatim",
    )

    event = build_event(
        decision, transforms=(), request_context={"model": "nufi"}, enforced=True,
    )

    # Prove completeness first.
    assert event["control"] == "G2a"
    assert event["risk"] == "LLM02"
    assert event["action"] == "redact"
    assert event["enforced"] is True
    assert event["model"] == "nufi"
    assert len(event["findings"]) == 1
    f = event["findings"][0]
    assert (f["detector"], f["score"], f["source"], f["entity"]) == (
        "presidio", 0.97, "user", "EMAIL_ADDRESS",
    )

    # `reason` must be rebuilt from the finding's structured fields — the
    # exact format policy.decide() itself uses — not whatever
    # `decision.reason` said.
    assert event["reason"] == "presidio=0.97 on user span"
    assert secret not in event["reason"]
    assert secret not in json.dumps(event)


def test_event_reason_passes_through_unchanged_for_a_finding_free_decision():
    # A Decision with no findings draws its reason from a closed set of
    # literals in policy._allow ("control disabled", "no finding crossed
    # threshold", "grounded hint honoured") — none can carry matched text,
    # so _safe_reason must leave these untouched rather than mangling them.
    decision = Decision(
        action=Action.ALLOW, control="G2", risk="LLM02",
        findings=(), reason="no finding crossed threshold",
    )

    event = build_event(decision, transforms=(), request_context={}, enforced=True)

    assert event["reason"] == "no finding crossed threshold"


# ---------------------------------------------------------------------------
# build_event — every label route, not just reason, must refuse matched text
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("field", ["control", "risk", "transforms", "detector", "entity"])
def test_a_matched_secret_smuggled_into_any_label_field_is_replaced_not_leaked(field):
    """`control`, `risk`, each `transforms` entry, and each finding's
    `detector`/`entity` are all meant to be fixed, closed-set labels — never
    matched text. Every current producer honours that today (a scanner
    setting `entity` to a category, `policy.py` setting `control`/`risk`
    from `policy.yaml`), but that is a fact about today's producers, not a
    guarantee this module enforces on its own. Simulate a future producer
    that puts a matched secret into each of these five routes in turn — one
    parametrised case per route — and confirm `_safe_label` closes all five,
    not just the one route this task happened to probe first (`reason`).

    Checked against completeness first, same shape as every other no-leak
    test in this file: asserts the untargeted fields kept their legitimate
    values and the full event shape is present, so this cannot pass against
    a stub that returns an empty or partially-deleted dict.
    """
    secret = "sun@dudaji.com"
    control = secret if field == "control" else "G2b"
    risk = secret if field == "risk" else "LLM02"
    transforms = (secret,) if field == "transforms" else ("homoglyph",)
    detector = secret if field == "detector" else "presidio"
    entity = secret if field == "entity" else "EMAIL_ADDRESS"

    finding = Finding(
        risk="LLM02", detector=detector, score=0.9,
        source=SpanSource.USER, start=0, end=10, entity=entity,
    )
    decision = Decision(
        action=Action.REDACT, control=control, risk=risk,
        findings=(finding,), reason="presidio=0.90 on user span",
    )

    event = build_event(decision, transforms=transforms, request_context={}, enforced=True)

    # Prove completeness first. `_safe_reason` rebuilds `reason` from the
    # finding's own (now-sanitised) `detector`, ignoring `decision.reason`
    # entirely whenever there is a finding — so when the smuggled secret IS
    # the detector, it must show up here as UNSAFE_LABEL too, not leak
    # through this second, independent path into the reason string.
    assert event["action"] == "redact"
    assert event["enforced"] is True
    expected_reason = (
        "UNSAFE_LABEL=0.90 on user span" if field == "detector" else "presidio=0.90 on user span"
    )
    assert event["reason"] == expected_reason
    assert len(event["findings"]) == 1
    f = event["findings"][0]
    assert (f["score"], f["source"], f["start"], f["end"]) == (0.9, "user", 0, 10)

    # The targeted route was replaced; the other four kept their legitimate
    # values — proving this is a per-field shape check, not a blanket
    # "something looked wrong, drop everything" reaction.
    assert event["control"] == ("UNSAFE_LABEL" if field == "control" else "G2b")
    assert event["risk"] == ("UNSAFE_LABEL" if field == "risk" else "LLM02")
    assert event["transforms"] == (
        ["UNSAFE_LABEL"] if field == "transforms" else ["homoglyph"]
    )
    assert f["detector"] == ("UNSAFE_LABEL" if field == "detector" else "presidio")
    assert f["entity"] == ("UNSAFE_LABEL" if field == "entity" else "EMAIL_ADDRESS")

    assert secret not in json.dumps(event)


def test_ordinary_labels_pass_through_byte_identical():
    """A guard that mangles legitimate labels is worse than no guard: `G1`
    would silently vanish from every dashboard and audit record. Confirm
    `_safe_label` is a no-op for every real label value this codebase
    actually produces today.
    """
    finding = Finding(
        risk="LLM02", detector="presidio", score=0.9,
        source=SpanSource.USER, start=0, end=10, entity="EMAIL_ADDRESS",
    )
    decision = Decision(
        action=Action.REDACT, control="G2b", risk="LLM02",
        findings=(finding,), reason="presidio=0.90 on user span",
    )

    event = build_event(
        decision, transforms=("homoglyph",), request_context={}, enforced=True,
    )

    assert event["control"] == "G2b"
    assert event["risk"] == "LLM02"
    assert event["transforms"] == ["homoglyph"]
    assert event["findings"][0]["detector"] == "presidio"
    assert event["findings"][0]["entity"] == "EMAIL_ADDRESS"


# ---------------------------------------------------------------------------
# record — happy path
# ---------------------------------------------------------------------------


def test_record_attaches_the_event_to_request_metadata():
    data: dict = {}
    event = build_event(_decision(), transforms=(), request_context={}, enforced=True)

    record(data, event)

    assert data["metadata"]["guardrail_information"][0]["control"] == "G1"


def test_record_appends_rather_than_overwrites():
    data: dict = {}
    record(data, build_event(_decision(), (), {}, True))
    record(data, build_event(_decision(Action.LOG), (), {}, False))

    bucket = data["metadata"]["guardrail_information"]
    assert len(bucket) == 2
    assert bucket[0]["action"] == "block"
    assert bucket[1]["action"] == "log"


def test_record_reuses_existing_metadata_dict_rather_than_replacing_it():
    data: dict = {"metadata": {"unrelated_key": "keep-me"}}
    record(data, build_event(_decision(), (), {}, True))

    assert data["metadata"]["unrelated_key"] == "keep-me"
    assert len(data["metadata"]["guardrail_information"]) == 1


def test_record_increments_the_guardrail_decisions_counter():
    before = _counter_value("G1", "LLM01", "block", True)

    record({}, build_event(_decision(), (), {}, True))

    after = _counter_value("G1", "LLM01", "block", True)
    assert after == before + 1


# ---------------------------------------------------------------------------
# record — the metadata shape must never be silently dropped
# ---------------------------------------------------------------------------


def test_record_raises_when_metadata_is_none():
    # `data.setdefault("metadata", {})` returns the EXISTING value when the
    # key is already present — even if that value is None — so a caller
    # that pre-seeds `data["metadata"] = None` (a real shape litellm's own
    # request dict can carry) must not have its event silently dropped.
    data = {"metadata": None}

    with pytest.raises(AuditRecordError):
        record(data, build_event(_decision(), (), {}, True))


def test_record_raises_when_metadata_is_not_a_dict():
    data = {"metadata": "not-a-dict"}

    with pytest.raises(AuditRecordError):
        record(data, build_event(_decision(), (), {}, True))


def test_record_raises_when_guardrail_information_is_not_a_list():
    data = {"metadata": {"guardrail_information": "not-a-list"}}

    with pytest.raises(AuditRecordError):
        record(data, build_event(_decision(), (), {}, True))


def test_record_raises_when_data_itself_is_not_a_dict():
    with pytest.raises(AuditRecordError):
        record(None, build_event(_decision(), (), {}, True))  # type: ignore[arg-type]


def test_record_still_increments_the_counter_when_the_metadata_write_fails():
    # The decision counter is the independent visibility layer: it must not
    # go dark just because the caller's metadata dict is malformed. A metric
    # that only increments when the audit sink happens to be healthy would
    # let a broken metadata pipeline hide behind a dashboard that still
    # looks clean.
    before = _counter_value("G1", "LLM01", "block", True)
    data = {"metadata": None}

    with pytest.raises(AuditRecordError):
        record(data, build_event(_decision(), (), {}, True))

    after = _counter_value("G1", "LLM01", "block", True)
    assert after == before + 1


# ---------------------------------------------------------------------------
# record — a malformed hand-built event must not create a garbage metric series
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("field", ["control", "risk", "action"])
def test_record_rejects_a_none_label_value_instead_of_stringifying_it(field):
    # prometheus_client silently accepts `None` as a label value and renders
    # it as the literal string "None" — verified against a live Counter, not
    # assumed. That is a real "looks like success" outcome: a garbage
    # 3-character series appears in Grafana with no error anywhere. record()
    # must refuse instead of instrumenting garbage.
    event = build_event(_decision(), (), {}, True)
    event[field] = None

    with pytest.raises(AuditRecordError):
        record({}, event)


def test_record_rejects_a_non_bool_enforced_value():
    event = build_event(_decision(), (), {}, True)
    event["enforced"] = "true"  # a string, not a bool

    with pytest.raises(AuditRecordError):
        record({}, event)


# ---------------------------------------------------------------------------
# canonical_transforms
# ---------------------------------------------------------------------------


def test_canonical_transforms_dedupes_preserving_first_occurrence_order():
    items = [
        Canonical(text="a", transforms=("base64", "homoglyph")),
        Canonical(text="b", transforms=("homoglyph", "nfkc")),
        Canonical(text="c", transforms=("base64",)),
    ]

    assert canonical_transforms(items) == ("base64", "homoglyph", "nfkc")


def test_canonical_transforms_of_no_canonicals_is_empty():
    assert canonical_transforms([]) == ()


def test_canonical_transforms_of_untouched_text_is_empty():
    items = [Canonical(text="plain text", transforms=())]

    assert canonical_transforms(items) == ()


# ---------------------------------------------------------------------------
# Prometheus collectors exist with the shape Task 10's integration expects
# ---------------------------------------------------------------------------


def test_guardrail_metrics_are_the_expected_type_and_carry_a_control_label():
    assert GUARDRAIL_DECISIONS._type == "counter"
    assert set(GUARDRAIL_DECISIONS._labelnames) == {"control", "risk", "action", "enforced"}

    assert GUARDRAIL_LATENCY._type == "histogram"
    assert set(GUARDRAIL_LATENCY._labelnames) == {"control"}

    assert GUARDRAIL_ENABLED._type == "gauge"
    assert set(GUARDRAIL_ENABLED._labelnames) == {"control", "mode"}

    assert GUARDRAIL_DEGRADED._type == "gauge"
    assert set(GUARDRAIL_DEGRADED._labelnames) == {"control"}


def test_reimporting_the_module_does_not_crash_on_duplicate_metric_registration():
    # Prometheus's default registry raises ValueError if the same metric
    # name is registered twice (verified directly against a live
    # CollectorRegistry). A second execution of this module's top level —
    # a duplicate import under a different qualified name, or a dev-server
    # reload — must not crash the whole guardrail pipeline just because the
    # metrics it defines already exist.
    import guardrails.audit as audit

    spec = importlib.util.spec_from_file_location(
        "guardrails_audit_duplicate_for_test", audit.__file__
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)

    spec.loader.exec_module(module)  # must not raise ValueError

    # And it must reuse the SAME collector rather than silently producing a
    # second, disconnected one that Grafana would never see updates to.
    assert module.GUARDRAIL_DECISIONS is audit.GUARDRAIL_DECISIONS
    assert module.GUARDRAIL_LATENCY is audit.GUARDRAIL_LATENCY
    assert module.GUARDRAIL_ENABLED is audit.GUARDRAIL_ENABLED
    assert module.GUARDRAIL_DEGRADED is audit.GUARDRAIL_DEGRADED
