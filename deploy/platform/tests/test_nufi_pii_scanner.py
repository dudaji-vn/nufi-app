"""Tests for the nufi-security Korean PII adapter.

Three halves, deliberately.

The REAL-ENGINE half runs the rules that ship in the image. It is not a mock of
the thing under test: the whole reason this scanner exists is a measured claim
about which Korean identifiers it finds and which strings it leaves alone, and
a stub cannot make that claim.

Every resident-registration number used here is GENERATED, by the checksum the
detector itself validates (weights [2,3,4,5,6,7,8,9,2,3,4,5], check digit
`(11 - sum % 11) % 10`). A test built on an invalid number asserts nothing: it
would pass just as well against a scanner that had been deleted. The negative
case is therefore not "some other string", it is the SAME number with one digit
changed, which pins the checksum itself.

The ADAPTER half stubs the engine, because the failures that matter there are
the ones a real, healthy library never produces: offsets into a different
string, a renamed field, a score of NaN. Those are exactly the states where
"returned an empty list" and "worked correctly" are indistinguishable
downstream.

The PROVENANCE half asserts that the vendored rules file is the pinned commit's
file, unedited, and that the pin has not moved underneath it.
"""

import asyncio
import hashlib
import math
import re
import subprocess
from pathlib import Path

import pytest
from guardrails.scanners.base import ScannerUnavailable
from guardrails.scanners.nufi_pii import (
    PATTERNS_PATH_ENV,
    PATTERNS_SHA256,
    PATTERNS_SOURCE_COMMIT,
    VENDORED_PATTERNS_PATH,
    NufiPiiScanner,
)
from guardrails.types import Finding, Span, SpanSource

# No blanket `pytestmark = pytest.mark.asyncio`: pyproject sets
# `asyncio_mode = "auto"`, and a blanket marker would tag the synchronous
# constructor tests below with it too.

PLATFORM = Path(__file__).resolve().parent.parent

DEFAULT_ENTITIES = ["KR_RRN", "KR_FOREIGNER_REG", "KR_PHONE"]

# Generated, never copied. See the module docstring.
_RRN_WEIGHTS = [2, 3, 4, 5, 6, 7, 8, 9, 2, 3, 4, 5]


def rrn(first12: str) -> str:
    """A checksum-VALID Korean RRN from its first twelve digits."""
    assert len(first12) == 12 and first12.isdigit()
    total = sum(int(d) * w for d, w in zip(first12, _RRN_WEIGHTS, strict=True))
    check = (11 - (total % 11)) % 10
    return f"{first12[:6]}-{first12[6:]}{check}"


def broken_rrn(first12: str) -> str:
    """The same number with a check digit that is deliberately wrong."""
    valid = rrn(first12)
    wrong = (int(valid[-1]) + 1) % 10
    return valid[:-1] + str(wrong)


VALID_RRN = rrn("900101123456")
INVALID_RRN = broken_rrn("900101123456")
_RRN_LEN = len(VALID_RRN)
# Gender digit 5-8 is the foreigner-registration range.
VALID_FOREIGNER = rrn("900101523456")

# Hangul, ASCII, a regional-indicator flag (TWO astral code points) and an
# emoji, with real identifiers embedded. Every offset assertion in this file
# that matters uses this string, because a wrong offset here means G2b redacts
# the wrong characters of a Korean answer.
MIXED = f"🇰🇷 안녕하세요 Ana 님, 주민번호 {VALID_RRN} 이고 폰 010-1234-5678 입니다 🎉 done"


def _span(text: str, source: SpanSource = SpanSource.UNTRUSTED) -> Span:
    return Span(text=text, source=source, message_index=0)


def _scanner(**kwargs) -> NufiPiiScanner:
    kwargs.setdefault("entities", list(DEFAULT_ENTITIES))
    return NufiPiiScanner(**kwargs)


class _StubFinding:
    """Shaped like the library's `Finding`, and nothing like ours."""

    def __init__(
        self,
        entity_type="KR_RRN",
        text=VALID_RRN,
        start=0,
        end=_RRN_LEN,
        score=0.99,
        drop=None,
    ):
        self.entity_type = entity_type
        self.text = text
        self.start = start
        self.end = end
        self.score = score
        self.source = "regex+checksum"
        if drop is not None:
            delattr(self, drop)


