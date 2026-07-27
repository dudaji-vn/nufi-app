"""LLM01 — prompt injection, scored per span by the classifier sidecar."""

from __future__ import annotations

import httpx

from guardrails.canonical import canonicalize
from guardrails.scanners.base import ScannerUnavailable
from guardrails.types import Finding, Span


class InjectionScanner:
    name = "injection"
    risk = "LLM01"

    def __init__(self, base_url: str, timeout_s: float) -> None:
        self._client = httpx.AsyncClient(base_url=base_url, timeout=timeout_s)

    async def scan(self, spans: list[Span]) -> list[Finding]:
        if not spans:
            return []

        # Each span contributes its canonical text plus every payload we could
        # decode out of it. All are scored; the span takes the highest score,
        # so a decoded injection cannot hide behind innocuous carrier prose.
        items: list[dict[str, str]] = []
        owners: list[int] = []
        for index, span in enumerate(spans):
            canonical = canonicalize(span.text)
            for candidate in (canonical.text, *canonical.derived):
                items.append({"text": candidate, "source": span.source.value})
                owners.append(index)

        try:
            response = await self._client.post("/scan/spans", json={"spans": items})
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ScannerUnavailable(f"injection scanner: {exc}") from exc

        # `body` must be a JSON object carrying a "results" list, one entry per
        # candidate we sent. Anything else is a malformed response and must
        # raise, never be coerced: `results = body.get("results") or []`
        # followed by `float(result.get("score", 0.0))` would silently score a
        # missing/garbled result as 0.0 — a broken sidecar then reads as
        # "everything is safe", the exact fail-open shape this project keeps
        # finding. A malformed response must surface as ScannerUnavailable so
        # the caller's fail-closed policy actually applies.
        results = body.get("results") if isinstance(body, dict) else None
        if not isinstance(results, list) or len(results) != len(items):
            got = len(results) if isinstance(results, list) else "no"
            raise ScannerUnavailable(
                f"injection scanner returned {got} results for {len(items)} candidates"
            )

        best = [0.0] * len(spans)
        complete = [True] * len(spans)
        try:
            for owner, result in zip(owners, results, strict=True):
                best[owner] = max(best[owner], float(result["score"]))
                complete[owner] = complete[owner] and bool(result.get("complete", True))
        except (KeyError, TypeError, ValueError) as exc:
            raise ScannerUnavailable(
                f"injection scanner returned a malformed result: {exc}"
            ) from exc

        findings = [
            Finding(
                risk=self.risk,
                detector=self.name,
                score=score,
                source=span.source,
                start=0,
                end=len(span.text),
            )
            for span, score in zip(spans, best, strict=True)
        ]

        # A span the scanner could not fully examine is reported, not assumed
        # safe. It carries its own detector so policy can price it separately:
        # partial coverage is not a likelihood on the same scale as a classifier
        # score, and treating it as one would either block constantly or say
        # nothing. `policy.yaml` decides what it costs.
        findings.extend(
            Finding(
                risk=self.risk,
                detector="coverage_gap",
                score=1.0,
                source=span.source,
                start=0,
                end=len(span.text),
            )
            for span, scanned in zip(spans, complete, strict=True)
            if not scanned
        )

        return findings
