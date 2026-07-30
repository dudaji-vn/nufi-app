"""Redact structured identifiers on their way into the observability backend.

This exists because of a measured hole, not a hypothetical one. G2b redacts the
model's output for the client, but on a STREAMED response litellm's
`CustomStreamWrapper` assembles the text it hands the logging backends *before*
our streaming hook runs. Measured on the live stack: the client received
`[EMAIL_ADDRESS]` while the Langfuse trace output held `support@zephyr.com`.
Non-streamed responses were clean, so the leak is streaming-only -- and it is
the wrong way round for a PII control, which exists precisely to stop that
value reaching another datastore.

litellm supports a masking callable for exactly this
(`integrations/langfuse/langfuse.py:625-632`, fed from
`metadata["langfuse_masking_function"]`), applied to both the input and the
output of every trace. The contract is `str -> str`, walked recursively over
dicts and lists.

**Why regex here and Presidio in the request path.** The masking function runs
inline inside the logger. It must be synchronous and it must not make a network
call -- an observability write is not allowed to add a Presidio round trip, and
it must not fail the request if a sidecar is down. So this covers the
*deterministic* identifiers only, which is the same reason those are the
default entity list: they match precisely and score 1.00, where NER guesses.

**What it does NOT cover, stated rather than implied.** Names, addresses and
organisations are not matched -- they need NER, which needs the network. Phone
numbers are deliberately absent too: a blunt digit-run regex mangles order
numbers, request ids, timestamps and hashes, and a log nobody can read is its
own kind of outage. This is defence in depth for the logging path, not a second
implementation of G2b.
"""

from __future__ import annotations

import re

_PLACEHOLDER = "[{}]"

# Luhn-checked separately; the pattern only finds candidates.
_CARD = re.compile(r"\b(?:\d[ -]?){12,18}\d\b")
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_US_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
# IBAN: 2-letter country, 2 check digits, then 11-30 alphanumerics.
_IBAN = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b")
# Dotted quad with each octet bounded, so 999.999.999.999 and version strings
# like 1.2.3.4000 do not match.
_IPV4 = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}"
    r"(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\b"
)


def _luhn(digits: str) -> bool:
    """Standard Luhn check.

    Applied because the candidate pattern alone matches any 13-19 digit run:
    order numbers, trace ids, and the millisecond timestamps that fill these
    very logs. Without it this function would redact the things an operator
    reads the log to find.
    """
    total = 0
    for index, char in enumerate(reversed(digits)):
        value = int(char)
        if index % 2 == 1:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0


def _mask_cards(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        digits = re.sub(r"[ -]", "", match.group(0))
        return _PLACEHOLDER.format("CREDIT_CARD") if _luhn(digits) else match.group(0)

    return _CARD.sub(replace, text)


def mask_for_logs(value: str) -> str:
    """Replace deterministic identifiers with their entity placeholder.

    Returns the input unchanged for anything that is not a `str`: litellm walks
    dicts and lists and hands leaves of any type here, and a masking function
    that raises inside a logger would turn a PII leak into a lost trace.

    Order matters. Cards are masked before IPs and IBANs because a card number
    written with separators can contain runs that those patterns would
    otherwise claim.
    """
    if not isinstance(value, str) or not value:
        return value

    masked = _mask_cards(value)
    masked = _EMAIL.sub(_PLACEHOLDER.format("EMAIL_ADDRESS"), masked)
    masked = _US_SSN.sub(_PLACEHOLDER.format("US_SSN"), masked)
    masked = _IBAN.sub(_PLACEHOLDER.format("IBAN_CODE"), masked)
    masked = _IPV4.sub(_PLACEHOLDER.format("IP_ADDRESS"), masked)
    return masked


def install(data: dict) -> None:
    """Attach the masking function to a request's metadata.

    Called from every pre_call hook, before any early return: a request that
    skips the guardrails entirely (an exempt model, a non-chat call type) still
    reaches the logging backend, and that is precisely when nothing else is
    watching. Idempotent, so several controls calling it costs nothing.

    litellm moves this key into `litellm_params["_langfuse_masking_function"]`
    (`litellm_logging.py:5662`) before the Langfuse integration reads it.
    """
    if not isinstance(data, dict):
        return
    metadata = data.setdefault("metadata", {})
    if isinstance(metadata, dict):
        metadata.setdefault("langfuse_masking_function", mask_for_logs)