class _StubEngine:
    """An engine whose behaviour each test dictates.

    The default finds the canary RRN wherever it appears, with correct
    offsets, and nothing otherwise -- the minimum needed to get past
    `_self_check`. A stub that cannot do that is testing the self-check, not
    the adapter.
    """

    def __init__(self, hits=None):
        self._hits = hits or self._default

    @staticmethod
    def _default(text):
        start = text.find(VALID_RRN)
        if start == -1:
            return []
        return [_StubFinding(start=start, end=start + len(VALID_RRN))]

    def analyze(self, text):
        return self._hits(text)


# --- the measured claim ------------------------------------------------------


async def test_a_checksum_valid_rrn_is_found():
    findings = await _scanner().scan([_span(f"제 주민등록번호는 {VALID_RRN} 입니다.")])

    assert len(findings) == 1
    assert findings[0].detector == "nufi_pii"
    assert findings[0].risk == "LLM02"
    assert findings[0].entity == "KR_RRN"
    assert findings[0].score >= 0.50, "must cross G2a/G2b's source threshold"


async def test_an_rrn_with_a_broken_check_digit_is_not_found():
    """The checksum is the reason this detector is more precise than a regex.

    `INVALID_RRN` differs from `VALID_RRN` in exactly one digit, so a scanner
    that had stopped validating -- or one that had degenerated into a bare
    13-digit match -- would flag it. Nothing else about the text changes.
    """
    assert await _scanner().scan([_span(f"제 주민등록번호는 {INVALID_RRN} 입니다.")]) == []


@pytest.mark.parametrize("first12", ["900101123456", "851231234567", "010203456789"])
async def test_the_checksum_holds_for_generated_pairs(first12):
    """Not one number: the valid/invalid split holds across generated pairs.

    A single hardcoded pair could pass against a detector that happened to
    match that one string.
    """
    scanner = _scanner()

    assert await scanner.scan([_span(f"번호 {rrn(first12)}")]) != []
    assert await scanner.scan([_span(f"번호 {broken_rrn(first12)}")]) == []


async def test_a_foreigner_registration_number_is_found():
    findings = await _scanner().scan([_span(f"외국인등록번호 {VALID_FOREIGNER} 입니다.")])

    assert [f.entity for f in findings] == ["KR_FOREIGNER_REG"]


async def test_a_korean_phone_number_is_found_and_labelled_as_ours():
    """Their `KR_PHONE` is Presidio's `PHONE_NUMBER`.

    Both engines run on the same text and `Finding.entity` becomes the
    redaction label a user reads, so the same kind of thing must not produce
    two different words in one answer.
    """
    findings = await _scanner().scan([_span("연락처는 010-1234-5678 입니다.")])

    assert [f.entity for f in findings] == ["PHONE_NUMBER"]


BENIGN = [
    # Korean, including the ISO date that KR_ACCOUNT would flag if enabled.
    "안녕하세요. 오늘 회의는 오후 3시에 시작합니다. 감사합니다.",
    "배포는 2026-07-29 에 완료될 예정입니다.",
    "도커 컴포즈로 프로메테우스와 엔진엑스를 배포했습니다.",
    "서울 본사에서 회의를 진행했습니다.",
    "테스트 커버리지는 87.5% 이며 목표는 90% 입니다.",
    # English technical, the sentences Presidio's PERSON recognizer got wrong.
    "We deploy Docker Compose with Prometheus and Nginx behind a reverse proxy.",
    "The Q3 roadmap for Southeast Asia covers React Query and Redis 7.4.",
    "litellm v1.83.10 was released on 2026-07-29 and pins httpx 0.28.1.",
    "The incident window was 2026-07-29 to 2026-08-01, about 48 hours.",
    "Ticket S12345678 was closed by the on-call engineer.",
    "Tracking 1234-5678-9012 was delivered this morning.",
]


@pytest.mark.parametrize("text", BENIGN)
async def test_benign_text_is_left_alone(text):
    """G2b REDACTS, so every one of these is a sentence a user would otherwise
    read with a placeholder in it.

    The dates and hyphenated groups are here on purpose: they are exactly what
    `KR_ACCOUNT` matches, and this is what pins its ABSENCE from the shipped
    entity list. Adding it back turns four of these red.
    """
    assert await _scanner().scan([_span(text)]) == []


