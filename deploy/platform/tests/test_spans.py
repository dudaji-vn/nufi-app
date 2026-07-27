from guardrails.spans import extract_spans
from guardrails.types import SpanSource


def test_user_message_is_a_user_span():
    spans = extract_spans([{"role": "user", "content": "hello"}])

    assert len(spans) == 1
    assert spans[0].text == "hello"
    assert spans[0].source is SpanSource.USER


def test_system_message_is_a_system_span():
    spans = extract_spans([{"role": "system", "content": "you are helpful"}])

    assert spans[0].source is SpanSource.SYSTEM


def test_tool_message_is_untrusted():
    spans = extract_spans([{"role": "tool", "content": "search result body"}])

    assert spans[0].source is SpanSource.UNTRUSTED


def test_multimodal_content_keeps_only_text_parts():
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "describe this"},
                {"type": "image_url", "image_url": {"url": "https://x/y.png"}},
            ],
        }
    ]

    spans = extract_spans(messages)

    assert [s.text for s in spans] == ["describe this"]


def test_message_index_is_preserved():
    messages = [
        {"role": "system", "content": "s"},
        {"role": "user", "content": "u"},
    ]

    spans = extract_spans(messages)

    assert [s.message_index for s in spans] == [0, 1]


def test_empty_content_produces_no_span():
    assert extract_spans([{"role": "user", "content": "   "}]) == []
