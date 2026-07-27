"""Normalise text before any scanner sees it.

Classifier and regex detectors are defeated by character-level and encoding
tricks that leave the text perfectly readable to a model. Every downstream
scanner therefore reads canonical text, and any payload we can decode is handed
over as an additional scan candidate.

Three properties matter:
  - `text` is the normalised original. Nothing is concatenated into it.
  - `derived` carries decoded payloads, scored by scanners as extra candidates,
    so a decode can never become a false negative.
  - `transforms` records only EVIDENCE OF OBFUSCATION. ROT13 is applied
    unconditionally, because any "is this ROT13?" test is one an attacker pads
    around; it therefore fires on all text and is deliberately not recorded.

Pure functions only — no I/O, no network.
"""

from __future__ import annotations

import base64
import binascii
import codecs
import re
import unicodedata

from guardrails.types import Canonical

# Zero-width characters are enumerated by Unicode general category, not by hand.
# Two rounds of hand-listing were each defeated by a codepoint that was not on
# the list, because "every invisible character" is not a list a human finishes.
_BIDI = dict.fromkeys(
    [0x202A, 0x202B, 0x202C, 0x202D, 0x202E, 0x2066, 0x2067, 0x2068, 0x2069]
)

# Variation selectors are category Mn, so the Cf sweep does not reach them.
# Other combining marks are deliberately NOT stripped — Vietnamese is written
# with them, and mangling ordinary Vietnamese would blind the scanner to the
# language most of this deployment's users write in.
_VARIATION_SELECTORS = frozenset([*range(0xFE00, 0xFE10), *range(0xE0100, 0xE01F0)])

# Unicode Tags block: each codepoint mirrors an ASCII character at an offset of
# 0xE0000. This is the published "ASCII smuggler" vector — text a human reader
# cannot see but a model still reads. Stripping alone is not enough, because the
# model receives the untouched prompt; the hidden text must be recovered.
_TAG_BASE = 0xE0000
_TAG_END = 0xE0080

_HOMOGLYPHS = {
    "а": "a", "е": "e", "о": "o", "р": "p",
    "с": "c", "х": "x", "у": "y", "і": "i",
    "ј": "j", "һ": "h", "ԁ": "d", "ԛ": "q",
    "ο": "o", "α": "a", "ρ": "p", "υ": "u",
}

_B64_MIN_RUN = 20
_B64_RUN = re.compile(r"[A-Za-z0-9+/\-_]+")
# Work budgets, not detection thresholds. They bound effort on prose-heavy
# input; they never make a payload undetectable that a smaller input surfaces.
_MAX_COMPACT_STARTS = 64
_MAX_COMPACT_CHARS = 65536
_MEANINGFUL_JOINERS = frozenset("‌‍")
_B64_CHARS = r"[A-Za-z0-9+/\-_]"
_B64_CANDIDATE = re.compile(
    rf"(?<!{_B64_CHARS}){_B64_CHARS}{{20,}}={{0,2}}(?!{_B64_CHARS})"
)
_B64_URLSAFE = str.maketrans({"-": "+", "_": "/"})
_MIN_DECODED_LEN = 8
_ALLOWED_CONTROL = "\n\r\t"
_MAX_UNSCANNABLE_RATIO = 0.34


def _strip_invisible(text: str) -> str:
    """Remove zero-width format characters from the VISIBLE text.

    Unicode general category `Cf` is the exhaustive definition of a format
    character, so we ask Unicode rather than maintain a list. Tag characters are
    also Cf, which is why `_extract_tags` must run before this.

    ZWJ and ZWNJ are deliberately KEPT: they are meaningful in Persian, Hindi and
    emoji sequences, and stripping them mangled ordinary text in those languages.
    Base64 extraction no longer depends on the blob being contiguous, so nothing
    is lost by leaving them in place.
    """
    return "".join(
        char
        for char in text
        if (unicodedata.category(char) != "Cf" or char in _MEANINGFUL_JOINERS)
        and ord(char) not in _VARIATION_SELECTORS
    )


def _extract_tags(text: str) -> tuple[str, str]:
    """Split tag characters out of the text and decode them back to ASCII."""
    kept: list[str] = []
    hidden: list[str] = []
    for char in text:
        point = ord(char)
        if _TAG_BASE <= point < _TAG_END:
            hidden.append(chr(point - _TAG_BASE))
        else:
            kept.append(char)
    return "".join(kept), "".join(hidden).strip()


