"""tests/test_scan_profiles.py — scan profile loading and CLI integration (patch110).

Tests:
1. load_profiles reads config/scan_profiles.yaml and returns expected profiles.
2. --profile ci applies profile settings to scan args (check_injection, parallel, etc.).
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pytest
import yaml

from enforcement.scan_profiles import (
    load_profiles,
    resolve_profile,
    apply_profile_to_args,
    ScanProfile,
)


# ---------------------------------------------------------------------------
# Test 1: profile loading from YAML
# ---------------------------------------------------------------------------

def test_load_profiles_returns_expected_keys(tmp_path: Path):
    """load_profiles parses YAML and returns the expected profile names."""
    profiles_yaml = tmp_path / "profiles.yaml"
    profiles_yaml.write_text(yaml.dump({
        "scan_profiles": {
            "development": {
                "check_injection": False,
                "min_severity": "high",
                "fail_on_pii": False,
                "parallel": 1,
            },
            "ci": {
                "check_injection": True,
                "min_severity": "medium",
                "fail_on_pii": True,
                "parallel": 4,
                "format": "sarif",
            },
            "strict": {
                "check_injection": True,
                "min_severity": "low",
                "fail_on_pii": True,
                "parallel": 4,
            },
        },
    }), encoding="utf-8")

    profiles = load_profiles(profiles_yaml)
    assert set(profiles.keys()) == {"development", "ci", "strict"}

    # Verify CI profile values
    ci = profiles["ci"]
    assert ci["check_injection"] is True
    assert ci["parallel"] == 4
    assert ci["format"] == "sarif"
    assert ci["fail_on_pii"] is True

    # Resolve to ScanProfile
    sp = resolve_profile("ci", profiles)
    assert isinstance(sp, ScanProfile)
    assert sp.name == "ci"
    assert sp.check_injection is True
    assert sp.parallel == 4
    assert sp.format == "sarif"

    # Unknown profile raises KeyError
    with pytest.raises(KeyError, match="Unknown scan profile"):
        resolve_profile("nonexistent", profiles)


# ---------------------------------------------------------------------------
# Test 2: --profile applies settings to args, explicit flags override
# ---------------------------------------------------------------------------

def test_profile_applies_defaults_and_explicit_flags_override(tmp_path: Path):
    """Profile settings apply as defaults; explicit CLI flags take precedence."""
    profiles_yaml = tmp_path / "profiles.yaml"
    profiles_yaml.write_text(yaml.dump({
        "scan_profiles": {
            "ci": {
                "check_injection": True,
                "fail_on_pii": True,
                "parallel": 4,
                "format": "sarif",
            },
        },
    }), encoding="utf-8")

    profiles = load_profiles(profiles_yaml)
    profile = resolve_profile("ci", profiles)

    # Simulate args with defaults (no explicit flags set)
    args = argparse.Namespace(
        check_injection=False,
        fail_on_pii=False,
        parallel=1,
        format=None,
        pattern=None,
        exclude=None,
        cache=False,
        stats=False,
    )

    apply_profile_to_args(profile, args)

    # Profile defaults should be applied
    assert args.check_injection is True
    assert args.fail_on_pii is True
    assert args.parallel == 4
    assert args.format == "sarif"

    # Now simulate with explicit flag overriding profile
    args2 = argparse.Namespace(
        check_injection=False,  # explicitly set to False
        fail_on_pii=True,      # explicitly set
        parallel=8,            # explicitly set higher than profile
        format="jsonl",        # explicitly set different format
        pattern=None,
        exclude=None,
        cache=False,
        stats=False,
    )

    apply_profile_to_args(profile, args2)

    # Explicit parallel=8 should NOT be overridden (it's != 1 default)
    assert args2.parallel == 8
    # Explicit format="jsonl" should NOT be overridden (it's not None)
    assert args2.format == "jsonl"
    # fail_on_pii was already True, stays True
    assert args2.fail_on_pii is True


# ---------------------------------------------------------------------------
# Test 3: default profiles file loads correctly
# ---------------------------------------------------------------------------

def test_default_profiles_file_loads():
    """The bundled config/scan_profiles.yaml loads without error."""
    profiles = load_profiles()
    assert "development" in profiles
    assert "ci" in profiles
    assert "strict" in profiles
