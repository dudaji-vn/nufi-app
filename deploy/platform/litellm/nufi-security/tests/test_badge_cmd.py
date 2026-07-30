"""Tests for enforcement/badge_cmd.py (patch164)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enforcement.badge_cmd import (
    generate_badge,
    badge_grade,
    badge_recall,
    badge_injection,
    badge_tests,
    cmd_report_badge,
)


def test_generate_badge_contains_text():
    """SVG contains the label and value text."""
    svg = generate_badge("NuFi", "Grade A", "#4c1")
    assert "<svg" in svg
    assert "NuFi" in svg
    assert "Grade A" in svg
    assert "#4c1" in svg


def test_badge_grade_default():
    """Grade badge produces valid SVG with grade text."""
    svg = badge_grade("B")
    assert "Grade B" in svg
    assert "<svg" in svg


def test_badge_recall():
    """Recall badge shows correct value."""
    svg = badge_recall(0.97)
    assert "0.97" in svg
    assert "PII Recall" in svg


def test_badge_injection():
    """Injection badge shows correct value."""
    svg = badge_injection(1.0)
    assert "1.0" in svg
    assert "Injection" in svg


def test_badge_tests():
    """Tests badge shows passed count."""
    svg = badge_tests(564)
    assert "564 passed" in svg
    assert "Tests" in svg


def test_cmd_report_badge_stdout(capsys):
    """CLI badge command outputs SVG to stdout."""
    class Args:
        badge_type = "grade"
        output = None

    rc = cmd_report_badge(Args())
    assert rc == 0
    captured = capsys.readouterr()
    assert "<svg" in captured.out
    assert "NuFi" in captured.out


def test_cmd_report_badge_file(tmp_path):
    """CLI badge command writes SVG to file."""
    out = str(tmp_path / "badge.svg")

    class Args:
        badge_type = "tests"
        output = out

    rc = cmd_report_badge(Args())
    assert rc == 0
    content = Path(out).read_text()
    assert "<svg" in content
    assert "Tests" in content
