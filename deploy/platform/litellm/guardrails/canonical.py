"""Normalise text before any scanner sees it.

Classifier and regex detectors are defeated by character-level and encoding
tricks that leave the text perfectly readable to a model. Every downstream
scanner therefore reads canonical text, and the applied transformations are
recorded so the audit trail shows how an input was obfuscated.

Pure functions only — no I/O, no network.
"""

from __future__ import annotations

import base64
import binascii
import codecs
import re
import unicodedata

from guardrails.types import Canonical

_ZERO_WIDTH = dict.fromkeys(
    [0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF],
)
_BIDI = dict.fromkeys(
    [0x202A, 0x202B, 0x202C, 0x202D, 0x202E, 0x2066, 0x2067, 0x2068, 0x2069],
)

_HOMOGLYPHS = str.maketrans(
    {
        "а": "a", "е": "e", "о": "o", "р": "p",
        "с": "c", "х": "x", "у": "y", "і": "i",
        "ј": "j", "һ": "h", "ԁ": "d", "ԛ": "q",
        "ο": "o", "α": "a", "ρ": "p", "υ": "u",
    }
)

_B64_CANDIDATE = re.compile(r"\b[A-Za-z0-9+/]{20,}={0,2}\b")
_MIN_DECODED_LEN = 8


def _decode_base64(text: str) -> list[str]:
    decoded: list[str] = []
    for match in _B64_CANDIDATE.finditer(text):
        chunk = match.group(0)
        padded = chunk + "=" * (-len(chunk) % 4)
        try:
            raw = base64.b64decode(padded, validate=True)
            candidate = raw.decode("utf-8")
        except (binascii.Error, UnicodeDecodeError, ValueError):
            continue
        if len(candidate) >= _MIN_DECODED_LEN and candidate.isprintable():
            decoded.append(candidate)
    return decoded


def _decode_rot13(text: str) -> str | None:
    rotated = codecs.decode(text, "rot_13")
    if rotated == text:
        return None
    # Only consider it ROT13 if the decoded version looks more English-like
    # by checking if it has more vowels (less gibberish-like)
    vowels = "aeiouAEIOU"
    orig_vowels = sum(1 for c in text if c in vowels)
    rotated_vowels = sum(1 for c in rotated if c in vowels)
    if rotated_vowels > orig_vowels:
        return rotated
    return None


def canonicalize(text: str) -> Canonical:
    transforms: list[str] = []
    working = text

    stripped = working.translate(_ZERO_WIDTH)
    if stripped != working:
        transforms.append("zero_width")
        working = stripped

    stripped = working.translate(_BIDI)
    if stripped != working:
        transforms.append("bidi")
        working = stripped

    normalised = unicodedata.normalize("NFKC", working)
    if normalised != working:
        transforms.append("nfkc")
        working = normalised

    folded = working.translate(_HOMOGLYPHS)
    if folded != working:
        transforms.append("homoglyph")
        working = folded

    extras: list[str] = []

    decoded_b64 = _decode_base64(working)
    if decoded_b64:
        transforms.append("base64")
        extras.extend(decoded_b64)

    decoded_rot = _decode_rot13(working)
    if decoded_rot is not None:
        transforms.append("rot13")
        extras.append(decoded_rot)

    if extras:
        working = working + "\n" + "\n".join(extras)

    return Canonical(text=working, transforms=tuple(transforms))