async def test_korean_person_and_location_are_not_reported():
    """`KR_PERSON` / `KR_LOCATION` are this library's counterpart of the
    Presidio PERSON and LOCATION recognizers this repo removed for being unable
    to separate a true hit from a false one -- measured on the gazetteer
    backend, `문의는` ("the inquiry is") came back as a person and both `서울`
    and `강남구` as locations.
    """
    findings = await _scanner().scan(
        [_span("고객 문의는 김철수 님께서 서울 강남구에서 접수하셨습니다.")]
    )

    assert findings == []


def test_the_engine_is_built_with_ner_and_the_confidential_channel_off():
    """The two constructor flags, asserted on the object they configure.

    The test above does NOT pin them, and that matters: with NER enabled the
    engine still reports KR_PERSON and KR_LOCATION, and the entity filter
    simply drops them -- so `enable_ner=True` would leave that test green while
    changing what the proxy runs. What it would change:

    * `ner_backend="auto"` resolves to transformers-or-gazetteer depending on
      which packages happen to be importable, so the image and the test venv
      could silently run different detectors;
    * a deployment adding `KR_PERSON` to policy.yaml would get an imprecise
      recogniser instead of the loud refusal below;
    * the confidential channel reports offsets into a NORMALISED copy of the
      text, and G2b redacts by character span.
    """
    engine = _scanner()._detector

    assert engine.ner_backend == "disabled"
    assert engine.confidential is None
    assert engine.edm is None


def test_naming_an_ner_entity_is_refused_rather_than_silently_inert():
    """With NER disabled, `KR_PERSON` can never be produced.

    A filter that simply never matched would leave the control scanning every
    request and discarding every result, reporting clean traffic forever.
    """
    with pytest.raises(ScannerUnavailable, match="KR_PERSON"):
        NufiPiiScanner(entities=["KR_RRN", "KR_PERSON"])


# --- offsets, the property G2b slices on -------------------------------------


async def test_offsets_are_python_str_offsets_on_mixed_script_text():
    """Hangul + ASCII + an astral flag + an emoji, in one string.

    If the engine ever reported UTF-8 byte offsets, UTF-16 units, or offsets
    into a normalised copy, this is where it shows -- and G2b would redact the
    wrong characters of a Korean answer rather than raise anything.
    """
    findings = await _scanner().scan([_span(MIXED)])

    assert len(findings) == 2
    assert [MIXED[f.start : f.end] for f in findings] == [VALID_RRN, "010-1234-5678"]


@pytest.mark.parametrize("form", ["NFC", "NFD"])
async def test_offsets_survive_unicode_normalisation_forms(form):
    import unicodedata

    text = unicodedata.normalize(form, MIXED)
    findings = await _scanner().scan([_span(text)])

    assert [text[f.start : f.end] for f in findings] == [VALID_RRN, "010-1234-5678"]


async def test_offsets_are_relative_to_each_span_not_the_batch():
    """`pii.py`'s contract, restated for this scanner: a finding's offsets are
    only meaningful against the span that produced it."""
    first = f"주민번호 {VALID_RRN}"
    second = f"매우 긴 문장입니다. 아주 길어요. 주민번호는 {VALID_RRN} 입니다."

    findings = await _scanner().scan([_span(first), _span(second)])

    assert first[findings[0].start : findings[0].end] == VALID_RRN
    assert second[findings[1].start : findings[1].end] == VALID_RRN
    assert findings[0].start != findings[1].start


async def test_g2b_redaction_over_these_offsets_replaces_the_identifier():
    """The end-to-end reason offsets matter: run the real redactor over them.

    Asserting `start`/`end` is not the same as asserting the right characters
    come out. `G2bPiiOutput.redact` is what a user actually sees.
    """
    from guardrails.entrypoints import G2bPiiOutput

    findings = await _scanner().scan([_span(MIXED)])
    redacted = G2bPiiOutput.redact(MIXED, list(findings))

    assert VALID_RRN not in redacted
    assert "010-1234-5678" not in redacted
    assert "[KR_RRN]" in redacted
    assert "[PHONE_NUMBER]" in redacted
    assert redacted.startswith("🇰🇷 안녕하세요 Ana 님, 주민번호 ")
    assert redacted.endswith(" 🎉 done")


# --- adapter shape -----------------------------------------------------------


