"""NuFi thin client SDK (CMP-119).

서빙빌더가 한 줄로 NuFi 를 앞단에 끼우는 얇은 Python 클라이언트.
OpenAI 호환 `base_url` 심(게이트웨이 `/v1/chat/completions` 재사용) +
가역 가명화 라운드트립/원복 핸들.

빠른 시작::

    from nufi_client import NuFi
    client = NuFi()                       # 서버 불필요(in-process 게이트웨이)
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "2+2 는?"}])
    print(resp.choices[0].message.content)

기존 OpenAI 클라이언트라면 base_url 만 교체::

    from openai import OpenAI
    client = OpenAI(base_url=NuFi.gateway_base_url(), api_key="nufi-local")
"""
from __future__ import annotations

from .client import NuFi, RoundTrip
from .models import (ChatCompletion, ChatCompletionChunk, Choice, ChunkChoice,
                     Delta, Message, NuFiBlocked)
from .transport import CompletionResult, HttpTransport, InProcessTransport

__all__ = [
    "NuFi", "RoundTrip", "NuFiBlocked",
    "ChatCompletion", "ChatCompletionChunk", "Choice", "ChunkChoice",
    "Delta", "Message",
    "InProcessTransport", "HttpTransport", "CompletionResult",
]
