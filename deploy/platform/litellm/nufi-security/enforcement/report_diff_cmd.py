"""``nufi-egress report diff`` -- diff report between two scan results (patch153).

Generates a human-readable diff report (markdown, JSON, or HTML) comparing
two scan results.  Reuses :func:`enforcement.compare_cmd.compare_scans` for
the actual comparison logic.

Usage::

    nufi-egress report diff before.json after.json
    nufi-egress report diff before.json after.json --format html --output diff.html
    nufi-egress report diff before.sarif after.sarif --format json
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from enforcement.compare_cmd import CompareResult, compare_scans, _NormFinding


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------

def _severity_from_type(finding_type: str) -> str:
    """Heuristic severity from finding_type string."""
    _STRONG = {"KR_RRN", "KR_PASSPORT", "KR_DRIVER"}
    if finding_type.startswith("INJECTION:"):
        return "critical"
    entity = finding_type.split(":", 1)[1] if ":" in finding_type else finding_type
    if entity in _STRONG:
        return "critical"
    if entity in {"KR_PHONE", "KR_ACCOUNT", "EMAIL"}:
        return "high"
    return "medium"


def _findings_table_md(findings: List[_NormFinding], *, label: str) -> str:
    """Render a markdown table for a list of findings."""
    if not findings:
        return ""
    lines = [
        f"### {label}\n",
        "| File | Entity | Severity |",
        "|------|--------|----------|",
    ]
    for f in findings:
        sev = _severity_from_type(f.finding_type)
        lines.append(f"| `{f.file}:{f.line}` | {f.finding_type} | {sev} |")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public renderers
# ---------------------------------------------------------------------------

def render_diff_md(result: CompareResult, *, before_name: str = "before",
                   after_name: str = "after") -> str:
    """Render a CompareResult as a markdown diff report."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    parts: List[str] = [
        "# Scan Diff Report\n",
        f"**Generated:** {now}  ",
        f"**Before:** `{before_name}` | **After:** `{after_name}`\n",
        "## Summary\n",
        (f"{len(result.new_findings)} new findings, "
         f"{len(result.resolved_findings)} resolved, "
         f"{len(result.unchanged_findings)} unchanged\n"),
    ]

    tbl_new = _findings_table_md(result.new_findings, label="New Findings")
    if tbl_new:
        parts.append(tbl_new)

    tbl_resolved = _findings_table_md(result.resolved_findings,
                                       label="Resolved Findings")
    if tbl_resolved:
        parts.append(tbl_resolved)

    parts.append(f"### Unchanged\n\n{len(result.unchanged_findings)} findings remain.\n")
    return "\n".join(parts)


def render_diff_json(result: CompareResult, *, before_name: str = "before",
                     after_name: str = "after") -> str:
    """Render a CompareResult as JSON."""
    d = result.to_dict()
    d["before"] = before_name
    d["after"] = after_name
    return json.dumps(d, ensure_ascii=False, indent=2)


def render_diff_html(result: CompareResult, *, before_name: str = "before",
                     after_name: str = "after") -> str:
    """Render a CompareResult as a minimal HTML report."""

    def _rows(findings: List[_NormFinding]) -> str:
        if not findings:
            return "<tr><td colspan='3'>(none)</td></tr>"
        return "\n".join(
            f"<tr><td><code>{f.file}:{f.line}</code></td>"
            f"<td>{f.finding_type}</td>"
            f"<td>{_severity_from_type(f.finding_type)}</td></tr>"
            for f in findings
        )

    summary = (f"{len(result.new_findings)} new findings, "
               f"{len(result.resolved_findings)} resolved, "
               f"{len(result.unchanged_findings)} unchanged")
    return f"""\
<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Scan Diff Report</title>
<style>body{{font-family:sans-serif;margin:2em}}table{{border-collapse:collapse;width:100%}}
th,td{{border:1px solid #ccc;padding:6px 10px;text-align:left}}th{{background:#f5f5f5}}</style>
</head><body>
<h1>Scan Diff Report</h1>
<p><b>Before:</b> <code>{before_name}</code> | <b>After:</b> <code>{after_name}</code></p>
<h2>Summary</h2><p>{summary}</p>
<h3>New Findings</h3>
<table><tr><th>File</th><th>Entity</th><th>Severity</th></tr>
{_rows(result.new_findings)}
</table>
<h3>Resolved Findings</h3>
<table><tr><th>File</th><th>Entity</th><th>Severity</th></tr>
{_rows(result.resolved_findings)}
</table>
<h3>Unchanged</h3><p>{len(result.unchanged_findings)} findings remain.</p>
</body></html>"""


# ---------------------------------------------------------------------------
# CLI handler
# ---------------------------------------------------------------------------

def cmd_report_diff(args) -> int:
    """``nufi-egress report diff`` CLI handler."""
    before = getattr(args, "before", None)
    after = getattr(args, "after", None)
    fmt = getattr(args, "format", "md") or "md"
    output = getattr(args, "output", None)

    if not before or not after:
        print("오류: before 와 after 경로를 모두 지정해야 합니다.", file=sys.stderr)
        return 2

    bp = Path(before)
    ap = Path(after)
    for p, label in [(bp, "before"), (ap, "after")]:
        if not p.exists():
            print(f"오류: {label} 파일을 찾을 수 없습니다: {p}", file=sys.stderr)
            return 2

    try:
        result = compare_scans(bp, ap)
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 2

    renderers = {
        "md": render_diff_md,
        "json": render_diff_json,
        "html": render_diff_html,
    }
    render_fn = renderers.get(fmt, render_diff_md)
    text = render_fn(result, before_name=bp.name, after_name=ap.name)

    if output:
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_text(text, encoding="utf-8")
        print(f"[report diff] 기록: {output}")
    else:
        print(text)

    return 0
