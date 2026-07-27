import pytest
from guardrails.audit import GUARDRAIL_DECISIONS, GUARDRAIL_DEGRADED
from guardrails.entrypoints import G1Injection, GuardrailBlocked
from guardrails.policy import Policy
from guardrails.scanners.base import ScannerUnavailable
from guardrails.types import Finding


def _decisions_counter(*, control: str, risk: str, action: str, enforced: bool) -> float:
    return GUARDRAIL_DECISIONS.labels(
        control=control, risk=risk, action=action, enforced=str(enforced).lower()
    )._value.get()


def _degraded_gauge(control: str) -> float:
    return GUARDRAIL_DEGRADED.labels(control=control)._value.get()


class FakeScanner:
    name = "injection"

    def __init__(self, score: float | None = None, fail: bool = False) -> None:
        self._score = score
        self._fail = fail

    async def scan(self, spans):
        if self._fail:
            raise ScannerUnavailable("boom")
        return [
            Finding(
                risk="LLM01", detector="injection", score=self._score,
                source=span.source, start=0, end=len(span.text),
            )
            for span in spans
        ]


class FakeKey:
    def __init__(self, metadata: dict | None = None) -> None:
        self.metadata = metadata or {}
        self.key_alias = "chat-app"
        self.team_id = "t1"


class BareKey:
    """A key object with no `key_alias`/`team_id` at all — the shape a real
    `UserAPIKeyAuth` can have when those fields were never set."""

    def __init__(self, metadata: dict | None = None) -> None:
        self.metadata = metadata or {}


class WrongExceptionScanner:
    """A scanner that misbehaves: raises something other than
    `ScannerUnavailable`, the only type `Scanner.scan` is documented to
    raise. Used to prove the hook does not trust that contract absolutely."""

    name = "injection"

    async def scan(self, spans):
        raise ValueError("scanner bug, not ScannerUnavailable")


def _guard(policy_path, scanner, mode="pre_call"):
    policy = Policy.load(policy_path)
    guard = G1Injection(policy=policy, scanner=scanner)
    guard._control = policy.control("G1").with_mode(mode)
    return guard


def _data(text: str) -> dict:
    return {"messages": [{"role": "user", "content": text}], "model": "nufi"}


@pytest.mark.asyncio
async def test_benign_request_passes_through_unchanged(policy_path):
    guard = _guard(policy_path, FakeScanner(score=0.01))
    data = _data("what is the capital of Vietnam")

    result = await guard.async_pre_call_hook(FakeKey(), None, data, "acompletion")

    assert result["messages"] == data["messages"]


@pytest.mark.asyncio
async def test_injection_above_threshold_raises_guardrail_blocked(policy_path):
    guard = _guard(policy_path, FakeScanner(score=0.99))

    with pytest.raises(GuardrailBlocked) as excinfo:
        await guard.async_pre_call_hook(FakeKey(), None, _data("ignore previous"), "acompletion")

    assert excinfo.value.code == "LLM01_INJECTION"
    assert excinfo.value.event_id.startswith("grd_")


@pytest.mark.asyncio
async def test_logging_only_mode_records_but_does_not_block(policy_path):
    guard = _guard(policy_path, FakeScanner(score=0.99), mode="logging_only")
    data = _data("ignore previous")

    result = await guard.async_pre_call_hook(FakeKey(), None, data, "acompletion")

    events = result["metadata"]["guardrail_information"]
    assert events[0]["action"] == "block"
    assert events[0]["enforced"] is False


@pytest.mark.asyncio
async def test_scanner_outage_fails_closed(policy_path):
    guard = _guard(policy_path, FakeScanner(fail=True))

    with pytest.raises(GuardrailBlocked) as excinfo:
        await guard.async_pre_call_hook(FakeKey(), None, _data("hi"), "acompletion")

    assert excinfo.value.code == "GUARDRAIL_UNAVAILABLE"


