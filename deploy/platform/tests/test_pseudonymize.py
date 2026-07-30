"""Tests for reversible pseudonymization.

The REAL-ENGINE half runs `nufi-security`'s own surrogate and vault code, not a
stub. A mock would assert that our adapter calls a function we wrote down, which
is not the claim: the claim is that a value survives a round trip through their
minter, their AES-256-GCM vault and their restorer, and comes back byte for byte.

The SEAM half is where the interesting failures are, and all of them share a
shape: an adapter that mistranslates between two vocabularies produces output
that looks fine. `TAG_OF.get("EMAIL_ADDRESS")` is `None`, so an unmapped entity
mints `⟦X1⟧` — same round trip, same counts, type information gone. Nothing
raises.

The MANGLED half covers the failure their library cannot see: a model that
returns `E1` with the delimiters stripped. `_EXACT` does not match it and
`_LENIENT` requires brackets on both sides, so restoration reports
`restored: 0, fallback: 0` and succeeds at nothing. Every test here that asserts
a count would pass against a `restore` that returned its input unchanged, so
each also asserts the text.
"""

import re
from pathlib import Path

import pytest
import yaml
from egress_audit import surrogate as _sg
from guardrails.pseudonymize import (
    _LABEL_OF_TAG,
    _TO_ENGINE_ENTITY,
    REVERSIBLE_ENTITIES,
    Pseudonymizer,
)
from guardrails.types import Finding, SpanSource

PLATFORM = Path(__file__).resolve().parent.parent
POLICY = PLATFORM / "litellm" / "guardrails" / "policy.yaml"

# A DETECTABLE domain, and the TLD is the reason. Measured against the shipped
# Presidio analyzer: `jane.doe@acme.example` scores `URL:0.5` and NO
# `EMAIL_ADDRESS` at all, while `.com`, `.io` and `.co.kr` all score
# `EMAIL_ADDRESS:1.0`. The stub scanners below make that irrelevant here, but a
# constant copied out of this file into a live test would measure nothing --
# which is exactly what happened to the first end-to-end smoke test of this
# feature.
EMAIL = "jane.doe@acme-industrial.com"
PHONE = "+84 90 123 4567"


def _finding(entity: str, start: int, end: int) -> Finding:
    return Finding(
        risk="LLM02_PII",
        detector="test",
        score=1.0,
        entity=entity,
        start=start,
        end=end,
        source=SpanSource.USER,
    )


@pytest.fixture
def pseudo() -> Pseudonymizer:
    return Pseudonymizer()


# --- the round trip, against the real engine ---------------------------------


def test_a_value_survives_the_round_trip_byte_for_byte(pseudo):
    text = f"Please reply to {EMAIL} today."
    start = text.index(EMAIL)

    forward = pseudo.pseudonymize(text, [_finding("EMAIL_ADDRESS", start, start + len(EMAIL))])

    assert EMAIL not in forward.text, "the value must not leave the process"
    assert forward.count == 1
    assert forward.ref

    back = pseudo.restore(forward.text, forward.ref)
    assert back.text == text, "the restored text must equal the original exactly"
    assert (back.restored, back.fallback, back.mangled) == (1, 0, 0)

    # And in a sentence the model wrote itself, rather than the echoed request:
    # the surrogate is what travels, so it can come back anywhere.
    reply = f"Sure — I will contact {_sg.make_surrogate('E', 1)} this afternoon."
    written = pseudo.restore(reply, forward.ref)
    assert written.text == f"Sure — I will contact {EMAIL} this afternoon."
    assert written.restored == 1


def test_the_surrogate_carries_the_entity_type_in_its_tag(pseudo):
    """The failure this catches: every entity minting `⟦X1⟧`.

    `TAG_OF` is keyed on THEIR entity names. Ours are different, and
    `TAG_OF.get(unknown)` falls back to `"X"` rather than raising, so a missing
    translation produces a working round trip with no type information left --
    and `_LABEL_OF_TAG` then cannot name the entity when restoration fails.
    """
    text = f"{EMAIL} and {PHONE}"
    findings = [
        _finding("EMAIL_ADDRESS", 0, len(EMAIL)),
        _finding("PHONE_NUMBER", text.index(PHONE), text.index(PHONE) + len(PHONE)),
    ]

    out = pseudo.pseudonymize(text, findings)

    assert out.count == 2
    assert "X1" not in out.text and "X2" not in out.text, out.text
    assert _sg.make_surrogate("E", 1) in out.text
    assert _sg.make_surrogate("T", 1) in out.text


