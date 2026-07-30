"""EgressGuard: 탐지 파이프라인 + 정책 엔진을 묶은 pre_call 진입점.

게이트웨이(LiteLLM 훅 / FastAPI 앱)가 public 송신 직전 호출한다.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional

from .pipeline import DetectionPipeline, Finding
from .policy import PolicyEngine, Decision
from .detectors.prompt_injection import PromptInjectionDetector

_logger = logging.getLogger(__name__)

_SEVERITY_RANK = {"low": 1, "medium": 2, "high": 3, "critical": 4}


@dataclass
class GuardResult:
    blocked: bool
    decision: Decision
    findings: List[Finding]

    @property
    def transformed_text(self) -> str:
        return self.decision.transformed_text

    @property
    def summary(self) -> dict:
        return self.decision.summary


class EgressGuard:
    def __init__(self, pipeline: Optional[DetectionPipeline] = None,
                 policy: Optional[PolicyEngine] = None,
                 check_injection: bool = False,
                 **pipeline_kwargs):
        self.pipeline = pipeline or DetectionPipeline(**pipeline_kwargs)
        self.policy = policy or PolicyEngine()
        self.check_injection = check_injection
        self._injection_detector: Optional[PromptInjectionDetector] = None
        if check_injection:
            self._injection_detector = PromptInjectionDetector()

    @property
    def ner_backend(self) -> str:
        return self.pipeline.ner_backend

    @property
    def ner_pool_config(self):
        return self.pipeline.ner_pool_config

    def _injection_policy(self) -> dict:
        """Return injection policy from policy.yaml (defaults: action=block, min_severity=medium)."""
        cfg = self.policy.cfg.get("injection", {})
        return {
            "action": cfg.get("action", "block"),
            "min_severity": cfg.get("min_severity", "medium"),
        }

    def inspect(self, text: str) -> GuardResult:
        findings = self.pipeline.analyze(text)
        decision = self.policy.apply(text, findings)

        # Prompt injection detection (patch61, policy-driven patch73)
        if self.check_injection and self._injection_detector:
            injection_findings = self._injection_detector.detect(text)
            if injection_findings:
                inj_policy = self._injection_policy()
                action = inj_policy["action"]
                min_sev = inj_policy["min_severity"]
                min_rank = _SEVERITY_RANK.get(min_sev, 2)

                # Filter by min_severity threshold
                def _finding_severity(f):
                    meta = getattr(f, "match_meta", None) or {}
                    return meta.get("severity", "medium")

                qualified = [
                    ijf for ijf in injection_findings
                    if _SEVERITY_RANK.get(_finding_severity(ijf), 2) >= min_rank
                ]

                if qualified:
                    if action == "log":
                        # Log only — don't add to findings, don't block
                        _logger.warning(
                            "injection detected (policy=log): %d pattern(s)",
                            len(qualified),
                        )
                    elif action == "warn":
                        # Add to findings but don't block
                        for ijf in qualified:
                            pf = Finding(
                                entity_type=ijf.entity_type,
                                text=ijf.text,
                                start=ijf.start,
                                end=ijf.end,
                                score=ijf.score,
                                source=ijf.source,
                            )
                            findings.append(pf)
                        decision.actions.append({
                            "action": "warn_injection",
                            "entity_type": "PROMPT_INJECTION",
                            "reason": "prompt injection detected (warn)",
                        })
                    else:
                        # block (default)
                        for ijf in qualified:
                            pf = Finding(
                                entity_type=ijf.entity_type,
                                text=ijf.text,
                                start=ijf.start,
                                end=ijf.end,
                                score=ijf.score,
                                source=ijf.source,
                            )
                            findings.append(pf)
                        decision.blocked = True
                        decision.actions.append({
                            "action": "block_injection",
                            "entity_type": "PROMPT_INJECTION",
                            "reason": "prompt injection detected",
                        })

        return GuardResult(blocked=decision.blocked, decision=decision, findings=findings)

    # ------------------------------------------------------------------
    # Context manager support (patch172)
    # ------------------------------------------------------------------

    def __enter__(self) -> "EgressGuard":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:  # noqa: ANN001
        return None
