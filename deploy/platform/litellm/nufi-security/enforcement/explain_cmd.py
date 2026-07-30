"""``nufi-egress explain`` -- explain WHY a text was flagged (patch116).

Useful for debugging false positives, training, and understanding detection logic.
Returns a detailed breakdown of:
- Each PII finding: entity type, matched text, position, detection method, confidence
- Each injection finding: pattern, severity, matched text
- Policy action that would apply (block/warn/pseudonymize/log)
- Routing decision (local/cloud) and reason
- Overall risk assessment

SDK usage::

    from enforcement.explain_cmd import explain_text
    result = explain_text("홍길동의 주민등록번호는 900101-1234567입니다")
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from egress_audit.pipeline import DetectionPipeline, Finding
from egress_audit.detectors.prompt_injection import (
    PromptInjectionDetector,
    Finding as InjectionFinding,
)
from gateway.pii_router import PiiRouter

# ---------------------------------------------------------------------------
# Risk computation (shared with inspect_cmd)
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
# Policy action inference
# ---------------------------------------------------------------------------

_RISK_TO_ACTION = {
    "critical": "block",
    "high": "block",
    "medium": "pseudonymize",
    "low": "log",
    "clean": "allow",
}


def _infer_action(risk: str) -> str:
    """Infer what policy action would apply given the risk level."""
    return _RISK_TO_ACTION.get(risk, "log")


# ---------------------------------------------------------------------------
# Core explain function
# ---------------------------------------------------------------------------

def explain_text(text: str, *, min_severity: str = "low") -> Dict[str, Any]:
    """Analyze text and produce a detailed explanation of detection results.

    Returns a dict with:
        text, has_findings, risk_level, action, routing, routing_reason,
        pii_findings (list of detailed dicts),
        injection_findings (list of detailed dicts),
        summary (human-readable one-liner)
    """
    # 1) PII detection
    pipeline = DetectionPipeline()
    pii_findings: List[Finding] = pipeline.analyze(text)

    # 2) Injection detection
    inj_detector = PromptInjectionDetector(min_severity=min_severity)
    inj_findings: List[InjectionFinding] = inj_detector.detect(text)

    # 3) Routing
    router = PiiRouter()
    decision = router.route(text)
    routed_local = decision.routed_to_local
    routing = "local" if routed_local else "cloud"
    routing_reason = decision.reason

    # 4) Risk
    risk = _compute_risk(pii_findings, inj_findings)

    # 5) Action
    action = _infer_action(risk)

    # 6) Build detailed findings
    pii_details: List[Dict[str, Any]] = []
    for f in pii_findings:
        pii_details.append({
            "entity_type": f.entity_type,
            "text": f.text,
            "start": f.start,
            "end": f.end,
            "detection_method": f.source,
            "confidence": round(f.score, 4),
        })

    inj_details: List[Dict[str, Any]] = []
    for f in inj_findings:
        meta = f.match_meta or {}
        inj_details.append({
            "pattern": f.entity_type,
            "matched_text": f.text,
            "start": f.start,
            "end": f.end,
            "severity": meta.get("severity", "medium"),
            "category": meta.get("category", "unknown"),
            "detection_method": f.source,
            "confidence": round(f.score, 4),
        })

    has_findings = bool(pii_details or inj_details)

    # 7) Summary
    if not has_findings:
        summary = "No findings — text is clean."
    else:
        parts = []
        if pii_details:
            types = sorted({d["entity_type"] for d in pii_details})
            parts.append(f"{len(pii_details)} PII ({', '.join(types)})")
        if inj_details:
            parts.append(f"{len(inj_details)} injection")
        summary = (f"Found {' + '.join(parts)}. "
                   f"Risk={risk}, action={action}, routing={routing}.")

    return {
        "text": text,
        "has_findings": has_findings,
        "risk_level": risk,
        "action": action,
        "routing": routing,
        "routing_reason": routing_reason,
        "pii_findings": pii_details,
        "injection_findings": inj_details,
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# Human-readable renderer
# ---------------------------------------------------------------------------

def render_human(result: Dict[str, Any]) -> str:
    """Render explain result in a detailed, educational human-readable format."""
    lines: List[str] = []
    text_display = result["text"]
    if len(text_display) > 80:
        text_display = text_display[:77] + "..."

    lines.append("=" * 60)
    lines.append("NuFi Explain — Detection Breakdown")
    lines.append("=" * 60)
    lines.append(f"Input: {text_display}")
    lines.append("")

    # --- PII Findings ---
    lines.append("[ PII Findings ]")
    if result["pii_findings"]:
        for i, f in enumerate(result["pii_findings"], 1):
            lines.append(f"  #{i} {f['entity_type']}")
            lines.append(f"     Matched text : {f['text']}")
            lines.append(f"     Position     : {f['start']}:{f['end']}")
            lines.append(f"     Method       : {f['detection_method']}")
            lines.append(f"     Confidence   : {f['confidence']}")
    else:
        lines.append("  (none)")
    lines.append("")

    # --- Injection Findings ---
    lines.append("[ Injection Analysis ]")
    if result["injection_findings"]:
        for i, f in enumerate(result["injection_findings"], 1):
            lines.append(f"  #{i} {f['pattern']}")
            lines.append(f"     Matched text : {f['matched_text']}")
            lines.append(f"     Severity     : {f['severity']}")
            lines.append(f"     Category     : {f['category']}")
            lines.append(f"     Position     : {f['start']}:{f['end']}")
            lines.append(f"     Method       : {f['detection_method']}")
            lines.append(f"     Confidence   : {f['confidence']}")
    else:
        lines.append("  (none)")
    lines.append("")

    # --- Policy / Routing ---
    lines.append("[ Policy Decision ]")
    lines.append(f"  Risk level : {result['risk_level']}")
    lines.append(f"  Action     : {result['action']}")
    lines.append("")

    lines.append("[ Routing Decision ]")
    lines.append(f"  Target     : {result['routing']}")
    lines.append(f"  Reason     : {result['routing_reason']}")
    lines.append("")

    # --- Summary ---
    lines.append("-" * 60)
    lines.append(f"Summary: {result['summary']}")
    lines.append("-" * 60)

    return "\n".join(lines)
