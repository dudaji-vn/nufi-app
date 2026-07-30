"""LLM02 — Korean PII, matched locally against `nufi-security`'s rules.

Presidio is English-centric and blind to Korean national identifiers.
Measured against the running presidio-analyzer on 2026-07-29, with the entity
list G2a/G2b actually ship:

    제 주민등록번호는 900101-1234568 입니다   ->  []
    연락처는 010-1234-5678 입니다             ->  []
    계좌번호 110-1234-567890                  ->  []
    사업자등록번호는 220-81-62517             ->  PHONE_NUMBER 0.40  (below 0.50)

Four Korean identifiers, nothing actionable from Presidio on any of them. This
scanner is that gap closed, and it closes it with regex plus a checksum rather
than with a model: `900101-1234567` — the number the design doc nearly recorded
as a miss — is CORRECTLY not flagged, because its check digit is wrong.

Scanner contract, same as every other: take spans, return `Finding`s, decide
nothing. Their `Finding` — a different dataclass, with
`entity_type`/`text`/`source`/`conf_class` — is mapped to ours here and never
reaches `policy.py` (integration doc §6, risk 3).

Offsets
-------
Unlike `nufi_injection.py`, this scanner reports REAL offsets, because G2b
slices `span.text[start:end]` to redact and a drifted offset there means
corrupted output or leaked PII rather than a wrong test assertion. Two things
make that safe, and both were verified by running the library rather than by
reading its README:

* `KoreanPiiDetector.detect` yields `m.start()`/`m.end()` from
  `re.finditer(text)`, which are Python `str` character offsets. Measured on
  Korean text mixing Hangul, ASCII, a regional-indicator flag (🇰🇷, two astral
  code points) and 🎉, in both NFC and NFD: `text[start:end] == finding.text`
  in every case. The constructor re-proves it on every process start, so a
  library upgrade that changed this stops the proxy instead of redacting the
  wrong characters.
* The library's OTHER finding source does not have that property, which is why
  it is switched off below rather than merely unused. `DetectionPipeline.
  _confidential` matches against `normalize.normalize(text)` and reports
  offsets into THAT string; `normalize.py`'s own docstring says spans after
  normalisation "may differ from the original" and are for audit reference
  only, not for redaction. Its EDM findings are worse still — `start=0,
  end=0`. `enable_confidential=False`, and the per-finding offset check below
  is the second lock on the same door.

Text is scanned VERBATIM: no canonicalisation, no base64 decode. `injection.py`
and `nufi_injection.py` scan derived views because they only need to know THAT
something is there; this scanner has to say WHERE, and an offset into a decoded
payload does not address `span.text`. The honest consequence is the same gap
Presidio has today: PII inside a base64 blob is not caught by this control.

Failure
-------
Local and synchronous: no sidecar, no HTTP, no timeout, so it cannot fail from
connectivity the way `pii.py` can. What it CAN do is be absent or neutered — an
uninstalled library, a patterns file that loaded zero rules, a policy naming
entity types this engine can never produce — and every one of those presents as
"found no PII", which is this project's signature defect wearing the costume of
a clean scan. This one runs on every request and on every response, so the
constructor proves the engine both FIRES (on a checksum-valid RRN, with offsets
that slice back) and STAYS QUIET (on the same digits with a bad check digit)
before the proxy serves anything.
"""

from __future__ import annotations

import math
import os
import re
from pathlib import Path
from typing import Any

import yaml

from guardrails.scanners.base import ScannerUnavailable
from guardrails.types import Finding, Span, SpanSource

# Where the detection rules come from. `pip install nufi-egress` ships
# `egress_audit/` but NOT `config/` — the distribution's `packages` list in
# pyproject.toml names seven Python packages and no data directory — so
# `DetectionPipeline()` with no argument raises FileNotFoundError looking for
# `<site-packages>/config/patterns.yaml`. Reproduced against the pinned commit.
#
# So the rules are vendored here, byte-identical to the pinned commit's
# `config/patterns.yaml`, and shipped by the existing `COPY guardrails
# /app/guardrails` line in litellm/Dockerfile. One file, in git, visible in a
# diff, and identical in the image and in the test venv.
#
# The path is resolved to an ABSOLUTE path off this module's own location and
# handed to `DetectionPipeline` explicitly. Never their discovery: the library
# resolves its default from `Path(egress_audit.pipeline.__file__).parent.parent`,
# which lands wherever the package happens to be imported from — measured to
# succeed under `python -c` from a source checkout and fail for the identical
# code run as a script file, because `sys.path[0]` differs. A path that depends
# on how the process was started is not a path.
#
# Deliberately NOT installed at `/app/config`, which is where the library WOULD
# find it on its own given that `nufi-security` is copied into `/app`. Keeping
# it somewhere their discovery cannot reach means the explicit argument below is
# the only thing that works — so dropping it fails in the image too, not just in
# CI.
PATTERNS_PATH_ENV = "NUFI_PII_PATTERNS_PATH"
VENDORED_PATTERNS_PATH = str(Path(__file__).resolve().parent.parent / "nufi_patterns.yaml")

