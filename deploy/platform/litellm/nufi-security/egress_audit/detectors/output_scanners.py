"""출력측(Output-side) 보안 탐지기 — LLM 응답 본문 검사.

세 가지 탐지기를 제공한다:
- SystemPromptLeakDetector: 시스템 프롬프트 유출 패턴 탐지
- OutputPiiDetector: 응답 내 PII 재노출 탐지 (기존 파이프라인 재사용)
- HarmfulContentDetector: 유해 콘텐츠 기초 필터링
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

from ..pipeline import Finding


# ---------------------------------------------------------------------------
# 1) 시스템 프롬프트 유출 탐지
# ---------------------------------------------------------------------------

# (pattern, score, severity, description)
_SYSTEM_PROMPT_LEAK_PATTERNS: list[tuple[str, float, str, str]] = [
    # 직접 유출 — 시스템 프롬프트 텍스트를 그대로 출력
    (r"(?:my|the)\s+system\s+prompt\s+(?:is|says|reads|states)\s*[:\"]",
     0.9, "critical", "direct_system_prompt_disclosure"),
    (r"시스템\s*프롬프트[는가을를]\s*(?:다음과\s*같|이렇|알려)",
     0.9, "critical", "direct_system_prompt_disclosure_ko"),
    (r"(?:here\s+is|below\s+is|this\s+is)\s+(?:my|the)\s+system\s+(?:prompt|instruction)",
     0.9, "critical", "system_instruction_disclosure"),

    # 역할/지시 유출 — 내부 역할 설명 노출
    (r"(?:i\s+(?:was|am)\s+(?:instructed|told|programmed|designed)\s+to)\s+.{20,}",
     0.8, "high", "instruction_leak"),
    (r"(?:나는|저는)\s+.{5,}(?:하도록|하라고)\s+(?:지시|프로그래밍|설정|설계)\s*(?:받았|되었|됐)",
     0.8, "high", "instruction_leak_ko"),
    (r"(?:my|the)\s+(?:instructions?|rules?|guidelines?)\s+(?:are|say|state|include)\s*:",
     0.8, "high", "rules_disclosure"),
    (r"(?:나의|제)\s+(?:지시|규칙|가이드라인|지침)[은는이가]\s*:",
     0.8, "high", "rules_disclosure_ko"),

    # 구분자/프레임 유출 — 프롬프트 구분자가 응답에 노출
    (r"\[system\]",
     0.7, "medium", "system_tag_leak"),
    (r"<\|?system\|?>",
     0.7, "medium", "system_marker_leak"),
    (r"###\s*System\s*(?:Prompt|Message|Instruction)\s*:",
     0.7, "medium", "system_header_leak"),

    # 내부 도구/함수 유출
    (r"(?:internal|hidden)\s+(?:tool|function|api)\s*:",
     0.7, "medium", "internal_tool_leak"),
    (r"(?:내부|숨겨진|비공개)\s+(?:도구|함수|API)\s*:",
     0.7, "medium", "internal_tool_leak_ko"),
]

_COMPILED_LEAK_PATTERNS = [
    (re.compile(p, re.IGNORECASE), score, sev, desc)
    for p, score, sev, desc in _SYSTEM_PROMPT_LEAK_PATTERNS
]


class SystemPromptLeakDetector:
    """LLM 응답에서 시스템 프롬프트 유출 패턴을 탐지한다."""

    def detect(self, text: str) -> List[Finding]:
        if not text:
            return []
        findings: List[Finding] = []
        seen_spans: set[tuple[int, int]] = set()
        for pattern, score, severity, desc in _COMPILED_LEAK_PATTERNS:
            for m in pattern.finditer(text):
                span = (m.start(), m.end())
                if span in seen_spans:
                    continue
                seen_spans.add(span)
                findings.append(Finding(
                    entity_type="SYSTEM_PROMPT_LEAK",
                    text=m.group(0),
                    start=m.start(),
                    end=m.end(),
                    score=score,
                    source="output_scanner",
                    match_meta={"severity": severity, "pattern": desc},
                ))
        return findings


# ---------------------------------------------------------------------------
# 2) 유해 콘텐츠 기초 필터링
# ---------------------------------------------------------------------------

# (pattern, score, severity, category)
_HARMFUL_CONTENT_PATTERNS: list[tuple[str, float, str, str]] = [
    # 위험 행위 지침 — 무기/폭발물/마약 제조
    (r"(?:how\s+to\s+(?:make|build|create|synthesize)\s+(?:a\s+)?(?:bomb|explosive|weapon|drug|meth|poison))",
     0.9, "critical", "dangerous_instructions"),
    (r"(?:폭탄|폭발물|무기|마약|독극물)[을를]?\s*(?:만드는|제조\S*|합성\S*|조립\S*)\s*(?:방법|법|과정)",
     0.9, "critical", "dangerous_instructions_ko"),

    # 자해/자살 조장
    (r"(?:how\s+to\s+(?:kill|harm)\s+(?:yourself|oneself))",
     0.9, "critical", "self_harm"),
    (r"(?:자살|자해)\s*(?:방법|하는\s*법)",
     0.9, "critical", "self_harm_ko"),

    # 불법 해킹 지침
    (r"(?:how\s+to\s+hack\s+(?:into|someone|a\s+bank|password))",
     0.8, "high", "illegal_hacking"),
    (r"(?:해킹|크래킹)\s*(?:방법|하는\s*법|절차)",
     0.8, "high", "illegal_hacking_ko"),

    # 개인정보 악용 조장
    (r"(?:how\s+to\s+(?:stalk|dox|doxx)\s+(?:someone|a\s+person))",
     0.8, "high", "privacy_violation"),
    (r"(?:스토킹|신상\s*털기)\s*(?:방법|하는\s*법)",
     0.8, "high", "privacy_violation_ko"),

    # 사기/피싱 지원
    (r"(?:(?:phishing|scam)\s+(?:email|message|template))",
     0.7, "medium", "fraud_assistance"),
    (r"(?:피싱|사기)\s*(?:메일|문자|메시지|템플릿)",
     0.7, "medium", "fraud_assistance_ko"),
]

_COMPILED_HARMFUL_PATTERNS = [
    (re.compile(p, re.IGNORECASE), score, sev, cat)
    for p, score, sev, cat in _HARMFUL_CONTENT_PATTERNS
]


class HarmfulContentDetector:
    """LLM 응답에서 유해 콘텐츠 패턴을 탐지한다.

    Args:
        min_severity: 최소 심각도 필터. 기본값 "medium".
    """

    _SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}

    def __init__(self, min_severity: str = "medium"):
        self.min_severity = min_severity

    def detect(self, text: str) -> List[Finding]:
        if not text:
            return []
        min_rank = self._SEVERITY_ORDER.get(self.min_severity, 1)
        findings: List[Finding] = []
        seen_spans: set[tuple[int, int]] = set()
        for pattern, score, severity, category in _COMPILED_HARMFUL_PATTERNS:
            if self._SEVERITY_ORDER.get(severity, 0) < min_rank:
                continue
            for m in pattern.finditer(text):
                span = (m.start(), m.end())
                if span in seen_spans:
                    continue
                seen_spans.add(span)
                findings.append(Finding(
                    entity_type="HARMFUL_CONTENT",
                    text=m.group(0),
                    start=m.start(),
                    end=m.end(),
                    score=score,
                    source="output_scanner",
                    match_meta={"severity": severity, "category": category},
                ))
        return findings
