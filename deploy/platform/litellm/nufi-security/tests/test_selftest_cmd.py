"""tests/test_selftest_cmd.py -- nufi-egress test self-verification (patch135).

Verifies that the selftest command runs all 7 checks and reports results.
"""
from __future__ import annotations

from enforcement.selftest_cmd import run_selftest, render_human, results_to_dict


def test_selftest_all_pass() -> None:
    """All 7 self-test checks should pass in a correctly installed environment."""
    results = run_selftest()

    # Must have exactly 7 checks
    assert len(results) == 7, f"expected 7 checks, got {len(results)}"

    # All should pass
    for r in results:
        assert r.passed, f"check '{r.name}' failed: {r.detail}"

    # Verify check names
    names = [r.name for r in results]
    assert "pii_detection" in names
    assert "injection_detection" in names
    assert "route_decision" in names
    assert "guard_block" in names
    assert "config_parse" in names
    assert "version_match" in names
    assert "pseudonymize" in names

    # Verify human-readable output contains summary
    human = render_human(results)
    assert "7/7 checks passed" in human

    # Verify dict output structure
    d = results_to_dict(results)
    assert d["summary"]["all_passed"] is True
    assert d["summary"]["total"] == 7
    assert d["summary"]["passed"] == 7
