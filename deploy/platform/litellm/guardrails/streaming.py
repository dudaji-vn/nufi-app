"""Chunk-boundary buffering for controls that must inspect a STREAMED response.

Why this module exists
----------------------
A post_call control sees a non-streamed response as one complete string and can
scan it, rewrite it, and hand back the result. A streamed response arrives as a
sequence of deltas, and the client CONCATENATES them: what a browser finally
renders is `"".join(deltas)`, not any individual delta. Two consequences, both
of which this module exists to handle and neither of which per-chunk scanning
addresses:

1. A match can straddle a chunk boundary. `"bill"` + `"ing@acme.co"` and
   `"![x](https://att"` + `"acker.example/leak.png)"` are each invisible to a
   scanner that looks at one delta at a time, while being perfectly visible --
   and perfectly dangerous -- in the concatenation the client assembles. A
   redactor that misses those while reporting `enforced=true` is worse than no
   redactor: it is a leak with a clean audit trail.

2. Emission is irreversible. Once a delta is yielded it is on the wire; there
   is no later pass that can take it back. So the only safe thing to emit is a
   prefix that CANNOT change meaning no matter what arrives next.

The whole module is therefore one idea: given the text accumulated so far,
compute a *cut index* -- the length of the prefix that is provably free of any
partially-formed match -- emit (after rewriting) only up to that index, and
carry the remainder forward into the next chunk. At end of stream the cut is
the whole buffer, because nothing more can arrive.

Bounded hold-back, and why the bound is not free
------------------------------------------------
"Provably free of a partially-formed match" is decided by a regex that matches
only when it can reach the END of the buffer, so `search` returns the leftmost
position from which an incomplete construct could still be growing. That rule
alone is unbounded: a single stray `[` in prose that is never closed would hold
every subsequent character until the stream ended -- which is exactly the
"you deleted streaming to protect it" failure the design must not ship
silently.

Each cut function therefore takes a `max_hold` in characters and will force the
cut forward when the natural cut would hold more than that. `Cut.forced` says
that happened, and every caller is expected to make it visible rather than
swallow it: a forced cut is the one case where a construct CAN be split across
the emission boundary and so reach the client intact. It is a bounded,
recorded, deliberately chosen hole -- not an accident. See each control's
`_STREAM_MAX_HOLD_*` constant in `entrypoints.py` for the number and the
reasoning behind it.

Nothing here decides anything. Detection lives in `guardrails.scanners`,
policy in `guardrails.policy`; this module only answers "how much of what I
have is safe to send", plus the mechanical business of reading and writing a
delta out of whatever chunk object litellm hands us.
"""

from __future__ import annotations

import contextlib
import copy
import re
from typing import Any, NamedTuple


class Cut(NamedTuple):
    """Where to split the pending buffer, and whether the bound forced it.

    `index` is a character offset into the buffer: `buffer[:index]` is safe to
    rewrite and emit, `buffer[index:]` must be carried forward.

    `forced` is True when the natural (match-aware) cut would have held more
    than `max_hold` characters and was overridden. A forced cut means a
    construct may be split across the emission boundary and therefore reach the
    client whole. Returning it as a separate field rather than folding it into
    `index` is deliberate: a caller that ignores it still behaves correctly for
    latency, and silently incorrectly for security, which is precisely the
    shape this project keeps removing. Callers record it.
    """

    index: int
    forced: bool


def _bounded(natural: int, length: int, max_hold: int) -> Cut:
    """Apply the hold-back bound to a natural cut index."""
    if natural >= length:
        return Cut(length, False)
    floor = length - max_hold
    if floor > natural:
        return Cut(max(floor, 0), True)
    return Cut(max(natural, 0), False)


# A markdown/HTML construct that is still being written, anchored to the end of
# the buffer. Built to mirror `scanners.patterns`' `_MD_IMAGE`, `_MD_LINK` and
# `_RAW_HTML` -- if those change, this must change with them, which is why
# `tests/test_streaming.py` drives this function through the real scanner (it
# asserts on `scan_exfil` of the assembled output, not on hand-written cut
# indices) at every split point of a real payload.
#
#   !?\[[^\]]*(?:\](?:\([^)]*)?)?\Z
#       `![x`            -- label still open
#       `![x]`           -- label closed, `(` may be the next character
#       `![x](https://a` -- destination still open
#     and NOT `![x](https://a)`, because `[^)]*` cannot cross the `)` that
#     completes the construct: a completed image is decided and can be scanned,
#     stripped and emitted immediately. This is the difference between holding
#     back one construct and holding back the rest of the response.
#
#   !\Z
#     A lone trailing `!`, which becomes `![` the instant the next chunk
#     starts with `[`. Found by execution, not by review: the split
#     `"Here: !" | "[chart](https://attacker.example/leak.png) done."` shipped
#     the exfiltration URL intact. The first buffer held nothing (no `[` to
#     match yet) and the second contained no `!`, so `_MD_IMAGE` -- which
#     requires the `!` -- matched nothing either, and `_MD_LINK`'s `(?<!!)`
#     made it a plain link, which G4 only checks for `javascript:`. One
#     character, one split point, a completely clean audit trail.
#
#   <[^>]{0,15}\Z
#     `_RAW_HTML` needs at most `<` + optional space + `embed`/`iframe`/... so
#     16 characters after `<` settles it; a `>` in between settles it sooner.
#
# `\Z`, never `$`: in Python's default (non-MULTILINE) mode `$` ALSO matches
# just before a trailing newline. That makes `$` strictly MORE permissive
# (every `\Z` match is a `$` match), so here it can only ever hold back more
# than necessary, never less -- a latency cost, not a hole, which is why
# swapping it back survives the suite. In `token_cut` below the same swap has
# a visible cost: a newline is the boundary that makes a whole line of prose
# emittable, and `$` keeps holding its last five tokens anyway. Written the
# precise way in both places so the two do not have to be reasoned about
# separately.
_OPEN_MARKUP = re.compile(r"!?\[[^\]]*(?:\](?:\([^)]*)?)?\Z|!\Z|<[^>]{0,15}\Z")


