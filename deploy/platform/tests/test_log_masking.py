"""Tests for the observability-path redactor.

This module exists because of a measured leak: on a STREAMED response the
client received `[EMAIL_ADDRESS]` while the Langfuse trace output held
`support@zephyr.com`. litellm's CustomStreamWrapper assembles the logged text
before the streaming guardrail hook runs, so the request path and the logging
path see different text.
"""

from __future__ import annotations

from guardrails import log_masking
from guardrails.log_masking import mask_for_logs


def test_email_is_masked():
    assert mask_for_logs("Contact support@zephyr.com now") == (
        "Contact [EMAIL_ADDRESS] now"
    )


def test_luhn_valid_card_is_masked():
    assert "[CREDIT_CARD]" in mask_for_logs("paid with 4111 1111 1111 1111 today")


def test_a_long_digit_run_that_is_not_a_card_survives():
    """The candidate pattern matches any 13-19 digit run.

    Without the Luhn check this would redact order numbers, trace ids and the
    millisecond timestamps that fill these very logs -- the things an operator
    opens the log to find. A masker that eats them is its own kind of outage.
    """
    text = "request 1753800000123456 completed"

    assert mask_for_logs(text) == text


def test_ssn_iban_and_ip_are_masked():
    masked = mask_for_logs("123-45-6789 GB82WEST12345698765432 10.0.0.5")

    assert "[US_SSN]" in masked
    assert "[IBAN_CODE]" in masked
    assert "[IP_ADDRESS]" in masked


def test_version_strings_are_not_addresses():
    """Each octet is bounded, so a four-part version is not an IPv4 address."""
    text = "upgraded to 1.2.3.4000 and semver 10.0.0.5000"

    assert mask_for_logs(text) == text


def test_names_are_left_alone_deliberately():
    """NER needs the network; a logger must not make a network call.

    Pinned so the documented boundary is a fact about the code rather than a
    claim in a docstring.
    """
    text = "Nguyen Van A visited the Hanoi office"

    assert mask_for_logs(text) == text


def test_non_strings_pass_through_untouched():
    """litellm walks dicts and lists and hands leaves of any type here.

    Raising inside a logger would turn a PII leak into a lost trace.
    """
    for value in (None, 42, 3.5, True, {"a": 1}, ["x"]):
        assert mask_for_logs(value) is value


def test_install_puts_the_callable_where_litellm_reads_it():
    data: dict = {}

    log_masking.install(data)

    assert data["metadata"]["langfuse_masking_function"] is mask_for_logs


def test_install_does_not_clobber_an_existing_masker():
    sentinel = object()
    data = {"metadata": {"langfuse_masking_function": sentinel}}

    log_masking.install(data)

    assert data["metadata"]["langfuse_masking_function"] is sentinel


def test_install_tolerates_a_malformed_metadata_shape():
    """A client can send anything. This must never raise from a hook."""
    data = {"metadata": "not-a-dict"}

    log_masking.install(data)  # must not raise
