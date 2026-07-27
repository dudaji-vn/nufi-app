"""Shared vocabulary for the guardrail pipeline.

Scanners produce `Finding`s. Only `policy` produces a `Decision`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class SpanSource(StrEnum):
    """Where a piece of text came from, which drives its scoring threshold."""

    USER = "user"
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
