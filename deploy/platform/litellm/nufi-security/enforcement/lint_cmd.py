"""``nufi-egress lint`` -- security anti-pattern checker (patch130).

Scans Python/YAML/JSON files for common security anti-patterns:
  - Hardcoded API keys/tokens
  - Debug mode in production configs
  - Insecure URLs (http:// instead of https://)
  - Disabled SSL verification
  - Passwords in code
  - eval()/exec() usage

Respects .nufiignore exclusion patterns.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from enforcement.scan_cmd import load_nufiignore, _is_excluded, _is_binary

# ---------------------------------------------------------------------------
# Anti-pattern definitions
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AntiPattern:
    """A security anti-pattern rule."""
    id: str
    name: str
    severity: str          # high / medium / low
    pattern: "re.Pattern[str]"
    description: str
    fix: Optional[str] = None   # regex replacement string if auto-fixable


_PATTERNS: List[AntiPattern] = [
    # --- HIGH severity -------------------------------------------------------
    AntiPattern(
        id="SEC001",
        name="hardcoded-api-key",
        severity="high",
        pattern=re.compile(
            r"""(?:api[_-]?key|apikey|api[_-]?secret|secret[_-]?key)\s*[:=]\s*["'][^"']{4,}["']""",
            re.IGNORECASE,
        ),
        description="Hardcoded API key or secret detected",
    ),
    AntiPattern(
        id="SEC002",
        name="hardcoded-token",
        severity="high",
        pattern=re.compile(
            r"""(?:token|auth[_-]?token|access[_-]?token|bearer)\s*[:=]\s*["'][^"']{4,}["']""",
            re.IGNORECASE,
        ),
        description="Hardcoded token detected",
    ),
    AntiPattern(
        id="SEC003",
        name="hardcoded-password",
        severity="high",
        pattern=re.compile(
            r"""(?:password|passwd|pwd)\s*[:=]\s*["'][^"']{1,}["']""",
            re.IGNORECASE,
        ),
        description="Hardcoded password detected",
    ),
    # --- MEDIUM severity -----------------------------------------------------
    AntiPattern(
        id="SEC004",
        name="debug-mode",
        severity="medium",
        pattern=re.compile(
            r"""(?:DEBUG|debug)\s*[:=]\s*(?:True|true|1|yes|on)\b""",
        ),
        description="Debug mode enabled (potential production risk)",
    ),
    AntiPattern(
        id="SEC005",
        name="ssl-verification-disabled",
        severity="medium",
        pattern=re.compile(
            r"""(?:verify\s*=\s*False|ssl\s*:\s*false|VERIFY_SSL\s*[:=]\s*(?:False|false|0))""",
            re.IGNORECASE,
        ),
        description="SSL verification disabled",
    ),
    AntiPattern(
        id="SEC006",
        name="insecure-url",
        severity="medium",
        pattern=re.compile(
            r"""(?:https?://)\S+""",  # placeholder, real check below
        ),
        description="Insecure HTTP URL (should use HTTPS)",
        fix="s|http://|https://|",
    ),
    # --- LOW severity --------------------------------------------------------
    AntiPattern(
        id="SEC007",
        name="eval-exec-usage",
        severity="low",
        pattern=re.compile(
            r"""\beval\s*\(|\bexec\s*\(""",
        ),
        description="Use of eval()/exec() -- potential code injection risk",
    ),
]


# Override the insecure-url pattern with a smarter check (detect http://
# but not https://).  The dataclass is frozen so we rebuild the list entry.
_HTTP_RE = re.compile(r"""http://\S+""")
_PATTERNS[5] = AntiPattern(
    id="SEC006",
    name="insecure-url",
    severity="medium",
    pattern=_HTTP_RE,
    description="Insecure HTTP URL (should use HTTPS)",
    fix="s|http://|https://|",
)


# ---------------------------------------------------------------------------
# Finding dataclass
# ---------------------------------------------------------------------------

@dataclass
class LintFinding:
    file: str
    line: int
    column: int
    rule_id: str
    rule_name: str
    severity: str
    message: str
    snippet: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file": self.file,
            "line": self.line,
            "column": self.column,
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "severity": self.severity,
            "message": self.message,
            "snippet": self.snippet,
        }


@dataclass
class LintResult:
    findings: List[LintFinding] = field(default_factory=list)
    files_scanned: int = 0
    files_fixed: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "findings": [f.to_dict() for f in self.findings],
            "files_scanned": self.files_scanned,
            "files_fixed": self.files_fixed,
            "total_findings": len(self.findings),
            "by_severity": self._by_severity(),
        }

    def _by_severity(self) -> Dict[str, int]:
        counts: Dict[str, int] = {"high": 0, "medium": 0, "low": 0}
        for f in self.findings:
            counts[f.severity] = counts.get(f.severity, 0) + 1
        return counts


# ---------------------------------------------------------------------------
# File extensions we lint
# ---------------------------------------------------------------------------

_LINT_EXTENSIONS = {".py", ".yaml", ".yml", ".json"}


def _should_lint(path: Path) -> bool:
    return path.suffix.lower() in _LINT_EXTENSIONS


# ---------------------------------------------------------------------------
# Core lint logic
# ---------------------------------------------------------------------------

def lint_file(path: Path) -> List[LintFinding]:
    """Lint a single file and return findings."""
    if _is_binary(path):
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    findings: List[LintFinding] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for ap in _PATTERNS:
            m = ap.pattern.search(line)
            if m:
                findings.append(LintFinding(
                    file=str(path),
                    line=lineno,
                    column=m.start() + 1,
                    rule_id=ap.id,
                    rule_name=ap.name,
                    severity=ap.severity,
                    message=ap.description,
                    snippet=line.strip(),
                ))
    return findings


