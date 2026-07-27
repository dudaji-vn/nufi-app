"""Contract tests against a live Presidio analyzer.

These require Docker (`mcr.microsoft.com/presidio-analyzer:2.2.362` on
:3000) and are excluded from the default test run via the `contract` marker
(see `pyproject.toml`'s `addopts = "-m 'not contract'"`). Adapter-only
behaviour — malformed responses, bad offsets, non-finite scores — is covered
without a live dependency in `tests/test_pii_scanner.py`.
"""

import os

import pytest
from guardrails.scanners.pii import PiiScanner
from guardrails.types import Span, SpanSource

pytestmark = pytest.mark.contract

BASE_URL = os.environ.get("PRESIDIO_ANALYZER_API_BASE", "http://localhost:3000")
ENTITIES = ["EMAIL_ADDRESS", "PHONE_NUMBER", "CREDIT_CARD", "PERSON"]


def _scanner() -> PiiScanner:
    return PiiScanner(base_url=BASE_URL, timeout_s=10.0, entities=ENTITIES, language="en")


@pytest.mark.asyncio
async def test_email_is_detected_with_offsets():
    spans = [Span(text="mail me at sun@dudaji.com please", source=SpanSource.USER, message_index=0)]

    findings = await _scanner().scan(spans)

    emails = [f for f in findings if f.entity == "EMAIL_ADDRESS"]
    assert len(emails) == 1
    assert spans[0].text[emails[0].start : emails[0].end] == "sun@dudaji.com"
    assert emails[0].risk == "LLM02"


@pytest.mark.asyncio
async def test_clean_text_produces_no_findings():
    findings = await _scanner().scan(
        [Span(text="what is the capital of Vietnam", source=SpanSource.USER, message_index=0)]
    )

    assert findings == []


@pytest.mark.asyncio
async def test_unreachable_presidio_raises_scanner_unavailable():
    from guardrails.scanners.base import ScannerUnavailable

    scanner = PiiScanner(
        base_url="http://127.0.0.1:9", timeout_s=0.5, entities=ENTITIES, language="en"
    )

    with pytest.raises(ScannerUnavailable):
        await scanner.scan([Span(text="sun@dudaji.com", source=SpanSource.USER, message_index=0)])


@pytest.mark.asyncio
async def test_vietnamese_diacritics_offsets_slice_the_email_cleanly():
    """Offsets must stay meaningful against the ORIGINAL span text.

    Vietnamese combining/precomposed diacritics are multi-byte in UTF-8 but a
    single Python `str` character each. If Presidio (or a layer between it
    and us) ever reported byte offsets instead of character offsets, slicing
    `span.text[start:end]` here would land on the wrong characters — this is
    exactly the "offsets that drift produce corrupted output or leaked PII"
    risk called out for Task 11's redaction. This test fails loudly (wrong
    slice, not an exception) if that ever regresses, because Presidio itself
    is the thing being contracted against here.
    """
    text = "Xin chào, đây là email của tôi: sun@dudaji.com, cảm ơn nhiều"
    spans = [Span(text=text, source=SpanSource.USER, message_index=0)]

    findings = await _scanner().scan(spans)

    emails = [f for f in findings if f.entity == "EMAIL_ADDRESS"]
    assert len(emails) == 1
    assert text[emails[0].start : emails[0].end] == "sun@dudaji.com"


@pytest.mark.asyncio
async def test_emoji_before_pii_does_not_shift_offsets():
    """An astral-plane emoji (outside the BMP) is a single Python `str`
    character but two UTF-16 code units / four UTF-8 bytes. Some tokenizers
    report offsets in UTF-16 units, which would shift everything after the
    emoji by one when read back against a Python string. Presidio's REST API
    is expected to report Python-str character offsets; this pins that
    contract against the real service.
    """
    text = "📧 contact sun@dudaji.com for details"
    spans = [Span(text=text, source=SpanSource.USER, message_index=0)]

    findings = await _scanner().scan(spans)

    emails = [f for f in findings if f.entity == "EMAIL_ADDRESS"]
    assert len(emails) == 1
    assert text[emails[0].start : emails[0].end] == "sun@dudaji.com"
