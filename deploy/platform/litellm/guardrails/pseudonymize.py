"""Reversible pseudonymization: send the model a surrogate, restore the original.

`redact` destroys a value. A user who asks for their own email signature back
gets `[EMAIL_ADDRESS]` where their address should be — the control protects them
from themselves. Pseudonymization replaces the value with an opaque token before
the request leaves the process and puts the original back into the response
before the client sees it. The provider never receives the value; the user never
loses it.

The engine is `nufi-security`'s (`egress_audit.surrogate`, `egress_audit.vault`).
This module is the seam between it and our types, in the sense
`docs/2026-07-27-llm-security-gateway-design.md` §5 means: their `Finding` and
their entity vocabulary do not cross into `policy.py`, and ours do not cross into
theirs.

WHY THE DESIGN LOOKS LIKE THIS

A surrogate only helps if it comes back. Measured on `gemini-2.5-flash`,
temperature 1.0, seven prompt shapes (signature rewrite, summary, translation,
markdown table, `repeat exactly`, Korean, long-form), three delimiters:

    ⟦E1⟧ (default)   68/70 all tokens intact    0/70 partial
    [[E1]]           70/70                      0/70
    <E1>             70/70                      0/70

Three readings of that table decide everything here.

**Partial return never happened.** When it fails, every bracket is stripped at
once, so there is no "one value restores while another leaks" case. The failure
is uniform, and therefore detectable.

**The failure is SILENT, and their library cannot see it.** `deanonymize`
reports `fallback` for a surrogate that is present but has no mapping — a
different failure. When the model returns `E1` with the delimiters stripped,
`_EXACT` does not match and `_LENIENT` requires brackets on both sides, so
restoration does nothing, reports `restored: 0, fallback: 0`, and the user sees
`E1` where their email should be while the audit trail says the round trip
completed. Widening `_LENIENT` is not the fix: bare `E1`, `P1`, `T2` are
ordinary strings (cell references, part numbers) and matching them without
brackets would corrupt normal text. Detecting the bare tag is therefore THIS
module's job, and `restore` reports it as `mangled`.

**68/70 is not a guarantee**, so nothing here reports a value as restored
without having restored it. `RestoreResult` separates all three outcomes and the
caller is expected to act on each.

THE DELIMITER STAYS AT THE DEFAULT. `[[E1]]` scored 70/70 against the default's
68/70, and that is not a reason to switch. `⟦⟧` was chosen upstream because it
essentially never occurs in ordinary text or code, while `[[E1]]` is wiki-link
syntax a user could type themselves and have substituted, and `<E1>` is markup a
markdown renderer may swallow — turning a visible wrong token into an invisible
missing one. `NUFI_SURROGATE_DELIMS` exists for a deployment whose own
measurement says otherwise.

WHAT IS NOT REVERSIBLE, ON PURPOSE. A card number, a national identifier or an
IBAN restored into a response is a card number put back on a screen and into
LibreChat's stored chat history. Those stay redacted. Only contact details a
user would legitimately want returned to them are reversible — see
`REVERSIBLE_ENTITIES`.

THE VAULT IS A NEW STORE OF PII, and the only one this platform has besides
LibreChat's chat history. In-process memory, AES-256-GCM at rest under a KEK
regenerated per process unless `EGRESS_VAULT_KEK` is set (so a restart makes old
mappings undecryptable — a safe failure), partitioned by session, TTL-bounded,
wiped by `end_session`, with no dump API. Anything claiming this platform stores
no PII outside chat history has to account for it.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Any

# From the vendored snapshot (litellm/nufi-security.provenance.md). Imported at
# module scope deliberately: a missing or broken snapshot must fail when the
# control is constructed, not on the first request that happens to carry PII.
from egress_audit import surrogate as _sg
from egress_audit.vault import MappingVault

#: Entity types restored to the user rather than destroyed, in OUR vocabulary
#: (Presidio's names plus the nufi adapter's). Every name here must be one the
#: configured detectors can actually produce — `policy.yaml`'s `entities` and
#: `nufi_entities` — or it is dead code; `tests/test_pseudonymize.py` asserts
#: that against the policy file.
#:
#: Everything else the detectors find (`CREDIT_CARD`, `US_SSN`, `IBAN_CODE`,
#: `IP_ADDRESS`, `KR_RRN`, `KR_FOREIGNER_REG`) is deliberately absent: see the
#: module docstring.
REVERSIBLE_ENTITIES: frozenset[str] = frozenset(
    {
        "EMAIL_ADDRESS",
        "PHONE_NUMBER",
        "KR_PHONE",
    }
)

#: Our entity names to theirs. Required, not cosmetic: their `SurrogateMinter`
#: derives the surrogate's tag letter from `TAG_OF[entity_type]` and falls back
#: to `"X"` for a name it does not know. Measured — `TAG_OF.get("EMAIL_ADDRESS")`
#: is `None`, so without this mapping EVERY entity we pseudonymize would mint
#: `⟦X1⟧`, `⟦X2⟧`: one shared counter and no type information left for the
#: failure labels below. Their vocabulary is
#: `{KR_PERSON: P, KR_PHONE: T, EMAIL: E, KR_BRN: B, KR_LOCATION: L}`.
_TO_ENGINE_ENTITY: dict[str, str] = {
    "EMAIL_ADDRESS": "EMAIL",
    "PHONE_NUMBER": "KR_PHONE",
    "KR_PHONE": "KR_PHONE",
}

#: Their tag letter back to the label we show when restoration failed. Chosen to
#: match what `G2bPiiOutput.redact` would have produced for the same value, so a
#: failed round trip degrades to exactly the output the previous behaviour gave
#: rather than to something new.
#:
#: `T` is reached from both `PHONE_NUMBER` and `KR_PHONE`, which share their
#: `KR_PHONE` type, so the label flattens to `[PHONE_NUMBER]`. Accurate in kind
#: and never misleading; distinguishing them would need per-session type state
#: that the response leg has no way to receive.
_LABEL_OF_TAG: dict[str, str] = {
    "E": "[EMAIL_ADDRESS]",
    "T": "[PHONE_NUMBER]",
}

#: Their own labels, for the `fallback` path — `deanonymize` writes
#: `[{their type}]` for a surrogate with no mapping. Rewritten to ours so a user
#: never sees `[KR_PHONE]` for a number that was not Korean, and so every label
#: the client can receive comes from one vocabulary.
_THEIR_LABEL_TO_OURS: dict[str, str] = {
    "[EMAIL]": "[EMAIL_ADDRESS]",
    "[KR_PHONE]": "[PHONE_NUMBER]",
}

#: How long a mapping may live. A round trip is one request, so this is generous
#: for a slow streamed completion and still short. `end_session` normally beats
#: it; the TTL is what covers the request that died before its response leg ran.
DEFAULT_TTL_SECONDS = 300.0

#: Matches a delimiter-stripped surrogate: a tag letter this module mints
#: followed by 1-4 digits, not adjacent to another alphanumeric. Bounded so
#: `SIZE12` and `E1000000` are not candidates, and restricted to our tags so a
#: document discussing cell `A1` is never considered.
_BARE_TAG = re.compile(
    rf"(?<![0-9A-Za-z])([{''.join(sorted(_LABEL_OF_TAG))}])([0-9]{{1,4}})(?![0-9A-Za-z])"
)


@dataclass(frozen=True)
class _EngineFinding:
    """The four attributes `surrogate.pseudonymize` reads off a finding.

    A shim rather than their `egress_audit.pipeline.Finding`: constructing
    theirs would pull their pipeline into our import graph and put their type on
    our side of the seam, which is what layer ② exists to prevent. Their
    function reads `entity_type`, `start`, `end` and `text` and nothing else —
    asserted in `tests/test_pseudonymize.py` against the real function, so an
    added upstream field becomes a failing test rather than an `AttributeError`
    on a request that happens to carry PII.
    """

    entity_type: str
    start: int
    end: int
    text: str


@dataclass(frozen=True)
class PseudonymizeResult:
    text: str
    #: Vault session id, to carry to the response leg. `None` when nothing was
    #: replaced — the common case, which must not allocate a session.
    ref: str | None
    count: int
    #: Entity types replaced, in our vocabulary, for the audit event. Types, not
    #: values: an audit trail that carried the values would be the leak.
    entities: tuple[str, ...] = ()


@dataclass(frozen=True)
class RestoreResult:
    text: str
    #: Surrogates replaced with their original value.
    restored: int = 0
    #: Surrogates present in the response with no mapping — expired, wrong
    #: session, or a token the model invented. Their library replaces these with
    #: a type label, so nothing raw is shown, but the user lost a value they
    #: should have got back.
    fallback: int = 0
    #: Surrogates the model returned with the delimiters stripped. Invisible to
    #: their library; see the module docstring. Replaced with a type label here,
    #: so the user never sees a bare `E1`.
    mangled: int = 0

    @property
    def failed(self) -> int:
        """Values the user should have got back and did not, by any route."""
        return self.fallback + self.mangled


class Pseudonymizer:
    """One instance per process; one vault session per request.

    Neither a scanner nor a control: it does not detect and does not decide. It
    is handed findings someone else produced under a decision someone else made.

    Holds NO per-request state. Every method takes its session `ref` as an
    argument for that reason — a process-wide instance serving concurrent
    requests that kept the "current" ref on `self` would restore one request's
    values into another's response.
    """

    def __init__(
        self,
        vault: MappingVault | None = None,
        ttl: float = DEFAULT_TTL_SECONDS,
        reversible: frozenset[str] = REVERSIBLE_ENTITIES,
    ) -> None:
        # Constructed eagerly so a missing `cryptography` fails here rather than
        # on the first request carrying PII. Their vault refuses to fall back to
        # plaintext storage, which is the behaviour we want, and is why this is
        # not wrapped in a try/except.
        self._vault = vault if vault is not None else MappingVault(default_ttl=ttl)
        self._ttl = ttl
        self._reversible = frozenset(reversible)

    # -- request leg ----------------------------------------------------------

    def pseudonymize(
        self, text: str, findings: list[Any], ref: str | None = None
    ) -> PseudonymizeResult:
        """Replace reversible findings in `text` with surrogates.

        `ref` lets a caller put several texts into ONE session, which is what a
        multi-message request needs: the response leg gets one place to look and
        one thing to wipe. It also makes the same value appearing in two messages
        mint the same surrogate, because their minter deduplicates within a
        session — so a conversation that repeats an address does not accumulate
        `⟦E1⟧`, `⟦E2⟧`, `⟦E3⟧` for it.
        """
        shims = [
            _EngineFinding(
                entity_type=_TO_ENGINE_ENTITY[entity],
                start=start,
                end=end,
                # Their minter deduplicates on the ORIGINAL value, so this must
                # be the matched substring. Sliced from `text` rather than read
                # off the finding: `Finding` carries no matched text by design,
                # and the offsets are character offsets into this same string.
                text=text[start:end],
            )
            for entity, start, end in self._eligible(text, findings)
        ]
        if not shims:
            return PseudonymizeResult(text=text, ref=None, count=0)

        # A caller-supplied ref is reused; `purge_session` below would otherwise
        # wipe mappings a previous message in the same request already stored.
        supplied = ref is not None
        ref = ref or f"grd-pseudo-{uuid.uuid4().hex}"
        out, count = _sg.pseudonymize(
            text,
            shims,  # type: ignore[arg-type]
            self._vault,
            ref,
            ttl=self._ttl,
            # Their names, because the shims now carry their names. Passing ours
            # would make their `entity_type not in reversible` filter drop every
            # finding and return the text unchanged with count 0 -- a control
            # that silently does nothing.
            reversible=tuple(sorted(set(_TO_ENGINE_ENTITY.values()))),
        )
        if count == 0:
            # Their filter rejected everything after all. Do not hand back a ref
            # that would make the response leg open a session on an empty
            # mapping, and do not leave the session allocated -- unless the ref
            # came from the caller, whose EARLIER messages may already have
            # mappings in it. Purging then would silently drop them and the
            # response leg would restore nothing.
            if not supplied:
                self._vault.purge_session(ref)
                return PseudonymizeResult(text=text, ref=None, count=0)
            return PseudonymizeResult(text=text, ref=ref, count=0)

        return PseudonymizeResult(
            text=out,
            ref=ref,
            count=count,
            entities=tuple(sorted({entity for entity, _, _ in self._eligible(text, findings)})),
        )

    # -- response leg ---------------------------------------------------------

    def restore(self, text: str, ref: str | None) -> RestoreResult:
        """Put the original values back, and report every way it did not work."""
        if not ref or not text:
            return RestoreResult(text=text)

        out, stats = _sg.deanonymize(text, self._vault, ref)
        fallback = int(stats.get("fallback", 0))
        if fallback:
            out = self._relabel(out)
        out, mangled = self._repair_mangled(out, ref)
        return RestoreResult(
            text=out,
            restored=int(stats.get("restored", 0)),
            fallback=fallback,
            mangled=mangled,
        )

    def stream_restorer(self, ref: str | None) -> Any | None:
        """A restorer that holds a surrogate split across chunk boundaries.

        Theirs, not ours: `feed`/`flush` already buffer a partial token up to
        `MAX_SURROGATE_LEN`, which is the entire difficulty of the streaming
        path. The tail still needs `repair_stream_tail` — a delimiter the model
        stripped is not a boundary problem and their buffer cannot see it.
        """
        return _sg.StreamingDeanonymizer(self._vault, ref) if ref else None

    def repair_stream_tail(self, text: str, ref: str | None) -> tuple[str, int]:
        """The `mangled` repair, for text that came out of a stream restorer."""
        if not ref or not text:
            return text, 0
        return self._repair_mangled(text, ref)

    def end_session(self, ref: str | None) -> int:
        """Wipe the mapping. Safe to call twice, and on `None`."""
        return self._vault.purge_session(ref) if ref else 0

    def active_count(self, ref: str | None = None) -> int:
        """Live mappings, for the metric that says the vault is not leaking."""
        return self._vault.active_count(ref)

    # -- internals ------------------------------------------------------------

    def _eligible(
        self, text: str, findings: list[Any]
    ) -> list[tuple[str, int, int]]:
        """Findings this module may act on, with offsets clamped to `text`.

        Clamping matters for the same reason it does in `redact`: two detectors
        scan the same string and an offset that does not fit would slice the
        wrong characters, replacing adjacent text with a surrogate and leaving
        part of the value in place. Neither failure raises.
        """
        length = len(text)
        out: list[tuple[str, int, int]] = []
        for finding in findings:
            entity = getattr(finding, "entity", None)
            if not isinstance(entity, str) or entity not in self._reversible:
                continue
            if entity not in _TO_ENGINE_ENTITY:
                # In `REVERSIBLE_ENTITIES` but with no engine name. Cannot be
                # minted with a correct tag, so it is not eligible -- silently
                # minting `⟦X1⟧` would lose the type. A test forbids the two
                # tables from drifting apart, so this is unreachable in practice
                # and present because "unreachable" is not "impossible".
                continue
            start = max(0, min(int(getattr(finding, "start", 0)), length))
            end = max(start, min(int(getattr(finding, "end", 0)), length))
            if start < end:
                out.append((entity, start, end))
        return out

    @staticmethod
    def _relabel(text: str) -> str:
        """Rewrite their fallback labels into our vocabulary."""
        for theirs, ours in _THEIR_LABEL_TO_OURS.items():
            text = text.replace(theirs, ours)
        return text

    def _repair_mangled(self, text: str, ref: str) -> tuple[str, int]:
        """Replace a delimiter-stripped surrogate with its type label.

        Runs AFTER `deanonymize`, so anything still matching is a token neither
        exact nor lenient matching resolved.

        A candidate is only treated as a stripped surrogate if it resolves in
        THIS session's vault. Without that check, a reply legitimately
        mentioning `T1` in a request that pseudonymized an email would have `T1`
        rewritten — corrupting text to fix a problem that was not there.

        The label is written rather than the original value, even though the
        value is known here. Substituting the value would put PII into a
        position the model did not put a token in, if the match was a
        coincidence; the label is wrong in the same way `redact` is wrong, which
        is a failure mode this system already has and users already understand.
        `mangled` is returned so the choice can be revisited with data.
        """
        count = 0

        def _replace(match: re.Match[str]) -> str:
            nonlocal count
            tag, index = match.group(1), match.group(2)
            if self._vault.resolve(ref, _sg.make_surrogate(tag, int(index))) is None:
                return match.group(0)
            count += 1
            return _LABEL_OF_TAG[tag]

        repaired = _BARE_TAG.sub(_replace, text)
        return (repaired, count) if count else (text, 0)


#: Where the request leg leaves the vault session id for the response leg. Under
#: `metadata` because that is the convention `verified_grounded` already uses,
#: and because litellm treats `metadata` as internal — it is not forwarded to the
#: provider, so the correlation id does not travel with the request.
SESSION_KEY = "nufi_pseudonym_ref"

#: Key metadata flag a workload sets to opt in. Read off `UserAPIKeyAuth`, not
#: off the request body: turning pseudonymization ON is not a security downgrade,
#: but WHICH workloads are payload-shaped is a deployment fact and not a caller's
#: choice — and a caller who could enable it could break their own subject-class
#: questions in a way that looks like a model fault.
OPT_IN_KEY = "nufi_pseudonymize"

#: Injected as a system message on requests where pseudonymization is active, and
#: only those. Without it the model asks what the token means or guesses:
#: measured, a signature request answered *"Please tell me what ⟦E1⟧ represents!
#: Assuming ⟦E1⟧ is the Company Name…"*. With it, payload-class prompts carried
#: the token 9/9 with correct answers
#: (`docs/2026-07-29-nufi-security-integration.md` §7.3a).
#:
#: This is a prompt WE add to a user's request. It costs tokens on every such
#: request and it can conflict with the user's own system prompt — which is why
#: the action is opt-in rather than free, and why this is attached only when a
#: token was actually minted.
INSTRUCTION = (
    "Text in ⟦…⟧ is a placeholder standing in for a real value that has been "
    "withheld for privacy — ⟦E1⟧ is an email address, ⟦T1⟧ a phone number. "
    "Treat each as the value it stands for. Reproduce it exactly, including the "
    "brackets, wherever the value belongs in your answer. Never explain, expand, "
    "guess at, or ask about a placeholder."
)

_SHARED: Pseudonymizer | None = None


def shared() -> Pseudonymizer:
    """The one instance per process.

    Process-wide rather than per-control because the two legs live in different
    control objects: `G2aPiiInput` mints and `G2bPiiOutput` restores. A
    per-control vault would leave every session unresolvable from the other side
    — restoration would report `fallback` for every token, the user would receive
    labels instead of values, and the audit trail would report a completed round
    trip. That is the failure this accessor exists to make impossible.

    Lazy so that importing this module does not require `cryptography` at import
    time. The first caller pays, and the vault raises rather than falling back to
    plaintext storage if it is missing.
    """
    global _SHARED
    if _SHARED is None:
        _SHARED = Pseudonymizer()
    return _SHARED


def instructed(messages: list[Any]) -> list[Any]:
    """Return `messages` with `INSTRUCTION` prepended as a system message.

    Prepended rather than spliced into an existing system message: rewriting the
    user's own system prompt is a larger intrusion than adding a message beside
    it, and a merge would have to guess where in their text to put it.

    A NEW list, never a mutation. The caller's list is the one inside the request
    dict litellm holds, which is also what spend logging and the audit trail
    read.
    """
    return [{"role": "system", "content": INSTRUCTION}, *messages]
