"""``nufi-egress scan`` — 파일/디렉터리 PII + 인젝션 스캐너 (patch86).

CI/pre-commit 훅에서 사용 가능한 파일·디렉터리 재귀 스캔 명령.
SDK 에서도 ``from nufi import scan_dir`` 로 사용 가능.

.nufiignore 파일 또는 --exclude 플래그로 스캔 대상에서 제외할 패턴 지정 가능.
--format text|json|sarif|csv 옵션으로 출력 포맷 선택 (v0.7.0).
--redact 모드로 PII 를 자동 치환하여 파일을 재작성 (patch88).
--parallel N 으로 멀티스레드 스캔 지원 (patch97).
--cache 로 파일 해시 기반 결과 캐싱 (patch101).
--profile NAME 으로 사전 정의 스캔 프로파일 적용 (patch110).
--verbose 로 발견 항목별 상세 정보 출력 (patch137).
--git-staged 로 git staged 파일만 스캔 (pre-commit 통합, patch171).
--ignore-file PATH 로 false positive 억제 (patch178).
--baseline PATH 로 이전 스캔 결과와 비교하여 신규 발견만 출력 (patch181).
--count-only 로 발견 건수만 빠르게 출력 (patch182).
--watch 모드로 디렉터리 실시간 파일 모니터링 + PII 탐지 (v0.7.3).
--recursive 로 디렉터리 재귀 스캔 + 집계 리포트 출력 (v0.7.4).
--profile NAME 으로 스캔 프로파일 프리셋 적용 (strict/standard/minimal/financial, v0.7.7).
--summary 로 집계 대시보드 출력 (타입별·심각도별 ASCII 바 차트, v0.7.7).
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


import yaml

from egress_audit.pipeline import DetectionPipeline, Finding
from egress_audit.detectors.prompt_injection import PromptInjectionDetector


# ---------------------------------------------------------------------------
# .nufiignore support
# ---------------------------------------------------------------------------

def load_nufiignore(root: Path) -> List[str]:
    """Load exclusion patterns from .nufiignore in the given directory.

    Returns an empty list if the file does not exist.
    """
    ignore_file = root / ".nufiignore"
    if not ignore_file.is_file():
        return []
    patterns: List[str] = []
    for line in ignore_file.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        patterns.append(stripped)
    return patterns


def _is_excluded(path: Path, root: Path, exclude_patterns: List[str]) -> bool:
    """Check if a path should be excluded based on glob patterns.

    Patterns are matched against the path relative to the scan root.
    """
    if not exclude_patterns:
        return False
    try:
        rel = path.relative_to(root)
    except ValueError:
        rel = path
    rel_str = str(rel)
    for pat in exclude_patterns:
        if fnmatch.fnmatch(rel_str, pat):
            return True
        # Also match against just the filename for simple patterns like *.pyc
        if fnmatch.fnmatch(path.name, pat):
            return True
    return False


# ---------------------------------------------------------------------------
# False positive suppression (.nufi_ignore_findings.yaml) — patch178
# ---------------------------------------------------------------------------

@dataclass
class Suppression:
    """A single suppression rule from .nufi_ignore_findings.yaml."""
    file: Optional[str] = None
    pattern: Optional[str] = None
    entity_type: Optional[str] = None
    reason: str = ""


def load_suppressions(path: str | Path) -> List[Suppression]:
    """Load suppression rules from a YAML file.

    Expected format::

        suppressions:
          - file: "tests/test_data.py"
            entity_type: "KR_PHONE"
            reason: "Test fixture"
          - pattern: "test_*"
            entity_type: "KR_PERSON"
            reason: "Sample names"

    Returns an empty list if the file does not exist or is empty.
    """
    p = Path(path)
    if not p.is_file():
        return []
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
    except (yaml.YAMLError, OSError):
        return []
    if not data or not isinstance(data, dict):
        return []
    raw_list = data.get("suppressions")
    if not raw_list or not isinstance(raw_list, list):
        return []
    result: List[Suppression] = []
    for item in raw_list:
        if not isinstance(item, dict):
            continue
        result.append(Suppression(
            file=item.get("file"),
            pattern=item.get("pattern"),
            entity_type=item.get("entity_type"),
            reason=item.get("reason", ""),
        ))
    return result


def _is_suppressed(finding: "ScanFinding", suppressions: List[Suppression], scan_root: Path) -> bool:
    """Check if a finding matches any suppression rule.

    Matching logic:
    - If suppression has ``file``, the finding's file path (relative to scan_root)
      must match exactly.
    - If suppression has ``pattern``, the finding's file path (relative to scan_root)
      or filename must match the glob pattern.
    - If suppression has ``entity_type``, the finding's entity_type (the part after
      'PII:' or 'INJECTION:') must match.
    - All specified fields must match (AND logic).
    """
    finding_path = Path(finding.file)
    try:
        rel_path = str(finding_path.relative_to(scan_root))
    except ValueError:
        rel_path = str(finding_path)
    filename = finding_path.name

    # Extract entity type from finding_type (e.g. "PII:KR_PHONE" -> "KR_PHONE")
    finding_entity = finding.finding_type.split(":", 1)[1] if ":" in finding.finding_type else finding.finding_type

    for s in suppressions:
        file_match = True
        pattern_match = True
        entity_match = True

        if s.file is not None:
            file_match = (rel_path == s.file or str(finding_path) == s.file)

        if s.pattern is not None:
            pattern_match = (
                fnmatch.fnmatch(rel_path, s.pattern) or
                fnmatch.fnmatch(filename, s.pattern)
            )

        if s.entity_type is not None:
            entity_match = (finding_entity == s.entity_type)

        # All specified conditions must match
        if file_match and pattern_match and entity_match:
            return True

    return False


def apply_suppressions(
    result: "ScanResult",
    suppressions: List[Suppression],
    scan_root: Path,
) -> int:
    """Remove suppressed findings from a ScanResult in-place.

    Returns the number of suppressed findings.
    """
    if not suppressions:
        return 0
    original_count = len(result.findings)
    result.findings = [
        f for f in result.findings
        if not _is_suppressed(f, suppressions, scan_root)
    ]
    suppressed = original_count - len(result.findings)
    # Recompute files_with_findings
    if suppressed:
        files_with = len(set(f.file for f in result.findings))
        result.files_with_findings = files_with
    return suppressed


# ---------------------------------------------------------------------------
# Binary detection helper
# ---------------------------------------------------------------------------

def _is_binary(path: Path) -> bool:
    """Check first 512 bytes for null bytes → likely binary."""
    try:
        with open(path, "rb") as f:
            chunk = f.read(512)
        return b"\x00" in chunk
    except OSError:
        return True


# ---------------------------------------------------------------------------
# Glob matching helper
# ---------------------------------------------------------------------------

def _matches_patterns(path: Path, patterns: Optional[List[str]]) -> bool:
    """Check if file matches any of the given glob patterns (by name)."""
    if not patterns:
        return True  # no filter → include all
    for pat in patterns:
        if path.match(pat):
            return True
    return False


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ScanFinding:
    """Single finding within a file."""
    file: str
    line: int
    finding_type: str  # e.g. "PII:KR_RRN" or "INJECTION:ignore_previous"
    text: str
    column: int = 1
    score: float = 1.0
    detection_method: str = "regex"
    context_before: str = ""
    context_after: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file": self.file,
            "line": self.line,
            "finding_type": self.finding_type,
            "text": self.text,
        }


@dataclass
class ScanResult:
    """Aggregated scan result."""
    files_scanned: int = 0
    files_with_findings: int = 0
    findings: List[ScanFinding] = field(default_factory=list)
    errors: List[Dict[str, str]] = field(default_factory=list)

    @property
    def has_pii(self) -> bool:
        return any(f.finding_type.startswith("PII:") for f in self.findings)

    @property
    def has_injection(self) -> bool:
        return any(f.finding_type.startswith("INJECTION:") for f in self.findings)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "files_scanned": self.files_scanned,
            "files_with_findings": self.files_with_findings,
            "total_findings": len(self.findings),
            "has_pii": self.has_pii,
            "has_injection": self.has_injection,
            "findings": [f.to_dict() for f in self.findings],
            "errors": self.errors,
        }


# ---------------------------------------------------------------------------
# File hash caching (patch101)
# ---------------------------------------------------------------------------

_CACHE_FILENAME = ".nufi_cache.json"


def _file_sha256(path: Path) -> str:
    """Compute SHA-256 hex digest of a file's contents."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _load_cache(cache_path: Path) -> Dict[str, Any]:
    """Load the scan cache from disk."""
    if not cache_path.is_file():
        return {}
    try:
        return json.loads(cache_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_cache(cache_path: Path, cache: Dict[str, Any]) -> None:
    """Persist the scan cache to disk."""
    cache_path.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def clear_scan_cache(target: str | Path) -> bool:
    """Delete the scan cache file for the given target root.

    Returns True if a cache file was removed, False otherwise.
    """
    target = Path(target)
    scan_root = target if target.is_dir() else target.parent
    cache_path = scan_root / _CACHE_FILENAME
    if cache_path.is_file():
        cache_path.unlink()
        return True
    return False


# ---------------------------------------------------------------------------
# Core scan logic
# ---------------------------------------------------------------------------

def _scan_file_isolated(
    path: Path,
    check_injection: bool,
    patterns: Optional[List[str]],
) -> ScanResult:
    """Scan a single file in isolation (thread-safe).

    Creates its own DetectionPipeline and optional PromptInjectionDetector
    so that each thread has independent state.
    """
    result = ScanResult()
    pipeline = DetectionPipeline()
    injection_detector = PromptInjectionDetector() if check_injection else None
    _scan_file(path, pipeline, injection_detector, result, patterns)
    return result


def _merge_results(results: List[ScanResult]) -> ScanResult:
    """Merge multiple ScanResult instances into one."""
    merged = ScanResult()
    for r in results:
        merged.files_scanned += r.files_scanned
        merged.files_with_findings += r.files_with_findings
        merged.findings.extend(r.findings)
        merged.errors.extend(r.errors)
    return merged


def scan_path(
    target: str | Path,
    *,
    patterns: Optional[List[str]] = None,
    check_injection: bool = False,
    exclude: Optional[List[str]] = None,
    parallel: int = 1,
    cache: bool = False,
) -> ScanResult:
    """Scan a file or directory for PII (and optionally injection patterns).

    Args:
        target: Path to a file or directory.
        patterns: Glob patterns to filter files (e.g. ["*.py", "*.md"]).
        check_injection: Whether to also detect prompt injection patterns.
        exclude: Glob patterns to exclude files/directories from scanning.
            If None, will attempt to load .nufiignore from the target dir.
        parallel: Number of threads to use for scanning (default 1 = sequential).
        cache: If True, cache results by file SHA-256 hash and skip unchanged files.

    Returns:
        ScanResult with all findings.
    """
    target = Path(target)
    result = ScanResult()

    # Determine scan root for .nufiignore and relative path computation
    scan_root = target if target.is_dir() else target.parent

    # Build exclusion patterns: explicit exclude > .nufiignore > empty
    if exclude is None:
        exclude_patterns = load_nufiignore(scan_root)
    else:
        exclude_patterns = list(exclude)

    # Collect files to scan
    files_to_scan: List[Path] = []
    if target.is_file():
        if not _is_excluded(target, scan_root, exclude_patterns):
            files_to_scan.append(target)
    elif target.is_dir():
        for root, _dirs, files in os.walk(target):
            for fname in sorted(files):
                fpath = Path(root) / fname
                if _is_excluded(fpath, scan_root, exclude_patterns):
                    continue
                files_to_scan.append(fpath)
    else:
        result.errors.append({"path": str(target), "error": "Path does not exist"})
        return result

    # Load cache if enabled
    cache_data: Dict[str, Any] = {}
    cache_path = scan_root / _CACHE_FILENAME
    if cache:
        cache_data = _load_cache(cache_path)

    # Separate files into cached (unchanged) and to-scan
    files_needing_scan: List[Path] = []
    if cache:
        for fpath in files_to_scan:
            # Skip cache file itself
            if fpath.name == _CACHE_FILENAME:
                continue
            file_key = str(fpath)
            file_hash = _file_sha256(fpath)
            cached_entry = cache_data.get(file_key)
            if cached_entry and cached_entry.get("hash") == file_hash:
                # Use cached findings
                result.files_scanned += 1
                cached_findings = cached_entry.get("findings", [])
                if cached_findings:
                    result.files_with_findings += 1
                for fd in cached_findings:
                    result.findings.append(ScanFinding(
                        file=fd["file"],
                        line=fd["line"],
                        finding_type=fd["finding_type"],
                        text=fd["text"],
                    ))
            else:
                files_needing_scan.append(fpath)
    else:
        files_needing_scan = [f for f in files_to_scan if f.name != _CACHE_FILENAME]
        # If not caching, include cache file in normal scan list
        files_needing_scan = files_to_scan

    if parallel > 1 and len(files_needing_scan) > 1:
        # Parallel scan: each thread creates its own pipeline instance
        with ThreadPoolExecutor(max_workers=parallel) as executor:
            futures = [
                executor.submit(_scan_file_isolated, fpath, check_injection, patterns)
                for fpath in files_needing_scan
            ]
            sub_results = [f.result() for f in futures]
        scan_result = _merge_results(sub_results)
        # Merge with cached results
        result.files_scanned += scan_result.files_scanned
        result.files_with_findings += scan_result.files_with_findings
        result.findings.extend(scan_result.findings)
        result.errors.extend(scan_result.errors)
    else:
        # Sequential scan (original behaviour)
        pipeline = DetectionPipeline()
        injection_detector = PromptInjectionDetector() if check_injection else None
        for fpath in files_needing_scan:
            _scan_file(fpath, pipeline, injection_detector, result, patterns)

    # Update cache if enabled
    if cache:
        for fpath in files_needing_scan:
            file_key = str(fpath)
            file_hash = _file_sha256(fpath)
            # Collect findings for this file from result
            file_findings = [
                f.to_dict() for f in result.findings if f.file == file_key
            ]
            cache_data[file_key] = {
                "hash": file_hash,
                "findings": file_findings,
                "ts": datetime.now(timezone.utc).isoformat(),
            }
        _save_cache(cache_path, cache_data)

    return result


def _extract_entity_type(finding_type: str) -> str:
    """Extract the entity type from a finding_type string.

    E.g. 'PII:KR_RRN' -> 'KR_RRN', 'INJECTION:ignore_previous' -> 'IGNORE_PREVIOUS'.
    """
    part = finding_type.split(":", 1)[1] if ":" in finding_type else finding_type
    return part.upper()


def _classify_detection_method(source: str) -> str:
    """Map a Finding.source value to a human-friendly detection method."""
    if not source:
        return "regex"
    s = source.lower()
    if "ner" in s or "gazetteer" in s:
        return "ner"
    return "regex"


def _scan_file(
    path: Path,
    pipeline: DetectionPipeline,
    injection_detector: Optional[PromptInjectionDetector],
    result: ScanResult,
    patterns: Optional[List[str]],
) -> None:
    """Scan a single file and append findings to result."""
    # Pattern filter
    if not _matches_patterns(path, patterns):
        return

    # Binary check
    if _is_binary(path):
        return

    result.files_scanned += 1

    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        result.errors.append({"path": str(path), "error": str(e)})
        return

    file_str = str(path)
    file_has_findings = False
    lines = text.splitlines()

    for line_no, line in enumerate(lines, start=1):
        if not line.strip():
            continue

        # PII detection
        pii_findings = pipeline.analyze(line)
        for f in pii_findings:
            snippet = f.text if len(f.text) <= 40 else f.text[:37] + "..."
            col = f.start + 1  # 1-based column
            ctx_before = line[max(0, f.start - 5):f.start]
            ctx_after = line[f.end:f.end + 5]
            method = _classify_detection_method(getattr(f, "source", "regex"))
            result.findings.append(ScanFinding(
                file=file_str,
                line=line_no,
                finding_type=f"PII:{f.entity_type}",
                text=snippet,
                column=col,
                score=getattr(f, "score", 1.0),
                detection_method=method,
                context_before=ctx_before,
                context_after=ctx_after,
            ))
            file_has_findings = True

        # Injection detection
        if injection_detector:
            inj_findings = injection_detector.detect(line)
            for f in inj_findings:
                snippet = f.text if len(f.text) <= 40 else f.text[:37] + "..."
                col = f.start + 1
                ctx_before = line[max(0, f.start - 5):f.start]
                ctx_after = line[f.end:f.end + 5]
                method = _classify_detection_method(getattr(f, "source", "regex"))
                result.findings.append(ScanFinding(
                    file=file_str,
                    line=line_no,
                    finding_type=f"INJECTION:{f.entity_type}",
                    text=snippet,
                    column=col,
                    score=getattr(f, "score", 1.0),
                    detection_method=method,
                    context_before=ctx_before,
                    context_after=ctx_after,
                ))
                file_has_findings = True

    if file_has_findings:
        result.files_with_findings += 1


# ---------------------------------------------------------------------------
# Redact mode (patch88)
# ---------------------------------------------------------------------------

@dataclass
class RedactInfo:
    """Single redaction applied to a file."""
    file: str
    line: int
    entity_type: str
    original_text: str


@dataclass
class RedactResult:
    """Result of a redact operation."""
    files_modified: int = 0
    total_redactions: int = 0
    redactions: List[RedactInfo] = field(default_factory=list)
    backups_created: List[str] = field(default_factory=list)


def redact_path(
    target: str | Path,
    *,
    patterns: Optional[List[str]] = None,
    exclude: Optional[List[str]] = None,
    dry_run: bool = False,
    no_backup: bool = False,
) -> RedactResult:
    """Scan files for PII and redact findings in-place.

    Only PII findings from DetectionPipeline are redacted (not injection patterns).
    Redaction is done in reverse order to preserve character positions.

    Args:
        target: Path to a file or directory.
        patterns: Glob patterns to filter files.
        exclude: Glob patterns to exclude.
        dry_run: If True, report what would be redacted without modifying files.
        no_backup: If True, skip creating .bak backup files.

    Returns:
        RedactResult with details of all redactions.
    """
    target = Path(target)
    result = RedactResult()
    pipeline = DetectionPipeline()

    scan_root = target if target.is_dir() else target.parent

    if exclude is None:
        exclude_patterns = load_nufiignore(scan_root)
    else:
        exclude_patterns = list(exclude)

    files_to_process: List[Path] = []
    if target.is_file():
        if not _is_excluded(target, scan_root, exclude_patterns):
            files_to_process.append(target)
    elif target.is_dir():
        for root, _dirs, files in os.walk(target):
            for fname in sorted(files):
                fpath = Path(root) / fname
                if _is_excluded(fpath, scan_root, exclude_patterns):
                    continue
                files_to_process.append(fpath)

    for fpath in files_to_process:
        if not _matches_patterns(fpath, patterns):
            continue
        if _is_binary(fpath):
            continue
        _redact_file(fpath, pipeline, result, dry_run=dry_run, no_backup=no_backup)

    return result


def _redact_file(
    path: Path,
    pipeline: DetectionPipeline,
    result: RedactResult,
    *,
    dry_run: bool,
    no_backup: bool,
) -> None:
    """Redact PII in a single file."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return

    lines = text.splitlines(keepends=True)
    file_str = str(path)
    file_modified = False

    for line_idx in range(len(lines)):
        line_text = lines[line_idx]
        # Strip the newline for analysis but keep track of it
        stripped = line_text.rstrip("\n").rstrip("\r")
        if not stripped.strip():
            continue

        findings = pipeline.analyze(stripped)
        # Only PII findings (ignore injection, confidential etc for redact)
        pii_findings = [f for f in findings if f.entity_type not in (
            "PROMPT_INJECTION",
        )]
        if not pii_findings:
            continue

        # Sort by start position descending for safe in-place replacement
        pii_findings.sort(key=lambda f: f.start, reverse=True)

        new_stripped = stripped
        for f in pii_findings:
            marker = f"[REDACTED:{f.entity_type}]"
            new_stripped = new_stripped[:f.start] + marker + new_stripped[f.end:]
            result.redactions.append(RedactInfo(
                file=file_str,
                line=line_idx + 1,
                entity_type=f.entity_type,
                original_text=f.text if len(f.text) <= 40 else f.text[:37] + "...",
            ))
            result.total_redactions += 1
            file_modified = True

        # Preserve original line ending
        ending = line_text[len(stripped):] if len(line_text) > len(stripped) else ""
        lines[line_idx] = new_stripped + ending

    if file_modified:
        result.files_modified += 1
        if not dry_run:
            if not no_backup:
                backup_path = str(path) + ".bak"
                shutil.copy2(str(path), backup_path)
                result.backups_created.append(backup_path)
            path.write_text("".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# SARIF 2.1.0 output (patch86)
# ---------------------------------------------------------------------------

_SARIF_SCHEMA = (
    "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/main/"
    "sarif-2.1/schema/sarif-schema-2.1.0.json"
)

# PII types considered "strong" (error level)
_STRONG_PII = {"KR_RRN", "KR_PASSPORT", "CREDIT_CARD", "SSN"}


def _nufi_version() -> str:
    """Read NuFi VERSION file."""
    ver_file = Path(__file__).resolve().parent.parent / "VERSION"
    if ver_file.is_file():
        return ver_file.read_text(encoding="utf-8").strip()
    return "unknown"


def _sarif_level(finding_type: str) -> str:
    """Map finding_type to SARIF level."""
    if finding_type.startswith("INJECTION:"):
        return "error"
    # PII: strong types → error, weak → warning
    entity = finding_type.split(":", 1)[1] if ":" in finding_type else finding_type
    if entity in _STRONG_PII:
        return "error"
    return "warning"


def _sarif_rule_id(finding_type: str) -> str:
    """Extract rule ID from finding_type (e.g. 'PII:KR_RRN' → 'KR_RRN')."""
    return finding_type.split(":", 1)[1] if ":" in finding_type else finding_type


def scan_result_to_sarif(result: "ScanResult") -> Dict[str, Any]:
    """Convert a ScanResult to SARIF 2.1.0 dictionary.

    Compatible with ``gh code-scanning upload-sarif``.
    """
    # Collect unique rules
    seen_rules: Dict[str, Dict[str, Any]] = {}
    sarif_results: List[Dict[str, Any]] = []

    for f in result.findings:
        rule_id = _sarif_rule_id(f.finding_type)
        level = _sarif_level(f.finding_type)

        if rule_id not in seen_rules:
            category = "injection" if f.finding_type.startswith("INJECTION:") else "pii"
            seen_rules[rule_id] = {
                "id": rule_id,
                "shortDescription": {"text": f"Detected {rule_id}"},
                "properties": {"category": category},
            }

        # Build location — use file URI for absolute paths
        file_path = f.file
        uri = file_path

        sarif_results.append({
            "ruleId": rule_id,
            "level": level,
            "message": {"text": f.text},
            "locations": [{
                "physicalLocation": {
                    "artifactLocation": {"uri": uri},
                    "region": {
                        "startLine": f.line,
                        "startColumn": 1,
                    },
                }
            }],
        })

    sarif: Dict[str, Any] = {
        "$schema": _SARIF_SCHEMA,
        "version": "2.1.0",
        "runs": [{
            "tool": {
                "driver": {
                    "name": "nufi-egress",
                    "version": _nufi_version(),
                    "rules": list(seen_rules.values()),
                }
            },
            "results": sarif_results,
        }],
    }
    return sarif


# ---------------------------------------------------------------------------
# Git staged files helper (patch171)
# ---------------------------------------------------------------------------

def _git_staged_files(repo: Optional[str] = None) -> List[str]:
    """Return list of git-staged file paths (``git diff --cached --name-only``).

    Returns an empty list if git is not available or no files are staged.
    """
    cmd = ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"]
    kwargs: Dict[str, Any] = {"capture_output": True, "text": True}
    if repo:
        kwargs["cwd"] = repo
    try:
        proc = subprocess.run(cmd, **kwargs)  # noqa: S603
    except FileNotFoundError:
        return []
    if proc.returncode != 0:
        return []
    return [line for line in proc.stdout.strip().splitlines() if line.strip()]


def scan_staged(
    *,
    patterns: Optional[List[str]] = None,
    check_injection: bool = False,
    exclude: Optional[List[str]] = None,
    parallel: int = 1,
    cache: bool = False,
    repo: Optional[str] = None,
) -> ScanResult:
    """Scan only git-staged files for PII/injection.

    Ideal for pre-commit hooks: only scans files in the staging area.
    Respects .nufiignore patterns.

    Args:
        patterns: Glob patterns to filter files.
        check_injection: Also check for prompt injection patterns.
        exclude: Glob patterns to exclude.
        parallel: Number of threads.
        cache: Enable file hash caching.
        repo: Git repository root (default: current directory).

    Returns:
        ScanResult with all findings.
    """
    staged = _git_staged_files(repo=repo)
    if not staged:
        return ScanResult()

    repo_root = Path(repo) if repo else Path(".")
    scan_root = repo_root

    # Build exclusion patterns
    if exclude is None:
        exclude_patterns = load_nufiignore(scan_root)
    else:
        exclude_patterns = list(exclude)

    # Filter staged files
    files_to_scan: List[Path] = []
    for rel in staged:
        fpath = repo_root / rel
        if not fpath.is_file():
            continue
        if _is_excluded(fpath, scan_root, exclude_patterns):
            continue
        files_to_scan.append(fpath)

    if not files_to_scan:
        return ScanResult()

    # Reuse scan_path logic by scanning each file
    result = ScanResult()
    if parallel > 1 and len(files_to_scan) > 1:
        with ThreadPoolExecutor(max_workers=parallel) as executor:
            futures = [
                executor.submit(_scan_file_isolated, fpath, check_injection, patterns)
                for fpath in files_to_scan
            ]
            sub_results = [f.result() for f in futures]
        result = _merge_results(sub_results)
    else:
        pipeline = DetectionPipeline()
        injection_detector = PromptInjectionDetector() if check_injection else None
        for fpath in files_to_scan:
            _scan_file(fpath, pipeline, injection_detector, result, patterns)

    return result


# ---------------------------------------------------------------------------
# Git diff changed-lines scan (v0.7.5)
# ---------------------------------------------------------------------------

def _git_diff_changed_lines(
    ref: str = "HEAD",
    repo: Optional[str] = None,
) -> Dict[str, List[int]]:
    """Parse ``git diff`` unified output to find added/modified line numbers.

    Returns a dict mapping file paths (relative to repo root) to a sorted list
    of 1-based line numbers that were added or modified.

    Args:
        ref: Git ref to diff against.  ``"HEAD"`` = staged changes only
             (``git diff --cached``).  Any other value uses ``git diff <ref>``.
        repo: Repository root directory.
    """
    if ref == "HEAD":
        cmd = ["git", "diff", "--cached", "-U0", "--diff-filter=ACMR"]
    else:
        cmd = ["git", "diff", "-U0", "--diff-filter=ACMR", ref, "HEAD"]

    kwargs: Dict[str, Any] = {"capture_output": True, "text": True}
    if repo:
        kwargs["cwd"] = repo
    try:
        proc = subprocess.run(cmd, **kwargs)  # noqa: S603
    except FileNotFoundError:
        return {}

    if proc.returncode != 0:
        return {}

    file_lines: Dict[str, List[int]] = {}
    current_file: Optional[str] = None

    for line in proc.stdout.splitlines():
        # Detect file header: +++ b/path/to/file
        if line.startswith("+++ b/"):
            current_file = line[6:]
            if current_file not in file_lines:
                file_lines[current_file] = []
        # Detect hunk header: @@ -old,count +new,count @@
        elif line.startswith("@@") and current_file is not None:
            # Parse the +new,count part
            parts = line.split("+")
            if len(parts) >= 2:
                hunk_info = parts[1].split("@@")[0].strip()
                if "," in hunk_info:
                    start_str, count_str = hunk_info.split(",", 1)
                    start = int(start_str)
                    count = int(count_str)
                else:
                    start = int(hunk_info)
                    count = 1
                if count > 0:
                    file_lines[current_file].extend(
                        range(start, start + count)
                    )

    # Sort line numbers
    for f in file_lines:
        file_lines[f] = sorted(set(file_lines[f]))

    return file_lines


def scan_diff(
    ref: str = "HEAD",
    *,
    repo: Optional[str] = None,
    check_injection: bool = False,
    format: Optional[str] = None,
) -> ScanResult:
    """Scan only changed lines from ``git diff`` for PII/injection.

    Unlike ``scan_git_diff`` (which scans entire changed files), this function
    scans **only the added/modified lines** identified by the unified diff,
    providing faster and more precise results for CI pipelines.

    Args:
        ref: Git ref to diff against.  ``"HEAD"`` (default) = staged changes.
             Other values: branch name, tag, or commit hash.
        repo: Git repository root (default: current directory).
        check_injection: Also detect prompt injection patterns.

    Returns:
        ScanResult with findings limited to changed lines.
    """
    changed_lines = _git_diff_changed_lines(ref, repo=repo)
    result = ScanResult()

    if not changed_lines:
        return result

    repo_root = Path(repo) if repo else Path(".")
    pipeline = DetectionPipeline()
    injection_detector = PromptInjectionDetector() if check_injection else None

    for rel_path, line_numbers in changed_lines.items():
        fpath = repo_root / rel_path
        if not fpath.is_file():
            continue
        if _is_binary(fpath):
            continue

        result.files_scanned += 1
        try:
            text = fpath.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            result.errors.append({"path": str(fpath), "error": str(e)})
            continue

        file_str = str(fpath)
        file_has_findings = False
        lines = text.splitlines()
        changed_set = set(line_numbers)

        for line_no in line_numbers:
            if line_no < 1 or line_no > len(lines):
                continue
            line = lines[line_no - 1]
            if not line.strip():
                continue

            # PII detection
            pii_findings = pipeline.analyze(line)
            for f in pii_findings:
                snippet = f.text if len(f.text) <= 40 else f.text[:37] + "..."
                col = f.start + 1
                ctx_before = line[max(0, f.start - 5):f.start]
                ctx_after = line[f.end:f.end + 5]
                method = _classify_detection_method(getattr(f, "source", "regex"))
                result.findings.append(ScanFinding(
                    file=file_str,
                    line=line_no,
                    finding_type=f"PII:{f.entity_type}",
                    text=snippet,
                    column=col,
                    score=getattr(f, "score", 1.0),
                    detection_method=method,
                    context_before=ctx_before,
                    context_after=ctx_after,
                ))
                file_has_findings = True

            # Injection detection
            if injection_detector:
                inj_findings = injection_detector.detect(line)
                for f in inj_findings:
                    snippet = f.text if len(f.text) <= 40 else f.text[:37] + "..."
                    col = f.start + 1
                    ctx_before = line[max(0, f.start - 5):f.start]
                    ctx_after = line[f.end:f.end + 5]
                    method = _classify_detection_method(getattr(f, "source", "regex"))
                    result.findings.append(ScanFinding(
                        file=file_str,
                        line=line_no,
                        finding_type=f"INJECTION:{f.entity_type}",
                        text=snippet,
                        column=col,
                        score=getattr(f, "score", 1.0),
                        detection_method=method,
                        context_before=ctx_before,
                        context_after=ctx_after,
                    ))
                    file_has_findings = True

        if file_has_findings:
            result.files_with_findings += 1

    return result


# ---------------------------------------------------------------------------
# Baseline comparison (patch181)
# ---------------------------------------------------------------------------

def _load_baseline(baseline_path: str) -> set:
    """Load baseline findings as a set of (file, line, finding_type, text) tuples.

    Supports JSON (ScanResult.to_dict() format) and JSONL (one finding per line).
    """
    p = Path(baseline_path)
    if not p.is_file():
        return set()

    content = p.read_text(encoding="utf-8").strip()
    if not content:
        return set()

    findings_set: set = set()

    # Try JSON first (full scan result dict)
    if content.startswith("{"):
        try:
            data = json.loads(content)
            for f in data.get("findings", []):
                key = (f.get("file", ""), f.get("line", 0),
                       f.get("finding_type", ""), f.get("text", ""))
                findings_set.add(key)
            return findings_set
        except json.JSONDecodeError:
            pass

    # JSONL format (one JSON object per line)
    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            f = json.loads(line)
            # JSONL from _render_jsonl uses "entity_type" key
            ftype = f.get("finding_type", f.get("entity_type", ""))
            key = (f.get("file", ""), f.get("line", 0), ftype, f.get("text", ""))
            findings_set.add(key)
        except json.JSONDecodeError:
            continue

    return findings_set


def _apply_baseline(result: "ScanResult", baseline_path: str) -> "ScanResult":
    """Remove findings that already exist in the baseline.

    Returns a new ScanResult with only NEW findings.
    """
    baseline = _load_baseline(baseline_path)
    if not baseline:
        return result

    new_findings = []
    for f in result.findings:
        key = (f.file, f.line, f.finding_type, f.text)
        if key not in baseline:
            new_findings.append(f)

    result.findings = new_findings
    result.files_with_findings = len(set(f.file for f in new_findings))
    return result


# ---------------------------------------------------------------------------
# CLI handler (called from cli.py)
# ---------------------------------------------------------------------------

def cmd_scan(args) -> int:
    """``nufi-egress scan`` CLI handler."""
    target = args.target

    # --profile: apply scan profile defaults before processing flags (patch110)
    profile_name = getattr(args, "profile", None)
    if profile_name:
        from enforcement.scan_profiles import resolve_profile, apply_profile_to_args
        profile = resolve_profile(profile_name)
        apply_profile_to_args(profile, args)

    # --diff [ref]: scan only changed lines from git diff (v0.7.5)
    diff_ref = getattr(args, "diff", None)
    if diff_ref is not None:
        result = scan_diff(
            ref=diff_ref if diff_ref else "HEAD",
            check_injection=getattr(args, "check_injection", False),
        )
        output_format = getattr(args, "format", None)
        if not output_format and getattr(args, "json", False):
            output_format = "json"
        diff_label = diff_ref if diff_ref else "HEAD (staged)"
        if output_format == "json":
            print(_render_json(result, target=f"diff:{diff_label}"))
        elif output_format == "sarif":
            sarif = scan_result_to_sarif(result)
            print(json.dumps(sarif, ensure_ascii=False, indent=2))
        elif output_format == "csv":
            print(_render_csv(result), end="")
        elif not result.findings:
            print(f"Diff scan ({diff_label}): {result.files_scanned} changed files, "
                  f"no PII in changed lines.")
        else:
            print(f"Diff scan ({diff_label}): {result.files_scanned} changed files, "
                  f"{result.files_with_findings} with findings, "
                  f"{len(result.findings)} total.")
            print()
            _render_human(result)
        if getattr(args, "fail_on_pii", False) and result.has_pii:
            return 1
        return 0

    # --recursive / -r: recursive directory scan with aggregate report (v0.7.4)
    if getattr(args, "recursive", False):
        if not target:
            print("Error: --recursive requires a target directory")
            return 2
        rec_patterns: Optional[List[str]] = None
        if getattr(args, "pattern", None):
            rec_patterns = [p.strip() for p in args.pattern.split(",") if p.strip()]
        rec_exclude: Optional[List[str]] = None
        if getattr(args, "exclude", None):
            rec_exclude = [p.strip() for p in args.exclude.split(",") if p.strip()]
        rec_include: Optional[List[str]] = None
        if getattr(args, "include", None):
            rec_include = [p.strip() for p in args.include.split(",") if p.strip()]
        rec_result = scan_recursive(
            target,
            check_injection=getattr(args, "check_injection", False),
            exclude=rec_exclude,
            include=rec_include,
            parallel=getattr(args, "parallel", 1),
        )
        output_format = getattr(args, "format", None)
        if not output_format and getattr(args, "json", False):
            output_format = "json"
        if output_format == "json":
            print(_render_recursive_json(rec_result, target=target))
        elif output_format == "csv":
            print(_render_recursive_csv(rec_result), end="")
        else:
            _render_recursive_human(rec_result)
        if getattr(args, "fail_on_pii", False) and rec_result.summary.files_with_pii > 0:
            return 1
        return 0

    # --watch: real-time file monitoring mode (v0.7.3)
    if getattr(args, "watch", False):
        if not target:
            print("Error: --watch requires a target directory")
            return 2
        watch_patterns: Optional[List[str]] = None
        if getattr(args, "pattern", None):
            watch_patterns = [p.strip() for p in args.pattern.split(",") if p.strip()]
        watch_exclude: Optional[List[str]] = None
        if getattr(args, "exclude", None):
            watch_exclude = [p.strip() for p in args.exclude.split(",") if p.strip()]
        output_format = getattr(args, "format", None)
        if not output_format and getattr(args, "json", False):
            output_format = "json"
        return scan_watch(
            target,
            interval=getattr(args, "watch_interval", 1.0),
            check_injection=getattr(args, "check_injection", False),
            patterns=watch_patterns,
            exclude=watch_exclude,
            output_format=output_format,
        )

    # --git-staged: scan only staged files (patch171)
    if getattr(args, "git_staged", False):
        patterns_list: Optional[List[str]] = None
        if getattr(args, "pattern", None):
            patterns_list = [p.strip() for p in args.pattern.split(",") if p.strip()]
        exclude_list: Optional[List[str]] = None
        if getattr(args, "exclude", None):
            exclude_list = [p.strip() for p in args.exclude.split(",") if p.strip()]
        result = scan_staged(
            patterns=patterns_list,
            check_injection=getattr(args, "check_injection", False),
            exclude=exclude_list,
            parallel=getattr(args, "parallel", 1),
            cache=getattr(args, "cache", False),
        )
        output_format = getattr(args, "format", None)
        if not output_format and getattr(args, "json", False):
            output_format = "json"
        if output_format == "json":
            print(_render_json(result, target="git-staged"))
        elif output_format == "sarif":
            sarif = scan_result_to_sarif(result)
            print(json.dumps(sarif, ensure_ascii=False, indent=2))
        elif output_format == "csv":
            print(_render_csv(result), end="")
        elif not result.findings:
            print(f"Staged scan: {result.files_scanned} files scanned, no findings.")
        else:
            _render_human(result)
        if getattr(args, "fail_on_pii", False) and result.has_pii:
            return 1
        return 0

    # --clear-cache: delete cache and exit
    if getattr(args, "clear_cache", False):
        removed = clear_scan_cache(target)
        if removed:
            print("Cache cleared.")
        else:
            print("No cache file found.")
        return 0

    # Parse patterns
    patterns: Optional[List[str]] = None
    if getattr(args, "pattern", None):
        patterns = [p.strip() for p in args.pattern.split(",") if p.strip()]

    # Parse exclude patterns
    exclude: Optional[List[str]] = None
    if getattr(args, "exclude", None):
        exclude = [p.strip() for p in args.exclude.split(",") if p.strip()]

    # Redact mode (patch88)
    do_redact = getattr(args, "redact", False)
    dry_run = getattr(args, "dry_run", False)
    no_backup = getattr(args, "no_backup", False)

    if do_redact or dry_run:
        redact_result = redact_path(
            target,
            patterns=patterns,
            exclude=exclude,
            dry_run=dry_run,
            no_backup=no_backup,
        )
        _render_redact(redact_result, dry_run=dry_run)
        return 0

    result = scan_path(
        target,
        patterns=patterns,
        check_injection=getattr(args, "check_injection", False),
        exclude=exclude,
        parallel=getattr(args, "parallel", 1),
        cache=getattr(args, "cache", False),
    )

    # --ignore-file: apply false positive suppressions (patch178)
    ignore_file = getattr(args, "ignore_file", None)
    suppressed_count = 0
    if ignore_file is None:
        # Auto-detect .nufi_ignore_findings.yaml in scan root
        scan_root = Path(target) if Path(target).is_dir() else Path(target).parent
        default_ignore = scan_root / ".nufi_ignore_findings.yaml"
        if default_ignore.is_file():
            ignore_file = str(default_ignore)
    if ignore_file:
        suppressions = load_suppressions(ignore_file)
        scan_root = Path(target) if Path(target).is_dir() else Path(target).parent
        suppressed_count = apply_suppressions(result, suppressions, scan_root)

    # --baseline: filter out findings already in baseline (patch181)
    baseline_path = getattr(args, "baseline", None)
    if baseline_path:
        result = _apply_baseline(result, baseline_path)

    # --only-types: filter to specific entity types (patch188)
    only_types_raw = getattr(args, "only_types", None)
    if only_types_raw:
        allowed = {t.strip().upper() for t in only_types_raw.split(",") if t.strip()}
        result.findings = [
            f for f in result.findings
            if _extract_entity_type(f.finding_type) in allowed
        ]
        result.files_with_findings = len(set(f.file for f in result.findings))

    # --min-score: filter findings below confidence threshold (patch186)
    min_score = getattr(args, "min_score", 0.0)
    if min_score > 0.0:
        result.findings = [f for f in result.findings if f.score >= min_score]
        result.files_with_findings = len(set(f.file for f in result.findings))

    # Output path (read early for --pseudonymize)
    output_path = getattr(args, "output", None)

    # --pseudonymize: apply reversible pseudonymization to scanned files (v0.6.0)
    do_pseudonymize = getattr(args, "pseudonymize", False)
    pseudonymized_texts: dict = {}  # file_path -> pseudonymized_text
    if do_pseudonymize and result.findings:
        import uuid as _uuid
        from egress_audit.reversible import ReversibleEgress
        _rev = ReversibleEgress(ner_backend="gazetteer")
        _psid = f"scan-{_uuid.uuid4().hex[:12]}"
        # Collect files with PII findings
        pii_files = sorted(set(
            f.file for f in result.findings if f.finding_type.startswith("PII:")
        ))
        for fpath in pii_files:
            try:
                content = Path(fpath).read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            r = _rev.pseudonymize(content, _psid)
            if not r.blocked and r.pseudonymized > 0:
                pseudonymized_texts[fpath] = r.transformed_text
        # Write pseudonymized files to --output directory if specified
        if output_path and pseudonymized_texts:
            out_dir = Path(output_path)
            out_dir.mkdir(parents=True, exist_ok=True)
            for fpath, ptext in pseudonymized_texts.items():
                out_file = out_dir / Path(fpath).name
                out_file.write_text(ptext + "\n", encoding="utf-8")

    # --count-only: print summary count and exit (patch182)
    if getattr(args, "count_only", False):
        count = len(result.findings)
        file_count = len(set(f.file for f in result.findings))
        print(f"Found: {count} PII findings in {file_count} files")
        if getattr(args, "fail_on_pii", False) and count > 0:
            return 1
        return 0

    # Output format — --json flag treated as --format json (v0.7.0)
    output_format = getattr(args, "format", None)
    if not output_format and getattr(args, "json", False):
        output_format = "json"
    # When --pseudonymize + --output, output_path is used as dir for pseudonymized
    # files, so skip writing scan results to output_path as a file.
    scan_output_path = None if (do_pseudonymize and pseudonymized_texts) else output_path

    def _write_or_print(text: str, *, end: str = "\n") -> None:
        if scan_output_path:
            Path(scan_output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(scan_output_path).write_text(text + end, encoding="utf-8")
        else:
            print(text, end=end)

    do_summary = getattr(args, "summary", False)

    if output_format == "json":
        text_out = _render_json(result, target=target, summary=do_summary)
        _write_or_print(text_out)
    elif output_format == "csv":
        text_out = _render_csv(result)
        _write_or_print(text_out, end="")
    elif output_format == "sarif":
        sarif = scan_result_to_sarif(result)
        text_out = json.dumps(sarif, ensure_ascii=False, indent=2)
        _write_or_print(text_out)
    elif scan_output_path:
        # --output without --format: default to JSON Lines
        lines = _render_jsonl(result)
        Path(scan_output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(scan_output_path).write_text(lines, encoding="utf-8")
    elif getattr(args, "summary_only", False):
        _render_summary_only(result)
    elif getattr(args, "verbose", False):
        _render_verbose(result)
    else:
        _render_human(result)

    # Suppression notice
    if suppressed_count > 0:
        print(f"{suppressed_count} findings suppressed")

    # Stats summary
    if getattr(args, "stats", False):
        _render_stats(result)

    # --summary: summary dashboard with ASCII bar charts (v0.7.7)
    if getattr(args, "summary", False):
        _render_summary_dashboard(result)

    # --pseudonymize: show pseudonymized text after normal output (v0.6.0)
    if do_pseudonymize and pseudonymized_texts and not output_path:
        print()
        print("── 가명화 결과 (Pseudonymized) ──")
        for fpath, ptext in pseudonymized_texts.items():
            print(f"\n  {fpath}:")
            for line in ptext.splitlines():
                print(f"    {line}")

    # Exit code — with --baseline, no new findings means pass even with --fail-on-pii
    if getattr(args, "fail_on_pii", False) and result.has_pii:
        return 1
    return 0


# ---------------------------------------------------------------------------
# Recursive directory scan with aggregate report (v0.7.4)
# ---------------------------------------------------------------------------

@dataclass
class RecursiveScanSummary:
    """Aggregate summary for --recursive scan."""
    files_scanned: int = 0
    files_skipped: int = 0
    files_with_pii: int = 0
    entity_counts: Dict[str, int] = field(default_factory=dict)
    top_files: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class RecursiveScanResult:
    """Result of a --recursive directory scan."""
    files: List[Dict[str, Any]] = field(default_factory=list)
    summary: RecursiveScanSummary = field(default_factory=RecursiveScanSummary)
    errors: List[Dict[str, str]] = field(default_factory=list)


def scan_recursive(
    directory: str | Path,
    *,
    check_injection: bool = False,
    exclude: Optional[List[str]] = None,
    include: Optional[List[str]] = None,
    parallel: int = 1,
) -> RecursiveScanResult:
    """Recursively scan all files in *directory* and build an aggregate report.

    Args:
        directory: Root directory to scan.
        check_injection: Also detect prompt injection patterns.
        exclude: Glob patterns to exclude (e.g. ``['*.pyc', '.git/*']``).
        include: Glob patterns to include (only scan matching files).
        parallel: Thread count (1 = sequential).

    Returns:
        RecursiveScanResult with per-file findings and aggregate summary.
    """
    directory = Path(directory)
    rec_result = RecursiveScanResult()

    if not directory.is_dir():
        rec_result.errors.append({"path": str(directory), "error": "Not a directory"})
        return rec_result

    # Build exclusion patterns
    if exclude is None:
        exclude_patterns = load_nufiignore(directory)
    else:
        exclude_patterns = list(exclude)

    # Collect files
    all_files: List[Path] = []
    skipped = 0
    for root, _dirs, fnames in os.walk(directory):
        for fname in sorted(fnames):
            fpath = Path(root) / fname
            if _is_excluded(fpath, directory, exclude_patterns):
                skipped += 1
                continue
            if include and not _matches_patterns(fpath, include):
                skipped += 1
                continue
            if _is_binary(fpath):
                skipped += 1
                continue
            all_files.append(fpath)

    rec_result.summary.files_skipped = skipped

    # Scan files
    if parallel > 1 and len(all_files) > 1:
        with ThreadPoolExecutor(max_workers=parallel) as executor:
            futures = [
                executor.submit(_scan_file_isolated, fpath, check_injection, None)
                for fpath in all_files
            ]
            sub_results = [f.result() for f in futures]
        merged = _merge_results(sub_results)
    else:
        merged = ScanResult()
        pipeline = DetectionPipeline()
        injection_detector = PromptInjectionDetector() if check_injection else None
        for fpath in all_files:
            _scan_file(fpath, pipeline, injection_detector, merged, None)

    rec_result.summary.files_scanned = merged.files_scanned
    rec_result.summary.files_with_pii = merged.files_with_findings

    # Build per-file entries and entity counts
    file_finding_counts: Dict[str, int] = {}
    entity_counts: Dict[str, int] = {}
    file_entries: Dict[str, Dict[str, Any]] = {}
    for f in merged.findings:
        et = _extract_entity_type(f.finding_type)
        entity_counts[et] = entity_counts.get(et, 0) + 1
        file_finding_counts[f.file] = file_finding_counts.get(f.file, 0) + 1
        if f.file not in file_entries:
            file_entries[f.file] = {"file": f.file, "findings": []}
        file_entries[f.file]["findings"].append({
            "line": f.line,
            "finding_type": f.finding_type,
            "text": f.text,
            "entity_type": et,
            "score": f.score,
        })

    rec_result.files = list(file_entries.values())
    rec_result.summary.entity_counts = dict(sorted(entity_counts.items()))

    # Top 5 files by finding count
    top_files_sorted = sorted(
        file_finding_counts.items(), key=lambda x: x[1], reverse=True,
    )[:5]
    rec_result.summary.top_files = [
        {"file": fp, "count": cnt} for fp, cnt in top_files_sorted
    ]
    rec_result.errors = merged.errors

    return rec_result


def _render_recursive_json(rec: RecursiveScanResult, *, target: str = "") -> str:
    """Render recursive scan result as JSON."""
    doc = {
        "version": _nufi_version(),
        "scan_target": target,
        "files": rec.files,
        "summary": {
            "files_scanned": rec.summary.files_scanned,
            "files_skipped": rec.summary.files_skipped,
            "files_with_pii": rec.summary.files_with_pii,
            "entity_counts": rec.summary.entity_counts,
            "top_files": rec.summary.top_files,
        },
        "errors": rec.errors,
    }
    return json.dumps(doc, ensure_ascii=False, indent=2)


def _render_recursive_csv(rec: RecursiveScanResult) -> str:
    """Render recursive scan findings as CSV."""
    import csv
    import io

    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_NONNUMERIC)
    writer.writerow(["file", "line", "entity_type", "text", "score"])
    for fe in rec.files:
        for f in fe["findings"]:
            writer.writerow([
                fe["file"], f["line"], f["entity_type"], f["text"], f["score"],
            ])
    return output.getvalue()


def _render_recursive_human(rec: RecursiveScanResult) -> None:
    """Human-readable recursive scan output with aggregate report."""
    s = rec.summary
    total_findings = sum(len(fe["findings"]) for fe in rec.files)

    print(f"Recursive scan complete: {s.files_scanned} files scanned, "
          f"{s.files_skipped} skipped, "
          f"{s.files_with_pii} with PII, "
          f"{total_findings} total findings.")

    if rec.files:
        print()
        for fe in rec.files:
            print(f"  {fe['file']}")
            for f in fe["findings"]:
                print(f"    L{f['line']}: [{f['finding_type']}] {f['text']}")

    # Aggregate report
    print()
    print("── 집계 리포트 (Aggregate Report) ──")
    print(f"  스캔 파일 수:       {s.files_scanned}")
    print(f"  건너뛴 파일 수:     {s.files_skipped}")
    print(f"  PII 발견 파일 수:   {s.files_with_pii}")
    if s.entity_counts:
        print(f"  엔티티 타입별 건수:")
        for etype, count in sorted(s.entity_counts.items(), key=lambda x: -x[1]):
            print(f"    {etype:<30} {count}")
    if s.top_files:
        print(f"  PII 최다 파일 Top {len(s.top_files)}:")
        for i, tf in enumerate(s.top_files, 1):
            print(f"    {i}. {tf['file']} ({tf['count']}건)")

    if rec.errors:
        print()
        print("Errors:")
        for e in rec.errors:
            print(f"  {e['path']}: {e['error']}")


# ---------------------------------------------------------------------------
# Watch mode — real-time file monitoring (v0.7.3)
# ---------------------------------------------------------------------------

def _get_mtime(path: Path) -> Optional[float]:
    """Get file mtime, returning None if file doesn't exist."""
    try:
        return os.stat(path).st_mtime
    except OSError:
        return None


def _collect_watchable_files(
    directory: Path,
    patterns: Optional[List[str]],
    exclude_patterns: List[str],
) -> List[Path]:
    """Collect all matching non-binary files in directory."""
    files: List[Path] = []
    for root, _dirs, fnames in os.walk(directory):
        for fname in sorted(fnames):
            fpath = Path(root) / fname
            if _is_excluded(fpath, directory, exclude_patterns):
                continue
            if not _matches_patterns(fpath, patterns):
                continue
            if _is_binary(fpath):
                continue
            files.append(fpath)
    return files


def _format_watch_event(
    path: Path,
    result: ScanResult,
    output_format: Optional[str],
    timestamp: str,
) -> str:
    """Format a watch event for output."""
    if output_format == "json":
        event = {
            "timestamp": timestamp,
            "file": str(path),
            "findings": [
                {
                    "line": f.line,
                    "finding_type": f.finding_type,
                    "text": f.text,
                    "score": f.score,
                }
                for f in result.findings
            ],
        }
        return json.dumps(event, ensure_ascii=False)
    # text format
    lines: List[str] = []
    for f in result.findings:
        lines.append(f"[{timestamp}] {path}: L{f.line} [{f.finding_type}] {f.text}")
    return "\n".join(lines)


def scan_watch(
    directory: str | Path,
    *,
    interval: float = 1.0,
    check_injection: bool = False,
    patterns: Optional[List[str]] = None,
    exclude: Optional[List[str]] = None,
    output_format: Optional[str] = None,
    _stop_after: Optional[int] = None,
) -> int:
    """Watch a directory for file changes and scan for PII in real time.

    Uses watchdog (inotify) if available, otherwise falls back to mtime polling.

    Args:
        directory: Path to directory to watch.
        interval: Polling interval in seconds (default 1.0).
        check_injection: Also detect prompt injection patterns.
        patterns: Glob patterns to filter files.
        exclude: Glob patterns to exclude files.
        output_format: Output format — "text" (default) or "json".
        _stop_after: (testing) Stop after this many scan cycles.

    Returns:
        Exit code 0.
    """
    directory = Path(directory)
    if not directory.is_dir():
        print(f"Error: {directory} is not a directory")
        return 2

    # Build exclusion patterns
    if exclude is None:
        exclude_patterns = load_nufiignore(directory)
    else:
        exclude_patterns = list(exclude)

    # Try watchdog-based watcher, fall back to polling
    try:
        return _watch_with_watchdog(
            directory, interval=interval, check_injection=check_injection,
            patterns=patterns, exclude_patterns=exclude_patterns,
            output_format=output_format, _stop_after=_stop_after,
        )
    except ImportError:
        return _watch_with_polling(
            directory, interval=interval, check_injection=check_injection,
            patterns=patterns, exclude_patterns=exclude_patterns,
            output_format=output_format, _stop_after=_stop_after,
        )


def _on_file_changed(
    path: Path,
    pipeline: DetectionPipeline,
    injection_detector: Optional[PromptInjectionDetector],
    output_format: Optional[str],
) -> None:
    """Scan a changed file and print results if findings exist."""
    if _is_binary(path):
        return
    result = ScanResult()
    _scan_file(path, pipeline, injection_detector, result, patterns=None)
    if result.findings:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        output = _format_watch_event(path, result, output_format, ts)
        print(output, flush=True)


def _watch_with_watchdog(
    directory: Path,
    *,
    interval: float,
    check_injection: bool,
    patterns: Optional[List[str]],
    exclude_patterns: List[str],
    output_format: Optional[str],
    _stop_after: Optional[int],
) -> int:
    """Watch using watchdog (inotify on Linux)."""
    from watchdog.observers import Observer  # type: ignore[import-untyped]
    from watchdog.events import FileSystemEventHandler, FileSystemEvent  # type: ignore[import-untyped]

    pipeline = DetectionPipeline()
    injection_detector = PromptInjectionDetector() if check_injection else None

    class _Handler(FileSystemEventHandler):
        def on_created(self, event: FileSystemEvent) -> None:
            if event.is_directory:
                return
            self._handle(event.src_path)

        def on_modified(self, event: FileSystemEvent) -> None:
            if event.is_directory:
                return
            self._handle(event.src_path)

        def _handle(self, src_path: str) -> None:
            fpath = Path(src_path)
            if _is_excluded(fpath, directory, exclude_patterns):
                return
            if not _matches_patterns(fpath, patterns):
                return
            _on_file_changed(fpath, pipeline, injection_detector, output_format)

    observer = Observer()
    observer.schedule(_Handler(), str(directory), recursive=True)
    observer.start()
    print(f"[watch] Monitoring {directory} (watchdog, interval={interval}s)",
          flush=True)
    try:
        if _stop_after is not None:
            for _ in range(_stop_after):
                time.sleep(interval)
            observer.stop()
        else:
            while True:
                time.sleep(interval)
    except KeyboardInterrupt:
        observer.stop()
        print("\n[watch] Stopped.")
    observer.join()
    return 0


def _watch_with_polling(
    directory: Path,
    *,
    interval: float,
    check_injection: bool,
    patterns: Optional[List[str]],
    exclude_patterns: List[str],
    output_format: Optional[str],
    _stop_after: Optional[int],
) -> int:
    """Watch using mtime polling fallback."""
    # Build initial mtime cache BEFORE heavy pipeline init
    mtime_cache: Dict[str, float] = {}
    files = _collect_watchable_files(directory, patterns, exclude_patterns)
    for f in files:
        mt = _get_mtime(f)
        if mt is not None:
            mtime_cache[str(f)] = mt

    pipeline = DetectionPipeline()
    injection_detector = PromptInjectionDetector() if check_injection else None

    print(f"[watch] Monitoring {directory} (polling, interval={interval}s, "
          f"{len(mtime_cache)} files tracked)", flush=True)

    cycle = 0
    try:
        while True:
            time.sleep(interval)
            cycle += 1
            files = _collect_watchable_files(directory, patterns, exclude_patterns)
            for f in files:
                mt = _get_mtime(f)
                if mt is None:
                    continue
                fkey = str(f)
                prev_mt = mtime_cache.get(fkey)
                if prev_mt is None or mt > prev_mt:
                    _on_file_changed(f, pipeline, injection_detector, output_format)
                    mtime_cache[fkey] = mt
            if _stop_after is not None and cycle >= _stop_after:
                break
    except KeyboardInterrupt:
        print("\n[watch] Stopped.")
    return 0


def _render_json(result: ScanResult, *, target: str = "", summary: bool = False) -> str:
    """Render scan result as structured JSON (v0.7.0, v0.7.7 --summary).

    Schema: version, scan_target, findings[], summary.
    When *summary* is True, the summary dict is enriched with by_severity
    and per-file counts (v0.7.7).
    """
    import collections

    findings_out = []
    for f in result.findings:
        entity = _extract_entity_type(f.finding_type)
        start = f.column
        end = f.column + max(len(f.text), 1)
        entry: Dict[str, Any] = {
            "entity_type": entity,
            "text": f.text,
            "start": start,
            "end": end,
            "score": f.score,
        }
        findings_out.append(entry)

    by_type: Dict[str, int] = {}
    for f in result.findings:
        et = _extract_entity_type(f.finding_type)
        by_type[et] = by_type.get(et, 0) + 1

    summary_dict: Dict[str, Any] = {
        "total": len(result.findings),
        "by_type": dict(sorted(by_type.items())),
    }

    if summary:
        full = _build_summary_dict(result)
        summary_dict["files_scanned"] = full["files_scanned"]
        summary_dict["files_with_findings"] = full["files_with_findings"]
        summary_dict["by_severity"] = full["by_severity"]

    doc = {
        "version": _nufi_version(),
        "scan_target": target or "",
        "findings": findings_out,
        "summary": summary_dict,
    }
    return json.dumps(doc, ensure_ascii=False, indent=2)


def _render_jsonl(result: ScanResult) -> str:
    """Render findings as JSON Lines (one JSON object per finding per line)."""
    lines: List[str] = []
    for f in result.findings:
        obj = {
            "file": f.file,
            "line": f.line,
            "entity_type": f.finding_type,
            "text": f.text,
            "score": 1.0,
        }
        lines.append(json.dumps(obj, ensure_ascii=False))
    return "\n".join(lines) + ("\n" if lines else "")


def _render_csv(result: ScanResult) -> str:
    """Render findings as standard CSV (comma-separated, quoted strings)."""
    import csv
    import io

    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_NONNUMERIC)
    writer.writerow(["entity_type", "text", "start", "end", "score"])
    for f in result.findings:
        entity_type = _extract_entity_type(f.finding_type)
        start = f.column
        end = f.column + max(len(f.text), 1)
        writer.writerow([entity_type, f.text, start, end, f.score])
    return output.getvalue()


