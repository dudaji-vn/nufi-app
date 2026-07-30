"""``nufi-egress stats`` -- NuFi configuration and capability overview (patch112).

Shows a summary of:
- Configuration files: which exist, which are active
- Detection: PII patterns, injection patterns, custom patterns
- Scan profiles: available named profiles
- Cache status: cache file presence, size, entries
- .nufiignore: exclusion pattern count
- Audit log stats: line count and date range (if logs/egress_audit.jsonl exists)
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class StatsResult:
    """Aggregated stats result."""
    config_files: List[Dict[str, Any]] = field(default_factory=list)
    pii_pattern_count: int = 0
    secret_pattern_count: int = 0
    injection_pattern_count: int = 0
    custom_injection_pattern_count: int = 0
    scan_profiles: List[str] = field(default_factory=list)
    cache_exists: bool = False
    cache_size_bytes: int = 0
    cache_entries: int = 0
    nufiignore_pattern_count: int = 0
    audit_log_exists: bool = False
    audit_log_lines: int = 0
    audit_log_first_ts: Optional[str] = None
    audit_log_last_ts: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "config_files": self.config_files,
            "detection": {
                "pii_patterns": self.pii_pattern_count,
                "secret_patterns": self.secret_pattern_count,
                "injection_patterns": self.injection_pattern_count,
                "custom_injection_patterns": self.custom_injection_pattern_count,
            },
            "scan_profiles": self.scan_profiles,
            "cache": {
                "exists": self.cache_exists,
                "size_bytes": self.cache_size_bytes,
                "entries": self.cache_entries,
            },
            "nufiignore_patterns": self.nufiignore_pattern_count,
            "audit_log": {
                "exists": self.audit_log_exists,
                "lines": self.audit_log_lines,
                "first_ts": self.audit_log_first_ts,
                "last_ts": self.audit_log_last_ts,
            },
        }
        return d


# ---------------------------------------------------------------------------
# Collectors
# ---------------------------------------------------------------------------

_CONFIG_FILES = [
    ("config/policy.yaml", "정책 정의"),
    ("config/routing.yaml", "라우팅 설정"),
    ("config/pii_routing.yaml", "PII 라우팅 설정"),
    ("config/patterns.yaml", "PII 탐지 패턴"),
    ("config/injection_patterns.yaml", "인젝션 패턴 (사용자 정의)"),
    ("config/scan_profiles.yaml", "스캔 프로파일"),
    ("config/audit_profiles.yaml", "감사 프로파일"),
]


def _collect_config_files(root: Path) -> List[Dict[str, Any]]:
    result = []
    for rel, desc in _CONFIG_FILES:
        p = root / rel
        exists = p.is_file()
        entry: Dict[str, Any] = {
            "file": rel,
            "description": desc,
            "exists": exists,
        }
        if exists:
            entry["size_bytes"] = p.stat().st_size
        result.append(entry)
    return result


def _count_pii_patterns(root: Path) -> tuple[int, int]:
    """Return (pii_count, secret_count) from config/patterns.yaml."""
    try:
        import yaml
    except ImportError:
        return 0, 0
    p = root / "config" / "patterns.yaml"
    if not p.is_file():
        return 0, 0
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception:
        return 0, 0
    pii = data.get("korean_pii")
    pii_count = len(pii) if isinstance(pii, list) else 0
    secrets = data.get("secrets")
    secret_count = len(secrets) if isinstance(secrets, list) else 0
    return pii_count, secret_count


def _count_injection_patterns() -> int:
    """Return built-in injection pattern count."""
    try:
        from egress_audit.detectors.prompt_injection import _PATTERN_DEFS
        return len(_PATTERN_DEFS)
    except Exception:
        return 0


def _count_custom_injection_patterns(root: Path) -> int:
    """Return custom injection pattern count from config/injection_patterns.yaml."""
    try:
        import yaml
    except ImportError:
        return 0
    p = root / "config" / "injection_patterns.yaml"
    if not p.is_file():
        return 0
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception:
        return 0
    patterns = data.get("custom_patterns")
    return len(patterns) if isinstance(patterns, list) else 0


def _list_scan_profiles(root: Path) -> List[str]:
    """Return available scan profile names."""
    try:
        import yaml
    except ImportError:
        return []
    p = root / "config" / "scan_profiles.yaml"
    if not p.is_file():
        return []
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception:
        return []
    profiles = data.get("scan_profiles")
    if isinstance(profiles, dict):
        return sorted(profiles.keys())
    return []


def _check_cache(root: Path) -> tuple[bool, int, int]:
    """Return (exists, size_bytes, entries) for the scan cache."""
    cache_path = root / ".nufi_cache.json"
    if not cache_path.is_file():
        return False, 0, 0
    size = cache_path.stat().st_size
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        entries = len(data) if isinstance(data, (dict, list)) else 0
    except Exception:
        entries = 0
    return True, size, entries


def _count_nufiignore(root: Path) -> int:
    """Return number of non-empty non-comment lines in .nufiignore."""
    p = root / ".nufiignore"
    if not p.is_file():
        return 0
    lines = p.read_text(encoding="utf-8").splitlines()
    return sum(1 for ln in lines if ln.strip() and not ln.strip().startswith("#"))


def _audit_log_stats(root: Path) -> tuple[bool, int, Optional[str], Optional[str]]:
    """Return (exists, line_count, first_ts, last_ts) for audit log."""
    log_path = root / "logs" / "egress_audit.jsonl"
    if not log_path.is_file():
        return False, 0, None, None

    first_ts: Optional[str] = None
    last_ts: Optional[str] = None
    count = 0
    try:
        with log_path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                count += 1
                try:
                    rec = json.loads(line)
                    ts = rec.get("ts")
                    if ts:
                        if first_ts is None:
                            first_ts = ts
                        last_ts = ts
                except (json.JSONDecodeError, TypeError):
                    pass
    except Exception:
        return True, 0, None, None

    return True, count, first_ts, last_ts


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def collect_stats(root: Optional[Path] = None) -> StatsResult:
    """Collect NuFi configuration and capability stats."""
    if root is None:
        root = _ROOT
    result = StatsResult()

    # Config files
    result.config_files = _collect_config_files(root)

    # Detection patterns
    pii, secrets = _count_pii_patterns(root)
    result.pii_pattern_count = pii
    result.secret_pattern_count = secrets
    result.injection_pattern_count = _count_injection_patterns()
    result.custom_injection_pattern_count = _count_custom_injection_patterns(root)

    # Scan profiles
    result.scan_profiles = _list_scan_profiles(root)

    # Cache
    result.cache_exists, result.cache_size_bytes, result.cache_entries = _check_cache(root)

    # .nufiignore
    result.nufiignore_pattern_count = _count_nufiignore(root)

    # Audit log
    (result.audit_log_exists, result.audit_log_lines,
     result.audit_log_first_ts, result.audit_log_last_ts) = _audit_log_stats(root)

    return result


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def render_human(stats: StatsResult) -> str:
    """Render stats as human-readable text."""
    lines: List[str] = []
    lines.append("=== NuFi Stats ===")
    lines.append("")

    # Config files
    lines.append("[Configuration Files]")
    for cf in stats.config_files:
        status = "OK" if cf["exists"] else "missing"
        size_info = f" ({cf['size_bytes']} bytes)" if cf.get("size_bytes") else ""
        lines.append(f"  {cf['file']:<40} {status}{size_info}")
    lines.append("")

    # Detection
    lines.append("[Detection Patterns]")
    lines.append(f"  PII patterns (patterns.yaml):       {stats.pii_pattern_count}")
    lines.append(f"  Secret patterns (patterns.yaml):    {stats.secret_pattern_count}")
    lines.append(f"  Injection patterns (built-in):      {stats.injection_pattern_count}")
    lines.append(f"  Injection patterns (custom):        {stats.custom_injection_pattern_count}")
    total = (stats.pii_pattern_count + stats.secret_pattern_count +
             stats.injection_pattern_count + stats.custom_injection_pattern_count)
    lines.append(f"  Total:                              {total}")
    lines.append("")

    # Scan profiles
    lines.append("[Scan Profiles]")
    if stats.scan_profiles:
        lines.append(f"  Available: {', '.join(stats.scan_profiles)}")
    else:
        lines.append("  (none)")
    lines.append("")

    # Cache
    lines.append("[Cache]")
    if stats.cache_exists:
        lines.append(f"  File: .nufi_cache.json ({stats.cache_size_bytes} bytes, "
                     f"{stats.cache_entries} entries)")
    else:
        lines.append("  No cache file")
    lines.append("")

    # .nufiignore
    lines.append("[Exclusions]")
    lines.append(f"  .nufiignore patterns: {stats.nufiignore_pattern_count}")
    lines.append("")

    # Audit log
    lines.append("[Audit Log]")
    if stats.audit_log_exists:
        lines.append(f"  File: logs/egress_audit.jsonl ({stats.audit_log_lines} entries)")
        if stats.audit_log_first_ts and stats.audit_log_last_ts:
            lines.append(f"  Date range: {stats.audit_log_first_ts} ~ {stats.audit_log_last_ts}")
    else:
        lines.append("  No audit log found")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI handler
# ---------------------------------------------------------------------------

def cmd_stats(args) -> int:
    """``nufi-egress stats`` CLI handler."""
    use_json = getattr(args, "json", False)
    stats = collect_stats()

    if use_json:
        print(json.dumps(stats.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(render_human(stats))

    return 0
