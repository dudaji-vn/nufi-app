from __future__ import annotations

from typing import Protocol

from guardrails.types import Finding, Span


class ScannerUnavailable(RuntimeError):
    """The backing detector could not be reached or returned garbage."""


class Scanner(Protocol):
    name: str

    async def scan(self, spans: list[Span]) -> list[Finding]: ...
