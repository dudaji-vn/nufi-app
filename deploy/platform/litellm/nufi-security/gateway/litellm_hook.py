"""LiteLLM Proxy 콜백 훅 — PII 기반 하이브리드 라우팅 + 감사 로깅 (CMP-244).

config/litellm_config.yaml 의 `callbacks: gateway.litellm_hook.egress_audit_hook` 로 등록.

라우팅 흐름:
  1. async_pre_call_hook: 요청 텍스트에 PII 감지 실행
     - PII 감지 → 모델명을 로컬 모델로 치환 (강제 라우팅)
     - PII 없음 → 클라우드 모델 허용
  2. public 행 요청은 기존 egress audit 적용 (block/redact/pseudonymize)
  3. async_log_success_event / async_log_failure_event: 100% 감사 로깅 + 비용 추적

LiteLLM 미설치 환경에서도 import 가 깨지지 않도록 베이스 클래스를 지연 처리한다.
"""
from __future__ import annotations

import logging
import os
import time
import uuid
from typing import Any, Optional

from egress_audit import ReversibleEgress, AuditLogger
from egress_audit.detectors.prompt_injection import PromptInjectionDetector
from egress_audit.output_guard import OutputGuard
from gateway.router import Router
from gateway.pii_router import PiiRouter, RoutingDecision, CostRecord, load_pii_routing_config
from gateway.complexity_classifier import ComplexityClassifier, ComplexityResult
from gateway.ab_testing import ABTestManager
from gateway.cost_dashboard import CostDashboard

logger = logging.getLogger("nufi.litellm_hook")

try:
    from litellm.integrations.custom_logger import CustomLogger as _Base  # type: ignore
    from litellm.proxy._types import UserAPIKeyAuth  # type: ignore
    _HAS_LITELLM = True
except Exception:  # pragma: no cover - 미설치 환경
    class _Base:  # 최소 스텁
        pass
    UserAPIKeyAuth = object       # type: ignore
    _HAS_LITELLM = False

try:
    from fastapi import HTTPException  # type: ignore
except Exception:  # pragma: no cover
    # Minimal stub that mimics HTTPException interface for non-fastapi envs
    class HTTPException(Exception):  # type: ignore
        def __init__(self, status_code: int = 500, detail: Any = None, **kwargs):
            self.status_code = status_code
            self.detail = detail
            super().__init__(f"HTTP {status_code}: {detail}")


def _public_classes() -> set:
    r = Router()
    pub = {name for name, b in r.backends.items() if b.get("egress_class") == "public"}
    pub |= {p for p, e in r.provider_egress.items() if e == "public"}
    return pub


def _is_public(model: str, metadata: Optional[dict]) -> bool:
    if metadata and metadata.get("egress_class"):
        return metadata["egress_class"] == "public"
    model_l = (model or "").lower()
    return any(p in model_l for p in ("claude", "anthropic", "gpt", "openai",
                                      "gemini", "google", "azure"))


def _extract_text(messages) -> str:
    parts = []
    for m in messages or []:
        c = m.get("content", "")
        if isinstance(c, list):
            parts.extend(b.get("text", "") for b in c if isinstance(b, dict))
        else:
            parts.append(str(c))
    return "\n".join(parts)


def _session_id(data: dict) -> str:
    meta = data.get("metadata") or {}
    sid = meta.get("session_id") or meta.get("egress_vault_ref") or data.get("litellm_call_id")
    if not sid:
        sid = "egress-" + uuid.uuid4().hex[:16]
    return str(sid)


def _restore_response(rev: "ReversibleEgress", session_id: str, response) -> int:
    """비스트리밍 응답 content 를 원본으로 원복(in-place). 원복 건수 반환."""
    total = 0
    choices = getattr(response, "choices", None)
    if choices is None and isinstance(response, dict):
        choices = response.get("choices")
    for ch in choices or []:
        msg = getattr(ch, "message", None) or (ch.get("message") if isinstance(ch, dict) else None)
        if msg is None:
            continue
        content = getattr(msg, "content", None) or (msg.get("content") if isinstance(msg, dict) else None)
        if not isinstance(content, str) or not content:
            continue
        restored, st = rev.deanonymize(content, session_id)
        total += st["restored"] + st["fallback"]
        if isinstance(msg, dict):
            msg["content"] = restored
        else:
            setattr(msg, "content", restored)
    return total


