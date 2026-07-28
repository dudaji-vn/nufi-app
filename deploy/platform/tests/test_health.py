import logging
import os
import subprocess
import sys
from pathlib import Path

import pytest
from guardrails import audit
from guardrails.health import StrictControlViolation, assert_controls, guardrail_status
from guardrails.policy import Policy

POLICY_FIXTURE = "litellm/guardrails/policy.yaml"


@pytest.fixture
def policy(policy_path):
    return Policy.load(policy_path)


def test_status_reports_every_control_with_its_mode(policy):
    status = guardrail_status(policy)

    # Pins the SHAPE and the mode/enforcing relationship, not the shipping
    # policy's current mode. Asserting `== "logging_only"` here meant that
    # flipping G1 to pre_call -- step 3 of the documented rollout -- turned the
    # suite red, so the procedure this whole project exists to enable made CI
    # fail. A rollout that reddens CI is a rollout people postpone.
    assert status["policy_digest"] == policy.digest()
    assert status["controls"]["G1"]["mode"] == policy.control("G1").mode
    assert status["controls"]["G1"]["mandatory"] is True
    assert status["controls"]["G1"]["enforcing"] is (
        policy.control("G1").mode != "logging_only"
    )


def test_status_marks_enforcing_controls(policy_path):
    policy = Policy.load(policy_path)
    policy.controls["G1"] = policy.controls["G1"].with_mode("pre_call")

    assert guardrail_status(policy)["controls"]["G1"]["enforcing"] is True


def test_status_reflects_a_disabled_control(policy_path):
    """Anti-trap: a status report that hardcodes every control as healthy
    would still pass a test that only checks shape/keys. Disabling a real
    control and asserting `enabled`/`enforcing` both flip to False is what
    catches an implementation that reports every control as healthy
    regardless of its actual `ControlConfig.enabled` value. Confirmed by
    mutation (see task-13 report): the two tests above, unmodified, still
    pass against a `guardrail_status` whose `"enabled"` field is hardcoded
    to `True` — this test is the only one that does not.
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


def test_gauge_write_is_observable_not_just_defaulted(policy_path):
    """A gauge assertion whose expected value is 0 proves nothing.

    Prometheus returns 0.0 for a label combination that was never `.set()`, so a
    test expecting 0 cannot distinguish "written correctly" from "never written".
    Deleting the entire gauge-write loop previously left all tests green — in the
    one test guarding the signal an operator watches longest. (That earlier test,
    `test_assert_controls_sets_the_enabled_gauge_per_control`, made exactly this
    mistake: both of its expected values were 0, so it could not tell "written"
    from "omitted" either — removed in favour of this one rather than kept
    alongside it.)

    Two defences: assert a control that must read 1, and pre-seed a sentinel so
    an omitted write cannot coincide with the default.
    """
    policy = Policy.load(policy_path)
    policy.controls["G1"] = policy.controls["G1"].with_mode("pre_call")
    enforcing = audit.GUARDRAIL_ENABLED.labels(control="G1", mode="pre_call")
    idle = audit.GUARDRAIL_ENABLED.labels(control="G2a", mode="logging_only")
    enforcing.set(-1)
    idle.set(-1)

    assert_controls(policy)

    assert enforcing._value.get() == 1
    assert idle._value.get() == 0


def test_import_time_failure_is_loud_not_swallowed(tmp_path):
    """The startup assertion must stop the proxy, not be caught and ignored.

    Verified as a subprocess because that is the only way to observe what a real
    import does. A refactor wrapping the startup block in a broad except would
    otherwise pass every test while restoring the exact silence this module was
    written to end.
    """
    broken = tmp_path / "policy.yaml"
    broken.write_text(
        Path(POLICY_FIXTURE)
        .read_text()
        .replace("strict_controls: false", "strict_controls: true")
        .replace(
            "    enabled: true\n    mandatory: true", "    enabled: false\n    mandatory: true", 1
        )
    )
    env = {**os.environ, "GUARDRAIL_POLICY_PATH": str(broken)}

    result = subprocess.run(
        [sys.executable, "-c", "import guardrails.entrypoints"],
        cwd=str(Path(POLICY_FIXTURE).parents[2]),
        env={**env, "PYTHONPATH": str(Path(POLICY_FIXTURE).parents[1])},
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "StrictControlViolation" in result.stderr


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