# Provenance of the vendored file, asserted by tests rather than trusted.
#
# `PATTERNS_SOURCE_COMMIT` must equal the `NUFI_SECURITY_COMMIT` pinned in
# litellm/Dockerfile and litellm/requirements.txt: bumping the library without
# refreshing the rules would leave the image running one version's code against
# another version's patterns, silently. `PATTERNS_SHA256` is the file's own
# digest, so an edit to a shipped security rule cannot pass as a no-op diff.
PATTERNS_SOURCE_COMMIT = "5eb9a027cbdd9c5d3142d4609782110a737c67e0"
PATTERNS_SHA256 = "7d425e01e1abc1cc1e3b171edefaec6336e4d240965b803d3f825928a0b5ac64"

# The two YAML sections `DetectionPipeline` turns into detectors. Every rule
# name under these keys is an entity type this scanner can produce, and nothing
# else is — which is what makes "policy named an entity that can never fire"
# detectable at construction rather than never.
_RULE_SECTIONS = ("korean_pii", "secrets")

# Their vocabulary, mapped to ours, for the entity types that mean the same
# thing as one of Presidio's. `Finding.entity` becomes the redaction label a
# user reads (`[PHONE_NUMBER]`), so two detectors that find the same kind of
# thing must not put two different words in the same answer. The Korean-only
# types have no Presidio equivalent and are carried through unchanged; their
# names satisfy `audit._safe_label`'s `^[A-Za-z0-9_.:-]{1,64}$` (verified
# against every name the vendored file declares, not assumed).
#
# Which ENGINE found it is not lost by this: `Finding.detector` is `nufi_pii`
# either way, and the audit event carries both fields.
_ENTITY_ALIASES = {
    "EMAIL": "EMAIL_ADDRESS",
    "KR_PHONE": "PHONE_NUMBER",
}

# `audit._safe_label`'s shape, restated here so a rule name that could not
# survive the audit trail is refused where the rules are loaded rather than
# quietly rewritten to "UNSAFE_LABEL" seven layers later.
_LABEL_SHAPE = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")

# The self-check pair. One 13-digit resident-registration number, twice, with
# only the final CHECK DIGIT different:
#
#   900101-1234568   valid   -> must be found, as KR_RRN
#   900101-1234567   invalid -> must find nothing at all
#
# The negative half is the one that carries the weight. A checksum is the whole
# reason this detector is more precise than a bare regex, and a test — or a
# canary — built on an invalid number asserts nothing: it would pass just as
# well against a detector that had stopped working. `900101-1234567` is the
# number the integration doc nearly recorded as a missed detection; it is
# supposed to be rejected, and pinning that here is what stops someone
# "fixing" the checksum away.
#
# The carrier text is deliberately mixed script — Hangul, ASCII, a
# regional-indicator flag (two astral code points) and an emoji — so the same
# call also proves the offsets are Python `str` offsets into the string that
# was scanned. That is the property G2b's redaction slices on, and the only
# place it can be proven cheaply is here, once per process, before the object
# is usable.
_CANARY_ENTITY = "KR_RRN"
_VALID_RRN = "900101-1234568"
_INVALID_RRN = "900101-1234567"
_CANARY_PREFIX = "🇰🇷 주민등록번호 Ana "
_CANARY_SUFFIX = " 확인 완료 🎉 ok"
_POSITIVE_CANARY = f"{_CANARY_PREFIX}{_VALID_RRN}{_CANARY_SUFFIX}"
_NEGATIVE_CANARY = f"{_CANARY_PREFIX}{_INVALID_RRN}{_CANARY_SUFFIX}"


