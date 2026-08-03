"""Adapter-only tests for PiiScanner: no live Presidio, no network.

Every HTTP exchange is stubbed via `httpx.MockTransport`, so these tests
exercise ONLY the adapter's own logic (per-span offset validation, malformed
-response handling, non-finite score rejection) rather than Presidio's real
recognizers, which are covered by the live contract tests in
tests/contract/test_pii_contract.py.
"""

import httpx
import pytest
from guardrails.scanners.base import ScannerUnavailable
from guardrails.scanners.pii import PiiScanner
from guardrails.types import Span, SpanSource

pytestmark = pytest.mark.asyncio

ENTITIES = ["EMAIL_ADDRESS", "PHONE_NUMBER", "CREDIT_CARD", "PERSON"]


def _scanner(handler) -> PiiScanner:
    scanner = PiiScanner(
        base_url="http://presidio.test", timeout_s=1.0, entities=ENTITIES, language="en"
    )
    scanner._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://presidio.test"
    )
    return scanner


def _json_handler(status_code, body):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json=body)

    return handler


async def test_email_finding_carries_risk_detector_and_offsets():
    handler = _json_handler(
        200,
        [{"entity_type": "EMAIL_ADDRESS", "score": 0.95, "start": 11, "end": 25}],
    )
    scanner = _scanner(handler)

    findings = await scanner.scan(
        [Span(text="mail me at sun@dudaji.com", source=SpanSource.USER, message_index=0)]
    )

    assert len(findings) == 1
    finding = findings[0]
    assert finding.risk == "LLM02"
    assert finding.detector == "presidio"
    assert finding.entity == "EMAIL_ADDRESS"
    assert finding.score == pytest.approx(0.95)
    assert finding.source == SpanSource.USER
    assert (finding.start, finding.end) == (11, 25)


async def test_clean_span_produces_no_findings():
    handler = _json_handler(200, [])
    scanner = _scanner(handler)

    findings = await scanner.scan(
        [Span(text="what is the capital of Vietnam", source=SpanSource.USER, message_index=0)]
    )

    assert findings == []


async def test_each_span_is_posted_separately_with_its_own_text():
    """Presidio is called per span, not on concatenated text, so offsets
    stay meaningful against each span's own `text` (redaction slices
    `span.text[start:end]` directly in Task 11). A bug that concatenates
    spans before scanning would send one request instead of two, and this
    is the test that would catch it.
    """
    seen_texts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        body = json.loads(request.content)
        seen_texts.append(body["text"])
        return httpx.Response(200, json=[])

    scanner = _scanner(handler)

    await scanner.scan(
        [
            Span(text="first span", source=SpanSource.USER, message_index=0),
            Span(text="second span", source=SpanSource.UNTRUSTED, message_index=1),
        ]
    )

    assert seen_texts == ["first span", "second span"]


async def test_empty_span_produces_no_findings_without_a_network_call():
    """Presidio's /analyze returns HTTP 500 ('No text provided') for an
    empty string — verified against the live service. Without a short
    circuit, a legitimately empty span would surface as ScannerUnavailable
    instead of the trivially-correct 'no PII' answer.
    """
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=[])

    scanner = _scanner(handler)

    findings = await scanner.scan([Span(text="", source=SpanSource.USER, message_index=0)])

    assert findings == []
    assert calls == []


async def test_empty_span_list_produces_no_findings_without_a_network_call():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=[])

    scanner = _scanner(handler)

    findings = await scanner.scan([])

    assert findings == []
    assert calls == []


async def test_transport_failure_raises_scanner_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    scanner = _scanner(handler)

    with pytest.raises(ScannerUnavailable):
        await scanner.scan([Span(text="hello", source=SpanSource.USER, message_index=0)])


async def test_timeout_raises_scanner_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    scanner = _scanner(handler)

    with pytest.raises(ScannerUnavailable):
        await scanner.scan([Span(text="hello", source=SpanSource.USER, message_index=0)])


async def test_http_500_raises_scanner_unavailable():
    handler = _json_handler(500, {"error": "internal error"})
    scanner = _scanner(handler)

    with pytest.raises(ScannerUnavailable):
        await scanner.scan([Span(text="hello", source=SpanSource.USER, message_index=0)])


