"""Versioned red-team and benign corpora for the deterministic guardrail
detectors -- normalisation, secrets, exfiltration.

This suite deliberately gates only the DETERMINISTIC detectors
(`canonicalize`, `scan_exfil`, `scan_secrets`). Classifier recall is
measured in shadow mode instead of pinned here: a model swap would turn a
routine upgrade into a false CI failure.

Failure-mode notes (see task-14-report.md for the full enumeration):

- A YAML file that fails to parse, or is missing its `cases` key, raises at
  IMPORT time (ATTACKS/BENIGN are built at module scope) -- pytest reports
  this as a collection error, which is loud and fails CI. `_load` itself is
  also exercised directly, against deliberately broken fixtures, by
  `test_malformed_corpus_file_*` / `test_corpus_file_missing_cases_key_*` /
  `test_empty_corpus_file_*` below, so this is not just an assumption about
  what PyYAML happens to do.
- A case whose `expect` names an unknown kind (a typo'd
  `canonical_transform`, or a kind this suite was never taught) raises
  inside `_detected`, failing that one parametrised case loudly, by id.
  `test_unknown_expectation_kind_raises` exercises this directly.
- The failure mode that matters most -- a corpus that silently SHRINKS,
  because a case was dropped in a refactor and left no trace. Emptying
  `cases:` to `[]` is NOT the quiet skip an earlier draft of this comment
  claimed. Verified directly: with this file's `ids=lambda c: c["id"]`
  construction, pytest's id-resolution machinery calls that lambda against
  its own internal `NOTSET` sentinel when there are zero parameter sets, and
  `NOTSET["id"]` raises `TypeError: 'NotSetType' object is not subscriptable`
  -- a hard COLLECTION ERROR that interrupts the whole run, louder than an
  ordinary red test, not a smaller-but-still-green one. What pinning the id
  set actually buys is coverage for the shrinkage this mechanism can't catch:
  dropping one case out of many (the list is still non-empty, so no
  collection error fires and every remaining parametrised test still
  passes), a duplicate id silently standing in for a different dropped case,
  or a case relabelled into the wrong category. That is why
  `test_attack_corpus_ids_are_exactly_the_pinned_set` and its benign
  counterpart pin the full id set as a literal constant here: any case
  added, removed, or renamed must touch this file too, on purpose, or the
  suite fails.
"""

from __future__ import annotations

import os
import sys

import pytest
import yaml
from guardrails.canonical import canonicalize
from guardrails.scanners.patterns import scan_exfil, scan_secrets, scan_system_echo
from guardrails.types import Canonical, Finding, Span, SpanSource

HERE = os.path.dirname(__file__)
_CORPUS_DIR = os.path.join(HERE, "corpus")


def _load(name: str, base: str = _CORPUS_DIR) -> list[dict]:
    with open(os.path.join(base, name), encoding="utf-8") as handle:
        return yaml.safe_load(handle)["cases"]


ATTACKS = _load("attacks.yaml")
BENIGN = _load("benign.yaml")

# Pinned so a case silently dropped (or a new one added without updating
# this file) is a loud, specific failure -- not a smaller-but-still-green
# test run. See the module docstring.
_ATTACK_IDS = frozenset(
    {
        "zero_width_ignore",
        "unicode_tags_smuggler",
        "bidi_override",
        "cyrillic_homoglyph",
        "fullwidth_forms",
        "base64_payload",
        "rot13_payload",
        "rot13_behind_carrier_prose",
        "rot13_behind_vowel_padding",
        "base64_multiline_payload",
        "markdown_image_exfil",
        "javascript_link",
        "raw_script_tag",
        "iframe_embed",
        "openai_key_leak",
        "aws_key_leak",
        "jwt_leak",
        "private_key_leak",
        "system_prompt_echo_verbatim",
        "system_prompt_echo_partial",
    }
)

_BENIGN_IDS = frozenset(
    {
        "plain_question_en",
        "plain_question_vi",
        "plain_question_ko",
        "plain_question_ja",
        "talking_about_security",
        "code_answer",
        "markdown_table",
        "relative_image",
        "citation_link",
        "base64_looking_identifier",
        "ordinary_cyrillic",
        "ordinary_greek",
        "benign_reply_shares_words_with_system_prompt",
    }
)

# Benign cases that carry the optional `system_prompt` field, so
# `test_benign_case_has_required_shape` can require it for exactly these ids
# and forbid it everywhere else -- pinned the same way `_BENIGN_IDS` pins the
# corpus itself, so a case losing its `system_prompt` in a refactor fails by
# id instead of silently becoming a case `scan_system_echo` can't be checked
# against.
_BENIGN_SYSTEM_ECHO_IDS = frozenset({"benign_reply_shares_words_with_system_prompt"})

