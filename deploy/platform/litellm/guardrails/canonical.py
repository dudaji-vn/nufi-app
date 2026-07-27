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

_B64_CHARS = r"[A-Za-z0-9+/\-_]"
_B64_CANDIDATE = re.compile(
    rf"(?<!{_B64_CHARS}){_B64_CHARS}{{20,}}={{0,2}}(?!{_B64_CHARS})"
)
_B64_URLSAFE = str.maketrans({"-": "+", "_": "/"})
_MIN_DECODED_LEN = 8
_ALLOWED_CONTROL = "\n\r\t"
_MAX_UNSCANNABLE_RATIO = 0.34


def _strip_invisible(text: str) -> str:
    """Remove every zero-width format character.

    Unicode general category `Cf` is the exhaustive definition, so we ask
    Unicode rather than maintain a list. Tag characters are also Cf, which is
    why `_extract_tags` must run before this.
    """
    return "".join(
        char
        for char in text
        if unicodedata.category(char) != "Cf" and ord(char) not in _VARIATION_SELECTORS
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
    `base64(payload + "\\x00")` decoded to a real injection that was then thrown
    away, so no scanner ever saw it. Candidates that are mostly unscannable are
    still rejected — that is binary noise, not a hidden instruction.
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


def _fold_homoglyphs(text: str) -> str:
    """Fold lookalikes only inside tokens that MIX scripts.

    A token written entirely in Cyrillic or Greek is ordinary non-English text
    and must survive intact. A token mixing an ASCII body with a lookalike
    character is the attack shape ("іgnore").
    """
    folded: list[str] = []
    for token in re.split(r"(\s+)", text):
        has_ascii_letter = any("a" <= char.lower() <= "z" for char in token)
        has_homoglyph = any(char in _HOMOGLYPHS for char in token)
        if has_ascii_letter and has_homoglyph:
            folded.append("".join(_HOMOGLYPHS.get(char, char) for char in token))
        else:
            folded.append(token)
    return "".join(folded)


def _decode_base64(text: str) -> list[str]:
    decoded: list[str] = []
    for match in _B64_CANDIDATE.finditer(text):
        chunk = match.group(0).translate(_B64_URLSAFE)
        padded = chunk + "=" * (-len(chunk) % 4)
        try:
            raw = base64.b64decode(padded, validate=True).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError, ValueError):
            continue
        candidate = _sanitise(raw)
        if candidate is not None and len(candidate.strip()) >= _MIN_DECODED_LEN:
            decoded.append(candidate)
    return decoded


def _decode_all(text: str) -> tuple[list[str], bool]:
    """One level of every decoder, applied uniformly.

    Both call sites go through here so the branches cannot drift apart. An
    earlier version re-decoded tag content but not ROT13 output, which left
    `rot13(base64(payload))` recoverable nowhere.

    Bounded by construction: base64 is applied to the ROT13 output, but nothing
    is applied to its own output. Decoding to a fixed point would be unbounded
    work on attacker-controlled input.
    """
    out: list[str] = []
    from_base64 = _decode_base64(text)
    out.extend(from_base64)

    nested: list[str] = []
    rotated = codecs.decode(text, "rot_13")
    if rotated != text:
        out.append(rotated)
        nested = _decode_base64(rotated)
        out.extend(nested)

    return out, bool(from_base64 or nested)


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

    normalised = unicodedata.normalize("NFKC", working)
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

    return Canonical(text=working, transforms=tuple(transforms), derived=tuple(derived))