def test_the_same_value_twice_mints_one_surrogate(pseudo):
    """Their minter deduplicates on the original value, which only works if we
    hand it the matched substring rather than the whole text."""
    text = f"{EMAIL} and again {EMAIL}"
    second = text.rindex(EMAIL)
    findings = [
        _finding("EMAIL_ADDRESS", 0, len(EMAIL)),
        _finding("EMAIL_ADDRESS", second, second + len(EMAIL)),
    ]

    out = pseudo.pseudonymize(text, findings)

    assert out.text.count(_sg.make_surrogate("E", 1)) == 2
    assert _sg.make_surrogate("E", 2) not in out.text
    assert pseudo.restore(out.text, out.ref).text == text


def test_two_values_restore_into_the_right_places(pseudo):
    """Offsets are applied back to front; a front-to-back pass would shift every
    later replacement by the length delta and silently corrupt the text."""
    text = f"Mail {EMAIL} or call {PHONE} now"
    findings = [
        _finding("EMAIL_ADDRESS", text.index(EMAIL), text.index(EMAIL) + len(EMAIL)),
        _finding("PHONE_NUMBER", text.index(PHONE), text.index(PHONE) + len(PHONE)),
    ]

    out = pseudo.pseudonymize(text, findings)
    back = pseudo.restore(out.text, out.ref)

    assert back.text == text
    assert back.restored == 2


# --- what must NOT be reversible ---------------------------------------------


@pytest.mark.parametrize(
    "entity", ["CREDIT_CARD", "US_SSN", "IBAN_CODE", "IP_ADDRESS", "KR_RRN", "KR_FOREIGNER_REG"]
)
def test_a_strong_identifier_is_not_pseudonymized(pseudo, entity):
    """Restoring one of these puts a card number or a national identifier back
    on a screen and into LibreChat's stored history. They stay redacted, which
    means this module must decline them and leave the text alone."""
    text = "the number is 4111-1111-1111-1111 ok"
    out = pseudo.pseudonymize(text, [_finding(entity, 14, 33)])

    assert out.text == text
    assert out.count == 0
    assert out.ref is None, "declining must not allocate a vault session"


@pytest.mark.parametrize(
    "start,end",
    [
        (100, 130),  # both past the end
        (9, 9),  # empty span
        (12, 4),  # inverted
        (900, 4),  # start past the end AND inverted
    ],
)
def test_an_offset_that_does_not_fit_the_text_is_refused(pseudo, start, end):
    """Two detectors scan the same string and either can report an offset that
    does not fit it. Python does not raise on an out-of-range slice: it returns
    `""`, so an unclamped implementation stores an EMPTY original in the vault
    and their `out[:start] + rep + out[end:]` appends the surrogate to the end of
    the text. The response leg then restores an empty string over it. Nothing
    raises at any point, and the audit trail reports a successful round trip.
    """
    text = "a short line"
    out = pseudo.pseudonymize(text, [_finding("EMAIL_ADDRESS", start, end)])

    assert out.text == text, "no surrogate may be appended for an unusable offset"
    assert out.count == 0
    assert out.ref is None
    assert pseudo.active_count() == 0


@pytest.mark.parametrize(
    "start,end,covers",
    [
        (5, 500, EMAIL),  # end past the end: still a real match on the tail
        (-4, 5 + len(EMAIL), f"mail {EMAIL}"),  # negative start clamps to 0
    ],
)
def test_a_partly_out_of_range_offset_is_clamped_not_dropped(pseudo, start, end, covers):
    """An offset that overshoots one edge still names a real span. Clamping
    keeps it; refusing it outright would leave the value in the request.

    This is the other half of the test above, and the pair is the point: an
    implementation that clamps everything to nothing would pass that one, and an
    implementation that clamps nothing would pass this one.
    """
    text = f"mail {EMAIL}"
    out = pseudo.pseudonymize(text, [_finding("EMAIL_ADDRESS", start, end)])

    assert out.count == 1
    assert covers not in out.text
    assert pseudo.restore(out.text, out.ref).text == text


