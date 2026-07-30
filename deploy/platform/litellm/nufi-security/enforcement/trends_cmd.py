"""``nufi-egress report trends`` -- PII detection trends over time (patch149).

Reads the audit log (logs/egress_audit.jsonl) and groups findings by day,
showing total events, blocked count, and PII types found per day.

Options:
  --period N    Show last N days (default 7)
  --json        Machine-readable JSON output
  --audit PATH  Override audit log path

SDK usage::

    from enforcement.trends_cmd import build_trends
    trends = build_trends(period=30)
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

_ROOT = Path(__file__).resolve().parent.parent


def _load_audit_log(path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Load events from egress_audit.jsonl."""
    p = Path(path) if path else _ROOT / "logs" / "egress_audit.jsonl"
    if not p.exists():
        return []
    events: List[Dict[str, Any]] = []
    with open(p, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                events.append(rec)
            except json.JSONDecodeError:
                continue
    return events


def _extract_date(record: Dict[str, Any]) -> Optional[str]:
    """Extract date string (YYYY-MM-DD) from a record's timestamp."""
    ts = record.get("ts") or record.get("timestamp") or ""
    if not ts:
        return None
    # Try ISO format: 2026-07-05T12:34:56... -> 2026-07-05
    try:
        return ts[:10]
    except (TypeError, IndexError):
        return None


def _extract_pii_types(record: Dict[str, Any]) -> List[str]:
    """Extract PII entity types from a record's findings."""
    findings = record.get("findings", [])
    if not isinstance(findings, list):
        return []
    types: List[str] = []
    for f in findings:
        if isinstance(f, dict):
            et = f.get("entity_type") or f.get("type") or f.get("category")
            if et:
                types.append(et)
    return types


def build_trends(
    period: int = 7,
    audit_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Build PII detection trends grouped by day.

    Args:
        period: Number of days to include (most recent N days with data).
        audit_path: Path to egress_audit.jsonl.

    Returns:
        Dict with trends data: days list, summary stats.
    """
    records = _load_audit_log(audit_path)

    # Group by date
    by_date: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for rec in records:
        date = _extract_date(rec)
        if date:
            by_date[date].append(rec)

    # Sort dates descending, take last N
    all_dates = sorted(by_date.keys(), reverse=True)
    selected_dates = all_dates[:period]
    selected_dates.sort()  # chronological order for output

    days: List[Dict[str, Any]] = []
    total_events = 0
    total_blocked = 0
    all_pii_types: Counter = Counter()

    for date in selected_dates:
        recs = by_date[date]
        blocked = sum(1 for r in recs if r.get("outcome") == "blocked")
        pii_types: Counter = Counter()
        for r in recs:
            for et in _extract_pii_types(r):
                pii_types[et] += 1

        day_entry = {
            "date": date,
            "total": len(recs),
            "blocked": blocked,
            "pii_types": dict(pii_types.most_common()),
        }
        days.append(day_entry)
        total_events += len(recs)
        total_blocked += blocked
        all_pii_types.update(pii_types)

    return {
        "period": period,
        "days_with_data": len(days),
        "total_events": total_events,
        "total_blocked": total_blocked,
        "pii_types_summary": dict(all_pii_types.most_common()),
        "days": days,
    }


def render_human(trends: Dict[str, Any]) -> str:
    """Render trends as human-readable text."""
    lines: List[str] = []
    lines.append(f"PII Detection Trends (last {trends['period']} days)")
    lines.append(f"  Days with data: {trends['days_with_data']}")
    lines.append(f"  Total events: {trends['total_events']}")
    lines.append(f"  Total blocked: {trends['total_blocked']}")
    lines.append("")

    if not trends["days"]:
        lines.append("  (No audit data found)")
        return "\n".join(lines)

    # Table header
    lines.append(f"  {'Date':<12} {'Events':>7} {'Blocked':>8}  PII Types")
    lines.append(f"  {'-'*12} {'-'*7} {'-'*8}  {'-'*30}")

    for day in trends["days"]:
        pii = ", ".join(f"{k}({v})" for k, v in day["pii_types"].items()) or "-"
        lines.append(
            f"  {day['date']:<12} {day['total']:>7} {day['blocked']:>8}  {pii}"
        )

    lines.append("")
    if trends["pii_types_summary"]:
        lines.append("  Overall PII types: " + ", ".join(
            f"{k}={v}" for k, v in trends["pii_types_summary"].items()
        ))

    return "\n".join(lines)


def cmd_report_trends(args) -> int:
    """CLI handler for ``nufi-egress report trends``."""
    period = getattr(args, "period", 7) or 7
    audit_path = getattr(args, "audit", None)
    use_json = getattr(args, "json", False)

    trends = build_trends(period=period, audit_path=audit_path)

    if use_json:
        print(json.dumps(trends, ensure_ascii=False, indent=2))
    else:
        print(render_human(trends))

    return 0
