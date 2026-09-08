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
                  a message whose role this code does not recognise --
                  content of unknown provenance. It stays the strict default,
                  and the fallback for any role not in the table.

    `TOOL` was split out of `UNTRUSTED` on 2026-09-04, and like the `ASSISTANT`
    split before it, it is the fix for a live defect rather than a taxonomy
    tidy-up. While a tool result was `untrusted` it blocked on one detector, and
    the classifier scores benign text near 1.0:

        {"ok":true}  as role=tool  -> 400 LLM01_INJECTION
        {"ok":true}  as role=user  -> 200

    Eleven characters, and every agent turn after the first carries a tool
    result. The only way to run an agent at all was to exempt its model from G1
    completely, which is a hole rather than a control. A source of its own is
    what lets the policy say something specific: in this deployment a tool
    result is the product's own API returning company-authored text -- the same
    words that reach the model as `user` in the wake briefing -- so it carries
    the same corroboration requirement, and G1 applies to agents again.

    Adding a member is deliberately expensive: `policy._parse_control` requires
    EVERY control in policy.yaml to declare a threshold for every member, so a
    new source cannot be introduced without every control stating what it costs.
    """

    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"
    UNTRUSTED = "untrusted"
    SYSTEM = "system"


class Action(StrEnum):
    ALLOW = "allow"
    BLOCK = "block"
    REDACT = "redact"
    LOG = "log"
    #: Replace the value with an opaque token on the way out and restore it on
    #: the way back, so the provider never receives it and the user does not lose
    #: it. Unlike every other member this one spans BOTH legs of a request: G2a
    #: mints, G2b restores, and they share one process-wide vault.
    #:
    #: Measured to be usable only where the value is CARRIED rather than reasoned
    #: about, and only when the gateway also injects an instruction explaining the
    #: token -- `docs/2026-07-29-nufi-security-integration.md` §7.3a. A request
    #: asking about the value ("is this a valid address?") cannot be served at
    #: all with the value hidden, so this action requires per-workload opt-in and
    #: is never a default. `guardrails/pseudonymize.py` carries the rest.
    PSEUDONYMIZE = "pseudonymize"


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
