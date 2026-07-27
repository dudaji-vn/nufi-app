import logging

import pytest
from guardrails import audit
from guardrails.health import StrictControlViolation, assert_controls, guardrail_status
from guardrails.policy import Policy


@pytest.fixture
def policy(policy_path):
    return Policy.load(policy_path)


def test_status_reports_every_control_with_its_mode(policy):
    status = guardrail_status(policy)

    assert status["policy_digest"] == policy.digest()
    assert status["controls"]["G1"]["mode"] == "logging_only"
    assert status["controls"]["G1"]["mandatory"] is True
    assert status["controls"]["G1"]["enforcing"] is False


def test_status_marks_enforcing_controls(policy_path):
    policy = Policy.load(policy_path)
    policy.controls["G1"] = policy.controls["G1"].with_mode("pre_call")

    assert guardrail_status(policy)["controls"]["G1"]["enforcing"] is True


def test_status_reflects_a_disabled_control(policy_path):
    """Anti-trap: a status report that hardcodes every control as healthy
    would still pass a test that only checks shape/keys. Disabling a real
    control and asserting `enabled`/`enforcing` both flip to False is what
    catches an implementation that reports every control as healthy
    regardless of its actual `ControlConfig.enabled` value.
    """
    policy = Policy.load(policy_path)
    policy.controls["G2a"] = policy.controls["G2a"].with_enabled(False)

    status = guardrail_status(policy)

    assert status["controls"]["G2a"]["enabled"] is False
    assert status["controls"]["G2a"]["enforcing"] is False


def test_disabled_mandatory_control_is_reported_as_a_violation(policy_path):
    policy = Policy.load(policy_path)
    policy.controls["G1"] = policy.controls["G1"].with_enabled(False)

    violations = assert_controls(policy)

    assert any("G1" in message for message in violations)


def test_non_mandatory_disabled_control_produces_no_violation(policy_path):
    """G2a is enabled but not mandatory (policy.yaml). Disabling it must not
    be reported as a violation — only MANDATORY controls are load-bearing
    for `strict_controls`. Guards against an implementation that flags any
    disabled control rather than checking `mandatory_ids()`.
    """
    policy = Policy.load(policy_path)
    assert policy.controls["G2a"].mandatory is False
    policy.controls["G2a"] = policy.controls["G2a"].with_enabled(False)

    assert assert_controls(policy) == []


def test_enabled_mandatory_controls_produce_no_violation(policy):
    assert assert_controls(policy) == []


def test_multiple_disabled_mandatory_controls_are_all_reported(policy_path):
    """policy.yaml declares two mandatory controls (G1, G4). Disabling both
    must surface both violations, not just the first one an implementation
    happens to check.
    """
    policy = Policy.load(policy_path)
    policy.controls["G1"] = policy.controls["G1"].with_enabled(False)
    policy.controls["G4"] = policy.controls["G4"].with_enabled(False)

    violations = assert_controls(policy)

    assert len(violations) == 2
    assert any("G1" in message for message in violations)
    assert any("G4" in message for message in violations)


def test_strict_mode_raises_instead_of_returning(policy_path):
    policy = Policy.load(policy_path)
    policy.strict_controls = True
    policy.controls["G4"] = policy.controls["G4"].with_enabled(False)

    with pytest.raises(StrictControlViolation):
        assert_controls(policy)


def test_strict_mode_does_not_raise_without_violations(policy_path):
    """`strict_controls: true` alone must not be sufficient to raise — only
    a real violation should. A blanket `if policy.strict_controls: raise`
    would fail every deployment that turns strict mode on with a clean
    policy, which is the opposite of what strict mode is for.
    """
    policy = Policy.load(policy_path)
    policy.strict_controls = True

    assert assert_controls(policy) == []


def test_strict_mode_error_names_every_disabled_mandatory_control(policy_path):
    policy = Policy.load(policy_path)
    policy.strict_controls = True
    policy.controls["G1"] = policy.controls["G1"].with_enabled(False)
    policy.controls["G4"] = policy.controls["G4"].with_enabled(False)

    with pytest.raises(StrictControlViolation) as exc_info:
        assert_controls(policy)

    assert "G1" in str(exc_info.value)
    assert "G4" in str(exc_info.value)


def test_assert_controls_sets_the_enabled_gauge_per_control(policy_path):
    """The Prometheus gauge is the signal that survives after the startup
    log scrolls away — this is the "where does an operator see it a week
    later" channel. Reads the real registry the way test_entrypoints.py
    does, rather than trusting that `assert_controls` merely returns the
    right list.
    """
    policy = Policy.load(policy_path)
    policy.controls["G2a"] = policy.controls["G2a"].with_enabled(False)

    assert_controls(policy)

    disabled_value = audit.GUARDRAIL_ENABLED.labels(
        control="G2a", mode=policy.controls["G2a"].mode
    )._value.get()
    assert disabled_value == 0

    enabled_control = policy.controls["G3"]
    assert enabled_control.enabled is True
    enabled_value = audit.GUARDRAIL_ENABLED.labels(
        control="G3", mode=enabled_control.mode
    )._value.get()
    assert enabled_value == (1 if enabled_control.mode != "logging_only" else 0)


def test_assert_controls_logs_a_violation_at_error_level(policy_path, caplog):
    """A violation that only lives in a Python list nobody reads is not
    "loud". `logger.error` is the channel a log-based alert can actually
    match on — verified here by reading the real log record rather than
    assuming the call happened.
    """
    policy = Policy.load(policy_path)
    policy.controls["G1"] = policy.controls["G1"].with_enabled(False)

    with caplog.at_level(logging.ERROR, logger="nufi.guardrails"):
        assert_controls(policy)

    assert any(
        record.levelno == logging.ERROR and "G1" in record.message
        for record in caplog.records
    )


def test_assert_controls_returns_list_of_str(policy_path):
    """The interface promises `list[str]` — a violation object that merely
    stringifies to something containing the control id (e.g. a dataclass
    with a good `__repr__`) would satisfy the brief's `"G1" in message`
    checks without actually being a `str`, defeating callers that log or
    join the list directly.
    """
    policy = Policy.load(policy_path)
    policy.controls["G1"] = policy.controls["G1"].with_enabled(False)

    violations = assert_controls(policy)

    assert all(isinstance(message, str) for message in violations)
