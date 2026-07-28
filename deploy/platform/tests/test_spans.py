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


# --- the two security-relevant defaults ------------------------------------
#
# Both of these survived the whole build unasserted, and both were confirmed by
# mutation to change nothing that any test could see. They decide which
# threshold a message is judged against, so getting them wrong silently widens
# what reaches the model.


def test_assistant_turns_are_untrusted_not_user():
    """Prior assistant turns carry whatever the model was induced to say.

    `SpanSource.USER` would judge them at G1's user threshold (0.90) instead of
    the untrusted one (0.50) -- the conversation-history and RAG-echo injection
    path, where the payload arrives as the model's own earlier output.
    """
    spans = extract_spans([{"role": "assistant", "content": "sure, here is the plan"}])

    assert spans[0].source is SpanSource.UNTRUSTED


def test_unknown_role_defaults_to_untrusted_not_system():
    """An unrecognised role must be the most suspicious source, not the least.

    `SpanSource.SYSTEM` carries threshold 1.01 in the shipping policy -- above
    any score a detector can produce -- so a message with an unknown role would
    be structurally exempt from G1, G2a and G2b at once. Anyone able to set a
    role string could opt out of every input control.
    """
    for role in ("function", "moderator", "", "SYSTEM_", "tool_result"):
        spans = extract_spans([{"role": role, "content": "x"}])
        assert spans[0].source is SpanSource.UNTRUSTED, role


def test_developer_role_is_system_like():
    """`developer` is OpenAI's rename of `system`; it must not become untrusted."""
    spans = extract_spans([{"role": "developer", "content": "you are a helpful bot"}])

    assert spans[0].source is SpanSource.SYSTEM