async def test_findings_are_our_type_not_theirs():
    """Their dataclass must not reach policy.py (integration doc §6, risk 3)."""
    findings = await _scanner().scan([_span(f"주민번호 {VALID_RRN}")])

    assert all(isinstance(f, Finding) for f in findings)
    assert not hasattr(findings[0], "entity_type")
    assert not hasattr(findings[0], "conf_class")


async def test_span_source_is_carried_through():
    findings = await _scanner().scan([_span(f"주민번호 {VALID_RRN}", SpanSource.USER)])

    assert findings[0].source is SpanSource.USER


async def test_no_spans_and_empty_spans_are_no_findings():
    assert await _scanner().scan([]) == []
    assert await _scanner().scan([_span("")]) == []


async def test_an_entity_outside_the_configured_list_is_not_reported():
    """The entity list is the real control over what this scanner reports.

    A KR_ACCOUNT is in the rules file and IS matched by the engine; it must not
    come out, because policy.yaml does not ask for it.
    """
    scanner = _scanner(entities=["KR_RRN"])

    assert await scanner.scan([_span("계좌번호 110-1234-567890 입니다")]) == []
    assert await scanner.scan([_span(f"주민번호 {VALID_RRN}")]) != []


async def test_a_configured_entity_that_is_normally_off_can_be_turned_on():
    """The exclusions in policy.yaml are policy, not a capability limit.

    Without this, "KR_ACCOUNT is excluded" and "KR_ACCOUNT cannot be reported"
    would be indistinguishable, and the recorded rationale for excluding it
    would be unfalsifiable.
    """
    scanner = _scanner(entities=["KR_ACCOUNT"])
    findings = await scanner.scan([_span("계좌번호 110-1234-567890 입니다")])

    assert [f.entity for f in findings] == ["KR_ACCOUNT"]
    # And the reason it is off by default, asserted rather than asserted-about:
    assert await scanner.scan([_span("배포는 2026-07-29 에 완료됩니다.")]) != []


async def test_the_alias_table_covers_the_engine_names_that_overlap_presidio():
    from guardrails.entrypoints import _DEFAULT_PII_ENTITIES
    from guardrails.scanners.nufi_pii import _ENTITY_ALIASES

    scanner = _scanner(entities=["EMAIL", "CREDIT_CARD"])
    findings = await scanner.scan(
        [_span("메일 hong@example.co.kr 카드 4111-1111-1111-1111")]
    )

    labels = {f.entity for f in findings}
    assert labels == {"EMAIL_ADDRESS", "CREDIT_CARD"}
    # Both land in Presidio's vocabulary, which is the point of the table.
    assert labels <= set(_DEFAULT_PII_ENTITIES)
    assert _ENTITY_ALIASES["EMAIL"] == "EMAIL_ADDRESS"


def test_every_rule_name_the_shipped_file_declares_survives_the_audit_trail():
    """`audit._safe_label` rewrites anything not identifier-shaped to
    "UNSAFE_LABEL", and `Finding.entity` is also the redaction label a user
    reads. Verified against every name in the file, not assumed for the two
    the design doc happened to mention."""
    import yaml
    from guardrails.audit import _safe_label

    doc = yaml.safe_load(Path(VENDORED_PATTERNS_PATH).read_text(encoding="utf-8"))
    names = [r["name"] for r in doc["korean_pii"]] + [r["name"] for r in doc["secrets"]]

    assert names, "the file declares no rules at all"
    for name in names:
        assert _safe_label(name) == name, name


# --- the self-check ----------------------------------------------------------


def test_an_engine_that_finds_nothing_is_refused_at_construction():
    """The failure this whole module is about.

    A rules file that compiled nothing, a library upgrade that renamed
    `analyze`, a stub left behind by a test helper -- every one produces an
    empty list, which is indistinguishable from PII-free text at every layer
    above.
    """
    with pytest.raises(ScannerUnavailable, match="found no KR_RRN"):
        _scanner(detector=_StubEngine(lambda text: []))


def test_an_engine_whose_checksum_stopped_working_is_refused():
    """The other direction, and the one a test could most easily fake.

    An engine that matches the INVALID number has lost the checksum, which is
    the only thing separating it from a bare 13-digit regex. G2b redacts, so
    that lands in users' answers.
    """

    def matches_anything_rrn_shaped(text):
        out = []
        for m in re.finditer(r"\d{6}-\d{7}", text):
            out.append(
                _StubFinding(text=m.group(0), start=m.start(), end=m.end())
            )
        return out

    with pytest.raises(ScannerUnavailable, match="INVALID check digit"):
        _scanner(detector=_StubEngine(matches_anything_rrn_shaped))