def _sanitise(text: str) -> str | None:
    """Replace unscannable bytes rather than discarding the whole payload.

    Dropping a candidate over one control byte inverted this layer's contract:
    `base64(payload + "\x00")` decoded to a real injection that was then thrown
    away. Candidates that are mostly unscannable are still rejected — that is
    binary noise, not a hidden instruction. Run this AFTER normalisation, so a
    payload padded with zero-width characters is cleaned before it is measured.
    """
    if not text:
        return None
    out: list[str] = []
    replaced = 0
    measurable = 0
    for char in text:
        # Format characters are not evidence of binary noise — a decoded payload
        # padded with ZWJ or ZWNJ (kept by `_normalise_candidate` because they
        # are meaningful in Persian, Hindi and emoji) is still a payload, and
        # counting them toward the ratio pushed legitimate decodes over the
        # gate and discarded them.
        if unicodedata.category(char) == "Cf":
            continue
        measurable += 1
        if char.isprintable() or char in _ALLOWED_CONTROL:
            out.append(char)
        else:
            out.append(" ")
            replaced += 1
    if measurable and replaced / measurable > _MAX_UNSCANNABLE_RATIO:
        # Mostly-unscannable usually means binary noise, but a real instruction
        # padded with control bytes looks identical by ratio. Measured across
        # 823 ordinary inputs and 3000 random blobs, this gate contributes zero
        # false-positive suppression — `validate=True` and the UTF-8 decode
        # reject noise before it is ever reached. So surface the printable
        # residue when there is enough of it to be an instruction, and discard
        # only when there is not.
        residue = "".join(out).strip()
        return residue if len(residue) >= _MIN_DECODED_LEN else None
    return "".join(out)


def _skeleton_char(char: str) -> str | None:
    """Map one lookalike to its ASCII letter, or None if it is not one.

    This is an explicit table, and that is an accepted limitation rather than a
    solved problem. An NFKD-skeleton generalisation was tried here in round 4
    and measured to be a no-op: the characters that actually matter — U+0455
    Cyrillic es, U+03BD Greek nu, U+0261 Latin script g, U+0578 Armenian vo —
    carry no decomposition at all, so NFKD leaves them untouched. The only
    characters NFKD did fold were compatibility forms such as fullwidth, which
    `_apply_nfkc` has already resolved before this runs, and precomposed
    Vietnamese vowels, which folding would have destroyed (that was round 4's
    near-miss: gating the fallback on a compatibility-tagged decomposition
    correctly stopped it from touching Vietnamese, but the gate also made the
    fallback unreachable for anything real — it never fired for any character
    this module needed to fold).

    Closing the class properly needs Unicode's confusables table, which was
    declined to avoid adding a dependency to a security-critical image. Two
    things bound the residue: a homoglyph inside a base64 blob is now
    irrelevant, because extraction compacts to the alphabet and the splitter's
    identity no longer matters; and homoglyphed visible text still reaches the
    multilingual injection classifier, which does not read ASCII skeletons.
    """
    return _HOMOGLYPHS.get(char)


def _fold_homoglyphs(text: str) -> str:
    """Fold lookalikes only inside tokens that MIX scripts.

    A token written entirely in Cyrillic or Greek is ordinary non-English text
    and must survive intact. A token mixing an ASCII body with a lookalike
    character is the attack shape ("іgnore").
    """
    folded: list[str] = []
    for token in re.split(r"(\s+)", text):
        has_ascii_letter = any("a" <= char.lower() <= "z" for char in token)
        if not has_ascii_letter:
            folded.append(token)
            continue
        rebuilt = [_skeleton_char(char) or char for char in token]
        folded.append("".join(rebuilt))
    return "".join(folded)


