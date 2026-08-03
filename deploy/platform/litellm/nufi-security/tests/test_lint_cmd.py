"""tests/test_lint_cmd.py -- nufi-egress lint anti-pattern checker tests (patch130).

Scenarios:
1. Detects hardcoded API key
2. Detects debug mode
3. Clean file returns no findings
4. fix_report_file generates before/after previews (patch183)
"""
from __future__ import annotations

from pathlib import Path

import pytest

from enforcement.lint_cmd import lint_file, lint_path, fix_report_file, LintFinding


# ---------------------------------------------------------------------------
# Test 1: Detects hardcoded API key
# ---------------------------------------------------------------------------

def test_detect_hardcoded_api_key(tmp_path: Path) -> None:
    f = tmp_path / "config.py"
    f.write_text(
        'api_key = "sk-abc123secretvalue"\n'
        'normal_var = 42\n',
        encoding="utf-8",
    )

    findings = lint_file(f)

    assert len(findings) >= 1
    key_findings = [x for x in findings if x.rule_name == "hardcoded-api-key"]
    assert len(key_findings) == 1
    assert key_findings[0].severity == "high"
    assert key_findings[0].line == 1
    assert "API key" in key_findings[0].message


# ---------------------------------------------------------------------------
# Test 2: Detects debug mode
# ---------------------------------------------------------------------------

def test_detect_debug_mode(tmp_path: Path) -> None:
    f = tmp_path / "settings.yaml"
    f.write_text(
        "server:\n"
        "  host: 0.0.0.0\n"
        "  debug: true\n"
        "  port: 8080\n",
        encoding="utf-8",
    )

    findings = lint_file(f)

    assert len(findings) >= 1
    debug_findings = [x for x in findings if x.rule_name == "debug-mode"]
    assert len(debug_findings) == 1
    assert debug_findings[0].severity == "medium"
    assert debug_findings[0].line == 3


# ---------------------------------------------------------------------------
# Test 3: Clean file returns no findings
# ---------------------------------------------------------------------------

def test_clean_file_no_findings(tmp_path: Path) -> None:
    f = tmp_path / "clean.py"
    f.write_text(
        "import os\n"
        "\n"
        "def greet(name: str) -> str:\n"
        '    return f"Hello, {name}!"\n'
        "\n"
        "if __name__ == '__main__':\n"
        "    print(greet('world'))\n",
        encoding="utf-8",
    )

    findings = lint_file(f)

    assert findings == []


# ---------------------------------------------------------------------------
# Test 4: fix_report_file generates before/after previews (patch183)
# ---------------------------------------------------------------------------

def test_fix_report_shows_before_after(tmp_path: Path) -> None:
    """fix_report_file returns FixPreview with http->https transformation."""
    f = tmp_path / "urls.py"
    f.write_text(
        'ENDPOINT = "http://example.com/api"\n'
        'SECURE = "https://safe.example.com"\n'
        'BACKUP = "http://backup.local/data"\n',
        encoding="utf-8",
    )

    previews = fix_report_file(f)

    # Should find 2 fixable http:// URLs (lines 1 and 3)
    assert len(previews) == 2

    # First preview
    assert previews[0].line == 1
    assert previews[0].rule_id == "SEC006"
    assert "http://" in previews[0].before
    assert "https://" in previews[0].after

    # Second preview
    assert previews[1].line == 3
    assert "http://backup.local" in previews[1].before
    assert "https://backup.local" in previews[1].after

    # File should NOT be modified (dry-run)
    content = f.read_text()
    assert "http://example.com" in content