def _render_human(result: ScanResult) -> None:
    """Human-friendly output."""
    if not result.findings:
        print(f"Scan complete: {result.files_scanned} files scanned, no findings.")
        return

    print(f"Scan complete: {result.files_scanned} files scanned, "
          f"{result.files_with_findings} with findings, "
          f"{len(result.findings)} total findings.")
    print()

    current_file = None
    for f in result.findings:
        if f.file != current_file:
            current_file = f.file
            print(f"  {f.file}")
        print(f"    L{f.line}: [{f.finding_type}] {f.text}")

    if result.errors:
        print()
        print("Errors:")
        for e in result.errors:
            print(f"  {e['path']}: {e['error']}")


def _render_verbose(result: ScanResult) -> None:
    """Verbose output: detailed per-finding information."""
    if not result.findings:
        print(f"Scan complete: {result.files_scanned} files scanned, no findings.")
        return

    print(f"Scan complete: {result.files_scanned} files scanned, "
          f"{result.files_with_findings} with findings, "
          f"{len(result.findings)} total findings.")
    print()

    current_file = None
    for f in result.findings:
        if f.file != current_file:
            current_file = f.file
            # Count findings for this file
            file_count = sum(1 for x in result.findings if x.file == f.file)
            print(f"  {f.file} ({file_count} finding(s))")
        ctx = f"...{f.context_before}[{f.text}]{f.context_after}..."
        print(f"    L{f.line}:C{f.column} [{f.finding_type}] "
              f"score={f.score:.2f} method={f.detection_method}")
        print(f"      text: {f.text}")
        print(f"      context: {ctx}")

    if result.errors:
        print()
        print("Errors:")
        for e in result.errors:
            print(f"  {e['path']}: {e['error']}")