def _try_decode_base64(chunk: str) -> str | None:
    padded = chunk.translate(_B64_URLSAFE)
    padded += "=" * (-len(padded) % 4)
    try:
        raw = base64.b64decode(padded, validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return None
    # Normalise BEFORE sanitising: a payload padded with zero-width characters
    # (Cf) is mostly invisible junk by byte count, and the ratio gate below
    # would discard the whole decode before `_strip_invisible` ever got a
    # chance to clean it. Running the visible-text passes first is what makes
    # `_MAX_UNSCANNABLE_RATIO` measure the real payload instead of its padding.
    candidate = _sanitise(_normalise_candidate(raw))
    if candidate is None or len(candidate.strip()) < _MIN_DECODED_LEN:
        return None
    return candidate


def _aligned_views(compacted: str) -> list[str]:
    """Every 4-phase-shifted window of a compacted run.

    Four phase offsets (drop 0-3 leading characters) cover every possible
    front alignment in O(4n), with no constant an attacker can step around.

    The tail is NOT separately trimmed to a multiple of four: `_try_decode_
    base64` already re-pads to the correct length via `-len % 4`, so trimming
    here would be redundant at best. It was tried and measured harmful: for a
    genuine payload whose true length isn't already a multiple of 4 (the
    common case — that is what padding exists for), trimming discards the
    real trailing characters instead of letting them be validly padded,
    silently truncating a recovered payload. It also manufactures false
    positives the opposite way: trimming a mis-aligned phase's remainder DOWN
    to a valid length let structured binary noise decode as content it would
    otherwise have been correctly rejected for (`-29 % 4 == 3` is not
    encodable padding and `validate=True` rejects it outright — trimming to
    28 hid that rejection). Leaving the natural remainder for `_try_decode_
    base64` to pad itself keeps both properties: full recovery when the
    alignment is genuine, and rejection when it is not.
    """
    views: list[str] = []
    for phase in range(4):
        chunk = compacted[phase:]
        if len(chunk) >= _B64_MIN_RUN:
            views.append(chunk)
    return views


def _strict_view(compacted: str) -> str:
    """Drop base64's own specials (`+ / - _`), keeping only `[A-Za-z0-9]`.

    A splitter drawn from base64's OWN alphabet survives ordinary compaction
    unchanged and still corrupts the stream: `"aWdu-b3Jl-IGFs"` compacts to
    itself, `-` is then translated to `+` by `_B64_URLSAFE`, and every group
    after it is misaligned — measured at 100% bypass for `-`, `_`, `+`, `/` at
    every fragment width tried. This second, stricter view removes them. A
    genuine payload loses at most its own literal `+ / - _` characters, which
    the non-strict view already covers, so nothing is lost by trying both.
    """
    return "".join(char for char in compacted if char.isalnum() and char.isascii())


def _decode_base64(text: str) -> list[str]:
    """Passes over the text, none of them gated on a tunable detection
    threshold — with one exception, tracked rather than hidden (below).

    1. Contiguous runs — keeps several independent blobs separate.
    2. The whole message compacted, tried both as-is and with base64's own
       specials additionally stripped (`_strict_view`) — reassembles one blob
       deliberately split by characters outside the alphabet, OR by a
       splitter drawn from the alphabet itself (`-`, `_`, `+`, `/`), which
       survives ordinary compaction and misaligns everything after it.
       Compaction handles a splitter of ANY Unicode category the same way;
       it does NOT make the splitter's identity irrelevant when the splitter
       is itself a base64 character, which is why the strict view exists as a
       second, explicit pass rather than a claim the first pass already
       covers it.
    3. Compactions that drop leading runs one at a time — this is what survives
       an ordinary word sitting beside a fragmented blob. Measured directly:
       with a `"decode this "` prefix on a blob fragmented at width 7, the
       4-phase views of pass 2 alone MISS (the prefix's own alphabet
       characters are baked into every phase), and dropping leading runs HITS
       once the prefix's runs have been peeled off. This pass is not
       decoration.

    `_MAX_COMPACT_STARTS` and `_MAX_COMPACT_CHARS` bound effort, and unlike
    the rest of this function they are a real, measured limit rather than a
    pure work budget: an attacker who prepends more leading alphabet runs
    than `_MAX_COMPACT_STARTS`, or pads past `_MAX_COMPACT_CHARS`, escapes
    pass 3 — measured at exactly 63 leading tokens recovered and 64 missed,
    same payload, larger input. Closing that fully is an O(n^2) scan over run
    boundaries, so some budget is inherent; this residue is tracked here
    rather than claimed closed. Ordinary text survives all three passes
    because `validate=True`, the UTF-8 decode, `_MIN_DECODED_LEN` and
    `_sanitise` reject it — measured at 0 false positives across 1512
    ordinary and random strings.

    NFD first: by the time this runs, `text` has already been through NFKC
    upstream, which performs canonical COMPOSITION as well as compatibility
    folding. A combining mark used as a splitter (e.g. a stray acute accent)
    composes with whatever base64 letter precedes it into one precomposed
    character — silently eating that letter out of the alphabet run instead
    of just sitting next to it as an ignorable gap. NFD reverses exactly the
    canonical composition step, restoring the letter and the mark as two
    codepoints, without touching anything NFKC already resolved (fullwidth,
    ligatures, ...), since those have no way back to their original form and
    do not need one — they already landed in the alphabet.
    """
    text = unicodedata.normalize("NFD", text)
    decoded: list[str] = []

    def offer(chunk: str) -> None:
        candidate = _try_decode_base64(chunk)
        if candidate is not None and candidate not in decoded:
            decoded.append(candidate)

    def offer_all_views(chunk: str) -> None:
        for view in _aligned_views(chunk):
            offer(view)
        strict = _strict_view(chunk)
        if strict != chunk:
            for view in _aligned_views(strict):
                offer(view)

    for match in _B64_CANDIDATE.finditer(text):
        offer(match.group(0))

    runs = _B64_RUN.findall(text)
    if not runs:
        return decoded

    compacted = "".join(runs)
    if len(compacted) < _B64_MIN_RUN:
        return decoded

    offer_all_views(compacted)

    if len(compacted) <= _MAX_COMPACT_CHARS:
        for index in range(1, min(len(runs), _MAX_COMPACT_STARTS)):
            tail = "".join(runs[index:])
            if len(tail) < _B64_MIN_RUN:
                break
            offer_all_views(tail)

    return decoded


def _decode_all(text: str) -> tuple[list[str], bool]:
    """One level of every decoder, applied uniformly, in both directions.

    Both call sites go through here so the branches cannot drift apart. The
    two-step composition matrix is closed: b64(x), rot13(x), b64(rot13(x)) and
    rot13(b64(x)) are all covered — an earlier version covered three of the four
    and `base64(rot13(payload))` was recoverable nowhere.

    Bounded by construction: no decoder is applied to its own output.
    """
    out: list[str] = []
    from_base64 = _decode_base64(text)
    out.extend(from_base64)

    # rot13 over each base64 result closes base64(rot13(payload)).
    for item in from_base64:
        rotated_item = codecs.decode(item, "rot_13")
        if rotated_item != item:
            out.append(rotated_item)

    nested: list[str] = []
    rotated = codecs.decode(text, "rot_13")
    if rotated != text:
        out.append(rotated)
        # base64 over the rot13 result closes rot13(base64(payload)).
        nested = _decode_base64(rotated)
        out.extend(nested)

    return out, bool(from_base64 or nested)


def _apply_nfkc(text: str) -> str:
    """Apply NFKC, but only when a COMPATIBILITY difference actually exists.

    `unicodedata.normalize("NFKC", text)` does two unrelated things at once:
    compatibility folding (fullwidth, ligatures, mathematical alphanumerics —
    the attack surface this transform exists for) and canonical composition
    (recombining a base letter with its combining marks into one codepoint —
    a pure re-encoding of ordinary text, not evidence of anything).

    Vietnamese, like any language written with combining marks, is sometimes
    delivered already decomposed (NFD) rather than precomposed (NFC). Running
    NFKC unconditionally recomposes that text — changing its bytes and
    recording a transform — even though nothing resembling an attack is
    present. NFD and NFKD agree on ordinary text (there is no compatibility
    mapping to apply), so comparing them tells us whether this text has any
    compatibility-level content at all before we touch it. Only then do we
    apply NFKC; otherwise the text is returned exactly as it arrived, in
    whatever normalisation form it was already in.
    """
    if unicodedata.normalize("NFD", text) == unicodedata.normalize("NFKD", text):
        return text
    return unicodedata.normalize("NFKC", text)


def _normalise_candidate(text: str) -> str:
    """Apply the visible-text passes to a decoded payload.

    Decoded candidates went to scanners raw, so a payload that was homoglyphed
    or written in fullwidth before being encoded arrived at the scanner still
    obfuscated, and one padded with zero-width characters was discarded by the
    sanitiser's ratio gate. A payload deserves the same normalisation the
    visible text gets.
    """
    working, _ = _extract_tags(text)
    working = working.translate(_BIDI)
    working = _strip_invisible(working)
    working = _apply_nfkc(working)
    return _fold_homoglyphs(working)


def canonicalize(text: str) -> Canonical:
    transforms: list[str] = []
    derived: list[str] = []
    working = text

    # Tags are themselves category Cf, so they must be recovered BEFORE the
    # invisible sweep would delete them.
    working, hidden = _extract_tags(working)
    if hidden:
        transforms.append("unicode_tags")
        derived.append(hidden)
        hidden_decoded, _ = _decode_all(hidden)
        derived.extend(hidden_decoded)

    stripped = working.translate(_BIDI)
    if stripped != working:
        transforms.append("bidi")
        working = stripped

    stripped = _strip_invisible(working)
    if stripped != working:
        transforms.append("invisible")
        working = stripped

    normalised = _apply_nfkc(working)
    if normalised != working:
        transforms.append("nfkc")
        working = normalised

    folded = _fold_homoglyphs(working)
    if folded != working:
        transforms.append("homoglyph")
        working = folded

    decoded, saw_base64 = _decode_all(working)
    if saw_base64:
        transforms.append("base64")
    derived.extend(decoded)

    normalised_derived: list[str] = []
    for item in derived:
        cleaned = _normalise_candidate(item)
        if cleaned and cleaned not in normalised_derived:
            normalised_derived.append(cleaned)
    derived = normalised_derived

    return Canonical(text=working, transforms=tuple(transforms), derived=tuple(derived))
