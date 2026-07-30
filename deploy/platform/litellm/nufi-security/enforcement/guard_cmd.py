"""``nufi-egress guard`` -- scan + policy + pseudonymize one-step CI gate (v0.7.1).

PII scan -> policy evaluation (block/warn/pseudonymize) -> action in one command.

Exit codes:
  0: no PII found, or pseudonymize completed successfully
  1: PII found + block policy (or --ci mode)
  2: PII found + warn policy

--ci mode (v0.7.5):
  Runs git-diff-based scan, outputs GitHub Actions / GitLab CI annotations.
  Exit 0 if clean, exit 1 if PII found.
"""
from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path
from typing import Optional

from egress_audit.pipeline import DetectionPipeline, Finding
from egress_audit.reversible import ReversibleEgress


def cmd_guard(args) -> int:
    """``nufi-egress guard`` CLI handler."""
    # --ci mode (v0.7.5): CI pipeline integration
    if getattr(args, "ci", False):
        return _cmd_guard_ci(args)

    target: Optional[str] = getattr(args, "target", None)
    policy: str = getattr(args, "policy_action_guard", "warn")
    fmt: str = getattr(args, "format", "text") or "text"
    output_path: Optional[str] = getattr(args, "output", None)
    strict: bool = getattr(args, "strict", False)

    # --strict promotes warn -> block
    if strict and policy == "warn":
        policy = "block"

    # Read input text
    text = _read_input(target)
    if text is None:
        print("Error: please specify a file path or pipe via stdin.",
              file=sys.stderr)
        return 1

    # Step 1: PII scan
    pipeline = DetectionPipeline()
    findings = pipeline.analyze(text)
    pii_findings = [f for f in findings if not f.entity_type.startswith("INJECTION:")]

    # No PII found -> clean exit
    if not pii_findings:
        _output_result(fmt, output_path, {
            "status": "clean",
            "policy": policy,
            "pii_found": False,
            "findings": [],
            "text": text,
        })
        return 0

    # Step 2: Apply policy action
    if policy == "block":
        _output_result(fmt, output_path, {
            "status": "blocked",
            "policy": "block",
            "pii_found": True,
            "findings": [_finding_dict(f) for f in pii_findings],
        })
        return 1

    if policy == "pseudonymize":
        rev = ReversibleEgress(ner_backend="gazetteer")
        sid = f"guard-{uuid.uuid4().hex[:12]}"
        result = rev.pseudonymize(text, sid)
        transformed = result.transformed_text
        if output_path:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(output_path).write_text(transformed + "\n", encoding="utf-8")
            print(f"[guard] pseudonymized output: {output_path}", file=sys.stderr)
        _output_result(fmt, output_path if not output_path else None, {
            "status": "pseudonymized",
            "policy": "pseudonymize",
            "pii_found": True,
            "session_id": sid,
            "pseudonymized_count": result.pseudonymized,
            "findings": [_finding_dict(f) for f in pii_findings],
            "text": transformed,
        })
        return 0

    # policy == "warn"
    _output_result(fmt, output_path, {
        "status": "warn",
        "policy": "warn",
        "pii_found": True,
        "findings": [_finding_dict(f) for f in pii_findings],
    })
    return 2


# ---------------------------------------------------------------------------
# --ci mode (v0.7.5)
# ---------------------------------------------------------------------------

def _cmd_guard_ci(args) -> int:
    """CI pipeline mode: scan git diff, emit annotations, exit 0/1."""
    from enforcement.scan_cmd import scan_diff

    diff_ref = getattr(args, "diff_ref", None) or "HEAD"
    check_injection = getattr(args, "check_injection", False)

    result = scan_diff(
        ref=diff_ref,
        check_injection=check_injection,
    )

    pii_findings = [
        f for f in result.findings if f.finding_type.startswith("PII:")
    ]

    if not pii_findings:
        print(f"nufi guard: OK — {result.files_scanned} files scanned, no PII detected.")
        return 0

    # Emit GitHub Actions annotation format
    for f in pii_findings:
        entity = f.finding_type.split(":", 1)[1] if ":" in f.finding_type else f.finding_type
        print(f"::error file={f.file},line={f.line}::PII detected: {entity}")

    print(f"\nnufi guard: FAIL — {len(pii_findings)} PII finding(s) "
          f"in {result.files_with_findings} file(s).",
          file=sys.stderr)
    return 1


def _read_input(target: Optional[str]) -> Optional[str]:
    """Read text from file path or stdin."""
    if target:
        p = Path(target)
        if not p.exists():
            print(f"Error: file not found: {target}", file=sys.stderr)
            return None
        return p.read_text(encoding="utf-8")
    # Try stdin
    if not sys.stdin.isatty():
        return sys.stdin.read()
    return None


def _finding_dict(f: Finding) -> dict:
    return {
        "entity_type": f.entity_type,
        "text": f.text,
        "start": f.start,
        "end": f.end,
        "score": f.score,
    }


def _output_result(fmt: str, output_path: Optional[str], data: dict) -> None:
    """Print result in the requested format."""
    if fmt == "json":
        out = json.dumps(data, ensure_ascii=False, indent=2)
    else:
        # Human-readable text output
        status = data["status"]
        findings = data.get("findings", [])
        lines = [f"[guard] status={status}  policy={data['policy']}"]
        if findings:
            lines.append(f"  PII findings: {len(findings)}")
            for f in findings:
                lines.append(f"    - {f['entity_type']}: {f['text']!r} "
                             f"(score={f['score']:.2f})")
        if "session_id" in data:
            lines.append(f"  session_id: {data['session_id']}")
        text = data.get("text")
        if text is not None and status == "pseudonymized":
            lines.append(f"  pseudonymized text:")
            for tl in text.splitlines()[:10]:
                lines.append(f"    {tl}")
            if len(text.splitlines()) > 10:
                lines.append("    ...")
        out = "\n".join(lines)

    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(out + "\n", encoding="utf-8")
    else:
        print(out)
