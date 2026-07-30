"""Split an OpenAI-shaped message list into spans tagged by trust level."""

from __future__ import annotations

from typing import Any

from guardrails.types import Span, SpanSource

# `assistant` is NOT `tool`/`function`, and conflating them was a live defect.
#
# All three mapped to `UNTRUSTED` until 2026-07-30. `untrusted` is exempt from
# G1's `require_corroboration` -- deliberately, because a jailbreak string in a
# retrieved document is near-certain attack whichever detector saw it -- so a
# prior assistant turn blocked the request on the classifier alone. The
# classifier scores a model's own safety refusal 1.0000 (measured on the live
# stack: "Thank you for providing the project ID. However, I cannot process,
# store, or accept sensitive personal information such as email addresses or
# credit card numbers." -> injection=1.0000, INJECTION), so every conversation
# in which the model refused something was blocked from that turn onward.
#
# The distinction that fixes it is whose text it is, which is the same
# distinction `user` already rests on:
#
#   assistant  the model's own prior output -- benign text the user has already
#              read. Requires corroboration, and measured against three
#              realistic refusals the regex detector fires on none of them, so
#              the requirement costs nothing here.
#   tool       a result that arrived from elsewhere mid-conversation. This is
#   function   where indirect injection lands, so it stays on the
#              single-detector path: of six realistic indirect-injection
#              payloads, four are invisible to the regex detector and would
#              become log-only if corroboration were required here.
#
# An UNRECOGNISED role keeps falling back to `UNTRUSTED` in `extract_spans`
# below, and that is now load-bearing in a second way: it must not fall back to
# `ASSISTANT` either. `assistant` is the lenient branch of this table, so a
# default of `ASSISTANT` would hand the corroboration discount to anyone who
# can invent a role string.
_ROLE_SOURCE = {
    "system": SpanSource.SYSTEM,
    "developer": SpanSource.SYSTEM,
    "user": SpanSource.USER,
    "assistant": SpanSource.ASSISTANT,
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