def _load_rule_names(path: str) -> frozenset[str]:
    """Read the patterns file and return every entity type it can produce.

    Read here, by us, rather than left to the library. `DetectionPipeline`
    opens the file itself and would raise on a missing one, but it accepts a
    file whose `korean_pii:` key is absent, empty, or not a list without a
    word: `cfg.get("korean_pii", [])` becomes zero rules, `KoreanPiiDetector`
    compiles nothing, and `analyze()` returns `[]` for every input. A proxy
    that started cleanly would then report every request free of PII.

    The returned set is also what makes a policy typo loud — see
    `NufiPiiScanner.__init__`.
    """
    try:
        with open(path, encoding="utf-8") as handle:
            parsed = yaml.safe_load(handle)
    except OSError as exc:
        raise ScannerUnavailable(
            f"nufi_pii: patterns file {path!r} is unreadable: {exc}. It ships "
            "as litellm/guardrails/nufi_patterns.yaml via the Dockerfile's "
            "`COPY guardrails /app/guardrails`; G2a/G2b have no Korean PII "
            "coverage without it."
        ) from exc
    except yaml.YAMLError as exc:
        raise ScannerUnavailable(
            f"nufi_pii: patterns file {path!r} is not valid YAML: {exc}"
        ) from exc

    if not isinstance(parsed, dict):
        raise ScannerUnavailable(
            f"nufi_pii: patterns file {path!r} is not a YAML mapping "
            f"(got {type(parsed).__name__})"
        )

    names: set[str] = set()
    for section in _RULE_SECTIONS:
        rules = parsed.get(section)
        if rules is None:
            continue
        if not isinstance(rules, list):
            raise ScannerUnavailable(
                f"nufi_pii: patterns file {path!r} has a {section!r} key that "
                f"is {type(rules).__name__}, not a list. The library reads it "
                "as zero rules and reports nothing."
            )
        for rule in rules:
            if not isinstance(rule, dict) or not isinstance(rule.get("name"), str):
                raise ScannerUnavailable(
                    f"nufi_pii: patterns file {path!r} has a {section!r} entry "
                    f"with no string `name:` ({rule!r})"
                )
            name = rule["name"]
            if not _LABEL_SHAPE.match(name):
                # Would survive as far as the audit trail and be rewritten to
                # "UNSAFE_LABEL" there, or be rendered into a user's answer as
                # a redaction label. Refused where it is declared instead.
                raise ScannerUnavailable(
                    f"nufi_pii: patterns file {path!r} declares rule name "
                    f"{name!r}, which is not identifier-shaped and cannot be "
                    "carried in an audit event or a redaction label."
                )
            names.add(name)

    if not names:
        raise ScannerUnavailable(
            f"nufi_pii: patterns file {path!r} declares no rules under any of "
            f"{list(_RULE_SECTIONS)}. The library would load it as an engine "
            "that matches nothing and report every request clean."
        )
    return frozenset(names)


def _load_pipeline(patterns_path: str) -> Any:
    """Build the library's `DetectionPipeline`, or say why not.

    Imported from `nufi` rather than from `egress_audit.pipeline`:
    `nufi/__init__.py`'s `__all__` is the surface the library declares stable,
    and it is where the commit pinned in the Dockerfile promises compatibility.
    `Detector` is that module's name for `DetectionPipeline`.

    The import is not at module scope, for the reason
    `nufi_injection._load_detector` documents: at module scope an ImportError
    surfaces as "guardrails.scanners.nufi_pii could not be imported" — a
    traceback about our module for a fault that is entirely about a missing
    dependency.

    Three constructor arguments, each load-bearing:

    * `patterns_path` — explicit and absolute. See `VENDORED_PATTERNS_PATH`.
    * `enable_ner=False` — the NER channel is this library's KR_PERSON /
      KR_LOCATION recogniser, the exact counterpart of the Presidio PERSON and
      LOCATION recognizers this repo removed on 2026-07-29 for being unable to
      separate a true hit from a false one. Measured on the gazetteer backend
      over 26 benign sentences: `서울` flagged KR_LOCATION and `문의는`
      ("the inquiry is") flagged KR_PERSON. Its accurate backend needs a
      14.7 MB KoELECTRA ONNX model the image does not carry and must not
      download on a request path. Worse than either, the default
      `ner_backend="auto"` picks transformers-or-gazetteer depending on which
      packages happen to be importable, so the image and the test venv could
      silently run different detectors — a scanner whose behaviour depends on
      an unpinned coincidence is not a scanner.
    * `enable_confidential=False` — its findings carry offsets into a
      NORMALISED copy of the text, and G2b redacts by offset. See the module
      docstring.
    """
    try:
        from nufi import Detector
    except ImportError as exc:  # pragma: no cover - exercised by the mutation table
        raise ScannerUnavailable(
            "nufi_pii: the nufi-security package is not importable "
            f"({exc}). It is installed by litellm/Dockerfile's builder stage "
            "and by litellm/requirements.txt for the test venv; G2a/G2b have "
            "no Korean PII coverage without it."
        ) from exc

    try:
        return Detector(
            patterns_path=patterns_path,
            enable_ner=False,
            enable_confidential=False,
        )
    except Exception as exc:
        raise ScannerUnavailable(
            f"nufi_pii: could not construct the detector from {patterns_path!r}: "
            f"{type(exc).__name__}: {exc}"
        ) from exc


