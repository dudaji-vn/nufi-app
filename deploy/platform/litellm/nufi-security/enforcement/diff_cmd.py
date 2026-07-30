"""``nufi-egress diff`` -- scan only git-changed files (patch104).

CI/pre-commit 에서 전체 디렉터리 대신 git 변경 파일만 빠르게 스캔.
``scan_git_diff(base)`` 로 SDK 사용도 가능.
"""
from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from enforcement.scan_cmd import (
    ScanFinding,
    ScanResult,
    _is_binary,
    _scan_file,
)
from egress_audit.pipeline import DetectionPipeline
from egress_audit.detectors.prompt_injection import PromptInjectionDetector


# ---------------------------------------------------------------------------
# Core: get changed files from git
# ---------------------------------------------------------------------------

def _git_changed_files(base: str = "HEAD", repo: Optional[str] = None) -> List[str]:
    """Return list of changed file paths relative to *base* using git diff.

    If *base* is ``"HEAD"`` the diff covers uncommitted (staged + unstaged)
    changes.  Otherwise it covers ``base...HEAD`` (merge-base range).
    """
    cmd = ["git", "diff", "--name-only", "--diff-filter=ACMR"]
    if base == "HEAD":
        # uncommitted changes: staged + unstaged
        cmd.append("HEAD")
    else:
        cmd.append(f"{base}...HEAD")

    kwargs: Dict[str, Any] = {"capture_output": True, "text": True}
    if repo:
        kwargs["cwd"] = repo
    try:
        proc = subprocess.run(cmd, **kwargs)  # noqa: S603
    except FileNotFoundError:
        return []

    if proc.returncode != 0:
        # Fallback: for repos with no commits yet, diff against empty tree
        if base == "HEAD":
            cmd2 = ["git", "diff", "--name-only", "--cached"]
            kwargs2 = dict(kwargs)
            proc2 = subprocess.run(cmd2, **kwargs2)  # noqa: S603
            if proc2.returncode == 0:
                return [l for l in proc2.stdout.strip().splitlines() if l.strip()]
        return []

    return [l for l in proc.stdout.strip().splitlines() if l.strip()]


# ---------------------------------------------------------------------------
# Scan only changed files
# ---------------------------------------------------------------------------

def scan_git_diff(
    base: str = "HEAD",
    *,
    repo: Optional[str] = None,
    check_injection: bool = False,
) -> ScanResult:
    """Scan only files changed relative to *base* for PII/injection.

    Args:
        base: Git ref to diff against (default ``"HEAD"`` = uncommitted changes).
        repo: Path to the git repository root (default: current directory).
        check_injection: Also check for prompt injection patterns.

    Returns:
        ScanResult aggregating all findings in changed files.
    """
    changed = _git_changed_files(base, repo=repo)
    result = ScanResult()

    if not changed:
        return result

    repo_root = Path(repo) if repo else Path(".")
    pipeline = DetectionPipeline()
    injection_detector = PromptInjectionDetector() if check_injection else None

    for rel in changed:
        fpath = repo_root / rel
        if not fpath.is_file():
            continue
        if _is_binary(fpath):
            continue
        _scan_file(fpath, pipeline, injection_detector, result, patterns=None)

    return result


# ---------------------------------------------------------------------------
# CLI handler
# ---------------------------------------------------------------------------

def cmd_diff(args) -> int:
    """``nufi-egress diff`` CLI handler."""
    base = getattr(args, "base", "HEAD") or "HEAD"
    check_injection = getattr(args, "check_injection", False)
    use_json = getattr(args, "json", False)
    fail_on_pii = getattr(args, "fail_on_pii", False)
    do_pseudonymize = getattr(args, "pseudonymize", False)

    result = scan_git_diff(
        base=base,
        check_injection=check_injection,
    )

    # --pseudonymize: pseudonymize files with PII findings (v0.6.1)
    pseudonymized_texts: dict = {}
    if do_pseudonymize and result.findings:
        import uuid as _uuid
        from egress_audit.reversible import ReversibleEgress
        _rev = ReversibleEgress(ner_backend="gazetteer")
        _psid = f"diff-{_uuid.uuid4().hex[:12]}"
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

    if use_json:
        out = result.to_dict()
        if do_pseudonymize and pseudonymized_texts:
            out["pseudonymized"] = {
                fp: pt for fp, pt in pseudonymized_texts.items()
            }
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        if not result.findings:
            print(f"Diff scan ({base}): {result.files_scanned} changed files scanned, "
                  "no findings.")
        else:
            print(f"Diff scan ({base}): {result.files_scanned} changed files scanned, "
                  f"{result.files_with_findings} with findings, "
                  f"{len(result.findings)} total findings.")
            print()
            current_file = None
            for f in result.findings:
                if f.file != current_file:
                    current_file = f.file
                    print(f"  {f.file}")
                print(f"    L{f.line}: [{f.finding_type}] {f.text}")

        # Show pseudonymized text after normal output
        if do_pseudonymize and pseudonymized_texts:
            print()
            print("── 가명화 결과 (Pseudonymized) ──")
            for fpath, ptext in pseudonymized_texts.items():
                print(f"\n  {fpath}:")
                for line in ptext.splitlines():
                    print(f"    {line}")

    if fail_on_pii and result.has_pii:
        return 1
    return 0