def test_an_engine_reporting_offsets_into_another_string_is_refused():
    """The library's confidential/EDM channels report offsets into a
    NORMALISED copy of the text. They are disabled, and this is the lock on
    the door: G2b redacts by character span, so offsets that address a
    different string corrupt the answer or leave the PII in place -- and
    neither raises on its own.
    """
    with pytest.raises(ScannerUnavailable, match="do not address the text"):
        _scanner(
            detector=_StubEngine(
                lambda text: [_StubFinding(start=0, end=len(VALID_RRN))]
                if VALID_RRN in text
                else []
            )
        )


def test_offsets_that_agree_with_the_engine_but_not_with_reality_are_refused():
    """The one failure the per-finding offset check cannot see.

    That check compares the offsets against the engine's own `text` field, so a
    version that reported BOTH from a normalised copy would be self-consistent
    and pass it. The canary is the only comparison made against a literal we
    control -- and it is what stops G2b redacting whatever happens to sit at
    those coordinates.
    """
    with pytest.raises(ScannerUnavailable, match="canary offsets"):
        _scanner(
            detector=_StubEngine(
                lambda text: [
                    _StubFinding(start=0, end=2, text=text[0:2])
                ]
                if VALID_RRN in text
                else []
            )
        )


def test_a_zero_width_finding_is_refused():
    """`start=0, end=0` is the shape the EDM channel produces. It is not a
    location in the text and cannot be redacted."""
    with pytest.raises(ScannerUnavailable, match="not a usable slice"):
        _scanner(
            detector=_StubEngine(
                lambda text: [_StubFinding(start=0, end=0, text="")]
                if VALID_RRN in text
                else []
            )
        )


def test_the_real_engine_passes_its_own_self_check():
    """Guards against the canary itself rotting: if a rules update ever made
    the invalid number match, every constructor call would raise and the proxy
    would not start. That must be caught here, not in production."""
    assert _scanner() is not None


def test_the_self_check_runs_before_the_object_is_usable():
    """Not a method someone remembers to call."""
    calls = {"n": 0}

    def counting(text):
        calls["n"] += 1
        return _StubEngine._default(text)

    _scanner(detector=_StubEngine(counting))

    assert calls["n"] >= 2, "both canaries must run at construction"


# --- malformed engine output -------------------------------------------------


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("score", "malformed finding"),
        ("start", "malformed finding"),
        ("end", "malformed finding"),
        ("text", "malformed finding"),
        ("entity_type", "no entity_type"),
    ],
)
def test_a_finding_missing_a_field_raises_rather_than_defaulting(field, message):
    """`float(getattr(item, "score", 0.0))` would read a renamed attribute as
    "definitely no PII" -- below every threshold, at the exact moment the
    adapter stopped working.

    The finding is otherwise PERFECT -- correct entity, correct offsets into
    the canary -- and `message` is asserted, so this cannot pass by tripping
    the offset guard instead of the one it names.
    """

    def hits(text):
        found = _StubEngine._default(text)
        for item in found:
            delattr(item, field)
        return found

    with pytest.raises(ScannerUnavailable, match=message):
        _scanner(detector=_StubEngine(hits))


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_a_non_finite_score_raises(bad):
    """NaN survives float() and then vanishes: `nan >= threshold` is always
    False in policy.decide, so a corrupted score reads as 'definitely safe'."""
    with pytest.raises(ScannerUnavailable, match="non-finite score"):
        _scanner(
            detector=_StubEngine(
                lambda text: [
                    _StubFinding(
                        score=bad,
                        start=text.find(VALID_RRN),
                        end=text.find(VALID_RRN) + len(VALID_RRN),
                    )
                ]
                if VALID_RRN in text
                else []
            )
        )


def test_an_engine_that_raises_surfaces_as_scanner_unavailable():
    def boom(text):
        raise RuntimeError("regex engine exploded")

    with pytest.raises(ScannerUnavailable, match="RuntimeError"):
        _scanner(detector=_StubEngine(boom))


