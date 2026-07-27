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

_MD_IMAGE = re.compile(r"!\[[^\]]*\]\(\s*(?P<url>[^)\s]+)")
_MD_LINK = re.compile(r"(?<!!)\[[^\]]*\]\(\s*(?P<url>[^)\s]+)")
_RAW_HTML = re.compile(r"<\s*(script|iframe|object|embed)\b", re.IGNORECASE)

_MIN_SYSTEM_PROMPT_WORDS = 8


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
    - The score is `overlap / len(system_shingles)`: a short, sensitive
      fragment (say, a stray credential) echoed verbatim out of a very long
      system prompt scores near zero, diluted by the prompt's total length,
      and can sit under any reasonable policy threshold while still being a
      genuine leak. A Finding is still emitted — this is a threshold problem
      for policy.yaml to price, not a silent miss — but it is recorded here
      because a near-zero score reads as "basically nothing" to a threshold
      that was not tuned with dilution in mind.
    """
    if len(re.findall(r"\w+", system_prompt)) < _MIN_SYSTEM_PROMPT_WORDS:
        return []

    system_shingles = _shingles(system_prompt, n)
    if not system_shingles:
        return []

    overlap = system_shingles & _shingles(output, n)
    if not overlap:
        return []

    score = len(overlap) / len(system_shingles)
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


def _host_allowed(url: str, allowlist: list[str]) -> bool:
    # Backslashes are not valid URL characters (RFC 3986), but a browser's
    # WHATWG-compliant URL parser treats an unescaped backslash exactly like
    # a forward slash when it appears before the path begins. Python's
    # urlparse does not: "https://evil.com\\@cdn.nufi.me/x" comes back from
    # urlparse with hostname "cdn.nufi.me" (the text after the last literal
    # "@"), while a real browser rendering the same markdown normalises the
    # backslash first and fetches from "evil.com". Left unnormalised, an
    # allowlisted host after the LAST "@" would clear the check below while
    # the request a client actually issues goes to the attacker's host —
    # the allowlist would wave through the exact exfiltration this scanner
    # exists to catch. Normalising first keeps our notion of "host" aligned
    # with what the client that renders this markdown will actually request.
    host = (urlparse(url.replace("\\", "/")).hostname or "").lower()
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

    Known, unfixed coverage gaps — a silent `[]` on any of these is not
    proof the output is clean, only that it does not match what this
    scanner was written to recognise:

    - Protocol-relative image URLs (`![x](//attacker.example/log)`) are not
      host-checked at all: the scheme guard below only inspects URLs that
      literally start with "http://"/"https://", and a client resolves a
      "//host/path" URL against the current page's scheme just as eagerly.
    - Reference-style markdown (`![x][ref]` with the URL supplied later in a
      separate `[ref]: https://...` definition line) is invisible to
      `_MD_IMAGE`, which only matches the inline `(url)` form.
    - `_RAW_HTML` matches only `<script>`, `<iframe>`, `<object>`, `<embed>`.
      `<img onerror=...>`, `<svg onload=...>`, `<link rel=prefetch>`,
      `<meta http-equiv=refresh>` and CSS `url(...)` are not covered.
    - A JAVASCRIPT_URL finding requires the literal token "javascript:" in
      the URL text (case-insensitively); HTML-entity or whitespace-obscured
      variants (`javascript&colon;alert(1)`, embedded control characters)
      are not decoded first and so are not matched.

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
        url = match.group("url")
        if url.lower().startswith(("http://", "https://")) and not _host_allowed(url, allowlist):
            add("EXTERNAL_IMAGE", match.start(), match.end())

    for match in _MD_LINK.finditer(output):
        if match.group("url").lower().startswith("javascript:"):
            add("JAVASCRIPT_URL", match.start(), match.end())

    for match in _RAW_HTML.finditer(output):
        add("RAW_HTML", match.start(), match.end())

    return findings
