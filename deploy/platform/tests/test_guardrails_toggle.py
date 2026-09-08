"""scripts/guardrails-toggle.sh -- the policy rewrite, exercised off the stack.

The restart-and-verify half of the script needs a running gateway and is
covered by running it. This covers the half that, if wrong, leaves a control
in a mode nobody asked for while the script still reports success: the edit
to policy.yaml. The functions are called by sourcing the script, the same way
its own `main` calls them.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

PLATFORM = Path(__file__).resolve().parents[1]
SCRIPT = PLATFORM / "scripts" / "guardrails-toggle.sh"
POLICY = PLATFORM / "litellm" / "guardrails" / "policy.yaml"

# The state docs/2026-08-03-deploy-develop-to-production.md declares correct
# after a deploy. `on` must land exactly here, whatever the file held before.
ENFORCING = {
    "G1": "pre_call",
    "G2a": "logging_only",
    "G2b": "post_call",
    "G3": "post_call",
    "G4": "post_call",
}
SHADOW = {control: "logging_only" for control in ENFORCING}


def call(function: str, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        # $0 is a label, not the script: the script only runs `main` when
        # BASH_SOURCE[0] == $0, and sourcing must not trip that.
        ["bash", "-c", f'source "$1" && shift && {function} "$@"', "test", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        check=check,
    )


def modes(path: Path) -> dict[str, str]:
    data = yaml.safe_load(path.read_text())
    return {control: body["mode"] for control, body in data["controls"].items()}


@pytest.fixture
def policy(tmp_path: Path) -> Path:
    copy = tmp_path / "policy.yaml"
    shutil.copy(POLICY, copy)
    return copy


def test_repo_policy_is_the_enforcing_state() -> None:
    # Precondition for the byte-for-byte round trip below. If this fails the
    # committed policy drifted from the documented deploy state -- fix that,
    # not the script.
    assert modes(POLICY) == ENFORCING


def test_off_flips_every_control_to_logging_only(policy: Path) -> None:
    call("set_modes", str(policy), "off")
    assert modes(policy) == SHADOW


def test_off_changes_only_the_mode_lines(policy: Path) -> None:
    # The file is mostly commentary explaining WHY each threshold is what it
    # is. An edit that drops or reflows a comment loses that.
    before = POLICY.read_text().splitlines()
    call("set_modes", str(policy), "off")
    after = policy.read_text().splitlines()
    assert len(before) == len(after)
    changed = [(b, a) for b, a in zip(before, after, strict=True) if b != a]
    assert changed, "off changed nothing"
    assert all(b.strip().startswith("mode:") for b, _ in changed)
    assert len(changed) == 4, changed  # G2a was already logging_only


def test_on_after_off_restores_the_file_byte_for_byte(policy: Path) -> None:
    call("set_modes", str(policy), "off")
    call("set_modes", str(policy), "on")
    assert policy.read_bytes() == POLICY.read_bytes()


def test_on_is_idempotent(policy: Path) -> None:
    call("set_modes", str(policy), "on")
    assert policy.read_bytes() == POLICY.read_bytes()


def test_refuses_a_policy_with_a_control_it_does_not_know(policy: Path) -> None:
    # A control the script has never heard of would be left enforcing after
    # `off` -- "security is off" would be a lie. Refuse, and leave the file
    # exactly as it was.
    text = policy.read_text().replace("  G3:\n", "  G9:\n", 1)
    policy.write_text(text)
    result = call("set_modes", str(policy), "off", check=False)
    assert result.returncode != 0
    assert "G9" in result.stderr
    assert "G3" in result.stderr
    assert policy.read_text() == text


def test_policy_modes_lists_every_control(policy: Path) -> None:
    result = call("policy_modes", str(policy))
    listed = dict(line.split() for line in result.stdout.splitlines())
    assert listed == ENFORCING
