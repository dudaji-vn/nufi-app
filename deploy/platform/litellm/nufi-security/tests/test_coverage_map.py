"""tests/test_coverage_map.py -- nufi-egress report coverage-map tests (patch166).

Tests:
1. Text/JSON/CSV output from directory with PII files
2. CLI integration via cmd_report_coverage_map
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from enforcement.coverage_map import (
    build_coverage_map,
    cmd_report_coverage_map,
    render,
    render_csv,
    render_json,
    render_text,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_pii_files(tmp_path: Path) -> None:
    """Create sample files with PII content."""
    (tmp_path / "user_data.txt").write_text(
        "김민수님 주민번호 900101-1234567\n"
        "이메일: test@example.com\n",
        encoding="utf-8",
    )
    (tmp_path / "contacts.txt").write_text(
        "연락처: 010-1234-5678\n"
        "이메일: admin@corp.co.kr\n",
        encoding="utf-8",
    )
    (tmp_path / "clean.txt").write_text(
        "이 파일에는 개인정보가 없습니다.\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_build_coverage_map_and_render_formats(tmp_path: Path) -> None:
    """coverage map from directory with PII returns correct matrix and renders."""
    _create_pii_files(tmp_path)

    data = build_coverage_map(str(tmp_path))

    # Should have found PII in at least one file
    assert data["total_files_scanned"] >= 2
    assert data["total_files_with_pii"] >= 1
    assert len(data["entity_types"]) >= 1
    assert len(data["files"]) >= 1

    # Matrix keys should be subset of files
    for f in data["matrix"]:
        assert any(f.endswith(name) for name in ("user_data.txt", "contacts.txt"))

    # Text render
    text_output = render_text(data)
    assert "PII Coverage Map" in text_output
    assert "TOTAL" in text_output

    # JSON render
    json_output = render_json(data)
    parsed = json.loads(json_output)
    assert "entity_types" in parsed
    assert "matrix" in parsed

    # CSV render
    csv_output = render_csv(data)
    lines = csv_output.strip().split("\n")
    assert lines[0].startswith("file")
    assert len(lines) >= 2  # header + at least one data row

    # render() dispatch
    assert render(data, "text") == text_output
    assert render(data, "json") == json_output
    assert render(data, "csv") == csv_output


def test_cmd_report_coverage_map_output_file(tmp_path: Path, capsys) -> None:
    """CLI handler writes output to file when --output specified."""
    _create_pii_files(tmp_path)
    out_file = tmp_path / "result.json"

    args = SimpleNamespace(
        directory=str(tmp_path),
        pattern=None,
        exclude=None,
        format="json",
        output=str(out_file),
    )

    rc = cmd_report_coverage_map(args)
    assert rc == 0
    assert out_file.exists()

    content = json.loads(out_file.read_text(encoding="utf-8"))
    assert "entity_types" in content
    assert "matrix" in content
    assert content["total_files_with_pii"] >= 1