def test_no_reversible_finding_allocates_no_session(pseudo):
    out = pseudo.pseudonymize("nothing here", [])

    assert out.ref is None
    assert pseudo.active_count() == 0


# --- the mangled case, which their library cannot see ------------------------


def test_a_delimiter_stripped_surrogate_is_detected_and_labelled(pseudo):
    """Measured: when the model drops the brackets it drops all of them, and
    `⟦E1⟧ → E1` matches neither `_EXACT` nor `_LENIENT`. Their `deanonymize`
    reports success at nothing."""
    text = f"Reply to {EMAIL}"
    out = pseudo.pseudonymize(text, [_finding("EMAIL_ADDRESS", 9, 9 + len(EMAIL))])
    stripped = out.text.replace(_sg.make_surrogate("E", 1), "E1")

    # First: their engine really cannot see it. If this stops being true the
    # test below is testing nothing.
    theirs, stats = _sg.deanonymize(stripped, pseudo._vault, out.ref)
    assert theirs == stripped and stats == {"restored": 0, "fallback": 0}

    back = pseudo.restore(stripped, out.ref)

    assert back.mangled == 1
    assert back.text == "Reply to [EMAIL_ADDRESS]"
    assert "E1" not in back.text, "the user must not be shown a bare tag"
    assert back.failed == 1


def test_a_coincidental_tag_is_left_alone(pseudo):
    """A reply that legitimately mentions `T1` in a request that pseudonymized
    an email must not have `T1` rewritten. Corrupting text to repair a failure
    that did not happen is worse than the failure."""
    text = f"Reply to {EMAIL}"
    out = pseudo.pseudonymize(text, [_finding("EMAIL_ADDRESS", 9, 9 + len(EMAIL))])

    reply = f"Cell T1 and row E9 refer to {out.text[9:]}"
    back = pseudo.restore(reply, out.ref)

    assert "T1" in back.text and "E9" in back.text
    assert back.mangled == 0
    assert back.restored == 1


@pytest.mark.parametrize("noise", ["SIZE12", "E1000000", "AE1", "E1x"])
def test_a_bare_tag_pattern_does_not_match_ordinary_text(pseudo, noise):
    text = f"Reply to {EMAIL}"
    out = pseudo.pseudonymize(text, [_finding("EMAIL_ADDRESS", 9, 9 + len(EMAIL))])

    back = pseudo.restore(f"nothing to see: {noise}", out.ref)

    assert back.text == f"nothing to see: {noise}"
    assert back.mangled == 0


def test_an_unmapped_surrogate_falls_back_to_our_label(pseudo):
    """A surrogate with no mapping -- expired, wrong session, or invented by the
    model. Their library labels it with THEIR type name; the client must only
    ever see labels from one vocabulary."""
    text = f"Reply to {EMAIL}"
    out = pseudo.pseudonymize(text, [_finding("EMAIL_ADDRESS", 9, 9 + len(EMAIL))])

    invented = f"see {_sg.make_surrogate('E', 99)} and {out.text[9:]}"
    back = pseudo.restore(invented, out.ref)

    assert back.fallback == 1
    assert back.restored == 1
    assert "[EMAIL_ADDRESS]" in back.text
    assert "[EMAIL]" not in back.text.replace("[EMAIL_ADDRESS]", "")
    assert back.failed == 1


# --- session lifetime -------------------------------------------------------


def test_ending_a_session_wipes_the_mapping(pseudo):
    text = f"Reply to {EMAIL}"
    out = pseudo.pseudonymize(text, [_finding("EMAIL_ADDRESS", 9, 9 + len(EMAIL))])
    assert pseudo.active_count(out.ref) == 1

    assert pseudo.end_session(out.ref) >= 1
    assert pseudo.active_count(out.ref) == 0

    after = pseudo.restore(out.text, out.ref)
    assert EMAIL not in after.text, "a wiped mapping must not still restore"
    assert after.fallback == 1


def test_ending_a_session_twice_and_on_none_is_safe(pseudo):
    assert pseudo.end_session(None) == 0
    out = pseudo.pseudonymize(f"a {EMAIL}", [_finding("EMAIL_ADDRESS", 2, 2 + len(EMAIL))])
    pseudo.end_session(out.ref)
    assert pseudo.end_session(out.ref) == 0


