"""``nufi-egress history`` -- activity log viewer (patch141).

Shows recent NuFi activity by reading the audit log and scan cache:
  - Scans, blocks, routing decisions
  - ``--last N`` to limit events (default 20)
  - ``--type scan|block|route|all`` to filter
  - ``--json`` for machine output

SDK usage::

    from enforcement.history_cmd import read_history
    events = read_history(last=10, event_type="all")
"""
from __future__ import annotations

import json
import sys
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


def _load_scan_cache(path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Load events from .nufi_cache.json."""
    p = Path(path) if path else _ROOT / ".nufi_cache.json"
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    # Cache can be a list of scan records or a dict with a "scans" key
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "scans" in data:
        return data["scans"] if isinstance(data["scans"], list) else []
    return []


def _classify_event(event: Dict[str, Any]) -> str:
    """Classify an event as scan/block/route based on its fields."""
    outcome = event.get("outcome", "")
    if outcome == "blocked":
        return "block"
    # Check for routing decision fields
    if "routed_to_local" in event or "target_model" in event:
        return "route"
    # Check for scan-related fields
    if "findings" in event or "finding_count" in event or "scan" in event.get("action", ""):
        return "scan"
    # Audit log entries with outcome
    if outcome in ("allowed", "transformed", "passed"):
        return "route"
    # Default: treat as scan
    return "scan"


def read_history(
    last: int = 20,
    event_type: str = "all",
    audit_path: Optional[str] = None,
    cache_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Read and merge activity events from audit log and scan cache.

    Args:
        last: Maximum number of events to return.
        event_type: Filter by type: "scan", "block", "route", or "all".
        audit_path: Path to egress_audit.jsonl (default: logs/egress_audit.jsonl).
        cache_path: Path to .nufi_cache.json (default: .nufi_cache.json).

    Returns:
        List of event dicts, most recent first.
    """
    audit_events = _load_audit_log(audit_path)
    cache_events = _load_scan_cache(cache_path)

    # Tag source and classify
    all_events: List[Dict[str, Any]] = []

    for ev in audit_events:
        classified = _classify_event(ev)
        entry = {**ev, "_source": "audit", "_type": classified}
        all_events.append(entry)

    for ev in cache_events:
        entry = {**ev, "_source": "cache", "_type": "scan"}
        all_events.append(entry)

    # Sort by timestamp (most recent first)
    def _sort_key(e: Dict[str, Any]) -> str:
        return e.get("ts", e.get("timestamp", ""))

    all_events.sort(key=_sort_key, reverse=True)

    # Filter by type
    if event_type != "all":
        all_events = [e for e in all_events if e.get("_type") == event_type]

    # Limit
    return all_events[:last]


def render_human(events: List[Dict[str, Any]]) -> str:
    """Render events as human-readable text."""
    if not events:
        return "No activity recorded yet"

    lines: List[str] = []
    lines.append(f"Recent activity ({len(events)} events):")
    lines.append("")

    for ev in events:
        ts = ev.get("ts", ev.get("timestamp", "?"))
        etype = ev.get("_type", "?")
        source = ev.get("_source", "?")
        outcome = ev.get("outcome", "")

        # Build description
        if etype == "block":
            findings = ev.get("findings", [])
            n = len(findings) if isinstance(findings, list) else 0
            desc = f"BLOCKED — {n} finding(s)"
        elif etype == "route":
            target = ev.get("target_model", "")
            local = ev.get("routed_to_local", None)
            if local is not None:
                route_str = "local" if local else "cloud"
            elif outcome:
                route_str = outcome
            else:
                route_str = target or "?"
            desc = f"ROUTE → {route_str}"
        else:  # scan
            finding_count = ev.get("finding_count", None)
            if finding_count is None:
                findings = ev.get("findings", [])
                finding_count = len(findings) if isinstance(findings, list) else 0
            desc = f"SCAN — {finding_count} finding(s)"

        lines.append(f"  [{ts}] {etype:<6} {desc}  (source: {source})")

    return "\n".join(lines)


def cmd_history(args) -> int:
    """CLI handler for ``nufi-egress history``."""
    last_n = getattr(args, "last", 20)
    event_type = getattr(args, "type", "all") or "all"
    use_json = getattr(args, "json", False)

    events = read_history(
        last=last_n,
        event_type=event_type,
    )

    if use_json:
        # Strip internal fields for clean output
        clean = []
        for ev in events:
            entry = {k: v for k, v in ev.items() if not k.startswith("_")}
            entry["type"] = ev.get("_type", "unknown")
            entry["source"] = ev.get("_source", "unknown")
            clean.append(entry)
        print(json.dumps(clean, ensure_ascii=False, indent=2))
    else:
        print(render_human(events))

    return 0
