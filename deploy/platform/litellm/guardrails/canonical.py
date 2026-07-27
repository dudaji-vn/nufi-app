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

_B64_ALPHABET = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/-_="
)
_B64_MIN_RUN = 20
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
    for char in text:
        if char.isprintable() or char in _ALLOWED_CONTROL:
            out.append(char)
        else:
            out.append(" ")
            replaced += 1
    if replaced / len(text) > _MAX_UNSCANNABLE_RATIO:
        return None
    return "".join(out)


def _skeleton_char(char: str) -> str | None:
    """Map one lookalike to its ASCII letter, or None if it is not one.

    Tries the explicit map first, then Unicode's own COMPATIBILITY
    decomposition: a character whose NFKD form reduces to a single ASCII
    letter once its combining marks are removed IS that letter as far as a
    reader is concerned (e.g. fullwidth or styled Latin letters). This
    replaces a 16-entry hand-list, which was the same failure shape as the
    hand-listed invisibles — a list nobody finishes.

    Restricted to CANONICAL-decomposition-free / compatibility-tagged
    characters only: `unicodedata.decomposition()` returns a bare codepoint
    list ("0061 0300") for a canonical decomposition and a tagged one
    ("<wide> 0072") for a compatibility decomposition. Precomposed accented
    Latin letters — "à", "ạ" — decompose canonically into base + combining
    mark; that IS the character, not a lookalike of something else, and
    Vietnamese is written with exactly these. Folding them by stripping their
    `Mn` part was the first draft of this function and it silently turned
    "bạn" into "ban" — the deployment's primary user language. Only a
    compatibility (tagged) decomposition, or no decomposition at all (caught
    by the explicit map above), is eligible here.
    """
    if char in _HOMOGLYPHS:
        return _HOMOGLYPHS[char]
    if not unicodedata.decomposition(char).startswith("<"):
        return None
    stripped = "".join(
        part
        for part in unicodedata.normalize("NFKD", char)
        if unicodedata.category(part) != "Mn"
    )
    if len(stripped) == 1 and "a" <= stripped.lower() <= "z":
        return stripped
    return None


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


def _compact(text: str) -> str:
    """Drop everything outside the base64 alphabet.

    A blob split by ONE character out of the alphabet was enough to defeat the
    decoder, and the categories that can supply such a character are unbounded:
    `Cf` format characters, `Lo` Hangul fillers that render blank, `So` braille
    blank, ordinary whitespace, and `Mn` combining marks — which cannot be
    stripped, because Vietnamese is written with them.

    So contiguity is no longer required. Stripping at the extraction site is
    bounded by design; stripping at the character site was bounded by a list.
    """
    return "".join(char for char in text if char in _B64_ALPHABET)


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


_B64_RUN = re.compile(rf"{_B64_CHARS}+=*")
# A run this short is an ordinary short English word ("this", "decode"); a
# base64 fragment split by one splitter character is not. Only runs on BOTH
# sides of a gap that clear this floor are bridged, so "decode this <blob>"
# never has "this" stitched onto the blob.
_MIN_BRIDGE_RUN = 8
# Wide enough to bridge a blob split by one splitter codepoint (and a couple
# of stacked ones); narrow enough that it never reaches across a sentence.
_MAX_BRIDGE_GAP = 3


def _bridge_spans(text: str) -> list[str]:
    """Reassemble a blob split by a small number of filler characters.

    A blob split by one splitter character no longer matches `_B64_CANDIDATE`
    at all: the two remaining pieces are each individually too short, or the
    combined run never existed as one contiguous match to begin with.
    Whitespace, Hangul fillers, the braille blank and a stray combining mark
    are all valid splitters here — none of them is `Cf`, so the invisible
    sweep does not remove them, and none of them can be enumerated exhaustively
    (see `_compact`). Bridging fixes the SITE instead of the character: two
    alphabet runs are joined only when each one is independently long enough
    to be a blob fragment rather than a word, and the gap between them is
    short enough that it can only be a handful of splitter characters, not an
    intervening sentence.
    """
    runs = list(_B64_RUN.finditer(text))
    spans: list[str] = []
    chain_start: int | None = None
    chain_runs = 0
    for idx, match in enumerate(runs):
        if chain_start is None:
            chain_start = match.start()
            chain_runs = 1
            continue
        prev = runs[idx - 1]
        gap = match.start() - prev.end()
        if (
            gap <= _MAX_BRIDGE_GAP
            and len(prev.group(0)) >= _MIN_BRIDGE_RUN
            and len(match.group(0)) >= _MIN_BRIDGE_RUN
        ):
            chain_runs += 1
        else:
            if chain_runs > 1:
                spans.append(text[chain_start : prev.end()])
            chain_start = match.start()
            chain_runs = 1
    if chain_runs > 1 and chain_start is not None:
        spans.append(text[chain_start : runs[-1].end()])
    return spans


def _decode_base64(text: str) -> list[str]:
    """Two passes: contiguous runs, then nearby runs bridged across a gap.

    The contiguous pass keeps several independent blobs separate. The
    bridging pass reassembles one blob that was deliberately split — scoped to
    the bridged span itself (via `_compact`), not the whole message, so
    surrounding prose is never absorbed into the candidate. Ordinary prose
    survives both because `validate=True` plus a UTF-8 decode plus
    `_MIN_DECODED_LEN` reject it — measured at 0 surfacings across 3000 random
    binary blobs and the whole ordinary-content corpus.

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
    for match in _B64_CANDIDATE.finditer(text):
        candidate = _try_decode_base64(match.group(0))
        if candidate is not None:
            decoded.append(candidate)

    for span in _bridge_spans(text):
        compacted = _compact(span)
        if len(compacted) >= _B64_MIN_RUN:
            candidate = _try_decode_base64(compacted)
            if candidate is not None and candidate not in decoded:
                decoded.append(candidate)

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