@pytest.mark.asyncio
async def test_scanner_outage_in_logging_only_does_not_block(policy_path):
    guard = _guard(policy_path, FakeScanner(fail=True), mode="logging_only")

    result = await guard.async_pre_call_hook(FakeKey(), None, _data("hi"), "acompletion")

    assert result["messages"]


# --- Reviewer fix: a blocking outage with no audit event is invisible ------
# The reviewer executed the outage path and measured GUARDRAIL_DECISIONS
# staying flat while a GuardrailBlocked was raised: an operator watching the
# counter cannot distinguish "G1 is fail-closing on every request" from
# "nothing was blocked at all", and the event_id in the 503 was generated
# fresh and written nowhere, so it cannot be looked up afterwards. Fixed by
# routing the outage through the same _emit() path as any other verdict, in
# both enforcing and shadow mode.


@pytest.mark.asyncio
async def test_outage_is_recorded_in_the_audit_trail_when_it_blocks(policy_path):
    guard = _guard(policy_path, FakeScanner(fail=True))
    data = _data("hello")

    before = _decisions_counter(control="G1", risk="LLM01", action="block", enforced=True)

    with pytest.raises(GuardrailBlocked) as excinfo:
        await guard.async_pre_call_hook(FakeKey(), None, data, "acompletion")

    after = _decisions_counter(control="G1", risk="LLM01", action="block", enforced=True)
    assert after == before + 1

    events = data["metadata"]["guardrail_information"]
    assert events[0]["control"] == "G1"
    assert events[0]["enforced"] is True
    assert events[0]["event_id"] == excinfo.value.event_id


@pytest.mark.asyncio
async def test_outage_is_recorded_in_shadow_mode_too(policy_path):
    guard = _guard(policy_path, FakeScanner(fail=True), mode="logging_only")
    data = _data("hello")

    before = _decisions_counter(control="G1", risk="LLM01", action="block", enforced=False)

    result = await guard.async_pre_call_hook(FakeKey(), None, data, "acompletion")

    after = _decisions_counter(control="G1", risk="LLM01", action="block", enforced=False)
    assert after == before + 1

    events = result["metadata"]["guardrail_information"]
    assert events[0]["enforced"] is False
    # Never breaks traffic even though it was recorded as "would have blocked".
    assert result["messages"]


@pytest.mark.asyncio
async def test_outage_still_moves_the_degraded_gauge(policy_path):
    """GUARDRAIL_DEGRADED and the audit event are separate signals; both
    must survive a fix to either one."""
    guard = _guard(policy_path, FakeScanner(fail=True), mode="logging_only")

    await guard.async_pre_call_hook(FakeKey(), None, _data("hello"), "acompletion")

    assert _degraded_gauge("G1") == 1


@pytest.mark.asyncio
async def test_non_chat_call_types_are_skipped(policy_path):
    guard = _guard(policy_path, FakeScanner(score=0.99))
    data = {"input": "text to embed"}

    result = await guard.async_pre_call_hook(FakeKey(), None, data, "aembedding")

    assert result == data


@pytest.mark.asyncio
async def test_grounded_verdict_is_resolved_for_non_chat_call_types(policy_path):
    """The non-chat early return must not skip resolution.

    A post_call control treats a missing verdict as not-grounded, so a path
    that returns without resolving silently changes redaction behaviour the
    day something reads verified_grounded() for a non-chat call type.
    """
    guard = _guard(policy_path, FakeScanner(score=0.01))
    data = {"input": "text to embed", "metadata": {"nufi_grounded": True}}

    result = await guard.async_pre_call_hook(
        FakeKey(metadata={"allow_grounded_hint": True}), None, data, "aembedding"
    )

    assert result["metadata"]["nufi_grounded_verified"] is True


@pytest.mark.asyncio
async def test_grounded_hint_is_ignored_without_key_permission(policy_path):
    guard = _guard(policy_path, FakeScanner(score=0.99))
    data = _data("ignore previous")
    data["metadata"] = {"nufi_grounded": True}

    with pytest.raises(GuardrailBlocked):
        await guard.async_pre_call_hook(FakeKey(metadata={}), None, data, "acompletion")