def _compute_scan_risk(result: ScanResult) -> str:
    """Compute overall risk level from scan findings."""
    has_injection = result.has_injection
    has_strong_pii = any(
        f.finding_type.split(":", 1)[1] in _STRONG_PII
        for f in result.findings
        if ":" in f.finding_type and f.finding_type.startswith("PII:")
    )
    if has_injection or has_strong_pii:
        return "critical"
    if len(result.findings) >= 5:
        return "high"
    if result.findings:
        return "medium"
    return "clean"


def _render_summary_only(result: ScanResult) -> None:
    """Print only a compact summary line — no per-file details."""
    risk = _compute_scan_risk(result)
    passed = not result.has_pii and not result.has_injection
    status = "PASS" if passed else "FAIL"
    print(f"Files scanned: {result.files_scanned} | "
          f"Findings: {len(result.findings)} | "
          f"Risk: {risk} | "
          f"Status: {status}")


def _render_stats(result: ScanResult) -> None:
    """Print summary statistics block after scan output."""
    import collections

    total_findings = len(result.findings)
    files_pct = (
        round(result.files_with_findings / result.files_scanned * 100, 1)
        if result.files_scanned else 0.0
    )

    # Entity type breakdown
    entity_counter: "collections.Counter[str]" = collections.Counter()
    for f in result.findings:
        entity_counter[f.finding_type] += 1

    # Risk breakdown (based on SARIF level mapping)
    risk_counter: "collections.Counter[str]" = collections.Counter()
    for f in result.findings:
        level = _sarif_level(f.finding_type)
        if level == "error":
            # Distinguish critical vs high
            entity = f.finding_type.split(":", 1)[1] if ":" in f.finding_type else f.finding_type
            if f.finding_type.startswith("INJECTION:") or entity in _STRONG_PII:
                risk_counter["critical"] += 1
            else:
                risk_counter["high"] += 1
        else:
            risk_counter["medium"] += 1

    print()
    print("── 스캔 요약 (Stats) ──")
    print(f"  총 스캔 파일:       {result.files_scanned}")
    print(f"  발견 있는 파일:     {result.files_with_findings} ({files_pct}%)")
    print(f"  총 발견 수:         {total_findings}")
    if entity_counter:
        print("  엔티티별:")
        for etype, count in entity_counter.most_common():
            print(f"    {etype:<30} {count}")
    if risk_counter:
        print("  위험도별:")
        for level in ("critical", "high", "medium", "low"):
            if risk_counter[level]:
                print(f"    {level:<12} {risk_counter[level]}")