async def test_non_json_body_raises_scanner_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json at all")

    scanner = _scanner(handler)

    with pytest.raises(ScannerUnavailable):
        await scanner.scan([Span(text="hello", source=SpanSource.USER, message_index=0)])


@pytest.mark.parametrize(
    "body",
    [
        {"entity_type": "EMAIL_ADDRESS", "score": 0.9, "start": 0, "end": 1},
        "not a list",
        42,
    ],
    ids=["object", "string", "number"],
)
async def test_non_list_body_raises_scanner_unavailable(body):
    handler = _json_handler(200, body)
    scanner = _scanner(handler)

    with pytest.raises(ScannerUnavailable):
        await scanner.scan([Span(text="hello", source=SpanSource.USER, message_index=0)])


async def test_json_null_body_raises_scanner_unavailable():
    # httpx.Response(200, json=None) sends an EMPTY body, not the literal
    # JSON token `null` — that would make this indistinguishable from the
    # "non-JSON body" case (both would already raise via the JSONDecodeError
    # path, masking whether the `isinstance(results, list)` check actually
    # runs). Send `null` as raw content so `response.json()` really returns
    # `None` and this exercises the type check, not the JSON parser.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"null", headers={"content-type": "application/json"})

    scanner = _scanner(handler)

    with pytest.raises(ScannerUnavailable):
        await scanner.scan([Span(text="hello", source=SpanSource.USER, message_index=0)])


@pytest.mark.parametrize(
    "entries",
    [
        ["not a dict"],
        [123],
        [["nested", "list"]],
        [None],
    ],
    ids=["string", "number", "list", "null"],
)
async def test_non_dict_entries_raise_scanner_unavailable(entries):
    handler = _json_handler(200, entries)
    scanner = _scanner(handler)

    with pytest.raises(ScannerUnavailable):
        await scanner.scan([Span(text="hello", source=SpanSource.USER, message_index=0)])


@pytest.mark.parametrize(
    "item",
    [
        {"score": 0.9, "start": 0, "end": 1},  # missing entity_type
        {"entity_type": "X", "start": 0, "end": 1},  # missing score
        {"entity_type": "X", "score": 0.9, "end": 1},  # missing start
        {"entity_type": "X", "score": 0.9, "start": 0},  # missing end
    ],
    ids=["missing_entity_type", "missing_score", "missing_start", "missing_end"],
)
async def test_missing_required_field_raises_scanner_unavailable_not_silently_defaulted(item):
    """A missing field must never be read as a benign default.

    `item.get("score", 0.0)` would silently turn a missing "score" into
    0.0 (definitely-safe); `item.get("start", 0)` / `item.get("end", 0)`
    would silently turn missing offsets into an empty [0:0] slice. Both are
    the fail-open shape this project keeps finding and removing — the
    adapter must raise instead of guessing.
    """
    handler = _json_handler(200, [item])
    scanner = _scanner(handler)

    with pytest.raises(ScannerUnavailable):
        await scanner.scan([Span(text="hello world", source=SpanSource.USER, message_index=0)])


async def test_non_numeric_score_raises_scanner_unavailable():
    handler = _json_handler(
        200, [{"entity_type": "X", "score": "high", "start": 0, "end": 1}]
    )
    scanner = _scanner(handler)

    with pytest.raises(ScannerUnavailable):
        await scanner.scan([Span(text="hello", source=SpanSource.USER, message_index=0)])


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity"])
async def test_non_finite_score_is_an_outage_not_a_clean_verdict(token):
    """`nan >= threshold` is always False in policy.decide, so a corrupted
    score reads as definitely-safe. json.loads accepts bare
    NaN/Infinity/-Infinity tokens, so a malformed response carries one without
    failing JSON parsing.

    Raw bytes, not `json=` — see the twin of this test in
    test_injection_scanner.py for the full explanation. The `json=` form raised
    during fixture construction, which `pytest.raises(ScannerUnavailable)`
    accepted while the guard under test never ran.
    """
    body = (
        b'[{"entity_type": "X", "score": ' + token.encode() + b', "start": 0, "end": 1}]'
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=body, headers={"content-type": "application/json"}
        )

    scanner = _scanner(handler)

    with pytest.raises(ScannerUnavailable):
        await scanner.scan([Span(text="hello", source=SpanSource.USER, message_index=0)])


