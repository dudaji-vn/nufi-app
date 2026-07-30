"""OutputGuard: LLM 응답(출력측) 보안 가드레일.

입력측 EgressGuard 와 대칭 구조로, LLM 응답 본문에 대해:
1. 시스템 프롬프트 유출 탐지
2. PII 재노출 탐지 (기존 DetectionPipeline 재사용)
3. 유해 콘텐츠 기초 필터링

게이트웨이 post_call 경로에서 호출한다.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import yaml

from .pipeline import DetectionPipeline, Finding
from .policy import PolicyEngine, Decision
from .detectors.output_scanners import (
    SystemPromptLeakDetector,
    HarmfulContentDetector,
)

_logger = logging.getLogger(__name__)

_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"

_SEVERITY_RANK = {"low": 1, "medium": 2, "high": 3, "critical": 4}


@dataclass
class OutputGuardResult:
    """출력측 가드레일 검사 결과."""
    blocked: bool
    findings: List[Finding] = field(default_factory=list)
    actions: List[dict] = field(default_factory=list)
    transformed_text: str = ""

    @property
    def summary(self) -> dict:
        counts: dict = {}
        for a in self.actions:
            counts[a.get("action", "unknown")] = counts.get(a.get("action", "unknown"), 0) + 1
        return {
            "blocked": self.blocked,
            "action_counts": counts,
            "finding_count": len(self.findings),
            "finding_types": list({f.entity_type for f in self.findings}),
        }


class OutputGuard:
    """LLM 응답 본문에 대한 출력측 보안 가드레일.

    Usage::

        guard = OutputGuard()
        result = guard.inspect("LLM response text here...")
        if result.blocked:
            # 응답 차단 또는 변환된 텍스트 사용
            safe_text = result.transformed_text

        # PII 재노출 검사도 활성화
        guard = OutputGuard(check_pii=True)

        # 시스템 프롬프트 레퍼런스와 비교
        guard = OutputGuard(system_prompt="You are a helpful assistant...")
        result = guard.inspect("My system prompt is: You are a helpful assistant...")
    """

    def __init__(
        self,
        *,
        check_leak: bool = True,
        check_pii: bool = True,
        check_harmful: bool = True,
        system_prompt: Optional[str] = None,
        pipeline: Optional[DetectionPipeline] = None,
        policy_path: Optional[str] = None,
        harmful_min_severity: str = "medium",
        **pipeline_kwargs,
    ):
        """초기화.

        Args:
            check_leak: 시스템 프롬프트 유출 탐지 활성화 (기본 True).
            check_pii: 응답 내 PII 재노출 탐지 활성화 (기본 True).
            check_harmful: 유해 콘텐츠 필터링 활성화 (기본 True).
            system_prompt: 시스템 프롬프트 원문. 제공 시 유사도 기반 유출 탐지 강화.
            pipeline: PII 탐지용 DetectionPipeline. None이면 기본 생성.
            policy_path: 출력측 정책 YAML 경로. None이면 기본 policy.yaml + output_policy 섹션.
            harmful_min_severity: 유해 콘텐츠 최소 심각도 필터.
            **pipeline_kwargs: DetectionPipeline 생성 시 추가 인자.
        """
        # 탐지기 초기화
        self._check_leak = check_leak
        self._check_pii = check_pii
        self._check_harmful = check_harmful

        self._leak_detector = SystemPromptLeakDetector() if check_leak else None
        self._harmful_detector = (
            HarmfulContentDetector(min_severity=harmful_min_severity)
            if check_harmful else None
        )

        # PII 탐지는 기존 파이프라인 재사용
        if check_pii:
            if pipeline is not None:
                self._pipeline = pipeline
            else:
                # 출력측은 NER 가볍게 (gazetteer) 기본
                kw = {"ner_backend": "gazetteer"}
                kw.update(pipeline_kwargs)
                self._pipeline = DetectionPipeline(**kw)
        else:
            self._pipeline = None

        # 시스템 프롬프트 유사도 비교용
        self._system_prompt = system_prompt
        self._system_prompt_tokens: Optional[set[str]] = None
        if system_prompt:
            self._system_prompt_tokens = set(system_prompt.lower().split())

        # 출력 정책 로드
        self._output_policy = self._load_output_policy(policy_path)

    def _load_output_policy(self, policy_path: Optional[str]) -> dict:
        """출력측 정책 설정 로드."""
        path = policy_path or str(_CONFIG_DIR / "policy.yaml")
        try:
            with open(path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
        except FileNotFoundError:
            cfg = {}

        output_cfg = cfg.get("output_guard", {})
        return {
            "leak_action": output_cfg.get("leak_action", "block"),
            "leak_min_severity": output_cfg.get("leak_min_severity", "medium"),
            "pii_action": output_cfg.get("pii_action", "redact"),
            "harmful_action": output_cfg.get("harmful_action", "block"),
            "harmful_min_severity": output_cfg.get("harmful_min_severity", "medium"),
        }

    def inspect(self, text: str) -> OutputGuardResult:
        """LLM 응답 텍스트를 검사한다.

        Args:
            text: LLM 응답 본문.

        Returns:
            OutputGuardResult with blocked, findings, actions, transformed_text.
        """
        all_findings: List[Finding] = []
        actions: List[dict] = []
        blocked = False
        transformed = text

        # 1) 시스템 프롬프트 유출 탐지
        if self._leak_detector:
            leak_findings = self._leak_detector.detect(text)

            # 시스템 프롬프트 원문이 있으면 유사도 검사 추가
            if self._system_prompt and self._system_prompt_tokens:
                sim_finding = self._check_system_prompt_similarity(text)
                if sim_finding:
                    leak_findings.append(sim_finding)

            if leak_findings:
                min_rank = _SEVERITY_RANK.get(
                    self._output_policy["leak_min_severity"], 2)
                qualified = [
                    f for f in leak_findings
                    if _SEVERITY_RANK.get(
                        (f.match_meta or {}).get("severity", "medium"), 2
                    ) >= min_rank
                ]
                if qualified:
                    action = self._output_policy["leak_action"]
                    all_findings.extend(qualified)
                    actions.append({
                        "action": f"{action}_leak",
                        "entity_type": "SYSTEM_PROMPT_LEAK",
                        "count": len(qualified),
                        "reason": "system prompt leakage detected in output",
                    })
                    if action == "block":
                        blocked = True

        # 2) PII 재노출 탐지
        if self._pipeline:
            pii_findings = self._pipeline.analyze(text)
            if pii_findings:
                pii_action = self._output_policy["pii_action"]
                all_findings.extend(pii_findings)
                for f in pii_findings:
                    actions.append({
                        "action": f"{pii_action}_output_pii",
                        "entity_type": f.entity_type,
                        "severity": "high",
                        "span": [f.start, f.end],
                        "source": f.source,
                        "score": f.score,
                    })
                if pii_action == "block":
                    blocked = True
                elif pii_action == "redact":
                    transformed = self._redact_findings(transformed, pii_findings)

        # 3) 유해 콘텐츠 필터링
        if self._harmful_detector:
            harmful_findings = self._harmful_detector.detect(text)
            if harmful_findings:
                action = self._output_policy["harmful_action"]
                all_findings.extend(harmful_findings)
                actions.append({
                    "action": f"{action}_harmful",
                    "entity_type": "HARMFUL_CONTENT",
                    "count": len(harmful_findings),
                    "reason": "harmful content detected in output",
                })
                if action == "block":
                    blocked = True

        return OutputGuardResult(
            blocked=blocked,
            findings=all_findings,
            actions=actions,
            transformed_text=transformed,
        )

    def _check_system_prompt_similarity(self, text: str) -> Optional[Finding]:
        """응답 텍스트가 시스템 프롬프트와 높은 유사도를 보이면 Finding 반환."""
        if not self._system_prompt or not self._system_prompt_tokens:
            return None

        response_tokens = set(text.lower().split())
        if not response_tokens:
            return None

        # Jaccard-like overlap: 시스템 프롬프트 토큰 중 응답에 등장하는 비율
        overlap = self._system_prompt_tokens & response_tokens
        coverage = len(overlap) / len(self._system_prompt_tokens)

        # 시스템 프롬프트가 짧으면(< 10 토큰) 높은 임계값 적용
        threshold = 0.7 if len(self._system_prompt_tokens) >= 10 else 0.9

        if coverage >= threshold:
            return Finding(
                entity_type="SYSTEM_PROMPT_LEAK",
                text="[system prompt similarity detected]",
                start=0,
                end=len(text),
                score=round(coverage, 3),
                source="output_scanner",
                match_meta={
                    "severity": "critical",
                    "pattern": "system_prompt_similarity",
                    "coverage": round(coverage, 3),
                },
            )
        return None

    @staticmethod
    def _redact_findings(text: str, findings: List[Finding]) -> str:
        """PII findings 를 텍스트에서 마스킹 처리 (offset 역순)."""
        edits = []
        for f in findings:
            if f.end <= f.start:
                continue
            edits.append((f.start, f.end, f"<{f.entity_type}_REDACTED>"))
        for start, end, rep in sorted(edits, key=lambda e: -e[0]):
            text = text[:start] + rep + text[end:]
        return text

    # Context manager support
    def __enter__(self) -> "OutputGuard":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        return None
