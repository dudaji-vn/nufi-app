"""Split an OpenAI-shaped message list into spans tagged by trust level."""

from __future__ import annotations

from typing import Any

from guardrails.types import Span, SpanSource

_ROLE_SOURCE = {
    "system": SpanSource.SYSTEM,
    "developer": SpanSource.SYSTEM,
    "user": SpanSource.USER,
    "assistant": SpanSource.UNTRUSTED,
    "tool": SpanSource.UNTRUSTED,
    "function": SpanSource.UNTRUSTED,
}


def _text_of(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts = [
        str(chunk.get("text", ""))
        for chunk in content
        if isinstance(chunk, dict) and chunk.get("type") == "text"
    ]
    return "\n".join(parts)


def extract_spans(messages: list[dict[str, Any]] | None) -> list[Span]:
    spans: list[Span] = []
    for index, message in enumerate(messages or []):
        source = _ROLE_SOURCE.get(str(message.get("role", "")), SpanSource.UNTRUSTED)
        text = _text_of(message.get("content")).strip()
        if not text:
            continue
        spans.append(Span(text=text, source=source, message_index=index))
    return spans
