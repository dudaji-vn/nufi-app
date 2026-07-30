"""``nufi-egress report security`` — 보안 포스처 요약 리포트 생성 (patch98).

디렉터리를 스캔하여 PII/인젝션 패턴을 탐지하고, 위험도를 평가해
마크다운 또는 JSON 형태의 보안 포스처 리포트를 생성한다.

SDK: ``from nufi import security_report``
"""
from __future__ import annotations

import collections
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from enforcement.scan_cmd import scan_path, ScanResult, _STRONG_PII


# ---------------------------------------------------------------------------
# Risk scoring
# ---------------------------------------------------------------------------

def _severity_for_finding(finding_type: str) -> str:
    """Map finding type to severity level."""
    if finding_type.startswith("INJECTION:"):
        return "critical"
    entity = finding_type.split(":", 1)[1] if ":" in finding_type else finding_type
    if entity in _STRONG_PII:
        return "critical"
    # Medium-strength PII
    if entity in ("EMAIL", "PHONE", "KR_PHONE", "IP_ADDRESS"):
        return "medium"
    # Remaining PII types
    return "high"


def _risk_level(findings: List[Any]) -> str:
    """Determine overall risk level from findings."""
    if not findings:
        return "low"
    severities = [_severity_for_finding(f.finding_type) for f in findings]
    if "critical" in severities:
        return "critical"
    if "high" in severities:
        return "high"
    if "medium" in severities:
        return "medium"
    return "low"


# ---------------------------------------------------------------------------
# Report data structure
# ---------------------------------------------------------------------------

@dataclass
class SecurityReport:
    """Security posture report data."""
    generated_at: str = ""
    directory: str = ""
    files_scanned: int = 0
    files_with_findings: int = 0
    total_findings: int = 0
    risk_level: str = "low"
    findings_by_severity: Dict[str, int] = field(default_factory=dict)
    top_entity_types: List[Dict[str, Any]] = field(default_factory=list)
    injection_patterns: List[Dict[str, Any]] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "directory": self.directory,
            "files_scanned": self.files_scanned,
            "files_with_findings": self.files_with_findings,
            "total_findings": self.total_findings,
            "risk_level": self.risk_level,
            "findings_by_severity": self.findings_by_severity,
            "top_entity_types": self.top_entity_types,
            "injection_patterns": self.injection_patterns,
            "recommendations": self.recommendations,
        }


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def generate_security_report(
    directory: str | Path,
    *,
    patterns: Optional[List[str]] = None,
    exclude: Optional[List[str]] = None,
) -> SecurityReport:
    """Scan a directory and produce a SecurityReport.

    Args:
        directory: Path to directory to scan.
        patterns: Glob patterns to filter files.
        exclude: Glob patterns to exclude.

    Returns:
        SecurityReport with findings analysis.
    """
    directory = Path(directory)
    result: ScanResult = scan_path(
        directory,
        patterns=patterns,
        check_injection=True,
        exclude=exclude,
    )

    # Severity breakdown
    severity_counter: collections.Counter[str] = collections.Counter()
    entity_counter: collections.Counter[str] = collections.Counter()
    injection_list: List[Dict[str, Any]] = []

    for f in result.findings:
        sev = _severity_for_finding(f.finding_type)
        severity_counter[sev] += 1

        if f.finding_type.startswith("INJECTION:"):
            injection_list.append({
                "pattern": f.finding_type.split(":", 1)[1],
                "file": f.file,
                "line": f.line,
                "text": f.text,
            })
        else:
            entity_counter[f.finding_type] += 1

    # Top entity types (up to 10)
    top_entities = [
        {"type": etype, "count": count}
        for etype, count in entity_counter.most_common(10)
    ]

    # Recommendations
    recommendations = _build_recommendations(result, severity_counter, injection_list)

    report = SecurityReport(
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        directory=str(directory),
        files_scanned=result.files_scanned,
        files_with_findings=result.files_with_findings,
        total_findings=len(result.findings),
        risk_level=_risk_level(result.findings),
        findings_by_severity=dict(severity_counter),
        top_entity_types=top_entities,
        injection_patterns=injection_list,
        recommendations=recommendations,
    )
    return report


