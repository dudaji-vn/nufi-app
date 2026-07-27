"""Adapter-only tests for InjectionScanner: no live sidecar, no network.

Every HTTP exchange is stubbed via `httpx.MockTransport`, and `canonicalize`
is patched to a deterministic fake so these tests exercise ONLY the adapter's
own logic (fan-out, owner attribution, max-aggregation, coverage_gap
emission, malformed-response handling) rather than the real canonicalizer or
classifier, which are covered elsewhere. Contract-marked tests in
tests/contract/ cover the real sidecar end to end.
"""

import httpx
import pytest
from guardrails.scanners.base import ScannerUnavailable
from guardrails.scanners.injection import InjectionScanner
from guardrails.types import Canonical, Span, SpanSource

pytestmark = pytest.mark.asyncio


def _scanner(handler, monkeypatch, canonical_map=None):
    """Build an InjectionScanner wired to a MockTransport and a fake canonicalize.

    `canonicalize` is ALWAYS patched, never left as the real implementation:
    the real one turns any span containing a letter into 2+ scan candidates
    (canonical text plus its unconditional ROT13 derivative — see
    guardrails/canonical.py), which silently changes how many items a test
    sends to the mock sidecar and previously masked a real bug (a
    count-mismatch failure fired first and hid that a missing "score" field
    was NOT actually raising). `canonical_map` maps a span's raw text to the
    Canonical it should produce; a span whose text is not in the map falls
    back to exactly one candidate (its own text, no derived payloads).
    """
    scanner = InjectionScanner(base_url="http://scanner.test", timeout_s=1.0)
    scanner._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://scanner.test"
    )
    mapping = canonical_map or {}
    monkeypatch.setattr(
        "guardrails.scanners.injection.canonicalize",
        lambda text: mapping.get(text, Canonical(text=text, transforms=())),
    )
    return scanner


def _json_handler(results, model="test-model"):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"model": model, "results": results})

    return handler


async def test_span_score_is_the_max_across_canonical_text_and_derived_payloads(monkeypatch):
    # One span, two scan candidates: canonical text scores low, a decoded
    # payload scores high. The span's finding must take the higher score —
    # a bug that scores only canonical.text, or averages, would miss this.
    canonical_map = {
        "carrier": Canonical(text="carrier", transforms=(), derived=("payload",)),
    }
    handler = _json_handler(
        [
            {"score": 0.10, "label": "SAFE", "complete": True},
            {"score": 0.93, "label": "INJECTION", "complete": True},
        ]
    )
    scanner = _scanner(handler, monkeypatch, canonical_map)

    findings = await scanner.scan(
        [Span(text="carrier", source=SpanSource.USER, message_index=0)]
    )

    assert len(findings) == 1
    assert findings[0].score == pytest.approx(0.93)
    assert findings[0].detector == "injection"
    assert findings[0].risk == "LLM01"


async def test_incomplete_span_gets_a_separate_coverage_gap_finding(monkeypatch):
    canonical_map = {
        "short": Canonical(text="short", transforms=()),
        "long": Canonical(text="long", transforms=()),
    }
    handler = _json_handler(
        [
            {"score": 0.05, "label": "SAFE", "complete": True},   # short: fully scanned
            {"score": 0.20, "label": "SAFE", "complete": False},  # long: budget exceeded
        ]
    )
    scanner = _scanner(handler, monkeypatch, canonical_map)

    findings = await scanner.scan(
        [
            Span(text="short", source=SpanSource.USER, message_index=0),
            Span(text="long", source=SpanSource.UNTRUSTED, message_index=1),
        ]
    )

    by_detector = {(f.detector, f.source): f for f in findings}
    # Exactly one coverage_gap finding, and it belongs to the incomplete span.
    assert len([f for f in findings if f.detector == "coverage_gap"]) == 1
    gap = by_detector[("coverage_gap", SpanSource.UNTRUSTED)]
    assert gap.score == 1.0
    assert gap.risk == "LLM01"
    # The fully-scanned span must not spuriously get a coverage_gap finding.
    assert ("coverage_gap", SpanSource.USER) not in by_detector
    # Both spans still get their ordinary injection finding regardless.
    assert by_detector[("injection", SpanSource.USER)].score == pytest.approx(0.05)
    assert by_detector[("injection", SpanSource.UNTRUSTED)].score == pytest.approx(0.20)