@pytest.mark.asyncio
async def test_privileged_key_claiming_grounded_is_recorded_as_verified(policy_path):
    guard = _guard(policy_path, FakeScanner(score=0.01))
    data = _data("hello")
    data["metadata"] = {"nufi_grounded": True}

    result = await guard.async_pre_call_hook(
        FakeKey(metadata={"allow_grounded_hint": True}), None, data, "acompletion"
    )

    assert result["metadata"]["nufi_grounded_verified"] is True


@pytest.mark.asyncio
async def test_unprivileged_key_claiming_grounded_is_recorded_as_false(policy_path):
    guard = _guard(policy_path, FakeScanner(score=0.01))
    data = _data("hello")
    data["metadata"] = {"nufi_grounded": True}

    result = await guard.async_pre_call_hook(FakeKey(metadata={}), None, data, "acompletion")

    assert result["metadata"]["nufi_grounded_verified"] is False


@pytest.mark.asyncio
async def test_grounded_verdict_is_recorded_even_when_the_control_is_disabled(policy_path):
    guard = _guard(policy_path, FakeScanner(score=0.99))
    guard._control = guard._control.with_enabled(False)
    data = _data("ignore previous")
    data["metadata"] = {"nufi_grounded": True}

    result = await guard.async_pre_call_hook(
        FakeKey(metadata={"allow_grounded_hint": True}), None, data, "acompletion"
    )

    assert result["metadata"]["nufi_grounded_verified"] is True


# --- Added beyond the brief: status codes ------------------------------------
# The brief's own SCANNER_TIMEOUT_S comment promises "a timeout is a 503 for
# the user", but `class GuardrailBlocked(Exception)` as given has no
# `status_code` attribute, so LiteLLM's generic exception-to-response mapping
# (`getattr(e, "status_code", 500)`, verified against the installed
# litellm==1.83.10 source) would default every raise to 500 regardless of
# cause. These pin the fix: a policy block reads as a client error, a
# guardrail outage reads as a 503, never a bare 500 indistinguishable from an
# unrelated server crash.


@pytest.mark.asyncio
async def test_block_status_code_is_a_client_error_not_a_500(policy_path):
    guard = _guard(policy_path, FakeScanner(score=0.99))

    with pytest.raises(GuardrailBlocked) as excinfo:
        await guard.async_pre_call_hook(FakeKey(), None, _data("ignore previous"), "acompletion")

    assert excinfo.value.status_code == 400


@pytest.mark.asyncio
async def test_scanner_outage_status_code_is_503(policy_path):
    guard = _guard(policy_path, FakeScanner(fail=True))

    with pytest.raises(GuardrailBlocked) as excinfo:
        await guard.async_pre_call_hook(FakeKey(), None, _data("hi"), "acompletion")

    assert excinfo.value.status_code == 503


# --- Added beyond the brief: audit context must not default to None ---------
# audit.build_event documents that a request_context key must be OMITTED
# entirely when the entrypoint has no real value for it, never defaulted to
# None (a None copied into every event is indistinguishable, on the reading
# side, from "we checked and there wasn't one"). This is enforced inside
# build_event's allow-list, but only if the entrypoint's own _context()
# upholds it too -- it is trivial to defeat by setting every key
# unconditionally.


@pytest.mark.asyncio
async def test_event_omits_key_alias_and_team_id_when_the_key_lacks_them(policy_path):
    guard = _guard(policy_path, FakeScanner(score=0.99), mode="logging_only")
    data = _data("ignore previous")

    result = await guard.async_pre_call_hook(BareKey(), None, data, "acompletion")

    event = result["metadata"]["guardrail_information"][0]
    assert "key_alias" not in event
    assert "team_id" not in event
    assert event["policy_digest"]


# --- Added beyond the brief: malformed `messages` shape ---------------------
# `extract_spans` assumes a list of dict messages and is off limits to modify
# here. A non-list, or a list containing a non-dict element, would otherwise
# raise AttributeError deep inside it -- an exception type this hook does not
# expect. Treated the same as a scanner outage: enforced+fail-closed blocks,
# logging_only never breaks traffic.