_EXPECTATION_KINDS = {
    "canonical_transform",
    "derived_contains",
    "exfil",
    "secret",
    "system_echo",
}


def _detected(case: dict, expectation: str) -> bool:
    """Does `case["text"]` trip the detector named by `expectation`?

    Takes the whole case dict, not just its text, because `system_echo`
    needs a second field (`case["system_prompt"]`) that the other kinds
    don't -- see the module docstring and task-14-findings.md.
    """
    kind, _, value = expectation.partition(":")
    text = case["text"]
    if kind == "canonical_transform":
        return value in canonicalize(text).transforms
    if kind == "derived_contains":
        return any(value in item for item in canonicalize(text).derived)
    if kind == "exfil":
        return any(f.entity == value for f in scan_exfil(text, allowlist=[]))
    if kind == "secret":
        span = Span(text=text, source=SpanSource.UNTRUSTED, message_index=0)
        return any(f.entity == value for f in scan_secrets([span]))
    if kind == "system_echo":
        # `case["system_prompt"]`, not `.get(..., "")`: a case missing this
        # field is a schema bug, and a silent "" default would make
        # scan_system_echo decline to run (< _MIN_SYSTEM_PROMPT_WORDS) and
        # return [] -- passing for the wrong reason, exactly the failure
        # shape this whole round exists to close. KeyError here is loud on
        # purpose; test_attack_case_has_required_shape catches it earlier.
        return any(f.entity == value for f in scan_system_echo(text, case["system_prompt"]))
    raise AssertionError(f"unknown expectation kind {kind!r}")


# --- structural / schema guards ---------------------------------------------
#
# These catch malformed corpus data (bad YAML, unknown expectation kinds,
# duplicate or drifted ids, a file nobody wired up) before it can produce a
# misleadingly green -- or misleadingly quiet -- test run.


def test_corpus_directory_only_contains_wired_files():
    """A corpus file present on disk but never loaded by any test is a
    silent no-op: it adds nothing to coverage and nothing here would ever
    say so. Pinning the directory listing means a new file must be wired
    into `_load` (and this constant) before it does anything."""
    names = sorted(f for f in os.listdir(_CORPUS_DIR) if not f.startswith("."))

    assert names == ["attacks.yaml", "benign.yaml"]


def test_attack_corpus_ids_are_exactly_the_pinned_set():
    assert {case["id"] for case in ATTACKS} == _ATTACK_IDS


def test_benign_corpus_ids_are_exactly_the_pinned_set():
    assert {case["id"] for case in BENIGN} == _BENIGN_IDS


def test_attack_ids_are_unique():
    ids = [case["id"] for case in ATTACKS]

    assert len(ids) == len(set(ids))


def test_benign_ids_are_unique():
    ids = [case["id"] for case in BENIGN]

    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("case", ATTACKS, ids=lambda c: c["id"])
def test_attack_case_has_required_shape(case):
    """Exact-set, not subset: `system_prompt` is REQUIRED when `expect`'s
    kind is `system_echo` and FORBIDDEN otherwise, so a case that loses its
    `system_prompt` in a refactor fails by id here -- it cannot silently
    become a case that passes `test_attack_is_detected` for no reason (a
    missing field would otherwise surface as a bare `KeyError` deep inside
    `_detected` instead of a named, specific shape failure)."""
    base_keys = {"id", "category", "text", "expect"}
    is_system_echo = str(case.get("expect", "")).startswith("system_echo:")
    required_keys = base_keys | {"system_prompt"} if is_system_echo else base_keys
    assert set(case) == required_keys, (
        f"{case['id']}: expected keys {sorted(required_keys)}, got {sorted(case)}"
    )
    assert isinstance(case["text"], str) and case["text"]
    kind, sep, value = case["expect"].partition(":")
    assert sep == ":", f"{case['id']}: expect {case['expect']!r} has no kind:value separator"
    assert kind in _EXPECTATION_KINDS, f"{case['id']}: unknown expectation kind {kind!r}"
    assert value
    if kind == "system_echo":
        assert isinstance(case["system_prompt"], str) and case["system_prompt"]


