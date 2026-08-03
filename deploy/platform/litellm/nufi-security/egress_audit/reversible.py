"""가역 가명화 오케스트레이터 (M3): EgressGuard(탐지·차단) + MappingVault(매핑) 결합.

설계: docs/design/gateway/m3-reversible-pseudonymization-spec.md §4 / CMP-76.

게이트웨이 훅(gateway/litellm_hook.py)이 얇게 호출하는 진입점:
- pseudonymize(text, session_id): pre_call — 차단판정 + 약한PII 가역 가명화 + Vault 적재.
- deanonymize(text, session_id): post_call 비스트리밍 원복.
- stream_restorer(session_id): post_call 스트리밍 원복기(경계 버퍼).

강한 PII/비밀/기밀 차단 동작은 M2 와 동일(회귀 없음) — 본 모듈은 비차단 경로만 가역화.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Iterator, List, Optional, Tuple

from .guard import EgressGuard
from .pipeline import Finding
from .policy import Decision
from .vault import MappingVault
from . import surrogate as sg


@dataclass
class RevResult:
    blocked: bool
    transformed_text: str
    decision: Decision
    findings: List[Finding]
    vault_ref: Optional[str]      # = session_id (pre→post 컨텍스트 전달용)
    pseudonymized: int            # 가역 치환된 토큰 수

    @property
    def summary(self) -> dict:
        s = dict(self.decision.summary)
        s["reversible_pseudonymized"] = self.pseudonymized
        return s


class ReversibleEgress:
    def __init__(self, guard: Optional[EgressGuard] = None,
                 vault: Optional[MappingVault] = None,
                 ttl: Optional[float] = None,
                 reversible: Tuple[str, ...] = sg.REVERSIBLE_ENTITIES,
                 **guard_kwargs):
        self.guard = guard or EgressGuard(**guard_kwargs)
        self.vault = vault or MappingVault()
        self.ttl = ttl
        self.reversible = reversible

    def pseudonymize(self, text: str, session_id: str) -> RevResult:
        result = self.guard.inspect(text)
        if result.blocked:
            # 강한 PII/secret/기밀 → 차단(M2 경로 그대로). 가역화·Vault 적재 없음.
            return RevResult(blocked=True, transformed_text=result.transformed_text,
                             decision=result.decision, findings=result.findings,
                             vault_ref=None, pseudonymized=0)
        transformed, n = sg.pseudonymize(text, result.findings, self.vault,
                                         session_id, ttl=self.ttl,
                                         reversible=self.reversible)
        return RevResult(blocked=False, transformed_text=transformed,
                         decision=result.decision, findings=result.findings,
                         vault_ref=session_id, pseudonymized=n)

    def deanonymize(self, text: str, session_id: str) -> Tuple[str, dict]:
        return sg.deanonymize(text, self.vault, session_id)

    def stream_restorer(self, session_id: str) -> sg.StreamingDeanonymizer:
        return sg.StreamingDeanonymizer(self.vault, session_id)

    def deanonymize_stream(
        self, chunks: Iterable[str], session_id: str
    ) -> Iterator[str]:
        """스트리밍 원복 — 청크 이터러블을 받아 원복된 청크를 yield.

        청크 경계에서 surrogate 토큰이 분할되는 경우 내부 버퍼링으로 처리.
        마지막에 잔여 버퍼를 자동 flush.
        """
        restorer = self.stream_restorer(session_id)
        for chunk in chunks:
            out = restorer.feed(chunk)
            if out:
                yield out
        tail = restorer.flush()
        if tail:
            yield tail

    def end_session(self, session_id: str) -> int:
        """라운드트립/세션 종료 시 매핑 즉시 폐기(secure wipe)."""
        return self.vault.purge_session(session_id)