def test_an_engine_returning_a_non_list_raises():
    with pytest.raises(ScannerUnavailable, match="expected a list"):
        _scanner(detector=_StubEngine(lambda text: "not a list"))


async def test_a_scan_time_failure_still_raises_after_a_clean_construction():
    """The self-check passing does not make later calls trustworthy."""
    calls = {"n": 0}

    def flaky(text):
        calls["n"] += 1
        if calls["n"] <= 2:  # the two canary calls
            return _StubEngine._default(text)
        raise RuntimeError("later failure")

    scanner = _scanner(detector=_StubEngine(flaky))

    with pytest.raises(ScannerUnavailable):
        await scanner.scan([_span("hello")])


# --- the rules file ----------------------------------------------------------


def test_a_missing_rules_file_is_refused(tmp_path):
    with pytest.raises(ScannerUnavailable, match="unreadable"):
        _scanner(patterns_path=str(tmp_path / "nope.yaml"))


def test_an_unparseable_rules_file_is_refused(tmp_path):
    path = tmp_path / "patterns.yaml"
    path.write_text("korean_pii: [unclosed\n", encoding="utf-8")

    with pytest.raises(ScannerUnavailable, match="not valid YAML"):
        _scanner(patterns_path=str(path))


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ("version: 1\n", "declares no rules"),
        ("korean_pii: []\n", "declares no rules"),
        ("korean_pii: {}\n", "is dict, not a list"),
        ("korean_pii:\n  - regex: 'x'\n", "no string `name:`"),
        ("[]\n", "not a YAML mapping"),
    ],
)
def test_a_rules_file_that_declares_nothing_usable_is_refused(tmp_path, body, message):
    """`cfg.get("korean_pii", [])` turns every one of these into an engine that
    matches nothing, silently, and a proxy that starts cleanly."""
    path = tmp_path / "patterns.yaml"
    path.write_text(body, encoding="utf-8")

    with pytest.raises(ScannerUnavailable, match=re.escape(message)):
        _scanner(patterns_path=str(path))


def test_a_rule_name_that_could_not_survive_the_audit_trail_is_refused(tmp_path):
    path = tmp_path / "patterns.yaml"
    path.write_text(
        "korean_pii:\n"
        "  - name: 'has spaces and @'\n"
        "    regex: 'x'\n"
        "    checksum: none\n",
        encoding="utf-8",
    )

    with pytest.raises(ScannerUnavailable, match="identifier-shaped"):
        NufiPiiScanner(entities=["has spaces and @"], patterns_path=str(path))


async def test_a_custom_rules_file_is_actually_loaded_and_its_rules_fire(tmp_path):
    """Not just "it constructs" -- the rules must reach the engine. A validated
    file that was then dropped on the floor would pass every check above.

    The real KR_RRN rule is included verbatim so the constructor's canary can
    still pass; the custom rule is what this asserts on.
    """
    path = tmp_path / "patterns.yaml"
    path.write_text(
        "korean_pii:\n"
        "  - name: KR_RRN\n"
        "    regex: '(?<![0-9])([0-9]{6})[-\\s]?([1-4][0-9]{6})(?![0-9])'\n"
        "    checksum: rrn\n"
        "  - name: BADGE_ID\n"
        "    regex: 'BADGE-[0-9]{4}'\n"
        "    checksum: none\n",
        encoding="utf-8",
    )
    scanner = NufiPiiScanner(entities=["KR_RRN", "BADGE_ID"], patterns_path=str(path))

    findings = await scanner.scan([_span("employee BADGE-4711 entered")])

    assert [f.entity for f in findings] == ["BADGE_ID"]


def test_the_patterns_path_env_var_is_honoured(tmp_path, monkeypatch):
    monkeypatch.setenv(PATTERNS_PATH_ENV, str(tmp_path / "nope.yaml"))

    with pytest.raises(ScannerUnavailable, match="unreadable"):
        _scanner()


def test_no_env_var_falls_back_to_the_vendored_file(monkeypatch):
    monkeypatch.delenv(PATTERNS_PATH_ENV, raising=False)

    assert _scanner().patterns_path == VENDORED_PATTERNS_PATH