def _build_recommendations(
    result: ScanResult,
    severity_counter: "collections.Counter[str]",
    injection_list: List[Dict[str, Any]],
) -> List[str]:
    """Build actionable recommendations based on findings."""
    recs: List[str] = []
    if not result.findings:
        recs.append("No issues found. Continue monitoring with periodic scans.")
        return recs

    if severity_counter.get("critical", 0) > 0:
        recs.append(
            "URGENT: Critical findings detected (strong PII or injection patterns). "
            "Remediate immediately before deployment."
        )
    if injection_list:
        recs.append(
            f"Prompt injection patterns found ({len(injection_list)} instance(s)). "
            "Review input validation and sanitization."
        )
    if severity_counter.get("high", 0) > 0:
        recs.append(
            "High-severity PII detected. Apply redaction (nufi-egress scan --redact) "
            "or remove sensitive data before sharing."
        )
    if severity_counter.get("medium", 0) > 0:
        recs.append(
            "Medium-severity findings (emails, phones, IPs). "
            "Consider masking or pseudonymizing before external use."
        )
    if not recs:
        recs.append("Review findings and apply appropriate data handling policies.")
    return recs


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------

def render_markdown(report: SecurityReport) -> str:
    """Render SecurityReport as a concise Markdown document."""
    lines: List[str] = []
    lines.append("# Security Posture Report")
    lines.append("")
    lines.append(f"**Generated:** {report.generated_at}  ")
    lines.append(f"**Directory:** `{report.directory}`  ")
    lines.append("")

    # Executive summary
    lines.append("## Executive Summary")
    lines.append("")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Files scanned | {report.files_scanned} |")
    lines.append(f"| Files with findings | {report.files_with_findings} |")
    lines.append(f"| Total findings | {report.total_findings} |")
    lines.append(f"| Risk level | **{report.risk_level.upper()}** |")
    lines.append("")

    # Findings by severity
    lines.append("## Findings by Severity")
    lines.append("")
    if report.findings_by_severity:
        lines.append("| Severity | Count |")
        lines.append("|----------|-------|")
        for sev in ("critical", "high", "medium", "low"):
            count = report.findings_by_severity.get(sev, 0)
            if count:
                lines.append(f"| {sev} | {count} |")
    else:
        lines.append("No findings.")
    lines.append("")

    # Top entity types
    lines.append("## Top Entity Types")
    lines.append("")
    if report.top_entity_types:
        lines.append("| Entity Type | Count |")
        lines.append("|-------------|-------|")
        for entry in report.top_entity_types:
            lines.append(f"| {entry['type']} | {entry['count']} |")
    else:
        lines.append("None detected.")
    lines.append("")

    # Injection patterns
    lines.append("## Injection Patterns")
    lines.append("")
    if report.injection_patterns:
        lines.append(f"**{len(report.injection_patterns)} pattern(s) detected:**")
        lines.append("")
        for inj in report.injection_patterns:
            lines.append(f"- `{inj['pattern']}` in `{inj['file']}` L{inj['line']}")
    else:
        lines.append("No injection patterns detected.")
    lines.append("")

    # Recommendations
    lines.append("## Recommended Actions")
    lines.append("")
    for rec in report.recommendations:
        lines.append(f"- {rec}")
    lines.append("")

    return "\n".join(lines)


