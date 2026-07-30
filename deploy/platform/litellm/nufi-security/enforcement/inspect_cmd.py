"""``nufi-egress inspect`` — PII + 인젝션 + 라우팅을 통합 분석하는 편의 명령 (patch78).

SDK 에서도 ``from nufi import inspect_text`` 로 사용 가능.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from egress_audit.pipeline import DetectionPipeline, Finding
from egress_audit.detectors.prompt_injection import (
    PromptInjectionDetector,
    Finding as InjectionFinding,
)
from gateway.pii_router import PiiRouter


# ---------------------------------------------------------------------------
# 강한 PII 엔티티 목록 (critical risk 판정 기준)
# ---------------------------------------------------------------------------
_STRONG_PII = {"KR_RRN", "SECRET", "CREDIT_CARD"}

# ---------------------------------------------------------------------------
# 위험도 계산
# ---------------------------------------------------------------------------

def _compute_risk(
    pii_findings: List[Finding],
    injection_findings: List[InjectionFinding],
) -> str:
    """PII + injection 결과로부터 위험도 문자열을 반환한다."""
    # Injection severity 최댓값
    inj_max_sev: Optional[str] = None
    sev_rank = {"low": 1, "medium": 2, "high": 3, "critical": 4}
    for f in injection_findings:
        meta = f.match_meta or {}
        sev = meta.get("severity", "medium")
        if inj_max_sev is None or sev_rank.get(sev, 0) > sev_rank.get(inj_max_sev, 0):
            inj_max_sev = sev

    has_strong_pii = any(f.entity_type in _STRONG_PII for f in pii_findings)

    # critical
    if inj_max_sev == "critical" or has_strong_pii:
        return "critical"
    # high
    if inj_max_sev == "high" or len(pii_findings) >= 2:
        return "high"
    # medium
    if inj_max_sev in ("medium", "low") or (len(pii_findings) == 1 and not has_strong_pii):
        return "medium"
    # low — PII found but low risk (shouldn't normally reach here with current logic)
    if pii_findings:
        return "low"
    # clean
    return "clean"


# ---------------------------------------------------------------------------
# 통합 분석 함수 (SDK 진입점)
# ---------------------------------------------------------------------------

@dataclass
class InspectResult:
    """inspect_text 반환 결과."""
    text: str
    risk_level: str
    pii_findings: List[Dict[str, Any]] = field(default_factory=list)
    injection_findings: List[Dict[str, Any]] = field(default_factory=list)
    routing: str = "cloud"
    blocked: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "risk_level": self.risk_level,
            "pii_findings": self.pii_findings,
            "injection_findings": self.injection_findings,
            "routing": self.routing,
            "blocked": self.blocked,
        }


def inspect_text(text: str, *, min_severity: str = "low") -> Dict[str, Any]:
    """텍스트를 통합 분석하여 PII, 인젝션, 라우팅, 위험도를 반환한다.

    Returns:
        dict with keys: text, risk_level, pii_findings, injection_findings,
        routing, blocked
    """
    # 1) PII detection
    pipeline = DetectionPipeline()
    pii_findings = pipeline.analyze(text)

    # 2) Injection detection
    injection_detector = PromptInjectionDetector(min_severity=min_severity)
    inj_findings = injection_detector.detect(text)

    # 3) Routing decision
    router = PiiRouter()
    decision = router.route(text)
    routing = "local" if decision.routed_to_local else "cloud"

    # 4) Risk level
    risk_level = _compute_risk(pii_findings, inj_findings)

    # 5) Block recommendation: critical or high → would be blocked
    blocked = risk_level in ("critical", "high")

    return {
        "text": text,
        "risk_level": risk_level,
        "pii_findings": [
            {"entity_type": f.entity_type, "text": f.text, "start": f.start, "end": f.end}
            for f in pii_findings
        ],
        "injection_findings": [
            {
                "pattern": f.text,
                "severity": (f.match_meta or {}).get("severity", "medium"),
            }
            for f in inj_findings
        ],
        "routing": routing,
        "blocked": blocked,
    }


# ---------------------------------------------------------------------------
# CLI 출력 렌더러
# ---------------------------------------------------------------------------

_RISK_ICONS = {
    "critical": "\U0001f534 critical",
    "high": "\U0001f7e0 high",
    "medium": "\U0001f7e1 medium",
    "low": "\U0001f7e2 low",
    "clean": "\u2705 clean",
}


def render_human(result: Dict[str, Any]) -> str:
    """사람 친화 포맷으로 렌더링."""
    lines: List[str] = []
    text_display = result["text"]
    if len(text_display) > 60:
        text_display = text_display[:57] + "..."
    lines.append("\U0001f50d NuFi Security Scan")
    lines.append(f"\uc785\ub825: {text_display}")
    lines.append(f"\uc704\ud5d8\ub3c4: {_RISK_ICONS.get(result['risk_level'], result['risk_level'])}")
    lines.append("")

    # PII
    if result["pii_findings"]:
        lines.append("[PII]")
        for f in result["pii_findings"]:
            lines.append(f"  {f['entity_type']}: {f['text']} ({f['start']}:{f['end']})")
    else:
        lines.append("[PII] \uc5c6\uc74c")

    lines.append("")

    # Injection
    if result["injection_findings"]:
        lines.append("[\uc778\uc81d\uc158]")
        for f in result["injection_findings"]:
            lines.append(f"  {f['pattern']} (severity: {f['severity']})")
    else:
        lines.append("[\uc778\uc81d\uc158] \uc5c6\uc74c")

    lines.append("")

    # Routing
    if result["routing"] == "local":
        lines.append("[\ub77c\uc6b0\ud305] \U0001f512 \ub85c\uceec \ubaa8\ub378 \uac15\uc81c")
    else:
        lines.append("[\ub77c\uc6b0\ud305] \u2601\ufe0f  \ud074\ub77c\uc6b0\ub4dc \ud5c8\uc6a9")

    # Block
    if result["blocked"]:
        lines.append("[\ucc28\ub2e8] \u26d4 Guard \ucc28\ub2e8 \ub300\uc0c1")
    else:
        lines.append("[\ucc28\ub2e8] \u2705 \ud1b5\uacfc")

    return "\n".join(lines)