def _render_summary_dashboard(result: ScanResult) -> None:
    """Print summary dashboard with ASCII bar charts to stderr (v0.7.7).

    Outputs: total scanned, PII found, type distribution, severity distribution.
    """
    import collections
    import sys as _sys

    total_findings = len(result.findings)
    files_pct = (
        round(result.files_with_findings / result.files_scanned * 100, 1)
        if result.files_scanned else 0.0
    )

    # Entity type breakdown
    entity_counter: "collections.Counter[str]" = collections.Counter()
    for f in result.findings:
        et = _extract_entity_type(f.finding_type)
        entity_counter[et] += 1

    # Severity breakdown
    severity_counter: "collections.Counter[str]" = collections.Counter()
    for f in result.findings:
        level = _sarif_level(f.finding_type)
        if level == "error":
            entity = f.finding_type.split(":", 1)[1] if ":" in f.finding_type else f.finding_type
            if f.finding_type.startswith("INJECTION:") or entity in _STRONG_PII:
                severity_counter["critical"] += 1
            else:
                severity_counter["high"] += 1
        else:
            severity_counter["medium"] += 1

    BAR_MAX = 30  # max bar width in characters

    def _bar(count: int, max_count: int) -> str:
        if max_count == 0:
            return ""
        width = max(1, round(count / max_count * BAR_MAX))
        return "█" * width

    w = _sys.stderr.write

    w("\n")
    w("╔══════════════════════════════════════════════════════╗\n")
    w("║           NuFi Scan Summary Dashboard               ║\n")
    w("╠══════════════════════════════════════════════════════╣\n")
    w(f"║  총 스캔 건수:     {result.files_scanned:>6} files                    ║\n")
    w(f"║  PII 발견 건수:    {total_findings:>6} findings                 ║\n")
    w(f"║  발견 파일 비율:   {files_pct:>6.1f}%                         ║\n")
    w("╠══════════════════════════════════════════════════════╣\n")

    if entity_counter:
        w("║  타입별 분포 (Entity Type Distribution)              ║\n")
        w("║──────────────────────────────────────────────────────║\n")
        max_count = entity_counter.most_common(1)[0][1] if entity_counter else 1
        for etype, count in entity_counter.most_common():
            bar = _bar(count, max_count)
            label = etype[:18].ljust(18)
            count_str = str(count).rjust(4)
            bar_str = bar.ljust(BAR_MAX)
            line = f"║  {label} {count_str} {bar_str}║\n"
            w(line)
        w("╠══════════════════════════════════════════════════════╣\n")

    if severity_counter:
        w("║  심각도 분포 (Severity Distribution)                 ║\n")
        w("║──────────────────────────────────────────────────────║\n")
        sev_max = max(severity_counter.values()) if severity_counter else 1
        for level in ("critical", "high", "medium", "low"):
            cnt = severity_counter.get(level, 0)
            if cnt == 0:
                continue
            bar = _bar(cnt, sev_max)
            label = level[:18].ljust(18)
            count_str = str(cnt).rjust(4)
            bar_str = bar.ljust(BAR_MAX)
            w(f"║  {label} {count_str} {bar_str}║\n")

    w("╚══════════════════════════════════════════════════════╝\n")
    w("\n")
    _sys.stderr.flush()


