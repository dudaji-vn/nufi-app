"""``nufi-egress pipeline`` -- chained detect -> decide -> transform (patch139).

Runs the full security pipeline in one operation:
  1. Detect PII and injection
  2. Apply policy (block/warn/allow)
  3. Transform if needed (mask/redact/pseudonymize)
  4. Route decision (local/cloud)

SDK usage::

    from enforcement.pipeline_cmd import run_pipeline
    result = run_pipeline("김민수님 주민번호 900101-1234568")
"""
from __future__ import annotations

import json
import sys
from typing import Any, Dict, List, Optional, Sequence

from egress_audit.pipeline import DetectionPipeline, Finding
from egress_audit.detectors.prompt_injection import (
    PromptInjectionDetector,
    Finding as InjectionFinding,
)
from egress_audit.pseudonymize import mask as _mask_value, pseudo_token
from gateway.pii_router import PiiRouter


# ---------------------------------------------------------------------------
# Risk / block logic (shared with inspect_cmd)
# ---------------------------------------------------------------------------

_STRONG_PII = {"KR_RRN", "SECRET", "CREDIT_CARD", "KR_PASSPORT", "SSN"}
_SEV_RANK = {"low": 1, "medium": 2, "high": 3, "critical": 4}


def _max_injection_severity(findings: List[InjectionFinding]) -> Optional[str]:
    best: Optional[str] = None
    for f in findings:
        sev = (f.match_meta or {}).get("severity", "medium")
        if best is None or _SEV_RANK.get(sev, 0) > _SEV_RANK.get(best, 0):
            best = sev
    return best


def _compute_risk(pii: List[Finding], inj: List[InjectionFinding]) -> str:
    inj_max = _max_injection_severity(inj)
    has_strong = any(f.entity_type in _STRONG_PII for f in pii)
    if inj_max == "critical" or has_strong:
        return "critical"
    if inj_max == "high" or len(pii) >= 2:
        return "high"
    if inj_max in ("medium", "low") or (len(pii) == 1 and not has_strong):
        return "medium"
    if pii:
        return "low"
    return "clean"


# ---------------------------------------------------------------------------
# Transform helpers
# ---------------------------------------------------------------------------

def _apply_transform(text: str, findings: List[Finding], mode: str) -> str:
    """Apply mask/redact/pseudonymize transform to text using PII findings."""
    pii = [f for f in findings if f.entity_type not in ("PROMPT_INJECTION",)]
    if not pii:
        return text
    pii.sort(key=lambda f: f.start, reverse=True)
    result = text
    for f in pii:
        if mode == "mask":
            replacement = _mask_value(f.text)
        elif mode == "redact":
            replacement = f"[{f.entity_type}]"
        else:  # pseudonymize
            replacement = pseudo_token(f.entity_type, f.text)
        result = result[:f.start] + replacement + result[f.end:]
    return result


# ---------------------------------------------------------------------------
# All available pipeline actions
# ---------------------------------------------------------------------------

ALL_ACTIONS = ("detect", "mask", "redact", "pseudonymize", "route", "block-check")


# ---------------------------------------------------------------------------
# Core pipeline function
# ---------------------------------------------------------------------------

