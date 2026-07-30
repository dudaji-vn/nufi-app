"""Shared vocabulary for the guardrail pipeline.

Scanners produce `Finding`s. Only `policy` produces a `Decision`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class SpanSource(StrEnum):
    """Where a piece of text came from, which drives its scoring threshold.

    Four sources, because there are four different answers to "who wrote this
    and what does a detector hit on it mean".

    `ASSISTANT` was split out of `UNTRUSTED` on 2026-07-30, and the split is
    the fix for a live false positive rather than a taxonomy tidy-up. While
    `assistant`, `tool` and `function` all mapped to `UNTRUSTED`, a model's own
    safety refusal -- "I cannot process, store, or accept sensitive personal
    information such as email addresses or credit card numbers" -- scored
    1.0000 on the injection classifier and blocked with 400 on a single
    detector, because `untrusted` is deliberately exempt from
    `require_corroboration`. Every conversation containing a refusal was then
    dead from that turn on, with no recovery but a new chat, and it hit hardest
    in the safety-conscious interactions the control exists to protect.

    The two things are not the same thing:

      ASSISTANT   the model's OWN prior output. Overwhelmingly benign, and the
                  user read it as it was produced. Benign text, so the same
                  reasoning that gave `USER` a corroboration requirement
                  applies -- measured, it costs nothing on refusals.
      UNTRUSTED   content that arrived from somewhere else mid-conversation: a
                  tool result, a function result, a message whose role this
                  code does not recognise. This is where indirect injection
                  actually lands, and where the classifier's recall earns its
                  keep on one detector alone.

    Adding a member is deliberately expensive: `policy._parse_control` requires
    EVERY control in policy.yaml to declare a threshold for every member, so a
    new source cannot be introduced without every control stating what it costs.
    """

    USER = "user"
    ASSISTANT = "assistant"
    UNTRUSTED = "untrusted"
    SYSTEM = "system"


class Action(StrEnum):
    ALLOW = "allow"
    BLOCK = "block"
    REDACT = "redact"
    LOG = "log"


@dataclass(frozen=True)
class Span:
    text: str
    source: SpanSource
    message_index: int


@dataclass(frozen=True)
class Finding:
    risk: str
    detector: str
    score: float
    source: SpanSource
    start: int
    end: int
    entity: str | None = None


@dataclass(frozen=True)
class Decision:
    action: Action
    control: str
    risk: str
    findings: tuple[Finding, ...]
    reason: str


@dataclass(frozen=True)
class Canonical:
    text: str
    transforms: tuple[str, ...]
    derived: tuple[str, ...] = ()