def test_one_sessions_values_never_reach_another(pseudo):
    """A process-wide instance serves concurrent requests. An implementation
    holding the 'current' ref on `self` would restore one request's values into
    another's response, and every count would still look right."""
    a = pseudo.pseudonymize(f"a {EMAIL}", [_finding("EMAIL_ADDRESS", 2, 2 + len(EMAIL))])
    other = "someone.else@other-vendor.com"
    b = pseudo.pseudonymize(f"b {other}", [_finding("EMAIL_ADDRESS", 2, 2 + len(other))])

    assert pseudo.restore(a.text, a.ref).text == f"a {EMAIL}"
    assert pseudo.restore(b.text, b.ref).text == f"b {other}"
    # A's surrogate resolved against B's session must not yield A's value.
    crossed = pseudo.restore(a.text, b.ref)
    assert EMAIL not in crossed.text


def test_restoring_with_no_ref_is_a_no_op(pseudo):
    assert pseudo.restore("anything", None).text == "anything"
    assert pseudo.stream_restorer(None) is None


# --- the seam, asserted against reality not against itself ------------------


def test_the_engine_reads_only_the_attributes_the_shim_provides():
    """If upstream adds a field to `Finding` and reads it in `pseudonymize`, the
    shim raises `AttributeError` on the first request carrying PII. This makes
    that a failing test instead."""
    source = _sg.pseudonymize.__code__
    attrs = {
        name
        for name in source.co_names
        if name in {"entity_type", "start", "end", "text", "score", "risk", "detector"}
    }

    assert attrs <= {"entity_type", "start", "end", "text"}, (
        f"surrogate.pseudonymize now reads {attrs - {'entity_type', 'start', 'end', 'text'}} "
        "off a finding; add it to _EngineFinding"
    )


def test_every_reversible_entity_has_an_engine_name():
    """A name in `REVERSIBLE_ENTITIES` with no `_TO_ENGINE_ENTITY` entry is
    silently skipped, so the control would run and do nothing for that type."""
    assert set(_TO_ENGINE_ENTITY) >= REVERSIBLE_ENTITIES


def test_every_engine_name_resolves_to_a_tag_we_can_label():
    """The two tables are joined by their `TAG_OF`. If a mapping points at an
    engine name their minter does not know, that type mints `⟦X…⟧` and
    `_LABEL_OF_TAG` has nothing for it."""
    for ours, theirs in _TO_ENGINE_ENTITY.items():
        tag = _sg.TAG_OF.get(theirs)
        assert tag is not None, f"{ours} -> {theirs} is not in their TAG_OF"
        assert tag in _LABEL_OF_TAG, f"{ours} mints tag {tag}, which has no label"


def test_every_reversible_entity_is_one_the_detectors_can_produce():
    """Dead configuration: pseudonymizing an entity no configured detector
    emits. `policy.yaml` is the authority for what is detected at all."""
    policy = yaml.safe_load(POLICY.read_text(encoding="utf-8"))
    configured: set[str] = set()
    for control in policy["controls"].values():
        options = control.get("options") or {}
        configured.update(options.get("entities") or [])
        configured.update(options.get("nufi_entities") or [])

    missing = REVERSIBLE_ENTITIES - configured
    assert not missing, (
        f"{missing} cannot be produced by any detector configured in policy.yaml, "
        "so pseudonymizing them is dead code"
    )


def test_the_bare_tag_pattern_covers_exactly_the_tags_we_mint():
    """Drift between the tags minted and the tags repaired means a mangled
    surrogate of the uncovered type reaches the user as a bare token."""
    from guardrails.pseudonymize import _BARE_TAG

    for tag in _LABEL_OF_TAG:
        assert _BARE_TAG.fullmatch(f"{tag}1"), tag
    assert not _BARE_TAG.search("P1"), "P is not a tag this module mints"


def test_the_default_delimiter_is_in_use():
    """The measurement behind `REVERSIBLE_ENTITIES` and the mangled-tag repair
    was taken with `⟦⟧`. A deployment that sets `NUFI_SURROGATE_DELIMS` gets
    different survival numbers, and `[[E1]]` in particular is syntax a user can
    type -- so a change here is a decision, not a default."""
    assert (_sg.LB, _sg.RB) == ("⟦", "⟧")
    assert re.search(r"\d", _sg.make_surrogate("E", 1))
