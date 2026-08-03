"""NuFi 얇은 클라이언트 (CMP-119).

서빙빌더가 기존 OpenAI 호출을 한 줄 바꿔 NuFi 게이트웨이 경유로 전환하는 SDK.

핵심 표면:
- `NuFi().chat.completions.create(...)` — OpenAI 호환 호출(비스트리밍/스트리밍).
- 민감정보 탐지 시 `NuFiBlocked` 예외(403) + 감사 1건 적재.
- `NuFi().pseudonymize(text)` → `RoundTrip` 핸들 — 가역 가명화 라운드트립/원복.
- `NuFi.gateway_base_url()` — 기존 `openai` 클라이언트에 그대로 꽂는 base_url 심.
"""
from __future__ import annotations

import re
import uuid
from typing import Any, Dict, Iterator, List, Optional, Tuple, Union

from .models import (ChatCompletion, ChatCompletionChunk, ChunkChoice, Delta,
                     NuFiBlocked)
from .transport import CompletionResult, HttpTransport, InProcessTransport

DEFAULT_GATEWAY = "http://localhost:4000"
# 스트리밍 청크 경계: 공백 단위로 자르되 surrogate 토큰(⟦P1⟧)은 원자 단위로 보존
# → 순진한 소비자가 청크별 restore() 해도 토큰이 쪼개지지 않는다.
_CHUNK_RE = re.compile(r"⟦[A-Z]{1,2}\d+⟧|\S+\s*|\s+")


class RoundTrip:
    """가역 가명화 라운드트립 핸들.

    `NuFi.pseudonymize(text)` 가 반환. 외부로 내보낼 가명화 텍스트(`masked`)와
    원복 컨텍스트(`session_id`)를 들고 있으며, 응답에 남은 surrogate 를 원본으로
    복원한다. 세션 매핑은 `close()`(또는 with 종료) 시 즉시 폐기된다.
    """

    def __init__(self, rev: Any, session_id: str, masked: str, *,
                 pseudonymized: int, blocked: bool):
        self._rev = rev
        self.session_id = session_id
        self.masked = masked
        self.pseudonymized = pseudonymized
        self.blocked = blocked

    def restore(self, text: str) -> str:
        """응답 텍스트의 surrogate 를 원본으로 무손실 복원."""
        restored, _stats = self._rev.deanonymize(text, self.session_id)
        return restored

    def stream_restorer(self):
        """스트리밍 응답 복원기(청크 경계 안전 버퍼)."""
        return self._rev.stream_restorer(self.session_id)

    def close(self) -> int:
        """라운드트립 종료 — 매핑 즉시 폐기(secure wipe)."""
        return self._rev.end_session(self.session_id)

    def __enter__(self) -> "RoundTrip":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


class _Completions:
    def __init__(self, client: "NuFi"):
        self._client = client

    def create(self, *, messages: List[Dict[str, Any]],
               model: Optional[str] = None, stream: bool = False,
               **extra: Any) -> Union[ChatCompletion, Iterator[ChatCompletionChunk]]:
        """OpenAI 호환 chat completion. `stream=True` 면 청크 이터레이터를 반환."""
        body: Dict[str, Any] = {"model": model or self._client.model,
                                "messages": messages}
        body.update(extra)
        result = self._client._send(body)
        self._client._raise_if_blocked(result)
        completion = ChatCompletion.from_body(
            result.body, audit_id=result.audit_id, outcome=result.outcome)
        if stream:
            return self._client._to_stream(completion)
        return completion


class _Chat:
    def __init__(self, client: "NuFi"):
        self.completions = _Completions(client)


class NuFi:
    """NuFi 얇은 클라이언트.

    base_url 없이 만들면 같은 프로세스의 게이트웨이를 직접 호출(서버 불필요).
    base_url 을 주면 실행 중인 게이트웨이로 HTTP 전송한다.
    """

    def __init__(self, base_url: Optional[str] = None, *, gateway: Any = None,
                 audit_log: Optional[str] = None, model: str = "gpt-4o-mini",
                 reversible: Any = None):
        if base_url:
            self._transport = HttpTransport(base_url)
        else:
            self._transport = InProcessTransport(gateway=gateway, audit_log=audit_log)
        self.model = model
        self._rev = reversible            # 지연 생성(ReversibleEgress)
        self.chat = _Chat(self)

    # ----- OpenAI base_url 심 ----------------------------------------------
    @staticmethod
    def gateway_base_url(host: str = DEFAULT_GATEWAY) -> str:
        """기존 `openai.OpenAI(base_url=...)` 에 그대로 꽂는 게이트웨이 base_url.

        예) client = OpenAI(base_url=NuFi.gateway_base_url(), api_key="nufi-local")
        """
        return host.rstrip("/") + "/v1"

    # ----- 전송/차단 -------------------------------------------------------
    def _send(self, body: Dict[str, Any]) -> CompletionResult:
        return self._transport.complete(body)

    @staticmethod
    def _raise_if_blocked(result: CompletionResult) -> None:
        if not result.blocked:
            return
        err = (result.body or {}).get("error", {}) or {}
        raise NuFiBlocked(
            entities=result.entities or err.get("entities", []),
            reason=err.get("message", "egress blocked"),
            audit_id=result.audit_id, decision=err.get("decision"),
            body=result.body)

    # ----- 스트리밍 어댑터 -------------------------------------------------
    @staticmethod
    def _to_stream(completion: ChatCompletion) -> Iterator[ChatCompletionChunk]:
        """단건 completion 을 OpenAI 호환 청크 스트림으로 변환.

        PoC 게이트웨이는 단건 JSON 을 반환하므로 SDK 가 클라이언트 측에서
        델타 청크로 쪼개 스트리밍 인터페이스를 제공한다(경계는 surrogate 보존).
        """
        content = completion.choices[0].message.content if completion.choices else ""
        first = True
        for piece in _CHUNK_RE.findall(content):
            if not piece:
                continue
            yield ChatCompletionChunk(
                id=completion.id, model=completion.model,
                choices=[ChunkChoice(index=0,
                                     delta=Delta(role="assistant" if first else None,
                                                 content=piece),
                                     finish_reason=None)])
            first = False
        yield ChatCompletionChunk(
            id=completion.id, model=completion.model,
            choices=[ChunkChoice(index=0, delta=Delta(role=None, content=None),
                                 finish_reason="stop")])

    # ----- 가역 가명화 라운드트립 -----------------------------------------
    def _reversible(self) -> Any:
        if self._rev is None:
            from egress_audit import ReversibleEgress
            self._rev = ReversibleEgress()
        return self._rev

    def pseudonymize(self, text: str, session_id: Optional[str] = None) -> RoundTrip:
        """텍스트의 가역 PII 를 surrogate 로 치환하고 원복 핸들을 반환.

        강한 PII/비밀/기밀은 차단 정책 그대로(핸들 `blocked=True`, 가역화 없음).
        """
        rev = self._reversible()
        sid = session_id or f"sdk-{uuid.uuid4().hex[:12]}"
        res = rev.pseudonymize(text, sid)
        return RoundTrip(rev, sid, res.transformed_text,
                         pseudonymized=res.pseudonymized, blocked=res.blocked)
