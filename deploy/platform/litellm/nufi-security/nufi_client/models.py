"""SDK 응답 모델 + 예외 (CMP-119).

게이트웨이의 OpenAI 호환 응답 dict 를 속성 접근 객체로 감싼다.
`resp.choices[0].message.content` 형태로 OpenAI SDK 와 동일하게 읽힌다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


class NuFiBlocked(Exception):
    """민감정보 탐지로 게이트웨이가 송신을 차단(403)했을 때 발생.

    감사 로그에는 차단 1건이 적재된다(`audit_id`). 호출측은 엔티티/사유를
    `entities`/`reason` 으로 확인할 수 있다.
    """

    def __init__(self, *, entities: List[str], reason: str,
                 audit_id: Optional[str] = None, decision: Optional[dict] = None,
                 body: Optional[dict] = None):
        self.entities = entities
        self.reason = reason
        self.audit_id = audit_id
        self.decision = decision or {}
        self.body = body or {}
        ents = ", ".join(entities) if entities else "?"
        super().__init__(f"NuFi blocked egress (entities: {ents}) — {reason}")


@dataclass
class Message:
    role: str
    content: str


@dataclass
class Choice:
    index: int
    message: Message
    finish_reason: Optional[str]


@dataclass
class ChatCompletion:
    id: str
    model: str
    choices: List[Choice]
    usage: Dict[str, Any] = field(default_factory=dict)
    audit_id: Optional[str] = None      # 감사 레코드 id (in-process transport 한정)
    outcome: Optional[str] = None       # forwarded | transformed | private
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_body(cls, body: Dict[str, Any], *, audit_id: Optional[str] = None,
                  outcome: Optional[str] = None) -> "ChatCompletion":
        choices = []
        for c in body.get("choices", []):
            m = c.get("message", {}) or {}
            choices.append(Choice(
                index=c.get("index", 0),
                message=Message(role=m.get("role", "assistant"),
                                content=m.get("content", "")),
                finish_reason=c.get("finish_reason")))
        return cls(id=body.get("id", ""), model=body.get("model", ""),
                   choices=choices, usage=body.get("usage", {}) or {},
                   audit_id=audit_id, outcome=outcome, raw=body)


@dataclass
class Delta:
    role: Optional[str]
    content: Optional[str]


@dataclass
class ChunkChoice:
    index: int
    delta: Delta
    finish_reason: Optional[str]


@dataclass
class ChatCompletionChunk:
    id: str
    model: str
    choices: List[ChunkChoice]