async def test_non_numeric_offsets_raise_scanner_unavailable():
    handler = _json_handler(
        200, [{"entity_type": "X", "score": 0.9, "start": "zero", "end": 5}]
    )
    scanner = _scanner(handler)

    with pytest.raises(ScannerUnavailable):
        await scanner.scan([Span(text="hello", source=SpanSource.USER, message_index=0)])


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (-1, 5),  # negative start
        (0, 999),  # end past the span's length
        (5, 2),  # start > end
        (999, 999),  # both past the span's length
    ],
    ids=["negative_start", "end_past_length", "start_after_end", "both_past_length"],
)
async def test_offsets_outside_span_bounds_raise_scanner_unavailable(start, end):
    """Offsets are trusted to slice span.text directly for redaction
    (Task 11). An out-of-bounds offset would slice the wrong characters —
    Python slicing clips silently rather than raising — so this must be
    rejected here, not discovered downstream as corrupted output.
    """
    handler = _json_handler(
        200, [{"entity_type": "X", "score": 0.9, "start": start, "end": end}]
    )
    scanner = _scanner(handler)

    with pytest.raises(ScannerUnavailable):
        await scanner.scan([Span(text="hello", source=SpanSource.USER, message_index=0)])


async def test_offsets_at_exact_span_boundaries_are_accepted():
    # start == 0 and end == len(text) is the whole span, a legitimate edge —
    # must NOT be rejected by an off-by-one in the bounds check.
    handler = _json_handler(200, [{"entity_type": "X", "score": 0.9, "start": 0, "end": 5}])
    scanner = _scanner(handler)

    findings = await scanner.scan([Span(text="hello", source=SpanSource.USER, message_index=0)])

    assert len(findings) == 1
    assert (findings[0].start, findings[0].end) == (0, 5)


async def test_byte_offset_dressed_as_char_offset_is_rejected_not_silently_accepted():
    """A stand-in for the 'byte vs. character offset' failure mode: a
    response whose `end` was computed against UTF-8 BYTES (each Vietnamese
    diacritic is multiple bytes but one Python `str` character) would claim
    an offset past the actual character length. Slicing `span.text[start:
    end]` would silently clip to the true end instead of raising — this
    must be caught by the bounds check, not discovered as a truncated
    redaction later.
    """
    text = "đây là email của tôi"  # 21 characters; well under any byte count
    byte_length = len(text.encode("utf-8"))
    assert byte_length > len(text)  # sanity check the fixture is actually multi-byte

    handler = _json_handler(
        200, [{"entity_type": "X", "score": 0.9, "start": 0, "end": byte_length}]
    )
    scanner = _scanner(handler)

    with pytest.raises(ScannerUnavailable):
        await scanner.scan([Span(text=text, source=SpanSource.USER, message_index=0)])


async def test_multiple_findings_in_one_span_are_all_reported():
    handler = _json_handler(
        200,
        [
            {"entity_type": "PERSON", "score": 0.85, "start": 0, "end": 3},
            {"entity_type": "EMAIL_ADDRESS", "score": 0.99, "start": 10, "end": 24},
        ],
    )
    scanner = _scanner(handler)

    findings = await scanner.scan(
        [Span(text="Sun contact sun@dudaji.com", source=SpanSource.USER, message_index=0)]
    )

    assert {f.entity for f in findings} == {"PERSON", "EMAIL_ADDRESS"}


async def test_second_span_finding_is_not_corrupted_by_first_spans_offsets():
    """Each span gets its own POST and its own bounds check. If offsets were
    ever validated/attributed against the wrong span (e.g. a shared running
    total), a finding legitimately in-bounds for span 2 but out-of-bounds for
    span 1's shorter text would be misattributed or wrongly rejected.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        body = json.loads(request.content)
        if body["text"] == "hi":
            return httpx.Response(200, json=[])
        return httpx.Response(
            200, json=[{"entity_type": "EMAIL_ADDRESS", "score": 0.9, "start": 11, "end": 25}]
        )

    scanner = _scanner(handler)

    findings = await scanner.scan(
        [
            Span(text="hi", source=SpanSource.USER, message_index=0),
            Span(
                text="mail me at sun@dudaji.com",
                source=SpanSource.UNTRUSTED,
                message_index=1,
            ),
        ]
    )

    assert len(findings) == 1
    assert findings[0].source == SpanSource.UNTRUSTED
    assert (findings[0].start, findings[0].end) == (11, 25)
