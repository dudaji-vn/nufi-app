"""tests/test_posture_cmd.py -- nufi-egress report posture tests (patch168).

Scenarios:
1. capture_posture returns a valid snapshot dict with expected keys
2. compare_posture correctly identifies improvements and regressions
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from enforcement.posture_cmd import (
    capture_posture,
    compare_posture,
    save_posture,
    load_history,
    get_last_posture,
    render_posture_text,
    render_comparison_text,
    _compute_grade,
)


# ---------------------------------------------------------------------------
# Test 1: capture_posture returns valid snapshot
# ---------------------------------------------------------------------------

class TestCapturePosture:
    def test_empty_dir_returns_grade_a(self, tmp_path):
        """An empty directory should produce grade A with 0 findings."""
        snapshot = capture_posture(tmp_path)

        assert snapshot["grade"] == "A"
        assert snapshot["file_count"] == 0
        assert snapshot["finding_count"] == 0
        assert "timestamp" in snapshot
        assert "entity_distribution" in snapshot
        assert "injection_status" in snapshot
        assert "doctor_results" in snapshot
        assert "config_completeness" in snapshot
        assert snapshot["target"] == str(tmp_path)

    def test_dir_with_pii_produces_findings(self, tmp_path):
        """A directory with PII content should have findings and lower grade."""
        # Write a file with a Korean RRN pattern
        pii_file = tmp_path / "data.txt"
        pii_file.write_text("주민등록번호: 900101-1234568\n", encoding="utf-8")

        snapshot = capture_posture(tmp_path)

        assert snapshot["file_count"] >= 1
        assert snapshot["finding_count"] >= 1
        # Grade should be worse than A
        assert snapshot["grade"] in ("B", "C", "D", "F")

    def test_snapshot_has_severity_counts(self, tmp_path):
        """Snapshot severity_counts should be a dict."""
        snapshot = capture_posture(tmp_path)
        assert isinstance(snapshot["severity_counts"], dict)

    def test_save_and_load_history(self, tmp_path):
        """save_posture should append to JSONL and load_history should read them."""
        history_file = tmp_path / "history.jsonl"
        snap1 = {"timestamp": "2026-01-01T00:00:00Z", "grade": "A", "finding_count": 0}
        snap2 = {"timestamp": "2026-01-02T00:00:00Z", "grade": "C", "finding_count": 5}

        save_posture(snap1, history_file)
        save_posture(snap2, history_file)

        entries = load_history(history_file)
        assert len(entries) == 2
        assert entries[0]["grade"] == "A"
        assert entries[1]["grade"] == "C"

        last = get_last_posture(history_file)
        assert last["grade"] == "C"

    def test_render_posture_text(self, tmp_path):
        """render_posture_text should produce readable output."""
        snapshot = capture_posture(tmp_path)
        text = render_posture_text(snapshot)
        assert "NuFi Security Posture Snapshot" in text
        assert "Grade" in text


# ---------------------------------------------------------------------------
# Test 2: compare_posture identifies improvements and regressions
# ---------------------------------------------------------------------------

class TestComparePosture:
    def test_improvement_detected(self):
        """When grade improves and findings decrease, should report improvement."""
        before = {
            "grade": "D",
            "finding_count": 10,
            "doctor_results": {"available": True, "fail": 2, "pass": 3, "warn": 1},
            "injection_status": {"available": True, "recall": 0.80, "precision": 0.85},
            "config_completeness": {"ratio": 0.5},
        }
        after = {
            "grade": "B",
            "finding_count": 2,
            "doctor_results": {"available": True, "fail": 0, "pass": 5, "warn": 1},
            "injection_status": {"available": True, "recall": 0.95, "precision": 0.92},
            "config_completeness": {"ratio": 0.75},
        }

        result = compare_posture(before, after)

        assert len(result["improved"]) >= 3  # grade, findings, doctor, recall, config
        assert len(result["regressed"]) == 0
        assert result["grade_change"] == ("D", "B")
        assert "summary" in result

    def test_regression_detected(self):
        """When grade regresses and findings increase, should report regression."""
        before = {
            "grade": "A",
            "finding_count": 0,
            "doctor_results": {"available": True, "fail": 0, "pass": 6, "warn": 0},
            "injection_status": {"available": True, "recall": 0.95, "precision": 0.95},
            "config_completeness": {"ratio": 1.0},
        }
        after = {
            "grade": "D",
            "finding_count": 8,
            "doctor_results": {"available": True, "fail": 2, "pass": 3, "warn": 1},
            "injection_status": {"available": True, "recall": 0.80, "precision": 0.85},
            "config_completeness": {"ratio": 0.5},
        }

        result = compare_posture(before, after)

        assert len(result["regressed"]) >= 3
        assert result["grade_change"] == ("A", "D")

    def test_no_change(self):
        """Identical snapshots should show no improvements or regressions."""
        snap = {
            "grade": "B",
            "finding_count": 3,
            "doctor_results": {"available": True, "fail": 0, "pass": 5, "warn": 1},
            "injection_status": {"available": True, "recall": 0.92, "precision": 0.90},
            "config_completeness": {"ratio": 0.75},
        }

        result = compare_posture(snap, snap)

        assert len(result["improved"]) == 0
        assert len(result["regressed"]) == 0
        assert result["grade_change"] is None

    def test_render_comparison_text(self):
        """render_comparison_text should produce readable output."""
        comparison = {
            "improved": ["Grade improved: D -> B"],
            "regressed": [],
            "unchanged": ["Findings unchanged: 3"],
            "grade_change": ("D", "B"),
            "summary": "1 improved, 0 regressed, 1 unchanged",
        }
        text = render_comparison_text(comparison)
        assert "Posture Comparison" in text
        assert "Grade improved" in text
