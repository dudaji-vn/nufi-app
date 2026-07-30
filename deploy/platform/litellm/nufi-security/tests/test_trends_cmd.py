"""Tests for ``nufi-egress report trends`` PII detection trends (patch149)."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from enforcement.trends_cmd import build_trends, render_human


def _write_audit_log(path: Path, records: list) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def test_build_trends_groups_by_date():
    """Trends are grouped by date with correct counts."""
    records = [
        {"ts": "2026-07-01T10:00:00", "outcome": "blocked",
         "findings": [{"entity_type": "PERSON"}, {"entity_type": "SSN"}]},
        {"ts": "2026-07-01T11:00:00", "outcome": "allowed",
         "findings": [{"entity_type": "PHONE"}]},
        {"ts": "2026-07-02T09:00:00", "outcome": "blocked",
         "findings": [{"entity_type": "PERSON"}]},
        {"ts": "2026-07-03T08:00:00", "outcome": "allowed", "findings": []},
    ]
    with tempfile.TemporaryDirectory() as td:
        log_path = Path(td) / "audit.jsonl"
        _write_audit_log(log_path, records)

        result = build_trends(period=7, audit_path=str(log_path))

    assert result["days_with_data"] == 3
    assert result["total_events"] == 4
    assert result["total_blocked"] == 2

    # Check per-day breakdown
    day_map = {d["date"]: d for d in result["days"]}
    assert day_map["2026-07-01"]["total"] == 2
    assert day_map["2026-07-01"]["blocked"] == 1
    assert "PERSON" in day_map["2026-07-01"]["pii_types"]
    assert day_map["2026-07-02"]["blocked"] == 1
    assert day_map["2026-07-03"]["blocked"] == 0

    # Render human output should not crash
    text = render_human(result)
    assert "2026-07-01" in text
    assert "Trends" in text


def test_build_trends_empty_log():
    """Empty or missing audit log returns zero counts."""
    with tempfile.TemporaryDirectory() as td:
        result = build_trends(period=7, audit_path=str(Path(td) / "missing.jsonl"))

    assert result["days_with_data"] == 0
    assert result["total_events"] == 0
    assert result["days"] == []

    text = render_human(result)
    assert "No audit data" in text


def test_build_trends_period_limits():
    """Period parameter limits the number of days shown."""
    records = [
        {"ts": f"2026-07-0{i}T10:00:00", "outcome": "allowed", "findings": []}
        for i in range(1, 8)
    ]
    with tempfile.TemporaryDirectory() as td:
        log_path = Path(td) / "audit.jsonl"
        _write_audit_log(log_path, records)

        result = build_trends(period=3, audit_path=str(log_path))

    # Should only show 3 most recent days
    assert result["days_with_data"] == 3
    dates = [d["date"] for d in result["days"]]
    assert "2026-07-07" in dates
    assert "2026-07-06" in dates
    assert "2026-07-05" in dates
    assert "2026-07-01" not in dates


def test_build_trends_json_output():
    """JSON output is valid and contains expected keys."""
    records = [
        {"ts": "2026-07-05T10:00:00", "outcome": "blocked",
         "findings": [{"entity_type": "SSN"}]},
    ]
    with tempfile.TemporaryDirectory() as td:
        log_path = Path(td) / "audit.jsonl"
        _write_audit_log(log_path, records)

        result = build_trends(period=7, audit_path=str(log_path))

    # Verify JSON serializable
    output = json.dumps(result, ensure_ascii=False)
    parsed = json.loads(output)
    assert "days" in parsed
    assert "total_events" in parsed
    assert "pii_types_summary" in parsed
    assert parsed["pii_types_summary"]["SSN"] == 1