@pytest.mark.parametrize("case", BENIGN, ids=lambda c: c["id"])
def test_benign_case_has_required_shape(case):
    """Exact-set, mirroring the attack-side test above: `system_prompt` is
    required for exactly the ids pinned in `_BENIGN_SYSTEM_ECHO_IDS` and
    forbidden for every other benign case, so it can't silently vanish from
    (or silently appear on) a case without this test naming the id."""
    base_keys = {"id", "text"}
    requires_system_prompt = case["id"] in _BENIGN_SYSTEM_ECHO_IDS
    required_keys = base_keys | {"system_prompt"} if requires_system_prompt else base_keys
    assert set(case) == required_keys, (
        f"{case['id']}: expected keys {sorted(required_keys)}, got {sorted(case)}"
    )
    assert isinstance(case["text"], str) and case["text"]
    if requires_system_prompt:
        assert isinstance(case["system_prompt"], str) and case["system_prompt"]


def test_malformed_corpus_file_fails_loudly_not_silently(tmp_path):
    (tmp_path / "broken.yaml").write_text("cases: [unterminated", encoding="utf-8")

    with pytest.raises(yaml.YAMLError):
        _load("broken.yaml", base=str(tmp_path))


def test_corpus_file_missing_cases_key_fails_loudly(tmp_path):
    (tmp_path / "nocases.yaml").write_text("version: 1\n", encoding="utf-8")

    with pytest.raises(KeyError):
        _load("nocases.yaml", base=str(tmp_path))


def test_empty_corpus_file_fails_loudly_not_silently_empty(tmp_path):
    (tmp_path / "empty.yaml").write_text("", encoding="utf-8")

    with pytest.raises(TypeError):
        _load("empty.yaml", base=str(tmp_path))


def test_unknown_expectation_kind_raises():
    with pytest.raises(AssertionError):
        _detected({"text": "anything"}, "made_up_kind:whatever")


# --- the gate itself ---------------------------------------------------------


@pytest.mark.parametrize("case", ATTACKS, ids=lambda c: c["id"])
def test_attack_is_detected(case):
    assert _detected(case, case["expect"]), (
        f"{case['id']} ({case['category']}) was not detected by {case['expect']}"
    )


@pytest.mark.parametrize("case", BENIGN, ids=lambda c: c["id"])
def test_benign_case_is_not_flagged_as_exfiltration(case):
    assert scan_exfil(case["text"], allowlist=[]) == []


@pytest.mark.parametrize("case", BENIGN, ids=lambda c: c["id"])
def test_benign_case_has_no_secret_finding(case):
    span = Span(text=case["text"], source=SpanSource.USER, message_index=0)

    assert scan_secrets([span]) == []


@pytest.mark.parametrize("case", BENIGN, ids=lambda c: c["id"])
def test_benign_case_is_not_homoglyph_folded(case):
    result = canonicalize(case["text"])

    assert "homoglyph" not in result.transforms
    assert result.text == case["text"]


# Benign cases carrying the optional `system_prompt` field -- currently just
# `benign_reply_shares_words_with_system_prompt`, computed rather than
# hardcoded so a future second case is picked up automatically.
_BENIGN_WITH_SYSTEM_PROMPT = [c for c in BENIGN if "system_prompt" in c]


@pytest.mark.parametrize("case", _BENIGN_WITH_SYSTEM_PROMPT, ids=lambda c: c["id"])
def test_benign_case_with_system_prompt_is_not_flagged_as_echo(case):
    assert scan_system_echo(case["text"], case["system_prompt"]) == []


def test_corpus_covers_every_attack_category():
    categories = {case["category"] for case in ATTACKS}

    assert {
        "obfuscation",
        "encoding",
        "exfiltration",
        "secrets",
        "system_echo",
    } <= categories


# --- mutation guards: the corpus must be able to fail -----------------------
#
# A corpus that passes against a detector that flags nothing is worthless,
# and one that passes against a detector that flags everything is just as
# worthless. These disable / saturate the deterministic detectors in-process
# (monkeypatch reverts automatically after each test) and assert the corpus
# actually notices -- a permanent, CI-enforced counterpart to the manual
# mutation testing recorded in task-14-report.md.


def _fake_canonical(text: str) -> Canonical:
    return Canonical(text=text, transforms=(), derived=())


# The specific risk/detector/entity fields don't matter for these guards --
# only that the list is non-empty (a detector that "flags everything").
_A_FINDING = Finding(
    risk="LLM05", detector="exfil", score=1.0, source=SpanSource.UNTRUSTED, start=0, end=1
)