def run_pipeline(
    text: str,
    actions: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Run the full security pipeline on *text*.

    Args:
        text: Input text to process.
        actions: Subset of ALL_ACTIONS to run.  ``None`` means all.

    Returns:
        Structured dict with keys for each step that was executed:
        ``detect``, ``block_check``, ``transform``, ``route``, ``transformed_text``.
    """
    if actions is None:
        actions = list(ALL_ACTIONS)

    result: Dict[str, Any] = {"input": text, "actions": list(actions)}

    # ------------------------------------------------------------------
    # Step 1: Detect PII and injection (always needed by other steps)
    # ------------------------------------------------------------------
    pipeline = DetectionPipeline()
    pii_findings = pipeline.analyze(text)
    injection_detector = PromptInjectionDetector()
    inj_findings = injection_detector.detect(text)

    if "detect" in actions:
        result["detect"] = {
            "pii_count": len(pii_findings),
            "pii_findings": [
                {"entity_type": f.entity_type, "text": f.text,
                 "start": f.start, "end": f.end}
                for f in pii_findings
            ],
            "injection_count": len(inj_findings),
            "injection_findings": [
                {"pattern": f.text,
                 "severity": (f.match_meta or {}).get("severity", "medium")}
                for f in inj_findings
            ],
        }

    # ------------------------------------------------------------------
    # Step 2: Block check (policy decision)
    # ------------------------------------------------------------------
    risk_level = _compute_risk(pii_findings, inj_findings)
    blocked = risk_level in ("critical", "high")

    if "block-check" in actions:
        result["block_check"] = {
            "risk_level": risk_level,
            "blocked": blocked,
        }

    # ------------------------------------------------------------------
    # Step 3: Transform (mask / redact / pseudonymize)
    # ------------------------------------------------------------------
    transformed_text = text
    transform_mode: Optional[str] = None
    for mode in ("mask", "redact", "pseudonymize"):
        if mode in actions:
            transform_mode = mode
            break

    if transform_mode is not None:
        transformed_text = _apply_transform(text, pii_findings, transform_mode)
        result["transform"] = {
            "mode": transform_mode,
            "transformed_text": transformed_text,
        }

    # ------------------------------------------------------------------
    # Step 4: Route decision
    # ------------------------------------------------------------------
    if "route" in actions:
        router = PiiRouter()
        decision = router.route(text)
        result["route"] = {
            "target": "local" if decision.routed_to_local else "cloud",
            "target_model": decision.target_model,
            "reason": decision.reason,
            "pii_detected": decision.pii_detected,
        }

    result["transformed_text"] = transformed_text
    return result


# ---------------------------------------------------------------------------
# CLI rendering
# ---------------------------------------------------------------------------

def render_human(result: Dict[str, Any]) -> str:
    """Human-friendly rendering of pipeline result."""
    lines: List[str] = []
    lines.append("=== NuFi Pipeline ===")
    lines.append(f"입력: {result['input'][:60]}{'...' if len(result['input']) > 60 else ''}")
    lines.append(f"실행 액션: {', '.join(result['actions'])}")
    lines.append("")

    if "detect" in result:
        d = result["detect"]
        lines.append(f"[탐지] PII {d['pii_count']}건, 인젝션 {d['injection_count']}건")
        for f in d["pii_findings"]:
            lines.append(f"  PII: {f['entity_type']} \"{f['text']}\" ({f['start']}:{f['end']})")
        for f in d["injection_findings"]:
            lines.append(f"  INJ: {f['pattern']} (severity: {f['severity']})")

    if "block_check" in result:
        bc = result["block_check"]
        status = "차단" if bc["blocked"] else "통과"
        lines.append(f"[정책] 위험도={bc['risk_level']} -> {status}")

    if "transform" in result:
        t = result["transform"]
        lines.append(f"[변환] 모드={t['mode']}")
        lines.append(f"  결과: {t['transformed_text']}")

    if "route" in result:
        r = result["route"]
        icon = "로컬" if r["target"] == "local" else "클라우드"
        lines.append(f"[라우팅] {icon} ({r['target_model']})")
        lines.append(f"  사유: {r['reason']}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI handler
# ---------------------------------------------------------------------------

def cmd_pipeline(args) -> int:
    """``nufi-egress pipeline`` CLI handler."""
    text: Optional[str] = getattr(args, "text", None)
    if not text:
        print("오류: --text 를 지정해야 합니다.", file=sys.stderr)
        return 1

    # Parse actions
    actions_str: Optional[str] = getattr(args, "actions", None)
    actions: Optional[List[str]] = None
    if actions_str:
        actions = [a.strip() for a in actions_str.split(",") if a.strip()]
        invalid = [a for a in actions if a not in ALL_ACTIONS]
        if invalid:
            print(f"오류: 알 수 없는 액션: {', '.join(invalid)}", file=sys.stderr)
            print(f"사용 가능: {', '.join(ALL_ACTIONS)}", file=sys.stderr)
            return 1

    result = run_pipeline(text, actions=actions)

    if getattr(args, "json", False):
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(render_human(result))

    return 0