@dataclass
class FixPreview:
    """A single fixable issue with before/after preview."""
    file: str
    line: int
    rule_id: str
    rule_name: str
    before: str
    after: str


def fix_file(path: Path) -> bool:
    """Apply auto-fixes to a file. Returns True if the file was modified."""
    if _is_binary(path):
        return False
    try:
        original = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False

    fixed = original.replace("http://", "https://")

    if fixed != original:
        path.write_text(fixed, encoding="utf-8")
        return True
    return False


def fix_report_file(path: Path) -> List[FixPreview]:
    """Generate fix previews for a file without modifying it (dry-run)."""
    if _is_binary(path):
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    previews: List[FixPreview] = []
    fixable = [ap for ap in _PATTERNS if ap.fix is not None]

    for lineno, line in enumerate(text.splitlines(), start=1):
        for ap in fixable:
            m = ap.pattern.search(line)
            if m:
                # Apply the sed-like fix spec to the line
                from_str, to_str = _parse_fix_spec(ap.fix)
                after_line = line.replace(from_str, to_str, 1)
                if after_line != line:
                    previews.append(FixPreview(
                        file=str(path),
                        line=lineno,
                        rule_id=ap.id,
                        rule_name=ap.name,
                        before=line.strip(),
                        after=after_line.strip(),
                    ))
    return previews


def _parse_fix_spec(fix_spec: str) -> tuple:
    """Parse a sed-like s|from|to| spec and return (from_str, to_str)."""
    # Format: s|pattern|replacement|
    parts = fix_spec.split("|")
    if len(parts) >= 3:
        return parts[1], parts[2]
    return "", ""


# ---------------------------------------------------------------------------
# Directory lint
# ---------------------------------------------------------------------------

def _collect_files(
    root: Path,
    exclude_patterns: List[str],
) -> List[Path]:
    """Collect lintable files under *root*, respecting exclusions."""
    if root.is_file():
        if _should_lint(root):
            return [root]
        return []

    files: List[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dp = Path(dirpath)
        # Prune excluded directories
        dirnames[:] = [
            d for d in dirnames
            if not _is_excluded(dp / d, root, exclude_patterns)
        ]
        for fn in sorted(filenames):
            fp = dp / fn
            if not _should_lint(fp):
                continue
            if _is_excluded(fp, root, exclude_patterns):
                continue
            files.append(fp)
    return files


import os  # noqa: E402  (already imported but keep explicit for _collect_files)


def lint_path(
    target: Path,
    *,
    fix: bool = False,
    exclude: Optional[List[str]] = None,
) -> LintResult:
    """Lint files under *target* and optionally apply auto-fixes."""
    root = target if target.is_dir() else target.parent
    nufiignore = load_nufiignore(root)
    all_exclude = nufiignore + (exclude or [])
    files = _collect_files(target, all_exclude)

    result = LintResult()
    result.files_scanned = len(files)

    for fp in files:
        findings = lint_file(fp)
        result.findings.extend(findings)

        if fix:
            if fix_file(fp):
                result.files_fixed += 1

    return result


def fix_report_path(
    target: Path,
    *,
    exclude: Optional[List[str]] = None,
) -> List[FixPreview]:
    """Generate fix previews for all fixable issues under *target* (dry-run)."""
    root = target if target.is_dir() else target.parent
    nufiignore = load_nufiignore(root)
    all_exclude = nufiignore + (exclude or [])
    files = _collect_files(target, all_exclude)

    previews: List[FixPreview] = []
    for fp in files:
        previews.extend(fix_report_file(fp))
    return previews


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def cmd_lint(args) -> int:
    """``nufi-egress lint`` CLI handler."""
    target = Path(args.target)
    if not target.exists():
        import sys
        print(f"오류: 경로를 찾을 수 없습니다: {args.target}", file=sys.stderr)
        return 1

    exclude = args.exclude.split(",") if getattr(args, "exclude", None) else None

    # --fix-report mode: show what would be fixed without modifying files
    if getattr(args, "fix_report", False):
        previews = fix_report_path(target, exclude=exclude)
        if getattr(args, "json", False):
            data = [
                {"file": p.file, "line": p.line, "rule_id": p.rule_id,
                 "rule_name": p.rule_name, "before": p.before, "after": p.after}
                for p in previews
            ]
            print(json.dumps(data, ensure_ascii=False, indent=2))
        else:
            if not previews:
                print("fix-report: no fixable issues found")
            else:
                for p in previews:
                    print(f"{p.file}:{p.line} [{p.rule_id}] {p.rule_name}")
                    print(f"  - {p.before}")
                    print(f"  + {p.after}")
                    print()
                print(f"fix-report: {len(previews)} fixable issue(s) found")
        return 0

    result = lint_path(target, fix=getattr(args, "fix", False), exclude=exclude)

    if getattr(args, "json", False):
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        if not result.findings:
            print(f"lint: {result.files_scanned} files scanned -- no findings")
        else:
            for f in result.findings:
                sev = f.severity.upper()
                print(f"{f.file}:{f.line}:{f.column}: [{sev}] {f.rule_id} "
                      f"{f.message}")
                print(f"  | {f.snippet}")
            print()
            by = result.to_dict()["by_severity"]
            print(f"lint: {result.files_scanned} files scanned, "
                  f"{len(result.findings)} findings "
                  f"(high={by['high']}, medium={by['medium']}, low={by['low']})")
        if result.files_fixed:
            print(f"  auto-fixed {result.files_fixed} file(s)")

    return 1 if result.findings else 0
