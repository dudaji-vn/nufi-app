import pytest
from guardrails.policy import Policy, _parse_control, decide
from guardrails.types import Action, Finding, SpanSource

_ALL_THRESHOLDS = {"user": 0.5, "untrusted": 0.5, "system": 1.01}


@pytest.fixture
def policy(policy_path):
    return Policy.load(policy_path)


def _finding(score: float, source: SpanSource = SpanSource.USER) -> Finding:
    return Finding(
        risk="LLM01", detector="test", score=score, source=source, start=0, end=1
    )


def test_loads_every_control(policy):
    assert set(policy.controls) == {"G1", "G2a", "G2b", "G3", "G4"}


def test_digest_is_stable_and_short(policy, policy_path):
    assert policy.digest() == Policy.load(policy_path).digest()
    assert len(policy.digest()) == 12


def test_mandatory_ids(policy):
    assert set(policy.mandatory_ids()) == {"G1", "G4"}


def test_score_below_threshold_is_allowed(policy):
    decision = decide(policy.control("G1"), [_finding(0.10)], grounded=False)

    assert decision.action is Action.ALLOW


def test_user_span_above_user_threshold_blocks(policy):
    decision = decide(policy.control("G1"), [_finding(0.95)], grounded=False)

    assert decision.action is Action.BLOCK
    assert decision.risk == "LLM01"


def test_untrusted_span_blocks_at_a_lower_score_than_user(policy):
    control = policy.control("G1")
    user = decide(control, [_finding(0.60, SpanSource.USER)], grounded=False)
    untrusted = decide(control, [_finding(0.60, SpanSource.UNTRUSTED)], grounded=False)

    assert user.action is Action.ALLOW
    assert untrusted.action is Action.BLOCK


def test_system_spans_are_never_flagged(policy):
    decision = decide(policy.control("G1"), [_finding(1.0, SpanSource.SYSTEM)], grounded=False)

    assert decision.action is Action.ALLOW


def test_logging_only_mode_downgrades_a_block_to_log(policy):
    control = policy.control("G1")
    assert control.mode == "logging_only"

    decision = decide(control, [_finding(0.99)], grounded=False)

    assert decision.action is Action.BLOCK

    enforcing = control.with_mode("pre_call")
    assert decide(enforcing, [_finding(0.99)], grounded=False).action is Action.BLOCK


def test_grounded_hint_suppresses_redaction_when_the_control_respects_it(policy):
    control = policy.control("G2b")
    finding = Finding(
        risk="LLM02", detector="presidio", score=0.9,
        source=SpanSource.UNTRUSTED, start=0, end=5, entity="EMAIL_ADDRESS",
    )

    assert decide(control, [finding], grounded=False).action is Action.REDACT
    assert decide(control, [finding], grounded=True).action is Action.ALLOW


def test_grounded_hint_is_ignored_by_controls_that_do_not_respect_it(policy):
    decision = decide(policy.control("G1"), [_finding(0.99)], grounded=True)

    assert decision.action is Action.BLOCK


def test_disabled_control_allows_everything(policy):
    control = policy.control("G1").with_enabled(False)

    assert decide(control, [_finding(1.0)], grounded=False).action is Action.ALLOW


def test_decision_carries_only_the_findings_that_crossed_threshold(policy):
    findings = [_finding(0.10), _finding(0.99)]

    decision = decide(policy.control("G1"), findings, grounded=False)

    assert len(decision.findings) == 1
    assert decision.findings[0].score == 0.99


def test_typo_in_a_threshold_key_is_refused_not_silently_ignored():
    """A typo must stop the proxy, not leave a control that never fires.

    `usr:` instead of `user:` previously defaulted all three sources to the
    unreachable 1.01, so the control loaded, reported enabled, and blocked
    nothing — the exact silent-decay failure this design exists to prevent.
    """
    body = {"risk": "LLM01", "thresholds": {"usr": 0.5, "untrusted": 0.5, "system": 1.01}}

    with pytest.raises(ValueError, match="unknown threshold key"):
        _parse_control("G1", body)


def test_missing_threshold_is_refused():
    body = {"risk": "LLM01", "thresholds": {"user": 0.5}}

    with pytest.raises(ValueError, match="missing threshold"):
        _parse_control("G1", body)


def test_missing_risk_names_the_control():
    with pytest.raises(ValueError, match="G7: missing required key 'risk'"):
        _parse_control("G7", {"thresholds": _ALL_THRESHOLDS})


def test_unknown_action_names_the_control():
    body = {"risk": "LLM01", "action": "detonate", "thresholds": _ALL_THRESHOLDS}

    with pytest.raises(ValueError, match="G1: unknown action"):
        _parse_control("G1", body)


def test_unknown_control_id_names_what_is_available(policy):
    with pytest.raises(KeyError, match="policy declares"):
        policy.control("G99")


def test_mandatory_ids_is_ordered(policy):
    assert policy.mandatory_ids() == tuple(sorted(policy.mandatory_ids()))


def test_fails_closed_reflects_the_policy(policy):
    assert policy.control("G1").fails_closed is True
    assert policy.control("G2a").fails_closed is False


def test_decision_risk_comes_from_the_control_not_the_finding(policy):
    mismatched = Finding(
        risk="LLM99", detector="test", score=0.99, source=SpanSource.USER, start=0, end=1
    )

    decision = decide(policy.control("G1"), [mismatched], grounded=False)

    assert decision.risk == "LLM01"


