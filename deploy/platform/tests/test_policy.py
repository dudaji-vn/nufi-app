import pytest
from guardrails.policy import Policy, decide
from guardrails.types import Action, Finding, SpanSource


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
