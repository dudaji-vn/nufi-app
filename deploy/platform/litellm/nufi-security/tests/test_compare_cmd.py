"""tests/test_compare_cmd.py -- nufi-egress compare scan comparison tests (patch133).

Scenarios:
1. Compare two NuFi JSON scan results — new / resolved / unchanged
2. --fail-on-new exits 1 when new findings exist
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from enforcement.compare_cmd import compare_scans, CompareResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_nufi_json(path: Path, findings: list) -> None:
    """Write a NuFi scan JSON file with the given findings list."""
    data = {
        "files_scanned": 1,
        "files_with_findings": 1 if findings else 0,
        "total_findings": len(findings),
        "has_pii": any(f["finding_type"].startswith("PII:") for f in findings),
        "has_injection": any(f["finding_type"].startswith("INJECTION:") for f in findings),
        "findings": findings,
        "errors": [],
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Test 1: Compare two NuFi JSON scan results
# ---------------------------------------------------------------------------

def test_compare_nufi_json(tmp_path: Path) -> None:
    """Compare before/after JSON: detect new, resolved, unchanged findings."""
    before_findings = [
        {"file": "app.py", "line": 10, "finding_type": "PII:KR_RRN", "text": "900101-1234567"},
        {"file": "app.py", "line": 20, "finding_type": "PII:KR_PHONE", "text": "010-1234-5678"},
        {"file": "config.py", "line": 5, "finding_type": "PII:EMAIL", "text": "test@example.com"},
    ]
    after_findings = [
        # unchanged: same KR_RRN
        {"file": "app.py", "line": 10, "finding_type": "PII:KR_RRN", "text": "900101-1234567"},
        # resolved: KR_PHONE is gone
        # new: KR_ACCOUNT introduced
        {"file": "utils.py", "line": 3, "finding_type": "PII:KR_ACCOUNT", "text": "110-123-456789"},
        # unchanged: same EMAIL
        {"file": "config.py", "line": 5, "finding_type": "PII:EMAIL", "text": "test@example.com"},
    ]

    before_file = tmp_path / "before.json"
    after_file = tmp_path / "after.json"
    _write_nufi_json(before_file, before_findings)
    _write_nufi_json(after_file, after_findings)

    result = compare_scans(before_file, after_file)

    assert isinstance(result, CompareResult)
    # 1 new (KR_ACCOUNT)
    assert len(result.new_findings) == 1
    assert result.new_findings[0].finding_type == "PII:KR_ACCOUNT"
    # 1 resolved (KR_PHONE)
    assert len(result.resolved_findings) == 1
    assert result.resolved_findings[0].finding_type == "PII:KR_PHONE"
    # 2 unchanged (KR_RRN, EMAIL)
    assert len(result.unchanged_findings) == 2
    # Summary string
    assert "1 new" in result.summary
    assert "1 resolved" in result.summary
    assert "2 unchanged" in result.summary


# ---------------------------------------------------------------------------
# Test 2: --fail-on-new via CLI handler
# ---------------------------------------------------------------------------

def test_compare_fail_on_new(tmp_path: Path) -> None:
    """CLI handler returns 1 when --fail-on-new and new findings exist."""
    from enforcement.compare_cmd import cmd_compare
    import argparse

    before_findings = [
        {"file": "a.py", "line": 1, "finding_type": "PII:EMAIL", "text": "a@b.com"},
    ]
    after_findings = [
        {"file": "a.py", "line": 1, "finding_type": "PII:EMAIL", "text": "a@b.com"},
        {"file": "a.py", "line": 5, "finding_type": "PII:KR_RRN", "text": "900101-1234567"},
    ]

    before_file = tmp_path / "before.json"
    after_file = tmp_path / "after.json"
    _write_nufi_json(before_file, before_findings)
    _write_nufi_json(after_file, after_findings)

    args = argparse.Namespace(
        before=str(before_file),
        after=str(after_file),
        json=True,
        fail_on_new=True,
    )

    rc = cmd_compare(args)
    assert rc == 1, "Should exit 1 when new findings introduced and --fail-on-new"

    # Without --fail-on-new, should exit 0
    args.fail_on_new = False
    rc2 = cmd_compare(args)
    assert rc2 == 0