def markup_cut(buffer: str, max_hold: int) -> Cut:
    """Cut for `scan_exfil`: hold back a markdown/HTML construct mid-flight."""
    match = _OPEN_MARKUP.search(buffer)
    natural = len(buffer) if match is None else match.start()
    return _bounded(natural, len(buffer), max_hold)


# The trailing whitespace-separated tokens a PII entity could still be
# assembling. `[ \t]` rather than `\s` on purpose: no entity in the shipped
# list spans a newline, so a newline is a hard boundary and everything before
# it can be emitted -- which is what keeps the hold-back short on ordinary
# prose. `\S+` at the tail is what holds `"bill"` back until `"ing@acme.co"`
# arrives.
def token_cut(buffer: str, max_hold: int, tokens: int) -> Cut:
    """Cut for PII: hold back the last `tokens` whitespace-separated tokens.

    `tokens` must cover the widest entity the control looks for *measured in
    space-separated pieces*, not characters: `EMAIL_ADDRESS`, `IP_ADDRESS`,
    `US_SSN` and `IBAN_CODE` are single tokens, but a `PHONE_NUMBER` written
    `+1 555 123 4567` and a `CREDIT_CARD` written `4111 1111 1111 1111` are
    four each.
    """
    if tokens < 1:
        raise ValueError(f"tokens must be >= 1, got {tokens}")
    pattern = re.compile(rf"\S+(?:[ \t]+\S+){{0,{tokens - 1}}}[ \t]*\Z")
    match = pattern.search(buffer)
    natural = len(buffer) if match is None else match.start()
    return _bounded(natural, len(buffer), max_hold)


# --------------------------------------------------------------------------
# Chunk plumbing.
#
# litellm hands the iterator hook `ModelResponseStream` objects, but the same
# hook is reachable with plain dicts (a passthrough route, a test double), and
# a chunk can legitimately carry no `choices` at all (a usage-only frame). Each
# accessor below tolerates both shapes and treats "not the shape I expected" as
# "nothing to do", never as an exception escaping a guardrail hook.
# --------------------------------------------------------------------------


def _attr(obj: Any, name: str) -> Any:
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


class Delta(NamedTuple):
    index: int
    content: str | None
    final: bool


def iter_deltas(chunk: Any) -> list[Delta]:
    """Per-choice text delta and whether that choice is finished.

    `final` is driven by `finish_reason`, which is the provider saying "no more
    text for this choice". That is the only in-band signal that the buffer can
    be flushed while a chunk is still in hand to carry the flushed text -- so
    it is what lets the hold-back be released without inventing an extra chunk.
    """
    choices = _attr(chunk, "choices")
    if not isinstance(choices, list | tuple):
        return []
    deltas: list[Delta] = []
    for position, choice in enumerate(choices):
        index = _attr(choice, "index")
        if not isinstance(index, int):
            index = position
        content = _attr(_attr(choice, "delta"), "content")
        if not isinstance(content, str):
            content = None
        deltas.append(Delta(index, content, _attr(choice, "finish_reason") is not None))
    return deltas


def set_delta(chunk: Any, index: int, text: str) -> bool:
    """Write `text` into the delta of choice `index`. True if it landed.

    A False return is load-bearing, not a formality: it means the rewritten
    text was NOT put back on the chunk, so whatever the caller computed is
    about to be dropped while the original is sent. Callers treat that as an
    enforcement failure to record, not as a no-op to ignore.
    """
    choices = _attr(chunk, "choices")
    if not isinstance(choices, list | tuple):
        return False
    for position, choice in enumerate(choices):
        choice_index = _attr(choice, "index")
        if not isinstance(choice_index, int):
            choice_index = position
        if choice_index != index:
            continue
        delta = _attr(choice, "delta")
        if delta is None:
            return False
        if isinstance(delta, dict):
            delta["content"] = text
        else:
            try:
                delta.content = text
            except Exception:  # noqa: BLE001 - a frozen/odd delta must not 500 a request
                return False
        return True
    return False


def tail_chunk(template: Any, index: int, text: str) -> Any | None:
    """A synthetic chunk carrying `text`, cloned from `template`.

    Only used when a stream ends WITHOUT a `finish_reason` for a choice that
    still has held-back text -- an abnormally terminated stream. In the normal
    case the `finish_reason` chunk itself carries the flush and nothing is
    synthesised.

    `finish_reason` and `usage` are cleared on the clone so this frame cannot
    be mistaken for a completion signal or double-count tokens.
    """
    if template is None:
        return None
    try:
        clone = copy.deepcopy(template)
    except Exception:  # noqa: BLE001 - never break a response to append a tail
        return None
    choices = _attr(clone, "choices")
    if not isinstance(choices, list | tuple) or not choices:
        return None
    if not set_delta(clone, index, text):
        return None
    for choice in choices:
        if isinstance(choice, dict):
            choice["finish_reason"] = None
        else:
            with contextlib.suppress(Exception):
                choice.finish_reason = None
    if isinstance(clone, dict):
        clone.pop("usage", None)
    else:
        with contextlib.suppress(Exception):
            clone.usage = None
    return clone
