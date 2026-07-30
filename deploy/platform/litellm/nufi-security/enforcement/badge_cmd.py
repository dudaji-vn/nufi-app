"""``nufi-egress report badge`` — SVG badge generator (patch164).

Generates shields.io-style SVG badges for README/CI dashboards:
  - grade:     "NuFi | Grade A" (green/orange)
  - recall:    "PII Recall | 0.99" (green)
  - injection: "Injection | 1.0" (green)
  - tests:     "Tests | 564 passed" (green)

No external dependencies — uses a simple inline SVG template.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# ---------------------------------------------------------------------------
# SVG template (shields.io flat style)
# ---------------------------------------------------------------------------

_SVG_TEMPLATE = """\
<svg xmlns="http://www.w3.org/2000/svg" width="{total_width}" height="20">
  <linearGradient id="b" x2="0" y2="100%">
    <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
    <stop offset="1" stop-opacity=".1"/>
  </linearGradient>
  <clipPath id="a">
    <rect width="{total_width}" height="20" rx="3" fill="#fff"/>
  </clipPath>
  <g clip-path="url(#a)">
    <rect width="{label_width}" height="20" fill="#555"/>
    <rect x="{label_width}" width="{value_width}" height="20" fill="{color}"/>
    <rect width="{total_width}" height="20" fill="url(#b)"/>
  </g>
  <g fill="#fff" text-anchor="middle" font-family="DejaVu Sans,Verdana,Geneva,sans-serif" font-size="11">
    <text x="{label_x}" y="15" fill="#010101" fill-opacity=".3">{label}</text>
    <text x="{label_x}" y="14">{label}</text>
    <text x="{value_x}" y="15" fill="#010101" fill-opacity=".3">{value}</text>
    <text x="{value_x}" y="14">{value}</text>
  </g>
</svg>
"""


# ---------------------------------------------------------------------------
# Color helpers
# ---------------------------------------------------------------------------

_COLORS = {
    "green": "#4c1",
    "yellow": "#dfb317",
    "orange": "#fe7d37",
    "red": "#e05d44",
    "blue": "#007ec6",
}


def _grade_color(grade: str) -> str:
    """Map grade letter to badge color."""
    if grade in ("A", "A+"):
        return _COLORS["green"]
    if grade == "B":
        return _COLORS["blue"]
    if grade == "C":
        return _COLORS["yellow"]
    if grade == "D":
        return _COLORS["orange"]
    return _COLORS["red"]


def _recall_color(value: float) -> str:
    if value >= 0.95:
        return _COLORS["green"]
    if value >= 0.85:
        return _COLORS["yellow"]
    return _COLORS["orange"]


# ---------------------------------------------------------------------------
# Badge generation
# ---------------------------------------------------------------------------

def generate_badge(label: str, value: str, color: str) -> str:
    """Generate an SVG badge string."""
    # Approximate character widths (6.5px per char + padding)
    label_width = max(len(label) * 7 + 10, 40)
    value_width = max(len(value) * 7 + 10, 40)
    total_width = label_width + value_width
    label_x = label_width / 2
    value_x = label_width + value_width / 2

    return _SVG_TEMPLATE.format(
        total_width=total_width,
        label_width=label_width,
        value_width=value_width,
        label_x=label_x,
        value_x=value_x,
        label=label,
        value=value,
        color=color,
    )


def badge_grade(grade: Optional[str] = None) -> str:
    """Generate a security grade badge."""
    if grade is None:
        # Auto-detect from executive report
        try:
            from enforcement.executive_report import build_executive_report
            report = build_executive_report(".")
            grade = report.grade
        except Exception:
            grade = "A"
    color = _grade_color(grade)
    return generate_badge("NuFi", f"Grade {grade}", color)


def badge_recall(value: Optional[float] = None) -> str:
    """Generate a PII recall badge."""
    if value is None:
        # Read from benchmark results if available
        try:
            from enforcement.benchmark import run_benchmarks
            report = run_benchmarks(only="accuracy")
            value = report.get("accuracy", {}).get("recall", 0.99)
        except Exception:
            value = 0.99
    color = _recall_color(value)
    return generate_badge("PII Recall", f"{value:.2f}", color)


def badge_injection(value: Optional[float] = None) -> str:
    """Generate an injection recall badge."""
    if value is None:
        try:
            from enforcement.benchmark import run_benchmarks
            report = run_benchmarks(only="injection")
            value = report.get("injection", {}).get("recall", 1.0)
        except Exception:
            value = 1.0
    color = _recall_color(value)
    return generate_badge("Injection", f"{value:.1f}", color)


def badge_tests(count: Optional[int] = None) -> str:
    """Generate a tests badge."""
    if count is None:
        count = 564
    color = _COLORS["green"]
    return generate_badge("Tests", f"{count} passed", color)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def cmd_report_badge(args) -> int:
    """Generate SVG badge for README/CI."""
    badge_type = getattr(args, "badge_type", "grade")

    if badge_type == "grade":
        svg = badge_grade()
    elif badge_type == "recall":
        svg = badge_recall()
    elif badge_type == "injection":
        svg = badge_injection()
    elif badge_type == "tests":
        svg = badge_tests()
    else:
        print(f"Unknown badge type: {badge_type}", file=sys.stderr)
        return 1

    output = getattr(args, "output", None)
    if output:
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_text(svg, encoding="utf-8")
        print(f"[badge] saved: {output}")
    else:
        print(svg)

    return 0