def render_html(report: SecurityReport) -> str:
    """Render SecurityReport as a self-contained HTML document with inline CSS."""
    severity_colors = {
        "critical": "#dc2626",
        "high": "#ea580c",
        "medium": "#ca8a04",
        "low": "#2563eb",
    }

    risk_color = severity_colors.get(report.risk_level, "#6b7280")

    # Build severity badges row
    severity_rows = ""
    for sev in ("critical", "high", "medium", "low"):
        count = report.findings_by_severity.get(sev, 0)
        if count:
            color = severity_colors[sev]
            severity_rows += (
                f'<tr><td><span class="badge" style="background:{color}">'
                f'{sev.upper()}</span></td><td>{count}</td></tr>\n'
            )

    # Entity type rows
    entity_rows = ""
    for entry in report.top_entity_types:
        entity_rows += f'<tr><td>{entry["type"]}</td><td>{entry["count"]}</td></tr>\n'

    # Injection rows
    injection_rows = ""
    for inj in report.injection_patterns:
        injection_rows += (
            f'<tr><td><code>{inj["pattern"]}</code></td>'
            f'<td><code>{inj["file"]}</code></td>'
            f'<td>{inj["line"]}</td></tr>\n'
        )

    # Recommendations list
    recs_html = ""
    for rec in report.recommendations:
        recs_html += f"<li>{rec}</li>\n"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Security Posture Report</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
         margin: 0; padding: 2rem; background: #f9fafb; color: #1f2937; line-height: 1.6; }}
  .container {{ max-width: 900px; margin: 0 auto; background: #fff;
               border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,.1); padding: 2rem; }}
  h1 {{ margin-top: 0; color: #111827; }}
  h2 {{ border-bottom: 2px solid #e5e7eb; padding-bottom: .5rem; margin-top: 2rem; }}
  .risk-banner {{ padding: 1rem; border-radius: 6px; color: #fff;
                 font-size: 1.1rem; font-weight: 600; margin-bottom: 1.5rem; }}
  table {{ border-collapse: collapse; width: 100%; margin-bottom: 1rem; }}
  th, td {{ border: 1px solid #e5e7eb; padding: .5rem .75rem; text-align: left; }}
  th {{ background: #f3f4f6; font-weight: 600; }}
  .badge {{ display: inline-block; padding: 2px 8px; border-radius: 4px;
           color: #fff; font-size: .8rem; font-weight: 600; text-transform: uppercase; }}
  .meta {{ color: #6b7280; font-size: .9rem; }}
  footer {{ margin-top: 2rem; padding-top: 1rem; border-top: 1px solid #e5e7eb;
           color: #9ca3af; font-size: .8rem; }}
  code {{ background: #f3f4f6; padding: 2px 4px; border-radius: 3px; font-size: .85rem; }}
  ul {{ padding-left: 1.5rem; }}
</style>
</head>
<body>
<div class="container">
  <h1>Security Posture Report</h1>
  <p class="meta"><strong>Directory:</strong> <code>{report.directory}</code><br>
  <strong>Generated:</strong> {report.generated_at}</p>

  <div class="risk-banner" style="background:{risk_color}">
    Overall Risk Level: {report.risk_level.upper()}
  </div>

  <h2>Executive Summary</h2>
  <table>
    <tr><th>Metric</th><th>Value</th></tr>
    <tr><td>Files scanned</td><td>{report.files_scanned}</td></tr>
    <tr><td>Files with findings</td><td>{report.files_with_findings}</td></tr>
    <tr><td>Total findings</td><td>{report.total_findings}</td></tr>
    <tr><td>Risk level</td><td><span class="badge" style="background:{risk_color}">{report.risk_level.upper()}</span></td></tr>
  </table>

  <h2>Findings by Severity</h2>
  {"<table><tr><th>Severity</th><th>Count</th></tr>" + severity_rows + "</table>" if severity_rows else "<p>No findings.</p>"}

  <h2>Top Entity Types</h2>
  {"<table><tr><th>Entity Type</th><th>Count</th></tr>" + entity_rows + "</table>" if entity_rows else "<p>None detected.</p>"}

  <h2>Injection Patterns</h2>
  {"<table><tr><th>Pattern</th><th>File</th><th>Line</th></tr>" + injection_rows + "</table>" if injection_rows else "<p>No injection patterns detected.</p>"}

  <h2>Recommended Actions</h2>
  {("<ul>" + recs_html + "</ul>") if recs_html else "<p>No recommendations.</p>"}

  <footer>
    Generated by NuFi Security &mdash; {report.generated_at}
  </footer>
</div>
</body>
</html>"""
    return html


def render_json(report: SecurityReport) -> str:
    """Render SecurityReport as JSON string."""
    return json.dumps(report.to_dict(), ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# CLI handler
# ---------------------------------------------------------------------------

def cmd_report_security(args) -> int:
    """CLI handler for ``nufi-egress report security``."""
    directory = args.directory

    # Parse patterns
    patterns: Optional[List[str]] = None
    if getattr(args, "pattern", None):
        patterns = [p.strip() for p in args.pattern.split(",") if p.strip()]

    exclude: Optional[List[str]] = None
    if getattr(args, "exclude", None):
        exclude = [p.strip() for p in args.exclude.split(",") if p.strip()]

    report = generate_security_report(
        directory,
        patterns=patterns,
        exclude=exclude,
    )

    fmt = getattr(args, "format", "md") or "md"
    if fmt == "json":
        text = render_json(report)
    elif fmt == "html":
        text = render_html(report)
    else:
        text = render_markdown(report)

    output_path = getattr(args, "output", None)
    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(text + "\n", encoding="utf-8")
        import sys
        print(f"[report security] written: {output_path}", file=sys.stderr)
    else:
        print(text)

    return 0