def _chunk_text(chunk) -> Optional[str]:
    choices = getattr(chunk, "choices", None)
    if choices is None and isinstance(chunk, dict):
        choices = chunk.get("choices")
    if not choices:
        return None
    ch = choices[0]
    delta = getattr(ch, "delta", None) or (ch.get("delta") if isinstance(ch, dict) else None)
    if delta is None:
        return None
    return getattr(delta, "content", None) or (delta.get("content") if isinstance(delta, dict) else None)


def _set_chunk_text(chunk, value: str) -> None:
    ch = (getattr(chunk, "choices", None) or chunk["choices"])[0]
    delta = getattr(ch, "delta", None) or ch.get("delta")
    if isinstance(delta, dict):
        delta["content"] = value
    else:
        setattr(delta, "content", value)


class EgressAuditHook(_Base):
    def __init__(self):
        self.rev = ReversibleEgress(ner_backend=os.environ.get("EGRESS_NER_BACKEND", "auto"))
        self.audit = AuditLogger()
        self.pii_router = PiiRouter(
            local_model=os.environ.get("NUFI_LOCAL_MODEL", "nufi-local"),
            cloud_model=os.environ.get("NUFI_CLOUD_MODEL", "nufi-cloud"),
            fail_closed=os.environ.get("NUFI_FAIL_CLOSED", "1") != "0",
            config_path=os.environ.get("NUFI_PII_ROUTING_CONFIG"),
        )
        # Injection detection (patch65)
        cfg = load_pii_routing_config(os.environ.get("NUFI_PII_ROUTING_CONFIG"))
        env_flag = os.environ.get("NUFI_CHECK_INJECTION", "")
        if env_flag == "1":
            self._check_injection = True
        elif env_flag == "0":
            self._check_injection = False
        else:
            self._check_injection = bool(cfg.get("check_injection", False))
        self._injection_detector = PromptInjectionDetector() if self._check_injection else None

        # Phase 2: 복잡도 분류기 + A/B 테스트 + 비용 대시보드 (CMP-293)
        complexity_config = os.environ.get("NUFI_COMPLEXITY_CONFIG")
        self.complexity_classifier = ComplexityClassifier(config_path=complexity_config)
        self.ab_manager = ABTestManager(config_path=complexity_config)
        self.cost_dashboard = CostDashboard()

        # Output-side guardrails (CMP-294)
        env_output_guard = os.environ.get("NUFI_OUTPUT_GUARD", "1")
        self._output_guard_enabled = env_output_guard != "0"
        self._output_guard = OutputGuard() if self._output_guard_enabled else None

    def _log_routing(self, decision: RoutingDecision, data: dict) -> None:
        """라우팅 결정을 감사 로그에 기록."""
        self.audit.log(
            model=decision.target_model,
            provider="local" if decision.routed_to_local else "cloud",
            is_public=not decision.routed_to_local,
            request_body={"model": data.get("model"), "routing": decision.to_dict()},
            decision_summary=decision.to_dict(),
            findings=[{"entity_type": f.entity_type, "score": f.score}
                      for f in decision.findings],
            outcome="routed_local" if decision.routed_to_local else "routed_cloud",
        )

    async def async_pre_call_hook(self, user_api_key_dict, cache, data: dict, call_type: str):
        text = _extract_text(data.get("messages"))
        original_model = data.get("model", "")

        # --- Phase 0: 프롬프트 인젝션 탐지 (patch65) ---
        if self._check_injection and self._injection_detector:
            injection_findings = self._injection_detector.detect(text)
            if injection_findings:
                self.audit.log(
                    model=original_model,
                    provider="unknown",
                    is_public=True,
                    request_body={"model": original_model, "messages": data.get("messages")},
                    decision_summary={"injection_detected": True,
                                      "pattern_count": len(injection_findings)},
                    findings=[{"entity_type": f.entity_type, "text": f.text,
                               "score": f.score, "start": f.start, "end": f.end}
                              for f in injection_findings],
                    outcome="blocked_injection",
                )
                logger.warning("Injection detected in request (model=%s): %s",
                               original_model,
                               [f.text for f in injection_findings])
                raise HTTPException(status_code=403, detail={
                    "error": "injection_blocked",
                    "patterns": [f.text for f in injection_findings],
                })

        # --- Phase 1: PII 기반 라우팅 결정 ---
        routing = self.pii_router.route(text, requested_model=original_model)
        data.setdefault("metadata", {})
        data["metadata"]["pii_routing"] = routing.to_dict()

        if routing.routed_to_local:
            # CMP-250: 강한 PII(block 대상)가 포함되면 egress audit이 차단하도록 양보
            from egress_audit.policy import PolicyEngine
            policy = PolicyEngine()
            blocking = policy.blocking_actions
            has_blocking = any(policy.action_for(f.entity_type) in blocking
                              for f in routing.findings)
            if not has_blocking:
                # PII 감지 → 로컬 모델로 강제 치환
                data["model"] = routing.target_model
                data["metadata"]["original_model"] = original_model
                data["metadata"]["egress_outcome"] = "routed_local"
                self._log_routing(routing, data)
                logger.info("PII routing: %s → %s (reason=%s, entities=%s)",
                            original_model, routing.target_model, routing.reason,
                            [f.entity_type for f in routing.findings])
                return data

        # --- Phase 2: 복잡도 기반 모델 선택 (CMP-293) ---
        if self.complexity_classifier.enabled:
            complexity = self.complexity_classifier.classify(text, requested_model=data.get("model", ""))
            data["metadata"]["complexity"] = complexity.to_dict()

            # A/B 테스트 실험이 있으면 실험 그룹에 따라 모델 결정
            session_id = _session_id(data)
            ab_assignment = None
            for exp_id in self.ab_manager.experiments:
                assignment = self.ab_manager.assign(exp_id, session_id)
                if assignment:
                    ab_assignment = assignment
                    data["metadata"]["ab_test"] = assignment.to_dict()
                    break  # 첫 번째 활성 실험만 적용

            if ab_assignment is None:
                # A/B 테스트 없음 → 복잡도 분류기 결과 적용
                if complexity.target_model != data.get("model", ""):
                    data["model"] = complexity.target_model
                    data["metadata"]["complexity_routed"] = True
                    logger.info("Complexity routing: %s → %s (score=%.3f, label=%s)",
                                complexity.original_model, complexity.target_model,
                                complexity.score, complexity.label)

        # --- Phase 2+: 클라우드 허용 → 기존 egress audit 적용 ---
        model = data.get("model", "")
        if not _is_public(model, data.get("metadata")):
            self._log_routing(routing, data)
            return data  # private → 통과

        session_id = _session_id(data)
        result = self.rev.pseudonymize(text, session_id)

        if result.blocked:
            self.audit.log(model=model, provider="public", is_public=True,
                           request_body=data, decision_summary=result.summary,
                           findings=[f.to_dict() for f in result.findings],
                           outcome="blocked")
            raise HTTPException(status_code=403, detail={
                "error": "egress_blocked",
                "entities": [a["entity_type"] for a in result.decision.actions],
            })

        # pre→post Vault 핸들 전달(spec §4.1). 동시요청 격리는 session_id 파티션.
        data["metadata"]["egress_vault_ref"] = result.vault_ref
        if result.transformed_text != text:
            for m in reversed(data.get("messages", [])):
                if m.get("role") == "user" and isinstance(m.get("content"), str):
                    m["content"] = result.transformed_text
                    break
            data["metadata"]["egress_outcome"] = "pseudonymized"
        else:
            data["metadata"]["egress_outcome"] = "forwarded"
        data["metadata"]["_egress_result"] = result.summary
        self._log_routing(routing, data)
        return data

    async def async_post_call_success_hook(self, data: dict, user_api_key_dict, response):
        """비스트리밍 원복 + 비용 추적."""
        meta = data.get("metadata") or {}

        # 비용 추적
        model = data.get("model", "")
        usage = {}
        if isinstance(response, dict):
            usage = response.get("usage", {})
        else:
            usage_obj = getattr(response, "usage", None)
            if usage_obj:
                usage = {"prompt_tokens": getattr(usage_obj, "prompt_tokens", 0),
                         "completion_tokens": getattr(usage_obj, "completion_tokens", 0)}
        routing_info = meta.get("pii_routing", {})
        is_local = routing_info.get("routed_to_local", False)
        complexity_info = meta.get("complexity", {})
        self.pii_router.record_cost(
            model=model,
            provider="local" if is_local else "cloud",
            is_local=is_local,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            routing_reason=routing_info.get("reason", ""),
        )

        # Phase 2: 비용 대시보드 기록 (CMP-293)
        self.cost_dashboard.record(
            model=model,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            routing_reason=routing_info.get("reason", ""),
            complexity_label=complexity_info.get("label", ""),
            is_local=is_local,
        )

        # A/B 테스트 메트릭 기록
        ab_info = meta.get("ab_test")
        if ab_info:
            cost = self.pii_router.estimate_cost(
                model, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0))
            self.ab_manager.record_metric(
                experiment_id=ab_info["experiment_id"],
                variant=ab_info["variant"],
                model=model,
                cost_usd=cost,
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
            )

        # Output-side guardrails (CMP-294): LLM 응답 검사
        if self._output_guard:
            response_text = self._extract_response_text(response)
            if response_text:
                output_result = self._output_guard.inspect(response_text)
                if output_result.blocked:
                    self.audit.log(
                        model=model, provider="public" if not is_local else "local",
                        is_public=not is_local,
                        request_body={"model": model},
                        decision_summary=output_result.summary,
                        findings=[{"entity_type": f.entity_type, "score": f.score,
                                   "source": f.source} for f in output_result.findings],
                        outcome="output_blocked",
                    )
                    logger.warning("Output guard blocked response (model=%s): %s",
                                   model, output_result.summary)
                    raise HTTPException(status_code=451, detail={
                        "error": "output_blocked",
                        "reasons": [a.get("reason", a.get("action", ""))
                                    for a in output_result.actions],
                    })
                elif output_result.findings:
                    # PII redaction 등 변환이 있으면 응답에 적용
                    if output_result.transformed_text != response_text:
                        self._apply_transformed_response(response, output_result.transformed_text)

        # 기존 원복 로직
        session_id = meta.get("egress_vault_ref")
        if not session_id:
            return response
        _restore_response(self.rev, session_id, response)
        return response

    async def async_post_call_streaming_iterator_hook(self, user_api_key_dict, response, request_data):
        """스트리밍 원복: 경계 버퍼로 쪼개진 surrogate 홀드 후 완결 시 원복(spec §4.3)."""
        session_id = (request_data.get("metadata") or {}).get("egress_vault_ref")
        if not session_id:
            async for chunk in response:
                yield chunk
            return
        restorer = self.rev.stream_restorer(session_id)
        prev = None
        async for chunk in response:
            txt = _chunk_text(chunk)
            if isinstance(txt, str) and txt:
                _set_chunk_text(chunk, restorer.feed(txt))
            if prev is not None:
                yield prev
            prev = chunk
        if prev is not None:
            tail = restorer.flush()
            if tail:
                cur = _chunk_text(prev)
                _set_chunk_text(prev, (cur or "") + tail)
            yield prev

    @staticmethod
    def _extract_response_text(response) -> Optional[str]:
        """비스트리밍 응답에서 content 텍스트 추출."""
        choices = getattr(response, "choices", None)
        if choices is None and isinstance(response, dict):
            choices = response.get("choices")
        parts = []
        for ch in choices or []:
            msg = getattr(ch, "message", None) or (ch.get("message") if isinstance(ch, dict) else None)
            if msg is None:
                continue
            content = getattr(msg, "content", None) or (msg.get("content") if isinstance(msg, dict) else None)
            if isinstance(content, str) and content:
                parts.append(content)
        return "\n".join(parts) if parts else None

    @staticmethod
    def _apply_transformed_response(response, transformed: str) -> None:
        """변환된 텍스트를 응답에 반영 (첫 번째 choice message)."""
        choices = getattr(response, "choices", None)
        if choices is None and isinstance(response, dict):
            choices = response.get("choices")
        for ch in choices or []:
            msg = getattr(ch, "message", None) or (ch.get("message") if isinstance(ch, dict) else None)
            if msg is None:
                continue
            if isinstance(msg, dict):
                msg["content"] = transformed
            else:
                setattr(msg, "content", transformed)
            break  # 첫 번째 choice만

    async def async_log_success_event(self, kwargs, response_obj, start_time, end_time):
        await self._audit_event(kwargs, "forwarded")

    async def async_log_failure_event(self, kwargs, response_obj, start_time, end_time):
        await self._audit_event(kwargs, "failed")

    async def _audit_event(self, kwargs, default_outcome):
        model = kwargs.get("model", "")
        meta = (kwargs.get("litellm_params", {}) or {}).get("metadata", {}) or {}
        if not _is_public(model, meta):
            return
        self.audit.log(model=model, provider="public", is_public=True,
                       request_body={"messages": kwargs.get("messages")},
                       decision_summary=meta.get("_egress_result", {}),
                       outcome=meta.get("egress_outcome", default_outcome))


# config 에서 참조하는 인스턴스
egress_audit_hook = EgressAuditHook()
