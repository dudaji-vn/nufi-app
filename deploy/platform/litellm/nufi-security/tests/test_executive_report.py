"""tests/test_executive_report.py -- nufi-egress report executive tests (patch163).

Scenarios:
1. Grade computation logic (A/B/C/D/F)
2. End-to-end report build on an empty directory yields grade A, text/json/md output
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from enforcement.executive_report import (
    build_executive_report,
    compute_grade,
    render,
    render_json,
    render_markdown,
    render_text,
    ExecutiveReport,
)


# ---------------------------------------------------------------------------
# Test 1: Grade computation
# ---------------------------------------------------------------------------

class TestComputeGrade:
    def test_grade_a_no_findings(self):
        counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        assert compute_grade(counts) == "A"

    def test_grade_b_low_only(self):
        counts = {"critical": 0, "high": 0, "medium": 0, "low": 3}
        assert compute_grade(counts) == "B"

    def test_grade_c_medium(self):
        counts = {"critical": 0, "high": 0, "medium": 2, "low": 1}
        assert compute_grade(counts) == "C"

    def test_grade_d_high(self):
        counts = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        assert compute_grade(counts) == "D"

    def test_grade_f_critical(self):
        counts = {"critical": 1, "high": 0, "medium": 0, "low": 0}
        assert compute_grade(counts) == "F"

    def test_grade_f_trumps_all(self):
        counts = {"critical": 1, "high": 5, "medium": 10, "low": 20}
        assert compute_grade(counts) == "F"

    def test_empty_counts(self):
        assert compute_grade({}) == "A"


# ---------------------------------------------------------------------------
# Test 2: End-to-end build + render on empty dir
# ---------------------------------------------------------------------------

class TestBuildExecutiveReport:
    def test_empty_dir_grade_a(self, tmp_path: Path):
        """Empty directory should yield grade A with zero findings."""
        report = build_executive_report(
            str(tmp_path),
            run_injection_bench=False,
            run_doctor=False,
            run_stats=False,
        )
        assert report.grade == "A"
        assert report.files_scanned == 0
        assert report.total_findings == 0
        assert report.target == str(tmp_path)
        assert report.generated_at != ""

    def test_render_text_contains_grade(self, tmp_path: Path):
        report = build_executive_report(
            str(tmp_path),
            run_injection_bench=False,
            run_doctor=False,
            run_stats=False,
        )
        text = render_text(report)
        assert "Grade:" in text
        assert "A" in text
        assert "EXECUTIVE SECURITY SUMMARY" in text
        assert "RECOMMENDATION" in text

    def test_render_json_valid(self, tmp_path: Path):
        report = build_executive_report(
            str(tmp_path),
            run_injection_bench=False,
            run_doctor=False,
            run_stats=False,
        )
        output = render_json(report)
        data = json.loads(output)
        assert data["grade"] == "A"
        assert data["files_scanned"] == 0
        assert "severity_counts" in data

    def test_render_markdown_structure(self, tmp_path: Path):
        report = build_executive_report(
            str(tmp_path),
            run_injection_bench=False,
            run_doctor=False,
            run_stats=False,
        )
        md = render_markdown(report)
        assert "# Executive Security Summary" in md
        assert "## Key Metrics" in md
        assert "## Risk Summary" in md
        assert "## Recommendation" in md

    def test_render_dispatch(self, tmp_path: Path):
        report = build_executive_report(
            str(tmp_path),
            run_injection_bench=False,
            run_doctor=False,
            run_stats=False,
        )
        assert "EXECUTIVE" in render(report, "text")
        assert "grade" in render(report, "json")
        assert "# Executive" in render(report, "md")

    def test_findings_affect_grade(self, tmp_path: Path):
        """Directory with PII content should produce a non-A grade."""
        # Write a file containing a fake Korean RRN (strong PII -> critical)
        pii_file = tmp_path / "secret.txt"
        pii_file.write_text("주민등록번호: 900101-1234568\n", encoding="utf-8")
        report = build_executive_report(
            str(tmp_path),
            run_injection_bench=False,
            run_doctor=False,
            run_stats=False,
        )
        assert report.total_findings > 0
        assert report.grade in ("C", "D", "F")