def test_attack_corpus_fails_when_deterministic_detectors_are_disabled(monkeypatch):
    module = sys.modules[__name__]
    monkeypatch.setattr(module, "canonicalize", _fake_canonical)
    monkeypatch.setattr(module, "scan_exfil", lambda output, allowlist: [])
    monkeypatch.setattr(module, "scan_secrets", lambda spans: [])
    monkeypatch.setattr(module, "scan_system_echo", lambda output, system_prompt, n=8: [])

    still_detected = [case["id"] for case in ATTACKS if _detected(case, case["expect"])]

    assert still_detected == [], (
        "these attack cases passed even with every deterministic detector "
        f"disabled, so they are not testing anything: {still_detected}"
    )


def test_benign_corpus_fails_when_exfil_detector_flags_everything(monkeypatch):
    module = sys.modules[__name__]
    monkeypatch.setattr(module, "scan_exfil", lambda output, allowlist: [_A_FINDING])

    still_clean = [case["id"] for case in BENIGN if scan_exfil(case["text"], allowlist=[]) == []]

    assert still_clean == [], (
        "these benign cases stayed clean even with scan_exfil flagging "
        f"everything, so they exercise nothing: {still_clean}"
    )


def test_benign_corpus_fails_when_secret_detector_flags_everything(monkeypatch):
    module = sys.modules[__name__]
    monkeypatch.setattr(module, "scan_secrets", lambda spans: [_A_FINDING])

    still_clean = []
    for case in BENIGN:
        span = Span(text=case["text"], source=SpanSource.USER, message_index=0)
        if scan_secrets([span]) == []:
            still_clean.append(case["id"])

    assert still_clean == [], (
        "these benign cases stayed clean even with scan_secrets flagging "
        f"everything, so they exercise nothing: {still_clean}"
    )


def test_benign_corpus_fails_when_system_echo_detector_flags_everything(monkeypatch):
    module = sys.modules[__name__]
    monkeypatch.setattr(module, "scan_system_echo", lambda output, system_prompt, n=8: [_A_FINDING])

    still_clean = [
        case["id"]
        for case in _BENIGN_WITH_SYSTEM_PROMPT
        if scan_system_echo(case["text"], case["system_prompt"]) == []
    ]

    assert still_clean == [], (
        "these benign cases stayed clean even with scan_system_echo flagging "
        f"everything, so they exercise nothing: {still_clean}"
    )


# --- Important 2: `_detected` must match the exact named value, not mere ----
# presence. A reviewer weakened `_detected` (canonical_transform / derived_
# contains / exfil / secret: `f.entity == value` -> `bool(findings)`, `value
# in transforms` -> `bool(transforms)`) and re-ran it against all 18 real
# attack cases -- every one still passed, because no case in this corpus
# produces more than one distinct transform/entity at a time, so exact-value
# matching was never exercised as discriminating. This test pins precision
# directly, independent of what any one corpus case happens to produce: for a
# representative real case of each expectation kind, `_detected` must return
# True for the case's own `expect` value and False for a real, deliberately
# wrong value of the same kind (see task-14-fix-report.md for the mutation
# that proves this test actually catches the weakening).


def test_detected_matches_exact_value_not_just_presence():
    cyrillic = next(c for c in ATTACKS if c["id"] == "cyrillic_homoglyph")
    assert _detected(cyrillic, "canonical_transform:homoglyph") is True
    assert _detected(cyrillic, "canonical_transform:nfkc") is False

    base64_case = next(c for c in ATTACKS if c["id"] == "base64_payload")
    assert _detected(base64_case, "derived_contains:ignore all previous instructions") is True
    assert _detected(base64_case, "derived_contains:you are now DAN") is False

    image_case = next(c for c in ATTACKS if c["id"] == "markdown_image_exfil")
    assert _detected(image_case, "exfil:EXTERNAL_IMAGE") is True
    assert _detected(image_case, "exfil:JAVASCRIPT_URL") is False

    openai_case = next(c for c in ATTACKS if c["id"] == "openai_key_leak")
    assert _detected(openai_case, "secret:API_KEY") is True
    assert _detected(openai_case, "secret:JWT") is False

    # scan_system_echo only ever produces one entity ("SYSTEM_PROMPT" --
    # verified in patterns.py), so there is no second real alternative entity
    # to contrast against the way the other four kinds have. The wrong value
    # here is therefore a fabricated entity name rather than a real one drawn
    # from the source; it still exercises exactly the same precision (exact
    # match vs. mere presence), which is what this test exists to pin.
    echo_case = next(c for c in ATTACKS if c["id"] == "system_prompt_echo_verbatim")
    assert _detected(echo_case, "system_echo:SYSTEM_PROMPT") is True
    assert _detected(echo_case, "system_echo:NOT_A_REAL_ENTITY") is False