class NufiPiiScanner:
    name = "nufi_pii"
    risk = "LLM02"

    def __init__(
        self,
        entities: list[str],
        detector: Any | None = None,
        patterns_path: str | None = None,
    ) -> None:
        if patterns_path is None:
            patterns_path = os.environ.get(PATTERNS_PATH_ENV) or VENDORED_PATTERNS_PATH
        self.patterns_path = patterns_path

        # Read the rules first, so an unusable file is reported as an unusable
        # file rather than as whatever the library does with one.
        declared = _load_rule_names(patterns_path)

        if not isinstance(entities, list) or not entities:
            raise ScannerUnavailable(
                f"nufi_pii: entities must be a non-empty list of rule names, "
                f"got {entities!r}. An empty list is an engine that runs on "
                "every request and can never report anything."
            )
        requested = [str(entity) for entity in entities]
        unknown = sorted(set(requested) - declared)
        if unknown:
            # The quiet failure this guard exists for: policy.yaml naming an
            # entity type no rule produces. Every request would be scanned,
            # every result discarded by the filter, and the control would
            # report clean traffic forever. `enable_ner=False` makes KR_PERSON
            # and KR_LOCATION exactly this case, which is why the list of what
            # IS available is printed rather than just the mistake.
            raise ScannerUnavailable(
                f"nufi_pii: entities {unknown} are not declared by "
                f"{patterns_path!r}, so they could never be reported and the "
                f"configuration would be inert. Available: {sorted(declared)}. "
                "(KR_PERSON / KR_LOCATION come from the NER channel, which is "
                "deliberately disabled -- see _load_pipeline.)"
            )
        self._entities = frozenset(requested)
        self._declared = declared

        self._detector = detector if detector is not None else _load_pipeline(patterns_path)
        self._self_check()

    def _self_check(self) -> None:
        """Prove the engine fires, stays quiet, and reports usable offsets.

        Runs the FULL adapter path, not just `analyze`: the same strict field
        reads, bounds check, offset round-trip and entity mapping every real
        finding goes through. A stub left behind by a test helper, a rules file
        that compiled nothing, a library upgrade that renamed a field or moved
        to normalised offsets — each produces either nothing or something this
        rejects, and none of them can produce a scanner that looks healthy.

        Costs two regex passes over two short strings (~0.1 ms measured), once
        per process.
        """
        found = self._findings(
            _POSITIVE_CANARY, SpanSource.USER, frozenset({_CANARY_ENTITY})
        )
        if not found:
            raise ScannerUnavailable(
                f"nufi_pii: the detector found no {_CANARY_ENTITY} in a known "
                f"Korean resident-registration number ({_VALID_RRN}). Its rules "
                "did not load, so it would report every request and every "
                "response free of Korean PII."
            )
        matched = _POSITIVE_CANARY[found[0].start : found[0].end]
        if matched != _VALID_RRN:
            # Unreachable through `_findings`, which already refuses a finding
            # whose offsets do not slice back to its own matched text. Asserted
            # anyway, against the LITERAL we control rather than against the
            # library's own report of what it matched: if a future version
            # returned offsets into a normalised copy AND a `text` field taken
            # from that same copy, the two would agree with each other and
            # disagree with reality. G2b would then redact the wrong
            # characters. This is the only check that compares against
            # something the library did not produce.
            raise ScannerUnavailable(
                f"nufi_pii: canary offsets {found[0].start}:{found[0].end} "
                f"select {matched!r}, not {_VALID_RRN!r}. The detector's "
                "offsets do not address the string that was scanned, and G2b "
                "redacts by character span."
            )

        # No entity filter here: the invalid number must be rejected by EVERY
        # rule, not merely by the one the positive canary exercised. A rule
        # that started matching it under some other entity type would still be
        # a checksum that had stopped working.
        rejected = self._analyze(_NEGATIVE_CANARY)
        if rejected:
            raise ScannerUnavailable(
                f"nufi_pii: the detector reported {[f.entity_type for f in rejected]} "
                f"on a resident-registration number with an INVALID check digit "
                f"({_INVALID_RRN}). Its checksum validation is not running, so "
                "its precision is that of a bare 13-digit regex -- and G2b "
                "redacts, so that lands in users' answers."
            )

    async def scan(self, spans: list[Span]) -> list[Finding]:
        """One `Finding` per match, with offsets into that span's own text.

        Scanned PER SPAN, never on concatenated text, for the same reason
        `pii.py` is: `start`/`end` have to stay meaningful character offsets
        into the string a caller will slice.
        """
        findings: list[Finding] = []
        for span in spans:
            if not span.text:
                continue
            findings.extend(self._findings(span.text, span.source, self._entities))
        return findings

    def _findings(
        self, text: str, source: SpanSource, entities: frozenset[str]
    ) -> list[Finding]:
        """The boundary. Their dataclass stops here.

        Every field is read strictly and a malformed one raises rather than
        being defaulted. `float(getattr(item, "score", 0.0))` would turn a
        library upgrade that renamed the attribute into a scanner that scores
        every match 0.0 — below every threshold, so real PII would read as "we
        looked and it was fine" at the exact moment the adapter stopped
        working.
        """
        out: list[Finding] = []
        for item in self._analyze(text):
            try:
                entity = str(item.entity_type)
            except AttributeError as exc:
                raise ScannerUnavailable(
                    f"nufi_pii: finding has no entity_type: {item!r}"
                ) from exc

            # Filtered before anything else is read. The entity list is the
            # real control over what this scanner can report -- more so than
            # any threshold, because a rule's score says how it was matched
            # (0.99 checksum, 0.85 regex) and not how likely it is to be
            # right. Measured on realistic machine identifiers: KR_ACCOUNT
            # fires on 100% of ISO-8601 dates, KR_BRN on ~10% of bare 10-digit
            # numbers including Unix timestamps. Which of those a deployment
            # accepts is a policy question, and it lives in policy.yaml.
            if entity not in entities:
                continue

            try:
                score = float(item.score)
                start = int(item.start)
                end = int(item.end)
                matched = item.text
            except (AttributeError, TypeError, ValueError) as exc:
                raise ScannerUnavailable(
                    f"nufi_pii: malformed finding for {entity}: {item!r}"
                ) from exc

            # NaN and infinity both survive float(). `nan >= threshold` is
            # always False in policy.decide, so a corrupted score would read as
            # "definitely safe" -- an outage must not present as a clean
            # verdict. Same guard, same reason, as pii.py and nufi_injection.py.
            if not math.isfinite(score):
                raise ScannerUnavailable(f"nufi_pii: non-finite score {score!r}")

            # Strict `<`, not `<=`: a zero-width finding cannot be redacted and
            # is not a location in the text. It is also the shape the library's
            # confidential/EDM channels produce (`start=0, end=0`), which carry
            # normalised-view offsets that must never reach G2b even if a
            # future version routes them through `analyze`.
            if not (0 <= start < end <= len(text)):
                raise ScannerUnavailable(
                    f"nufi_pii: {entity} offsets [{start}:{end}] are not a "
                    f"usable slice of a {len(text)}-character string"
                )

            # The offset contract, checked on every finding rather than assumed
            # from the constructor's canary. `matched` is the substring the
            # library says it matched; if the offsets address a different
            # string -- a normalised copy, a decoded payload -- these disagree.
            # G2b would otherwise redact whatever happened to sit at those
            # coordinates: corrupted output, or PII left in place, neither of
            # which raises anything on its own.
            if not isinstance(matched, str) or text[start:end] != matched:
                raise ScannerUnavailable(
                    f"nufi_pii: {entity} offsets [{start}:{end}] select "
                    f"{text[start:end]!r} but the finding reports {matched!r}. "
                    "The offsets do not address the text that was scanned."
                )

            out.append(
                Finding(
                    risk=self.risk,
                    detector=self.name,
                    score=score,
                    source=source,
                    start=start,
                    end=end,
                    entity=_ENTITY_ALIASES.get(entity, entity),
                )
            )
        return out

    def _analyze(self, text: str) -> list[Any]:
        try:
            results = self._detector.analyze(text)
        except Exception as exc:
            raise ScannerUnavailable(
                f"nufi_pii: detector raised {type(exc).__name__}: {exc}"
            ) from exc

        if not isinstance(results, list):
            raise ScannerUnavailable(
                "nufi_pii: detector returned "
                f"{type(results).__name__}, expected a list of findings"
            )
        return results
