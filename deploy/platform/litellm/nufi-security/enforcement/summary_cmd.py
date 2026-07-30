"""``nufi-egress summary`` -- project health dashboard (patch147).

Combines multiple data sources into a quick one-screen overview:
  - Config status (from stats)
  - Recent activity (last 5 events from history)
  - Last scan risk level (from cache if available)
  - Doctor check status (quick 6-check summary)
  - NuFi version

SDK usage::

    from enforcement.summary_cmd import collect_summary
    summary = collect_summary()
"""
from __future__ import annotations

import json
import platform
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Data collectors
# ---------------------------------------------------------------------------

def _get_version() -> str:
    """Return NuFi version string."""
    vf = _ROOT / "VERSION"
    return vf.read_text(encoding="utf-8").strip() if vf.exists() else "unknown"


def _get_config_status() -> Dict[str, Any]:
    """Quick config status from stats module."""
    try:
        from enforcement.stats_cmd import collect_stats
        stats = collect_stats(_ROOT)
        existing = [c["file"] for c in stats.config_files if c["exists"]]
        missing = [c["file"] for c in stats.config_files if not c["exists"]]
        return {
            "existing_count": len(existing),
            "missing_count": len(missing),
            "existing": existing,
            "missing": missing,
            "pii_patterns": stats.pii_pattern_count,
            "injection_patterns": stats.injection_pattern_count,
        }
    except Exception as e:
        return {"error": str(e)}


def _get_recent_activity(last: int = 5) -> List[Dict[str, Any]]:
    """Get recent activity events from history module."""
    try:
        from enforcement.history_cmd import read_history
        events = read_history(last=last, event_type="all")
        # Clean internal fields
        clean = []
        for ev in events:
            entry = {k: v for k, v in ev.items() if not k.startswith("_")}
            entry["type"] = ev.get("_type", "unknown")
            clean.append(entry)
        return clean
    except Exception:
        return []


def _get_last_scan_risk() -> Optional[str]:
    """Try to determine last scan risk level from cache."""
    cache_path = _ROOT / ".nufi_cache.json"
    if not cache_path.exists():
        return None
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "risk_level" in data:
            return data["risk_level"]
        if isinstance(data, list) and data:
            last = data[-1]
            return last.get("risk_level")
        return None
    except Exception:
        return None


def _get_doctor_summary() -> Dict[str, Any]:
    """Run quick doctor checks and return summary counts."""
    try:
        from enforcement.doctor import DoctorContext, run_checks, PASS, WARN, FAIL
        ctx = DoctorContext(ner_backend="gazetteer", connect_timeout=1.0)
        results = run_checks(ctx)
        counts = {PASS: 0, WARN: 0, FAIL: 0}
        for r in results:
            counts[r.status] = counts.get(r.status, 0) + 1
        checks = [{"id": r.id, "status": r.status} for r in results]
        if counts[FAIL]:
            overall = "RED"
        elif counts[WARN]:
            overall = "YELLOW"
        else:
            overall = "GREEN"
        return {
            "overall": overall,
            "pass": counts[PASS],
            "warn": counts[WARN],
            "fail": counts[FAIL],
            "total": len(results),
            "checks": checks,
        }
    except Exception as e:
        return {"overall": "UNKNOWN", "error": str(e),
                "pass": 0, "warn": 0, "fail": 0, "total": 0, "checks": []}


# ---------------------------------------------------------------------------
# Main collector
# ---------------------------------------------------------------------------

def collect_summary() -> Dict[str, Any]:
    """Collect all summary data into a single dict."""
    return {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime()),
        "version": _get_version(),
        "python": platform.python_version(),
        "config": _get_config_status(),
        "recent_activity": _get_recent_activity(last=5),
        "last_scan_risk": _get_last_scan_risk(),
        "doctor": _get_doctor_summary(),
    }


# ---------------------------------------------------------------------------
# Human rendering
# ---------------------------------------------------------------------------

def render_human(summary: Dict[str, Any]) -> str:
    """Render summary as a one-screen human-readable dashboard."""
    lines: List[str] = []
    lines.append("=" * 60)
    lines.append(f"  NuFi Project Health Dashboard  (v{summary['version']})")
    lines.append("=" * 60)
    lines.append(f"  Time: {summary['ts']}  |  Python: {summary['python']}")
    lines.append("")

    # Config
    cfg = summary.get("config", {})
    if "error" in cfg:
        lines.append(f"[Config] Error: {cfg['error']}")
    else:
        lines.append(f"[Config] Files: {cfg.get('existing_count', 0)} present, "
                     f"{cfg.get('missing_count', 0)} missing")
        lines.append(f"  PII patterns: {cfg.get('pii_patterns', 0)}  |  "
                     f"Injection patterns: {cfg.get('injection_patterns', 0)}")
    lines.append("")

    # Recent activity
    activity = summary.get("recent_activity", [])
    lines.append(f"[Recent Activity] (last {len(activity)} events)")
    if activity:
        for ev in activity:
            ts = ev.get("ts", ev.get("timestamp", "?"))
            etype = ev.get("type", "?")
            outcome = ev.get("outcome", "")
            lines.append(f"  [{ts}] {etype:<6} {outcome}")
    else:
        lines.append("  (no activity recorded)")
    lines.append("")

    # Last scan risk
    risk = summary.get("last_scan_risk")
    if risk:
        lines.append(f"[Last Scan Risk] {risk}")
    else:
        lines.append("[Last Scan Risk] (no cached scan data)")
    lines.append("")

    # Doctor
    doc = summary.get("doctor", {})
    overall = doc.get("overall", "UNKNOWN")
    _overall_icon = {"GREEN": "GREEN", "YELLOW": "YELLOW", "RED": "RED"}
    lines.append(f"[Doctor] {_overall_icon.get(overall, overall)}  "
                 f"(PASS {doc.get('pass', 0)} / WARN {doc.get('warn', 0)} / "
                 f"FAIL {doc.get('fail', 0)} / {doc.get('total', 0)} checks)")
    for chk in doc.get("checks", []):
        _glyph = {"PASS": "+", "WARN": "~", "FAIL": "!"}
        lines.append(f"  [{chk['status']}] {_glyph.get(chk['status'], '?')} {chk['id']}")
    lines.append("")
    lines.append("=" * 60)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI handler
# ---------------------------------------------------------------------------

def cmd_summary(args) -> int:
    """``nufi-egress summary`` CLI handler."""
    summary = collect_summary()

    if getattr(args, "json", False):
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(render_human(summary))

    return 0
