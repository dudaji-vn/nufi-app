"""tests/test_report_diff_cmd.py -- nufi-egress report diff tests (patch153).

Scenarios:
1. Markdown diff report contains summary, new/resolved tables, unchanged count
2. JSON output contains expected structure
3. HTML output contains expected elements
4. --output writes to file
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from enforcement.compare_cmd import compare_scans, CompareResult
from enforcement.report_diff_cmd import (
    cmd_report_diff,
    render_diff_md,
    render_diff_json,
    render_diff_html,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_nufi_json(path: Path, findings: list) -> None:
    data = {
        "files_scanned": 1,
        "files_with_findings": 1 if findings else 0,
        "total_findings": len(findings),
        "has_pii": any(f["finding_type"].startswith("PII:") for f in findings),
        "has_injection": False,
        "findings": findings,
        "errors": [],
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


_BEFORE = [
    {"file": "app.py", "line": 10, "finding_type": "PII:KR_RRN", "text": "900101-1234567"},
    {"file": "app.py", "line": 20, "finding_type": "PII:KR_PHONE", "text": "010-1234-5678"},
    {"file": "config.py", "line": 5, "finding_type": "PII:EMAIL", "text": "test@example.com"},
]

_AFTER = [
    {"file": "app.py", "line": 10, "finding_type": "PII:KR_RRN", "text": "900101-1234567"},
    {"file": "utils.py", "line": 3, "finding_type": "PII:KR_ACCOUNT", "text": "110-123-456789"},
    {"file": "config.py", "line": 5, "finding_type": "PII:EMAIL", "text": "test@example.com"},
    {"file": "new.py", "line": 1, "finding_type": "INJECTION:SQL", "text": "DROP TABLE"},
]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_report_diff_md_json_html(tmp_path: Path) -> None:
    """All three renderers produce correct content for a known diff."""
    before_file = tmp_path / "before.json"
    after_file = tmp_path / "after.json"
    _write_nufi_json(before_file, _BEFORE)
    _write_nufi_json(after_file, _AFTER)

    result = compare_scans(before_file, after_file)

    # 2 new (KR_ACCOUNT + INJECTION:SQL), 1 resolved (KR_PHONE), 2 unchanged
    assert len(result.new_findings) == 2
    assert len(result.resolved_findings) == 1
    assert len(result.unchanged_findings) == 2

    # --- Markdown ---
    md = render_diff_md(result, before_name="before.json", after_name="after.json")
    assert "2 new findings" in md
    assert "1 resolved" in md
    assert "2 unchanged" in md
    assert "### New Findings" in md
    assert "### Resolved Findings" in md
    assert "KR_ACCOUNT" in md
    assert "INJECTION:SQL" in md
    assert "KR_PHONE" in md

    # --- JSON ---
    js = render_diff_json(result, before_name="before.json", after_name="after.json")
    d = json.loads(js)
    assert d["summary"]["new_count"] == 2
    assert d["summary"]["resolved_count"] == 1
    assert d["summary"]["unchanged_count"] == 2
    assert d["before"] == "before.json"
    assert d["after"] == "after.json"

    # --- HTML ---
    html = render_diff_html(result, before_name="before.json", after_name="after.json")
    assert "<h1>Scan Diff Report</h1>" in html
    assert "2 new findings" in html
    assert "KR_ACCOUNT" in html


def test_report_diff_cli_output_file(tmp_path: Path) -> None:
    """CLI handler writes report to --output file."""
    import argparse

    before_file = tmp_path / "before.json"
    after_file = tmp_path / "after.json"
    _write_nufi_json(before_file, _BEFORE)
    _write_nufi_json(after_file, _AFTER)

    out_file = tmp_path / "report.md"
    args = argparse.Namespace(
        before=str(before_file),
        after=str(after_file),
        format="md",
        output=str(out_file),
    )
    rc = cmd_report_diff(args)
    assert rc == 0
    assert out_file.exists()
    content = out_file.read_text(encoding="utf-8")
    assert "2 new findings" in content
    assert "### New Findings" in content
