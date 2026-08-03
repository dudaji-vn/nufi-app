"""``nufi-egress report executive`` — one-page executive summary (patch163).

Combines security scan, injection benchmark, doctor checks, and config status
into a concise one-page summary for leadership with an overall grade (A-F).

Grading:
  A = 0 findings
  B = low-severity only
  C = medium-severity present
  D = high-severity present
  F = critical-severity present

Formats: text (default), json, markdown.
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# ---------------------------------------------------------------------------
# Severity classification (reuse from security_report)
# ---------------------------------------------------------------------------

def _severity_for_finding(finding_type: str) -> str:
    """Map finding type to severity level."""
    from enforcement.scan_cmd import _STRONG_PII

    if finding_type.startswith("INJECTION:"):
        return "critical"
    entity = finding_type.split(":", 1)[1] if ":" in finding_type else finding_type
    if entity in _STRONG_PII:
        return "critical"
    if entity in ("EMAIL", "PHONE", "KR_PHONE", "IP_ADDRESS"):
        return "medium"
    return "high"


# ---------------------------------------------------------------------------
# Grade logic
# ---------------------------------------------------------------------------

def compute_grade(severity_counts: Dict[str, int]) -> str:
    """Compute letter grade from severity counts.

    A = 0 findings, B = low only, C = medium, D = high, F = critical.
    """
    total = sum(severity_counts.values())
    if total == 0:
        return "A"
    if severity_counts.get("critical", 0) > 0:
        return "F"
    if severity_counts.get("high", 0) > 0:
        return "D"
    if severity_counts.get("medium", 0) > 0:
        return "C"
    return "B"


# ---------------------------------------------------------------------------
# Data structure
# ---------------------------------------------------------------------------

@dataclass
class ExecutiveReport:
    """Executive summary report data."""
    generated_at: str = ""
    target: str = ""
    grade: str = "A"
    files_scanned: int = 0
    total_findings: int = 0
    severity_counts: Dict[str, int] = field(default_factory=dict)
    injection_recall: Optional[float] = None
    injection_precision: Optional[float] = None
    doctor_status: str = "unknown"  # GREEN / YELLOW / RED / unknown
    doctor_checks_pass: int = 0
    doctor_checks_warn: int = 0
    doctor_checks_fail: int = 0
    config_files_found: int = 0
    config_files_total: int = 0
    recommendation: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Core builder
# ---------------------------------------------------------------------------

def build_executive_report(
    target: str = ".",
    *,
    run_scan: bool = True,
    run_injection_bench: bool = True,
    run_doctor: bool = True,
    run_stats: bool = True,
) -> ExecutiveReport:
    """Build an executive summary report combining multiple data sources."""
    report = ExecutiveReport(
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        target=str(target),
    )

    severity_counts: Dict[str, int] = {
        "critical": 0, "high": 0, "medium": 0, "low": 0,
    }

    # 1. Security scan
    if run_scan:
        try:
            from enforcement.scan_cmd import scan_path
            result = scan_path(target, check_injection=True)
            report.files_scanned = result.files_scanned
            report.total_findings = len(result.findings)
            for f in result.findings:
                sev = _severity_for_finding(f.finding_type)
                severity_counts[sev] = severity_counts.get(sev, 0) + 1
        except Exception:
            pass

    # 2. Injection benchmark
    if run_injection_bench:
        try:
            from egress_audit.detectors.prompt_injection import PromptInjectionDetector
            gold_path = _ROOT / "samples" / "injection_gold.jsonl"
            if gold_path.exists():
                import json as _json
                samples = []
                with open(gold_path, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            samples.append(_json.loads(line))
                detector = PromptInjectionDetector(min_severity="low")
                tp = fn = fp = 0
                for s in samples:
                    detected = detector.is_injection(s["text"])
                    if s["label"] == "injection":
                        if detected:
                            tp += 1
                        else:
                            fn += 1
                    else:
                        if detected:
                            fp += 1
                recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
                precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
                report.injection_recall = round(recall, 3)
                report.injection_precision = round(precision, 3)
        except Exception:
            pass

    # 3. Doctor checks
    if run_doctor:
        try:
            from enforcement.doctor import DoctorContext, run_checks, PASS, WARN, FAIL
            ctx = DoctorContext()
            results = run_checks(ctx)
            passes = sum(1 for r in results if r.status == PASS)
            warns = sum(1 for r in results if r.status == WARN)
            fails = sum(1 for r in results if r.status == FAIL)
            report.doctor_checks_pass = passes
            report.doctor_checks_warn = warns
            report.doctor_checks_fail = fails
            if fails > 0:
                report.doctor_status = "RED"
            elif warns > 0:
                report.doctor_status = "YELLOW"
            else:
                report.doctor_status = "GREEN"
        except Exception:
            pass

    # 4. Config status (stats)
    if run_stats:
        try:
            from enforcement.stats_cmd import collect_stats
            stats = collect_stats()
            found = sum(1 for cf in stats.config_files if cf.get("exists"))
            total = len(stats.config_files)
            report.config_files_found = found
            report.config_files_total = total
        except Exception:
            pass

    # Compute grade
    report.severity_counts = severity_counts
    report.grade = compute_grade(severity_counts)

    # Generate recommendation
    report.recommendation = _make_recommendation(report)

    return report


def _make_recommendation(report: ExecutiveReport) -> str:
    """Generate 1-2 sentence recommendation based on report data."""
    if report.grade == "A":
        return "No security findings detected. Continue regular scanning to maintain posture."
    if report.grade == "F":
        return ("Critical findings require immediate remediation. "
                "Review and remove exposed PII/credentials and fix injection vulnerabilities.")
    if report.grade == "D":
        return ("High-severity findings detected. "
                "Prioritize remediation of sensitive data exposure before next release.")
    if report.grade == "C":
        return ("Medium-severity findings present. "
                "Schedule remediation in the current sprint to reduce risk.")
    # B
    return "Only low-severity findings detected. Address during routine maintenance."


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------

def render_text(report: ExecutiveReport) -> str:
    """Render as plain text (default)."""
    lines = [
        "=" * 60,
        "  EXECUTIVE SECURITY SUMMARY",
        "=" * 60,
        f"  Date:    {report.generated_at}",
        f"  Target:  {report.target}",
        f"  Grade:   {report.grade}",
        "-" * 60,
        "  KEY METRICS",
        f"    Files scanned:      {report.files_scanned}",
        f"    Total findings:     {report.total_findings}",
    ]
    if report.injection_recall is not None:
        lines.append(f"    Injection recall:   {report.injection_recall:.1%}")
    if report.injection_precision is not None:
        lines.append(f"    Injection precision:{report.injection_precision:.1%}")
    lines.append(f"    Doctor status:      {report.doctor_status}")
    lines.append(f"    Config files:       {report.config_files_found}/{report.config_files_total}")
    lines.append("-" * 60)
    lines.append("  RISK SUMMARY")
    for sev in ("critical", "high", "medium", "low"):
        count = report.severity_counts.get(sev, 0)
        lines.append(f"    {sev.upper():<12} {count}")
    lines.append("-" * 60)
    lines.append("  RECOMMENDATION")
    lines.append(f"    {report.recommendation}")
    lines.append("=" * 60)
    return "\n".join(lines) + "\n"


def render_json(report: ExecutiveReport) -> str:
    """Render as JSON."""
    return json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n"


def render_markdown(report: ExecutiveReport) -> str:
    """Render as Markdown."""
    lines = [
        "# Executive Security Summary",
        "",
        f"**Date:** {report.generated_at}  ",
        f"**Target:** {report.target}  ",
        f"**Grade:** {report.grade}",
        "",
        "## Key Metrics",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Files scanned | {report.files_scanned} |",
        f"| Total findings | {report.total_findings} |",
    ]
    if report.injection_recall is not None:
        lines.append(f"| Injection recall | {report.injection_recall:.1%} |")
    if report.injection_precision is not None:
        lines.append(f"| Injection precision | {report.injection_precision:.1%} |")
    lines.append(f"| Doctor status | {report.doctor_status} |")
    lines.append(f"| Config files | {report.config_files_found}/{report.config_files_total} |")
    lines.append("")
    lines.append("## Risk Summary")
    lines.append("")
    lines.append("| Severity | Count |")
    lines.append("|----------|-------|")
    for sev in ("critical", "high", "medium", "low"):
        count = report.severity_counts.get(sev, 0)
        lines.append(f"| {sev.upper()} | {count} |")
    lines.append("")
    lines.append("## Recommendation")
    lines.append("")
    lines.append(report.recommendation)
    lines.append("")
    return "\n".join(lines)


def render(report: ExecutiveReport, fmt: str = "text") -> str:
    """Render report in the given format."""
    if fmt == "json":
        return render_json(report)
    if fmt in ("md", "markdown"):
        return render_markdown(report)
    return render_text(report)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def cmd_report_executive(args) -> int:
    """CLI handler for `nufi-egress report executive`."""
    target = getattr(args, "directory", ".")
    fmt = getattr(args, "format", "text")
    output = getattr(args, "output", None)

    report = build_executive_report(target)
    text = render(report, fmt)

    if output:
        Path(output).write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0