async def test_multi_span_candidates_are_attributed_to_the_right_owner(monkeypatch):
    # Span A has 2 candidates, span B has 1. If owner indices were built
    # incorrectly (e.g. off-by-one, or flattened in the wrong order), B's
    # score would leak into A or vice versa.
    canonical_map = {
        "a": Canonical(text="a", transforms=(), derived=("a-derived",)),
        "b": Canonical(text="b", transforms=()),
    }
    handler = _json_handler(
        [
            {"score": 0.11, "label": "SAFE", "complete": True},       # a (canonical)
            {"score": 0.22, "label": "SAFE", "complete": True},       # a (derived)
            {"score": 0.99, "label": "INJECTION", "complete": True},  # b
        ]
    )
    scanner = _scanner(handler, monkeypatch, canonical_map)

    findings = await scanner.scan(
        [
            Span(text="a", source=SpanSource.USER, message_index=0),
            Span(text="b", source=SpanSource.USER, message_index=1),
        ]
    )

    # Injection findings are returned in span order: findings[0] is span "a",
    # findings[1] is span "b" (the coverage_gap tail, if any, comes after).
    injection_findings = [f for f in findings if f.detector == "injection"]
    assert injection_findings[0].score == pytest.approx(0.22)  # a: max(0.11, 0.22)
    assert injection_findings[1].score == pytest.approx(0.99)  # b: 0.99


async def test_empty_spans_returns_empty_findings_without_a_network_call(monkeypatch):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"model": "x", "results": []})

    scanner = _scanner(handler, monkeypatch)

    findings = await scanner.scan([])

    assert findings == []
    assert calls == []


async def test_result_count_mismatch_raises_scanner_unavailable(monkeypatch):
    # One item sent, sidecar returns zero results.
    handler = _json_handler([])
    scanner = _scanner(handler, monkeypatch)

    with pytest.raises(ScannerUnavailable):
        await scanner.scan([Span(text="hello", source=SpanSource.USER, message_index=0)])


async def test_missing_score_field_raises_scanner_unavailable_not_silently_zero(monkeypatch):
    """A malformed result must never be read as a benign score.

    `float(result.get("score", 0.0))` would silently turn a missing "score"
    key into 0.0 — a corrupted sidecar response then reads as "definitely
    safe" instead of "unavailable". This is exactly the fail-open shape
    flagged elsewhere in this project; the adapter must raise instead.
    """
    handler = _json_handler([{"label": "SAFE", "complete": True}])  # no "score"
    scanner = _scanner(handler, monkeypatch)

    with pytest.raises(ScannerUnavailable):
        await scanner.scan([Span(text="hello", source=SpanSource.USER, message_index=0)])


async def test_non_numeric_score_raises_scanner_unavailable(monkeypatch):
    handler = _json_handler([{"score": "not-a-number", "label": "SAFE", "complete": True}])
    scanner = _scanner(handler, monkeypatch)

    with pytest.raises(ScannerUnavailable):
        await scanner.scan([Span(text="hello", source=SpanSource.USER, message_index=0)])


async def test_non_object_body_raises_scanner_unavailable(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=["not", "an", "object"])

    scanner = _scanner(handler, monkeypatch)

    with pytest.raises(ScannerUnavailable):
        await scanner.scan([Span(text="hello", source=SpanSource.USER, message_index=0)])


async def test_transport_failure_raises_scanner_unavailable(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    scanner = _scanner(handler, monkeypatch)

    with pytest.raises(ScannerUnavailable):
        await scanner.scan([Span(text="hello", source=SpanSource.USER, message_index=0)])


async def test_non_json_body_raises_scanner_unavailable(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json at all")

    scanner = _scanner(handler, monkeypatch)

    with pytest.raises(ScannerUnavailable):
        await scanner.scan([Span(text="hello", source=SpanSource.USER, message_index=0)])
