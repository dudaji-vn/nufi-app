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


def test_assistant_turns_are_their_own_source_not_untrusted():
    """A prior assistant turn is the model's own words, not foreign content.

    It mapped to `UNTRUSTED` until 2026-07-30, and that was a live defect rather
    than a nuance: `untrusted` is exempt from G1's `require_corroboration`, so a
    prior assistant turn blocked the request on the classifier alone -- and the
    classifier scores the model's own safety refusal 1.0000 (measured). Every
    conversation in which the model refused something was dead from that turn
    onward, recoverable only by starting a new chat.

    `SpanSource.USER` would be wrong in the other direction: it carries G1's
    0.90 threshold, high enough to drop a corroborated classifier hit at 0.85
    below the line and turn a two-detector verdict into a log line.
    """
    spans = extract_spans([{"role": "assistant", "content": "sure, here is the plan"}])

    assert spans[0].source is SpanSource.ASSISTANT


def test_unknown_role_defaults_to_untrusted_not_system():
    """An unrecognised role must be the most suspicious source, not the least.

    `SpanSource.SYSTEM` carries threshold 1.01 in the shipping policy -- above
    any score a detector can produce -- so a message with an unknown role would
    be structurally exempt from G1, G2a and G2b at once. Anyone able to set a
    role string could opt out of every input control.
    """
    for role in ("moderator", "", "SYSTEM_", "tool_result"):
        spans = extract_spans([{"role": role, "content": "x"}])
        assert spans[0].source is SpanSource.UNTRUSTED, role


def test_unknown_role_does_not_default_to_assistant_either():
    """The fallback must not become the LENIENT branch of the role table.

    Since 2026-07-30 the table has two non-system destinations, and `assistant`
    is the one that requires corroboration before G1 may act. A default of
    `ASSISTANT` would hand that discount to anyone who can invent a role string
    -- and unlike a default of `SYSTEM` (which the test above catches by
    threshold), it would still detect, still record, still count, and look
    entirely healthy on every dashboard while enforcing on one fewer path.
    """
    for role in ("assistant_2", "Assistant", "ASSISTANT", "model", "ai"):
        spans = extract_spans([{"role": role, "content": "x"}])
        assert spans[0].source is SpanSource.UNTRUSTED, role


def test_developer_role_is_system_like():
    """`developer` is OpenAI's rename of `system`; it must not become untrusted."""
    spans = extract_spans([{"role": "developer", "content": "you are a helpful bot"}])

    assert spans[0].source is SpanSource.SYSTEM


def test_a_tool_result_is_its_own_source():
    """A tool result is not "a role this code does not recognise".

    Both mapped to `UNTRUSTED` until now, and that conflation is what forced
    `nufi-agent` to be exempted from G1 entirely: `untrusted` blocks on one
    detector, the classifier scores benign text near 1.0, and every agent turn
    after the first carries a tool result. Measured 2026-09-03 on this gateway,
    the smallest tool result that exists:

        {"ok":true}  as role=tool  -> 400 LLM01_INJECTION
        {"ok":true}  as role=user  -> 200

    Splitting the source is what lets the policy say something specific about
    tool results instead of exempting the model and losing the control.
    """
    spans = extract_spans(
        [
            {"role": "tool", "content": '{"ok":true}'},
            {"role": "function", "content": "result"},
        ]
    )

    assert [span.source for span in spans] == [SpanSource.TOOL, SpanSource.TOOL]


def test_an_unrecognised_role_is_still_untrusted():
    """`untrusted` keeps meaning what it says, and stays the strict default.

    It must not fall back to TOOL either — `tool` now carries a corroboration
    requirement, so a default of TOOL would hand that discount to anyone who
    can invent a role string.
    """
    spans = extract_spans([{"role": "wizard", "content": "hello"}])

    assert spans[0].source is SpanSource.UNTRUSTED
