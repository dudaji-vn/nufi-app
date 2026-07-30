"""``nufi-egress report posture`` — compliance posture snapshot (patch168).

Captures a point-in-time security posture snapshot for tracking over time.
Snapshots include overall grade, finding counts, entity distribution,
injection benchmark results, doctor check results, and config completeness.

Snapshots can be saved to ``.nufi_posture_history.jsonl`` for trend tracking,
and compared to show improvements or regressions.

SDK:
  from enforcement.posture_cmd import capture_posture, compare_posture
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

POSTURE_HISTORY_FILE = ".nufi_posture_history.jsonl"


# ---------------------------------------------------------------------------
# Grade logic (reuse from executive_report)
# ---------------------------------------------------------------------------

def _compute_grade(severity_counts: Dict[str, int]) -> str:
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
# Posture capture
# ---------------------------------------------------------------------------

def capture_posture(target_dir: str | Path) -> Dict[str, Any]:
    """Capture a posture snapshot for the given directory.

    Returns a dict with timestamp, grade, counts, entity distribution,
    injection status, doctor results, and config completeness.
    """
    from enforcement.scan_cmd import scan_path

    target_dir = Path(target_dir)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # --- Scan ---
    result = scan_path(target_dir, patterns=None, check_injection=True, exclude=None)

    severity_counter: Counter = Counter()
    entity_counter: Counter = Counter()
    for f in result.findings:
        sev = _severity_for_finding(f.finding_type)
        severity_counter[sev] += 1
        if not f.finding_type.startswith("INJECTION:"):
            entity_counter[f.finding_type] += 1

    grade = _compute_grade(dict(severity_counter))

    # --- Injection benchmark status ---
    injection_status = _get_injection_status()

    # --- Doctor checks ---
    doctor_results = _get_doctor_results()

    # --- Config completeness ---
    config_completeness = _get_config_completeness()

    return {
        "timestamp": timestamp,
        "target": str(target_dir),
        "grade": grade,
        "file_count": result.files_scanned,
        "finding_count": len(result.findings),
        "severity_counts": dict(severity_counter),
        "entity_distribution": dict(entity_counter.most_common(20)),
        "injection_status": injection_status,
        "doctor_results": doctor_results,
        "config_completeness": config_completeness,
    }


def _get_injection_status() -> Dict[str, Any]:
    """Get injection benchmark recall/precision if available."""
    try:
        from enforcement.benchmark import (
            run_injection_benchmark,
            INJECTION_RECALL_FLOOR,
            INJECTION_PRECISION_FLOOR,
        )
        result = run_injection_benchmark()
        return {
            "available": True,
            "recall": result.get("recall"),
            "precision": result.get("precision"),
            "f1": result.get("f1"),
            "pass": result.get("pass", False),
        }
    except Exception:
        return {"available": False, "recall": None, "precision": None, "f1": None, "pass": None}


def _get_doctor_results() -> Dict[str, Any]:
    """Run doctor checks and return summary."""
    try:
        from enforcement.doctor import DoctorContext, run_checks, build_report
        ctx = DoctorContext()
        report = build_report(run_checks(ctx))
        summary = report.get("summary", {})
        return {
            "available": True,
            "pass": summary.get("pass", 0),
            "warn": summary.get("warn", 0),
            "fail": summary.get("fail", 0),
            "total": summary.get("total", 0),
        }
    except Exception:
        return {"available": False, "pass": 0, "warn": 0, "fail": 0, "total": 0}


def _get_config_completeness() -> Dict[str, Any]:
    """Check how complete the configuration is."""
    checks = {
        "routing_yaml": (_ROOT / "config" / "routing.yaml").exists(),
        "policy_yaml": (_ROOT / "config" / "policy.yaml").exists(),
        "capture_targets": (_ROOT / "config" / "capture_targets.yaml").exists(),
        "nufiignore": (_ROOT / ".nufiignore").exists(),
    }
    present = sum(1 for v in checks.values() if v)
    total = len(checks)
    return {
        "present": present,
        "total": total,
        "ratio": round(present / total, 2) if total else 1.0,
        "files": checks,
    }


# ---------------------------------------------------------------------------
# History management
# ---------------------------------------------------------------------------

def save_posture(snapshot: Dict[str, Any], history_path: Optional[Path] = None) -> Path:
    """Append posture snapshot to the JSONL history file."""
    path = history_path or Path(POSTURE_HISTORY_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(snapshot, ensure_ascii=False) + "\n")
    return path


def load_history(history_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Load all posture snapshots from history file."""
    path = history_path or Path(POSTURE_HISTORY_FILE)
    if not path.exists():
        return []
    entries: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def get_last_posture(history_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Get the most recent posture snapshot from history."""
    entries = load_history(history_path)
    return entries[-1] if entries else None


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------

def compare_posture(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
    """Compare two posture snapshots and show improvements/regressions.

    Returns a dict with:
      - improved: list of improvement descriptions
      - regressed: list of regression descriptions
      - unchanged: list of unchanged items
      - grade_change: (before_grade, after_grade) or None
    """
    improved: List[str] = []
    regressed: List[str] = []
    unchanged: List[str] = []

    # Grade
    grade_before = before.get("grade", "?")
    grade_after = after.get("grade", "?")
    grade_order = {"A": 0, "B": 1, "C": 2, "D": 3, "F": 4}
    gb = grade_order.get(grade_before, 5)
    ga = grade_order.get(grade_after, 5)
    grade_change = None
    if gb != ga:
        grade_change = (grade_before, grade_after)
        if ga < gb:
            improved.append(f"Grade improved: {grade_before} -> {grade_after}")
        else:
            regressed.append(f"Grade regressed: {grade_before} -> {grade_after}")
    else:
        unchanged.append(f"Grade unchanged: {grade_after}")

    # Finding count
    fc_before = before.get("finding_count", 0)
    fc_after = after.get("finding_count", 0)
    if fc_after < fc_before:
        improved.append(f"Findings reduced: {fc_before} -> {fc_after}")
    elif fc_after > fc_before:
        regressed.append(f"Findings increased: {fc_before} -> {fc_after}")
    else:
        unchanged.append(f"Findings unchanged: {fc_after}")

    # Doctor checks
    doc_before = before.get("doctor_results", {})
    doc_after = after.get("doctor_results", {})
    fail_before = doc_before.get("fail", 0)
    fail_after = doc_after.get("fail", 0)
    if fail_after < fail_before:
        improved.append(f"Doctor failures reduced: {fail_before} -> {fail_after}")
    elif fail_after > fail_before:
        regressed.append(f"Doctor failures increased: {fail_before} -> {fail_after}")

    # Injection recall
    inj_before = before.get("injection_status", {})
    inj_after = after.get("injection_status", {})
    r_before = inj_before.get("recall")
    r_after = inj_after.get("recall")
    if r_before is not None and r_after is not None:
        if r_after > r_before:
            improved.append(f"Injection recall improved: {r_before:.2f} -> {r_after:.2f}")
        elif r_after < r_before:
            regressed.append(f"Injection recall regressed: {r_before:.2f} -> {r_after:.2f}")

    # Config completeness
    cfg_before = before.get("config_completeness", {}).get("ratio", 0)
    cfg_after = after.get("config_completeness", {}).get("ratio", 0)
    if cfg_after > cfg_before:
        improved.append(f"Config completeness improved: {cfg_before:.0%} -> {cfg_after:.0%}")
    elif cfg_after < cfg_before:
        regressed.append(f"Config completeness regressed: {cfg_before:.0%} -> {cfg_after:.0%}")

    return {
        "improved": improved,
        "regressed": regressed,
        "unchanged": unchanged,
        "grade_change": grade_change,
        "summary": (
            f"{len(improved)} improved, {len(regressed)} regressed, "
            f"{len(unchanged)} unchanged"
        ),
    }


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def render_posture_text(snapshot: Dict[str, Any]) -> str:
    """Render posture snapshot as human-readable text."""
    lines: List[str] = []
    lines.append("=== NuFi Security Posture Snapshot ===")
    lines.append(f"Timestamp : {snapshot.get('timestamp', 'N/A')}")
    lines.append(f"Target    : {snapshot.get('target', 'N/A')}")
    lines.append(f"Grade     : {snapshot.get('grade', '?')}")
    lines.append(f"Files     : {snapshot.get('file_count', 0)}")
    lines.append(f"Findings  : {snapshot.get('finding_count', 0)}")
    lines.append("")

    sev = snapshot.get("severity_counts", {})
    if sev:
        lines.append("Severity Distribution:")
        for k, v in sorted(sev.items()):
            lines.append(f"  {k}: {v}")
        lines.append("")

    entity = snapshot.get("entity_distribution", {})
    if entity:
        lines.append("Entity Types:")
        for k, v in list(entity.items())[:10]:
            lines.append(f"  {k}: {v}")
        lines.append("")

    inj = snapshot.get("injection_status", {})
    if inj.get("available"):
        lines.append("Injection Benchmark:")
        lines.append(f"  Recall    : {inj.get('recall', 'N/A')}")
        lines.append(f"  Precision : {inj.get('precision', 'N/A')}")
        lines.append(f"  Pass      : {inj.get('pass', 'N/A')}")
        lines.append("")

    doc = snapshot.get("doctor_results", {})
    if doc.get("available"):
        lines.append("Doctor Checks:")
        lines.append(f"  PASS: {doc.get('pass', 0)}  WARN: {doc.get('warn', 0)}  FAIL: {doc.get('fail', 0)}")
        lines.append("")

    cfg = snapshot.get("config_completeness", {})
    lines.append(f"Config Completeness: {cfg.get('present', 0)}/{cfg.get('total', 0)} ({cfg.get('ratio', 0):.0%})")

    return "\n".join(lines)


def render_comparison_text(comparison: Dict[str, Any]) -> str:
    """Render comparison as human-readable text."""
    lines: List[str] = []
    lines.append("=== Posture Comparison ===")
    lines.append(f"Summary: {comparison.get('summary', '')}")
    lines.append("")

    if comparison.get("improved"):
        lines.append("Improved:")
        for item in comparison["improved"]:
            lines.append(f"  + {item}")
        lines.append("")

    if comparison.get("regressed"):
        lines.append("Regressed:")
        for item in comparison["regressed"]:
            lines.append(f"  - {item}")
        lines.append("")

    if comparison.get("unchanged"):
        lines.append("Unchanged:")
        for item in comparison["unchanged"]:
            lines.append(f"  = {item}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI handler
# ---------------------------------------------------------------------------

def cmd_report_posture(args) -> int:
    """Handle ``nufi-egress report posture`` subcommand."""
    target = getattr(args, "directory", ".") or "."
    history_path = Path(getattr(args, "history", None) or POSTURE_HISTORY_FILE)

    if getattr(args, "compare", False):
        # Compare mode: compare current posture with last saved
        last = get_last_posture(history_path)
        if last is None:
            print("No saved posture history found. Run with --save first.",
                  file=sys.stderr)
            return 1
        current = capture_posture(target)
        comparison = compare_posture(last, current)
        if getattr(args, "json", False):
            print(json.dumps(comparison, ensure_ascii=False, indent=2))
        else:
            print(render_comparison_text(comparison))
        return 0

    # Capture posture
    snapshot = capture_posture(target)

    if getattr(args, "save", False):
        path = save_posture(snapshot, history_path)
        print(f"[posture] Saved to {path}", file=sys.stderr)

    if getattr(args, "json", False):
        print(json.dumps(snapshot, ensure_ascii=False, indent=2))
    else:
        print(render_posture_text(snapshot))

    return 0