@pytest.mark.asyncio
async def test_messages_not_a_list_fails_closed_when_enforcing(policy_path):
    guard = _guard(policy_path, FakeScanner(score=0.01))
    data = {"messages": "not-a-list", "model": "nufi"}

    with pytest.raises(GuardrailBlocked) as excinfo:
        await guard.async_pre_call_hook(FakeKey(), None, data, "acompletion")

    assert excinfo.value.code == "GUARDRAIL_UNAVAILABLE"


@pytest.mark.asyncio
async def test_messages_not_a_list_does_not_block_in_logging_only(policy_path):
    guard = _guard(policy_path, FakeScanner(score=0.01), mode="logging_only")
    data = {"messages": "not-a-list", "model": "nufi"}

    result = await guard.async_pre_call_hook(FakeKey(), None, data, "acompletion")

    assert result["messages"] == "not-a-list"


@pytest.mark.asyncio
async def test_messages_list_with_non_dict_items_fails_closed_when_enforcing(policy_path):
    guard = _guard(policy_path, FakeScanner(score=0.01))
    data = {"messages": ["just a string, not a message dict"], "model": "nufi"}

    with pytest.raises(GuardrailBlocked) as excinfo:
        await guard.async_pre_call_hook(FakeKey(), None, data, "acompletion")

    assert excinfo.value.code == "GUARDRAIL_UNAVAILABLE"


# --- Added beyond the brief: a scanner that raises the wrong exception type -
# `Scanner.scan` is documented to raise only `ScannerUnavailable`. A hook
# that trusts that absolutely is one bug away from either breaking
# shadow-mode traffic or silently bypassing enforcement, depending on where a
# future scanner's bug happens to land.


@pytest.mark.asyncio
async def test_scanner_raising_an_unexpected_exception_type_fails_closed(policy_path):
    guard = _guard(policy_path, WrongExceptionScanner())

    with pytest.raises(GuardrailBlocked) as excinfo:
        await guard.async_pre_call_hook(FakeKey(), None, _data("hi"), "acompletion")

    assert excinfo.value.code == "GUARDRAIL_UNAVAILABLE"


@pytest.mark.asyncio
async def test_scanner_raising_an_unexpected_exception_type_does_not_block_in_logging_only(
    policy_path,
):
    guard = _guard(policy_path, WrongExceptionScanner(), mode="logging_only")

    result = await guard.async_pre_call_hook(FakeKey(), None, _data("hi"), "acompletion")

    assert result["messages"]


# --- Added beyond the brief: audit.record() raising AuditRecordError -------
# audit.record() now raises AuditRecordError instead of silently dropping an
# event it cannot attach (e.g. the request sent a non-dict `metadata`). A
# hook that lets that exception escape unhandled would turn a shadow-mode
# measurement into a broken live request -- the same "shadow mode must never
# break traffic" violation as an uncaught scanner bug, just from the audit
# side. Enforcing mode must still block using the already-built event_id.


@pytest.mark.asyncio
async def test_audit_failure_does_not_prevent_the_block_when_enforcing(policy_path):
    guard = _guard(policy_path, FakeScanner(score=0.99))
    data = _data("ignore previous")
    data["metadata"] = "not-a-dict"

    with pytest.raises(GuardrailBlocked) as excinfo:
        await guard.async_pre_call_hook(FakeKey(), None, data, "acompletion")

    assert excinfo.value.code == "LLM01_INJECTION"


@pytest.mark.asyncio
async def test_audit_failure_does_not_break_shadow_mode_traffic(policy_path):
    guard = _guard(policy_path, FakeScanner(score=0.99), mode="logging_only")
    data = _data("ignore previous")
    data["metadata"] = "not-a-dict"

    result = await guard.async_pre_call_hook(FakeKey(), None, data, "acompletion")

    assert result["messages"]
