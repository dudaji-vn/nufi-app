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

# Any zero-width codepoint inserted mid-ciphertext splits a base64 blob and
# defeats the decode, so this list must be exhaustive rather than illustrative.
_INVISIBLE = dict.fromkeys(
    [
        0x00AD,  # soft hyphen
        0x180E,  # mongolian vowel separator
        0x200B,  # zero width space
        0x200C,  # zero width non-joiner
        0x200D,  # zero width joiner
        0x2060,  # word joiner
        0x2061,  # function application
        0x2062,  # invisible times
        0x2063,  # invisible separator
        0x2064,  # invisible plus
        0xFEFF,  # zero width no-break space
        *range(0xFE00, 0xFE10),  # variation selectors 1-16
        *range(0xE0100, 0xE01F0),  # variation selectors supplement
        0x1D173,  # musical symbol begin beam
        0x1D174,
        0x1D175,
        0x1D176,
        0x1D177,
        0x1D178,
        0x1D179,
        0x1D17A,
    ]
)
_BIDI = dict.fromkeys(
    [0x202A, 0x202B, 0x202C, 0x202D, 0x202E, 0x2066, 0x2067, 0x2068, 0x2069]
)

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

_B64_CANDIDATE = re.compile(r"(?<![A-Za-z0-9+/\-_])[A-Za-z0-9+/\-_]{20,}={0,2}(?![A-Za-z0-9+/\-_])")
_B64_URLSAFE = str.maketrans({"-": "+", "_": "/"})
_MIN_DECODED_LEN = 8
_ALLOWED_CONTROL = "\n\r\t"


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


def _is_scannable(text: str) -> bool:
    """Printable, but tolerating the whitespace a real payload contains."""
    return all(char.isprintable() or char in _ALLOWED_CONTROL for char in text)


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
            candidate = base64.b64decode(padded, validate=True).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError, ValueError):
            continue
        if len(candidate) >= _MIN_DECODED_LEN and _is_scannable(candidate):
            decoded.append(candidate)
    return decoded


def canonicalize(text: str) -> Canonical:
    transforms: list[str] = []
    derived: list[str] = []
    working = text

    stripped = working.translate(_INVISIBLE)
    if stripped != working:
        transforms.append("invisible")
        working = stripped

    stripped = working.translate(_BIDI)
    if stripped != working:
        transforms.append("bidi")
        working = stripped

    working, hidden = _extract_tags(working)
    if hidden:
        transforms.append("unicode_tags")
        derived.append(hidden)
        # Recovered tag text is itself attacker-authored, so it gets the same
        # decoders as the visible text. Without this, base64 or ROT13 hidden
        # inside the Tags block lands in neither `text` nor `derived` — two
        # layers of invisibility and a working bypass. One extra level only,
        # deliberately: decoding to a fixed point is unbounded work on
        # attacker-controlled input.
        derived.extend(_decode_base64(hidden))
        rotated_hidden = codecs.decode(hidden, "rot_13")
        if rotated_hidden != hidden:
            derived.append(rotated_hidden)

    normalised = unicodedata.normalize("NFKC", working)
    if normalised != working:
        transforms.append("nfkc")
        working = normalised

    folded = _fold_homoglyphs(working)
    if folded != working:
        transforms.append("homoglyph")
        working = folded

    from_base64 = _decode_base64(working)
    if from_base64:
        transforms.append("base64")
        derived.extend(from_base64)

    rotated = codecs.decode(working, "rot_13")
    if rotated != working:
        derived.append(rotated)

    return Canonical(text=working, transforms=tuple(transforms), derived=tuple(derived))
