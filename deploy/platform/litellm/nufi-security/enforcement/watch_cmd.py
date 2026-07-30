"""``nufi-egress watch`` — continuous file watcher for PII detection (patch92).

Watches a directory for file changes (create/modify) using mtime polling.
When PII is detected in a changed file, prints an alert to stdout.

No external dependencies — uses os.stat mtime tracking with configurable interval.
--webhook URL posts JSON payloads on PII detection (patch102).
"""
from __future__ import annotations

import fnmatch
import json
import logging
import os
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from enforcement.scan_cmd import (
    ScanResult,
    load_nufiignore,
    _is_binary,
    _is_excluded,
    _matches_patterns,
    _scan_file,
)
from egress_audit.pipeline import DetectionPipeline
from egress_audit.detectors.prompt_injection import PromptInjectionDetector


def _collect_files(
    directory: Path,
    patterns: Optional[List[str]],
    exclude_patterns: List[str],
) -> List[Path]:
    """Collect all matching files in directory."""
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


def _get_mtime(path: Path) -> Optional[float]:
    """Get file mtime, returning None if file doesn't exist."""
    try:
        return os.stat(path).st_mtime
    except OSError:
        return None


def _scan_single_file(
    path: Path,
    pipeline: DetectionPipeline,
    injection_detector: Optional[PromptInjectionDetector],
) -> ScanResult:
    """Scan a single file and return its result."""
    result = ScanResult()
    _scan_file(path, pipeline, injection_detector, result, patterns=None)
    return result


def _print_alert(path: Path, result: ScanResult) -> None:
    """Print alert for findings in a file."""
    for f in result.findings:
        print(f"[ALERT] {path}: L{f.line} [{f.finding_type}] {f.text}")


logger = logging.getLogger(__name__)


def _post_webhook(url: str, path: Path, result: ScanResult) -> None:
    """POST a JSON payload to the webhook URL (non-blocking on failure)."""
    payload = {
        "event": "pii_detected",
        "file": str(path),
        "findings": [
            {
                "line": f.line,
                "finding_type": f.finding_type,
                "text": f.text,
            }
            for f in result.findings
        ],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=10)
    except (urllib.error.URLError, OSError) as e:
        logger.warning("Webhook POST to %s failed: %s", url, e)


def watch_directory(
    directory: str | Path,
    *,
    interval: float = 5.0,
    check_injection: bool = False,
    patterns: Optional[List[str]] = None,
    once: bool = False,
    webhook: Optional[str] = None,
) -> int:
    """Watch a directory for file changes and alert on PII detection.

    Args:
        directory: Path to directory to watch.
        interval: Polling interval in seconds.
        check_injection: Also check for prompt injection patterns.
        patterns: Glob patterns to filter files (e.g. ["*.py", "*.md"]).
        once: Scan all matching files once and exit.
        webhook: URL to POST JSON payload on PII detection.

    Returns:
        Exit code: 1 if PII found (in --once mode), 0 otherwise.
    """
    directory = Path(directory)
    if not directory.is_dir():
        print(f"Error: {directory} is not a directory")
        return 2

    # Load .nufiignore
    exclude_patterns = load_nufiignore(directory)

    # Initialize detectors
    pipeline = DetectionPipeline()
    injection_detector = PromptInjectionDetector() if check_injection else None

    # --once mode: scan all files once and exit
    if once:
        return _scan_once(directory, pipeline, injection_detector, patterns, exclude_patterns, webhook=webhook)

    # Continuous watch mode
    mtime_cache: Dict[str, float] = {}

    # Initial scan to populate mtime cache
    files = _collect_files(directory, patterns, exclude_patterns)
    for f in files:
        mt = _get_mtime(f)
        if mt is not None:
            mtime_cache[str(f)] = mt

    print(f"[watch] Monitoring {directory} (interval={interval}s, "
          f"{len(mtime_cache)} files tracked)")

    try:
        while True:
            time.sleep(interval)
            files = _collect_files(directory, patterns, exclude_patterns)
            for f in files:
                mt = _get_mtime(f)
                if mt is None:
                    continue
                fkey = str(f)
                prev_mt = mtime_cache.get(fkey)
                if prev_mt is None or mt > prev_mt:
                    # New or modified file — scan it
                    result = _scan_single_file(f, pipeline, injection_detector)
                    if result.findings:
                        _print_alert(f, result)
                        if webhook:
                            _post_webhook(webhook, f, result)
                    mtime_cache[fkey] = mt
    except KeyboardInterrupt:
        print("\n[watch] Stopped.")
        return 0


def _scan_once(
    directory: Path,
    pipeline: DetectionPipeline,
    injection_detector: Optional[PromptInjectionDetector],
    patterns: Optional[List[str]],
    exclude_patterns: List[str],
    *,
    webhook: Optional[str] = None,
) -> int:
    """Scan all matching files once and exit."""
    files = _collect_files(directory, patterns, exclude_patterns)
    found_any = False

    for f in files:
        result = _scan_single_file(f, pipeline, injection_detector)
        if result.findings:
            _print_alert(f, result)
            if webhook:
                _post_webhook(webhook, f, result)
            found_any = True

    if not found_any:
        print(f"[watch] Scan complete: {len(files)} files checked, no findings.")

    return 1 if found_any else 0


def cmd_watch(args) -> int:
    """``nufi-egress watch`` CLI handler."""
    # Parse patterns
    patterns: Optional[List[str]] = None
    if getattr(args, "pattern", None):
        patterns = [p.strip() for p in args.pattern.split(",") if p.strip()]

    return watch_directory(
        args.directory,
        interval=args.interval,
        check_injection=getattr(args, "check_injection", False),
        patterns=patterns,
        once=getattr(args, "once", False),
        webhook=getattr(args, "webhook", None),
    )