def test_detector_thresholds_defaults_to_empty_when_absent():
    """A control with no `detector_thresholds` key must still parse.

    Unlike `thresholds`, which is mandatory per SpanSource, per-detector
    overrides are optional — most detectors are priced purely by source.
    """
    control = _parse_control("G1", {"risk": "LLM01", "thresholds": _ALL_THRESHOLDS})

    assert control.detector_thresholds == {}


def test_coverage_gap_is_ignored_by_g1_by_default(policy):
    """The scanner's own `coverage_gap` finding must not silently block.

    G1's per-source `user` threshold is 0.90; a coverage_gap Finding always
    scores 1.0 (guardrails/scanners/injection.py), so if `decide` compared it
    against the plain source threshold instead of the detector override, an
    unscanned span would BLOCK the instant G1 is flipped from logging_only to
    pre_call — silently turning "we could not check this" into "we blocked
    this", the opposite of the shadow-mode default recorded in policy.yaml.
    """
    gap = Finding(
        risk="LLM01", detector="coverage_gap", score=1.0,
        source=SpanSource.USER, start=0, end=1,
    )

    decision = decide(policy.control("G1"), [gap], grounded=False)

    assert decision.action is Action.ALLOW


def test_detector_threshold_overrides_the_source_threshold_for_that_detector():
    """`decide` must consult `detector_thresholds` before falling back to
    the per-source `thresholds`, and only for findings from that detector."""
    body = {
        "risk": "LLM01",
        "action": "block",
        "thresholds": {"user": 0.99, "untrusted": 0.99, "system": 1.01},
        "detector_thresholds": {"coverage_gap": 0.5},
    }
    control = _parse_control("G1", body)

    gap = Finding(
        risk="LLM01", detector="coverage_gap", score=0.6,
        source=SpanSource.USER, start=0, end=1,
    )
    ordinary = Finding(
        risk="LLM01", detector="injection", score=0.6,
        source=SpanSource.USER, start=0, end=1,
    )

    # 0.6 is below the plain 0.99 source threshold but above the 0.5
    # detector-specific override, so only the coverage_gap finding blocks.
    assert decide(control, [gap], grounded=False).action is Action.BLOCK
    assert decide(control, [ordinary], grounded=False).action is Action.ALLOW


def test_typo_in_a_detector_threshold_key_is_refused_not_silently_ignored():
    """A misspelled detector_thresholds key must stop the proxy, exactly like
    a misspelled `thresholds` key already does.

    `coverge_gap` (missing an `a`) previously parsed cleanly and was simply
    never consulted: the real `coverage_gap` finding (always score=1.0) fell
    back to the plain per-source `thresholds`, and G1's `user` threshold
    (0.90) means every unscanned span would BLOCK the instant G1 enforces —
    the exact opposite of the shadow-mode-ignore default this key exists to
    express, with no error and no signal anywhere that the override never
    applied.
    """
    body = {
        "risk": "LLM01",
        "thresholds": _ALL_THRESHOLDS,
        "detector_thresholds": {"coverge_gap": 1.01},
    }

    with pytest.raises(ValueError, match="unknown detector_thresholds key"):
        _parse_control("G1", body)


def test_typo_in_a_detector_threshold_key_names_the_control_and_valid_set():
    body = {
        "risk": "LLM01",
        "thresholds": _ALL_THRESHOLDS,
        "detector_thresholds": {"coverge_gap": 1.01},
    }

    with pytest.raises(ValueError, match=r"G1:.*coverge_gap.*expected one of"):
        _parse_control("G1", body)


def test_the_shipped_policy_still_parses_with_detector_threshold_validation(policy):
    """Regression: the real coverage_gap: 1.01 entry in policy.yaml must be a
    known, accepted key — validation must not reject legitimate config."""
    assert policy.control("G1").detector_thresholds == {"coverage_gap": 1.01}


def test_presidio_detector_threshold_parses():
    """`PiiScanner` (guardrails/scanners/pii.py) reports its findings with
    `detector="presidio"`. A control that wants to price a presidio finding
    differently from the plain per-source threshold — e.g. G2a/G2b — must be
    able to declare `detector_thresholds: {presidio: ...}` without it being
    rejected as an unknown key."""
    body = {
        "risk": "LLM02",
        "thresholds": _ALL_THRESHOLDS,
        "detector_thresholds": {"presidio": 0.7},
    }

    control = _parse_control("G2a", body)

    assert control.detector_thresholds == {"presidio": 0.7}


def test_typo_in_the_presidio_detector_threshold_key_is_still_refused():
    """The guard must stay sharp after `presidio` is added to
    `_KNOWN_DETECTORS`: a near-miss spelling is still an unknown key, not a
    silently-inert override — same failure shape as `coverge_gap` above."""
    body = {
        "risk": "LLM02",
        "thresholds": _ALL_THRESHOLDS,
        "detector_thresholds": {"presidoo": 0.7},
    }

    with pytest.raises(ValueError, match=r"G2a:.*presidoo.*expected one of"):
        _parse_control("G2a", body)


@pytest.mark.parametrize("detector", ["secrets", "system_echo", "exfil"])
def test_pattern_scanner_detector_thresholds_parse(detector):
    """`guardrails.scanners.patterns` (Task 8) reports findings with
    `detector="secrets"`, `detector="system_echo"` and `detector="exfil"`.
    A policy declaring a `detector_thresholds` override for any one of them
    must load, exactly like the existing `presidio`/`coverage_gap` entries."""
    body = {
        "risk": "LLM05",
        "thresholds": _ALL_THRESHOLDS,
        "detector_thresholds": {detector: 0.75},
    }

    control = _parse_control("G4", body)

    assert control.detector_thresholds == {detector: 0.75}
