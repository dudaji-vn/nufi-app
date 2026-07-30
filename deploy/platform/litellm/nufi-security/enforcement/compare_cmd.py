"""``nufi-egress compare`` -- compare two scan results (patch133).

Compares two SARIF or JSON scan results and reports:
  - New findings (introduced in *after* but not in *before*)
  - Resolved findings (present in *before* but not in *after*)
  - Unchanged findings (present in both)

Useful for PR reviews: "did this change introduce new PII?"

Usage::

    nufi-egress compare before.sarif after.sarif
    nufi-egress compare before.json after.json --json
    nufi-egress compare before.sarif after.sarif --fail-on-new
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


# ---------------------------------------------------------------------------
# Normalised finding representation
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _NormFinding:
    """Hashable normalised finding for set operations."""
    file: str
    line: int
    finding_type: str
    text: str


def _key(f: _NormFinding) -> Tuple[str, int, str, str]:
    return (f.file, f.line, f.finding_type, f.text)


# ---------------------------------------------------------------------------
# Loaders (SARIF 2.1 + NuFi JSON)
# ---------------------------------------------------------------------------

def _load_findings(path: Path) -> List[_NormFinding]:
    """Load findings from a SARIF or NuFi JSON file.

    Auto-detects format:
      - SARIF: has ``"version": "2.1.0"`` and ``"runs"`` key
      - NuFi JSON: has ``"findings"`` list with ``file``/``line``/``finding_type``
    """
    data = json.loads(path.read_text(encoding="utf-8"))

    # --- SARIF 2.1 ---
    if isinstance(data, dict) and data.get("version") == "2.1.0" and "runs" in data:
        return _parse_sarif(data)

    # --- NuFi scan JSON ---
    if isinstance(data, dict) and "findings" in data:
        return _parse_nufi_json(data)

    raise ValueError(
        f"Unrecognised scan result format in {path}. "
        "Expected SARIF 2.1.0 or NuFi JSON (with 'findings' key)."
    )


def _parse_sarif(data: Dict[str, Any]) -> List[_NormFinding]:
    findings: List[_NormFinding] = []
    for run in data.get("runs", []):
        for r in run.get("results", []):
            rule_id = r.get("ruleId", "UNKNOWN")
            text = r.get("message", {}).get("text", "")
            for loc in r.get("locations", []):
                phys = loc.get("physicalLocation", {})
                uri = phys.get("artifactLocation", {}).get("uri", "")
                line = phys.get("region", {}).get("startLine", 0)
                # Reconstruct finding_type from rule properties if available
                # SARIF ruleId is the entity (e.g. KR_RRN), we need the category prefix
                category = "PII"
                for rule_def in run.get("tool", {}).get("driver", {}).get("rules", []):
                    if rule_def.get("id") == rule_id:
                        cat = rule_def.get("properties", {}).get("category", "pii")
                        if cat == "injection":
                            category = "INJECTION"
                        break
                finding_type = f"{category}:{rule_id}"
                findings.append(_NormFinding(file=uri, line=line,
                                             finding_type=finding_type, text=text))
    return findings


def _parse_nufi_json(data: Dict[str, Any]) -> List[_NormFinding]:
    findings: List[_NormFinding] = []
    for f in data.get("findings", []):
        findings.append(_NormFinding(
            file=f.get("file", ""),
            line=f.get("line", 0),
            finding_type=f.get("finding_type", "UNKNOWN"),
            text=f.get("text", ""),
        ))
    return findings


# ---------------------------------------------------------------------------
# Core comparison
# ---------------------------------------------------------------------------

@dataclass
class CompareResult:
    """Result of comparing two scan outputs."""
    new_findings: List[_NormFinding] = field(default_factory=list)
    resolved_findings: List[_NormFinding] = field(default_factory=list)
    unchanged_findings: List[_NormFinding] = field(default_factory=list)

    @property
    def summary(self) -> str:
        return (f"{len(self.new_findings)} new, "
                f"{len(self.resolved_findings)} resolved, "
                f"{len(self.unchanged_findings)} unchanged")

    def to_dict(self) -> Dict[str, Any]:
        def _ser(lst: List[_NormFinding]) -> List[Dict[str, Any]]:
            return [{"file": f.file, "line": f.line,
                     "finding_type": f.finding_type, "text": f.text}
                    for f in lst]
        return {
            "new": _ser(self.new_findings),
            "resolved": _ser(self.resolved_findings),
            "unchanged": _ser(self.unchanged_findings),
            "summary": {
                "new_count": len(self.new_findings),
                "resolved_count": len(self.resolved_findings),
                "unchanged_count": len(self.unchanged_findings),
            },
        }


def compare_scans(before_path: str | Path, after_path: str | Path) -> CompareResult:
    """Compare two scan results (SARIF or NuFi JSON).

    Args:
        before_path: Path to the *before* scan result file.
        after_path: Path to the *after* scan result file.

    Returns:
        CompareResult with new / resolved / unchanged findings.
    """
    before_path = Path(before_path)
    after_path = Path(after_path)

    before_set = set(_load_findings(before_path))
    after_set = set(_load_findings(after_path))

    new = sorted(after_set - before_set, key=_key)
    resolved = sorted(before_set - after_set, key=_key)
    unchanged = sorted(before_set & after_set, key=_key)

    return CompareResult(
        new_findings=new,
        resolved_findings=resolved,
        unchanged_findings=unchanged,
    )


# ---------------------------------------------------------------------------
# CLI handler
# ---------------------------------------------------------------------------

def cmd_compare(args) -> int:
    """``nufi-egress compare`` CLI handler."""
    before = getattr(args, "before", None)
    after = getattr(args, "after", None)
    use_json = getattr(args, "json", False)
    fail_on_new = getattr(args, "fail_on_new", False)

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

    if use_json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(f"Compare: {result.summary}")
        if result.new_findings:
            print()
            print("  [NEW] Introduced findings:")
            for f in result.new_findings:
                print(f"    {f.file}:{f.line} [{f.finding_type}] {f.text}")
        if result.resolved_findings:
            print()
            print("  [RESOLVED] Fixed findings:")
            for f in result.resolved_findings:
                print(f"    {f.file}:{f.line} [{f.finding_type}] {f.text}")
        if result.unchanged_findings:
            print()
            print(f"  [UNCHANGED] {len(result.unchanged_findings)} findings remain.")

    if fail_on_new and result.new_findings:
        return 1
    return 0
