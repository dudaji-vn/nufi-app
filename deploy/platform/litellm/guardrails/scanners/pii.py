"""LLM02 — PII detection via the Presidio analyzer.

Detection only. Whether a finding is logged or redacted is decided by policy,
and input text is never mutated here: the previous system masked PII on
input and the model started answering the placeholder instead of the
question (see policy.yaml's G2a).

Presidio is called PER SPAN, never on concatenated text, so `start`/`end`
stay meaningful character offsets into that span's own `text` — Task 11's
redaction slices `span.text[start:end]` directly, and a drifted offset there
means corrupted output or leaked PII, not just a wrong test assertion.
"""

from __future__ import annotations

import math

import httpx

from guardrails.scanners.base import ScannerUnavailable
from guardrails.types import Finding, Span


class PiiScanner:
    name = "presidio"
    risk = "LLM02"

    def __init__(
        self, base_url: str, timeout_s: float, entities: list[str], language: str
    ) -> None:
        self._client = httpx.AsyncClient(base_url=base_url, timeout=timeout_s)
        self._entities = entities
        self._language = language

    async def scan(self, spans: list[Span]) -> list[Finding]:
        findings: list[Finding] = []
        for span in spans:
            findings.extend(await self._scan_one(span))
        return findings

    async def _scan_one(self, span: Span) -> list[Finding]:
        # Presidio's /analyze rejects an empty string with an HTTP 500
        # ("No text provided"), which would otherwise surface as a spurious
        # ScannerUnavailable for input that trivially contains no PII. An
        # empty span carries nothing to find, so short-circuit instead of
        # turning a non-event into an outage.
        if not span.text:
            return []

        payload = {
            "text": span.text,
            "language": self._language,
            "entities": self._entities,
        }
        try:
            response = await self._client.post("/analyze", json=payload)
            response.raise_for_status()
            results = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ScannerUnavailable(f"presidio: {exc}") from exc

        # Presidio's contract is a JSON array, one object per detected
        # entity. Anything else — an object, a scalar, `null` — is a
        # malformed response and must raise, never be iterated: iterating a
        # dict yields its keys as strings, and `"x".get(...)` below would
        # raise an unhandled AttributeError instead of the ScannerUnavailable
        # the caller's fail-closed policy depends on.
        if not isinstance(results, list):
            raise ScannerUnavailable(
                f"presidio: expected a JSON array, got {type(results).__name__}"
            )

        return [self._to_finding(item, span) for item in results]

    def _to_finding(self, item: object, span: Span) -> Finding:
        if not isinstance(item, dict):
            raise ScannerUnavailable(f"presidio: expected a result object, got {item!r}")

        # `score`/`start`/`end`/`entity_type` are required keys, read with
        # `item[...]` rather than `.get(..., default)`. A default here would
        # turn a missing field into a value that reads as a clean result —
        # `score` defaulting to 0.0 is "definitely no PII", and `start`/`end`
        # both defaulting to 0 is an empty, silently-accepted slice — exactly
        # the fail-open shape this project keeps finding and removing.
        try:
            score = float(item["score"])
            start = int(item["start"])
            end = int(item["end"])
            entity = str(item["entity_type"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ScannerUnavailable(f"presidio: malformed result {item!r}") from exc

        # NaN and infinity both survive float() silently. `nan >= threshold`
        # is always False in policy.decide, so a corrupted score would read
        # as "definitely safe" — an outage must not present as a clean
        # verdict. json.loads also accepts bare NaN/Infinity tokens by
        # default, so this can arrive without ever failing JSON parsing.
        if not math.isfinite(score):
            raise ScannerUnavailable(f"presidio: non-finite score {score!r}")

        # Offsets are trusted downstream to slice span.text directly
        # (redaction, in Task 11, and this adapter's own contract tests).
        # An offset outside the span's bounds, or start > end, would slice
        # into the wrong characters or silently redact nothing — corrupted
        # output or leaked PII, not a loud failure. Reject it here instead.
        if not (0 <= start <= end <= len(span.text)):
            raise ScannerUnavailable(
                f"presidio: offsets [{start}:{end}] out of bounds for a "
                f"{len(span.text)}-character span"
            )

        return Finding(
            risk=self.risk,
            detector=self.name,
            score=score,
            source=span.source,
            start=start,
            end=end,
            entity=entity,
        )