@pytest.mark.parametrize("entities", [[], "KR_RRN", None, {}])
def test_an_unusable_entity_list_is_refused(entities):
    """An empty list is an engine that runs on every request and every response
    and can never report anything."""
    with pytest.raises(ScannerUnavailable, match="non-empty list"):
        NufiPiiScanner(entities=entities)


# --- provenance --------------------------------------------------------------


def test_the_vendored_rules_file_is_where_the_code_looks_for_it():
    path = Path(VENDORED_PATTERNS_PATH)

    assert path.is_absolute(), "the library's own discovery must never be relied on"
    assert path.is_file(), VENDORED_PATTERNS_PATH
    assert path == PLATFORM / "litellm" / "guardrails" / "nufi_patterns.yaml"


def test_the_vendored_rules_file_has_not_been_edited():
    """A shipped detection rule must not change as an unremarked diff hunk."""
    digest = hashlib.sha256(Path(VENDORED_PATTERNS_PATH).read_bytes()).hexdigest()

    assert digest == PATTERNS_SHA256, (
        "litellm/guardrails/nufi_patterns.yaml changed. If that was intended, "
        "update PATTERNS_SHA256 in guardrails/scanners/nufi_pii.py in the same "
        "commit and say in the message what rule moved and why."
    )


def test_the_rules_file_matches_the_library_commit_the_image_installs():
    """The drift this catches: bumping NUFI_SECURITY_COMMIT without
    re-vendoring the rules, leaving one version's code running against another
    version's patterns with nothing to say so.
    """
    dockerfile = (PLATFORM / "litellm" / "Dockerfile").read_text(encoding="utf-8")
    requirements = (PLATFORM / "litellm" / "requirements.txt").read_text(encoding="utf-8")

    pinned = re.search(r"ARG NUFI_SECURITY_COMMIT=([0-9a-f]{40})", dockerfile)
    assert pinned, "litellm/Dockerfile no longer pins NUFI_SECURITY_COMMIT to a commit"
    assert pinned.group(1) == PATTERNS_SOURCE_COMMIT
    assert f"nufi-security@{PATTERNS_SOURCE_COMMIT}" in requirements


@pytest.mark.contract
def test_the_vendored_rules_file_matches_upstream_at_the_pinned_commit(tmp_path):
    """Marked `contract` because it needs the network.

    The two tests above are self-consistent by construction; this one is the
    only thing that says the vendored bytes came from that commit at all.

    Fetched into a THROWAWAY repo under `tmp_path`, never into this one. An
    earlier draft ran `git fetch --depth=1 <remote> <sha>` in the platform
    directory, which is inside the nufi-app checkout: it wrote another
    project's objects into `.git/objects` and left a `.git/shallow` marker
    behind, silently converting the developer's repository into a shallow
    clone. A test must not modify the repository it is testing.
    """
    scratch = tmp_path / "upstream.git"
    remote = "https://github.com/dudaji/nufi-security"
    subprocess.run(["git", "init", "--quiet", "--bare", str(scratch)], check=True)
    fetched = subprocess.run(
        ["git", "fetch", "--quiet", "--depth=1", remote, PATTERNS_SOURCE_COMMIT],
        capture_output=True,
        cwd=scratch,
        check=False,
    )
    assert fetched.returncode == 0, fetched.stderr.decode()

    blob = subprocess.run(
        ["git", "cat-file", "blob", f"{PATTERNS_SOURCE_COMMIT}:config/patterns.yaml"],
        capture_output=True,
        cwd=scratch,
        check=True,
    )

    assert blob.stdout == Path(VENDORED_PATTERNS_PATH).read_bytes()


# --- performance -------------------------------------------------------------


def test_the_scan_is_fast_enough_to_run_per_chunk_on_a_stream():
    """The claim in the integration doc §5 that makes this usable inline.

    A per-chunk scan against Presidio over HTTP (~103 ms) is not viable; a
    per-chunk scan against a local regex engine is. Asserted with a wide
    margin -- this is a "still three orders of magnitude from a network call"
    check, not a benchmark.
    """
    import time

    scanner = _scanner()
    text = " ".join(BENIGN) + f" {VALID_RRN}"

    async def once():
        await scanner.scan([_span(text)])

    asyncio.run(once())
    started = time.perf_counter()
    for _ in range(50):
        asyncio.run(once())
    per_call = (time.perf_counter() - started) / 50

    assert per_call < 0.010, f"{per_call * 1000:.2f} ms per scan"