def _build_summary_dict(result: ScanResult) -> Dict[str, Any]:
    """Build summary dict for JSON output (v0.7.7)."""
    import collections

    entity_counter: "collections.Counter[str]" = collections.Counter()
    for f in result.findings:
        et = _extract_entity_type(f.finding_type)
        entity_counter[et] += 1

    severity_counter: "collections.Counter[str]" = collections.Counter()
    for f in result.findings:
        level = _sarif_level(f.finding_type)
        if level == "error":
            entity = f.finding_type.split(":", 1)[1] if ":" in f.finding_type else f.finding_type
            if f.finding_type.startswith("INJECTION:") or entity in _STRONG_PII:
                severity_counter["critical"] += 1
            else:
                severity_counter["high"] += 1
        else:
            severity_counter["medium"] += 1

    return {
        "files_scanned": result.files_scanned,
        "files_with_findings": result.files_with_findings,
        "total_findings": len(result.findings),
        "by_type": dict(sorted(entity_counter.items())),
        "by_severity": {
            k: severity_counter.get(k, 0)
            for k in ("critical", "high", "medium", "low")
            if severity_counter.get(k, 0) > 0
        },
    }


def _render_redact(result: RedactResult, *, dry_run: bool) -> None:
    """Render redaction results."""
    mode = "DRY-RUN" if dry_run else "REDACT"
    if not result.redactions:
        print(f"[{mode}] No PII found to redact.")
        return

    print(f"[{mode}] {result.files_modified} file(s), "
          f"{result.total_redactions} redaction(s).")
    print()

    current_file = None
    for r in result.redactions:
        if r.file != current_file:
            current_file = r.file
            print(f"  {r.file}")
        print(f"    L{r.line}: [{r.entity_type}] {r.original_text}")

    if not dry_run and result.backups_created:
        print()
        print("Backups:")
        for b in result.backups_created:
            print(f"  {b}")
