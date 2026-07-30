"""G2a mints, G2b restores, and the two are different objects.

`tests/test_pseudonymize.py` covers the transform. This covers the wiring, where
the failures are of one kind: a control that runs, records a decision, and
rewrites nothing.

Three of them are already in the history of this file's subject and each has a
test below:

  * `Finding` has no `message_index`. A first draft filtered pooled findings on
    that attribute, so every filter returned empty and G2a rewrote nothing while
    the audit trail recorded `pseudonymize`.
  * The two legs live in different control objects. A per-control vault would
    make every session unresolvable from the other side: restoration reports
    `fallback` for every token, the user receives labels, and both legs look
    healthy.
  * Restoration must run AFTER redaction. Restoring first puts the address back
    and G2b redacts the value it just recovered.
"""

from pathlib import Path
from typing import Any

import pytest
import yaml
from guardrails import pseudonymize
from guardrails.entrypoints import G2aPiiInput, G2bPiiOutput
from guardrails.policy import Policy
from guardrails.types import Finding

# A DETECTABLE domain, and the TLD is the reason. Measured against the shipped
# Presidio analyzer: `jane.doe@acme.example` scores `URL:0.5` and NO
# `EMAIL_ADDRESS` at all, while `.com`, `.io` and `.co.kr` all score
# `EMAIL_ADDRESS:1.0`. The stub scanners below make that irrelevant here, but a
# constant copied out of this file into a live test would measure nothing --
# which is exactly what happened to the first end-to-end smoke test of this
# feature.
EMAIL = "jane.doe@acme-industrial.com"


class _EmailScanner:
    """Finds one substring per span, with the span's own offsets."""

    name = "presidio"

    def __init__(self, needle: str = EMAIL, entity: str = "EMAIL_ADDRESS") -> None:
        self._needle = needle
        self._entity = entity

    async def scan(self, spans: list[Any]) -> list[Finding]:
        found = []
        for span in spans:
            start = span.text.find(self._needle)
            if start == -1:
                continue
            found.append(
                Finding(
                    risk="LLM02_PII",
                    detector="presidio",
                    score=1.0,
                    source=span.source,
                    start=start,
                    end=start + len(self._needle),
                    entity=self._entity,
                )
            )
        return found


class _NoopScanner:
    name = "nufi_pii"

    async def scan(self, spans: list[Any]) -> list[Finding]:
        return []


@pytest.fixture
def policy_path(tmp_path: Path) -> Path:
    """A copy of the real policy with G2a switched to `pseudonymize`.

    The real file is copied rather than hand-written so every threshold, source
    and option stays exactly what production uses -- a hand-built policy would
    let this suite pass against a shape policy.yaml does not have.
    """
    source = Path(__file__).resolve().parent.parent / "litellm" / "guardrails" / "policy.yaml"
    body = yaml.safe_load(source.read_text(encoding="utf-8"))
    g2a = body["controls"]["G2a"]
    g2a["action"] = "pseudonymize"
    g2a["mode"] = "pre_call"
    options = g2a.setdefault("options", {})
    options["require_opt_in"] = True
    path = tmp_path / "policy.yaml"
    path.write_text(yaml.safe_dump(body), encoding="utf-8")
    return path


def _g2a(policy_path: Path) -> G2aPiiInput:
    policy = Policy.load(str(policy_path))
    guard = G2aPiiInput(policy=policy, scanner=_EmailScanner(), nufi_scanner=_NoopScanner())
    guard._control = policy.control("G2a").with_mode("pre_call")
    return guard


def _g2b(policy_path: Path) -> G2bPiiOutput:
    policy = Policy.load(str(policy_path))
    guard = G2bPiiOutput(policy=policy, scanner=_EmailScanner(), nufi_scanner=_NoopScanner())
    guard._control = policy.control("G2b").with_mode("post_call")
    return guard


class _Key:
    def __init__(self, opted_in: bool | None = True) -> None:
        self.metadata = {} if opted_in is None else {pseudonymize.OPT_IN_KEY: opted_in}
        self.key_alias = "test"
        self.team_id = None
        self.parent_otel_span = None


def _request(content: str, **extra: Any) -> dict[str, Any]:
    return {
        "model": "gemini-2.5-flash",
        "messages": [{"role": "user", "content": content}],
        **extra,
    }


@pytest.fixture(autouse=True)
def _fresh_vault(monkeypatch):
    """A vault per test. The shared instance is process-wide by design, and
    leaking sessions between tests would let one test's mapping satisfy
    another's restore."""
    monkeypatch.setattr(pseudonymize, "_SHARED", pseudonymize.Pseudonymizer())


# --- the request leg ---------------------------------------------------------


async def test_the_value_is_replaced_and_the_session_recorded(policy_path):
    guard = _g2a(policy_path)
    data = _request(f"Please write a signature using {EMAIL}")

    out = await guard.async_pre_call_hook(_Key(), None, data, "acompletion")

    assert EMAIL not in str(out["messages"]), "the value must not reach the provider"
    ref = out["metadata"][pseudonymize.SESSION_KEY]
    assert ref.startswith("grd-pseudo-")
    # The instruction is what makes the model carry the token rather than ask
    # about it; without it a signature request answered "Please tell me what
    # ⟦E1⟧ represents!".
    assert out["messages"][0]["role"] == "system"
    assert "placeholder" in out["messages"][0]["content"]


async def test_a_pooled_finding_would_have_rewritten_nothing(policy_path):
    """The `message_index` bug, pinned. `Finding` carries `start`/`end` and NOT
    which text they index into, so a rewrite driven by pooled findings has no way
    to attribute them and silently replaces nothing."""
    guard = _g2a(policy_path)
    data = _request(f"first {EMAIL}")
    data["messages"].append({"role": "user", "content": f"second {EMAIL}"})

    out = await guard.async_pre_call_hook(_Key(), None, data, "acompletion")

    bodies = [m["content"] for m in out["messages"] if m["role"] == "user"]
    assert all(EMAIL not in body for body in bodies), bodies
    # The same value in two messages shares one surrogate: their minter
    # deduplicates within a session, and one session covers the request.
    assert bodies[0].count("⟦E1⟧") == 1 and bodies[1].count("⟦E1⟧") == 1


async def test_without_opt_in_nothing_is_rewritten(policy_path):
    guard = _g2a(policy_path)
    data = _request(f"Please write a signature using {EMAIL}")

    out = await guard.async_pre_call_hook(_Key(opted_in=False), None, data, "acompletion")

    assert EMAIL in out["messages"][0]["content"]
    assert pseudonymize.SESSION_KEY not in (out.get("metadata") or {})
    assert out["messages"][0]["role"] == "user", "no instruction on a request we did not rewrite"


async def test_a_key_with_no_metadata_does_not_opt_in(policy_path):
    guard = _g2a(policy_path)
    data = _request(f"a {EMAIL}")

    out = await guard.async_pre_call_hook(_Key(opted_in=None), None, data, "acompletion")

    assert EMAIL in out["messages"][0]["content"]


async def test_require_opt_in_false_serves_every_request(policy_path, tmp_path):
    body = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    body["controls"]["G2a"]["options"]["require_opt_in"] = False
    other = tmp_path / "open.yaml"
    other.write_text(yaml.safe_dump(body), encoding="utf-8")

    guard = _g2a(other)
    out = await guard.async_pre_call_hook(
        _Key(opted_in=None), None, _request(f"a {EMAIL}"), "acompletion"
    )

    assert EMAIL not in str(out["messages"])


async def test_a_streamed_request_is_pseudonymized_too(policy_path):
    """Streaming is the chat default, so a feature that skipped it would be a
    feature nobody in chat ever gets. It was skipped and counted until the
    restore path existed; this asserts it no longer is."""
    guard = _g2a(policy_path)
    data = _request(f"a {EMAIL}", stream=True)

    out = await guard.async_pre_call_hook(_Key(), None, data, "acompletion")

    assert EMAIL not in str(out["messages"])
    assert out["metadata"][pseudonymize.SESSION_KEY].startswith("grd-pseudo-")


async def test_no_pii_leaves_the_request_and_the_vault_alone(policy_path):
    guard = _g2a(policy_path)
    data = _request("what is the capital of Vietnam?")

    out = await guard.async_pre_call_hook(_Key(), None, data, "acompletion")

    assert out["messages"] == [{"role": "user", "content": "what is the capital of Vietnam?"}]
    assert pseudonymize.shared().active_count() == 0, "nothing to mint means no session"


async def test_an_unusable_metadata_shape_leaves_the_request_unchanged(policy_path):
    """Nowhere to record the session means the rewrite must not happen: tokens
    the response leg cannot resolve are worse than values it would redact."""
    guard = _g2a(policy_path)
    data = _request(f"a {EMAIL}")
    data["metadata"] = "not a dict"

    out = await guard.async_pre_call_hook(_Key(), None, data, "acompletion")

    assert EMAIL in out["messages"][0]["content"]
    assert pseudonymize.shared().active_count() == 0, "the session must be wiped, not orphaned"


# --- the response leg, and the two legs together -----------------------------


async def test_the_user_gets_their_own_value_back(policy_path):
    """The round trip across TWO control objects, which is the point: a
    per-control vault would make this return a label and look healthy."""
    g2a, g2b = _g2a(policy_path), _g2b(policy_path)
    data = _request(f"Sign off with {EMAIL}")

    data = await g2a.async_pre_call_hook(_Key(), None, data, "acompletion")
    model_said = f"Best regards,\nJane Doe\n{data['messages'][-1]['content'].split()[-1]}"

    out = await g2b.apply_guardrail(
        inputs={"texts": [model_said]}, request_data=data, input_type="response"
    )

    assert EMAIL in out["texts"][0]
    assert "⟦" not in out["texts"][0]


async def test_pii_the_model_invented_is_still_redacted(policy_path):
    """Restoration must not become a hole in redaction. The surrogate is restored
    AND a different address the model produced on its own is redacted, in the
    same response."""
    g2a = _g2a(policy_path)
    data = await g2a.async_pre_call_hook(_Key(), None, _request(f"about {EMAIL}"), "acompletion")

    invented = "someone.else@other-vendor.com"
    g2b_with_both = _g2b(policy_path)
    g2b_with_both._scanners = [_EmailScanner(needle=invented), _NoopScanner()]
    said = f"Your address ⟦E1⟧ and also {invented}"

    out = await g2b_with_both.apply_guardrail(
        inputs={"texts": [said]}, request_data=data, input_type="response"
    )

    assert EMAIL in out["texts"][0], "the user's own value comes back"
    assert invented not in out["texts"][0], "the model's own PII is still redacted"
    assert "[EMAIL_ADDRESS]" in out["texts"][0]


async def test_the_session_is_wiped_after_a_non_streamed_response(policy_path):
    g2a, g2b = _g2a(policy_path), _g2b(policy_path)
    data = await g2a.async_pre_call_hook(_Key(), None, _request(f"a {EMAIL}"), "acompletion")
    assert pseudonymize.shared().active_count() == 1

    await g2b.apply_guardrail(
        inputs={"texts": ["done ⟦E1⟧"]}, request_data=data, input_type="response"
    )

    assert pseudonymize.shared().active_count() == 0, "a mapping outliving its request leaks"


async def test_a_response_with_no_session_is_untouched(policy_path):
    g2b = _g2b(policy_path)
    out = await g2b.apply_guardrail(
        inputs={"texts": ["plain text ⟦E1⟧"]}, request_data=_request("x"), input_type="response"
    )

    assert out["texts"][0] == "plain text ⟦E1⟧", "no ref means nothing to resolve against"


async def test_restoration_happens_even_when_g2b_is_not_enforcing(policy_path):
    """A shadow-mode G2b that skipped restoration would hand a workload that
    opted in a response full of raw surrogates."""
    g2a = _g2a(policy_path)
    data = await g2a.async_pre_call_hook(_Key(), None, _request(f"a {EMAIL}"), "acompletion")

    policy = Policy.load(str(policy_path))
    shadow = G2bPiiOutput(policy=policy, scanner=_EmailScanner(), nufi_scanner=_NoopScanner())
    shadow._control = policy.control("G2b").with_mode("logging_only")

    out = await shadow.apply_guardrail(
        inputs={"texts": ["here: ⟦E1⟧"]}, request_data=data, input_type="response"
    )

    assert EMAIL in out["texts"][0]


# --- the streaming leg -------------------------------------------------------
#
# The hard part of streaming is not the restore, it is that what goes on the
# WIRE and what `verify` judges must differ. `feed` returns what redaction
# produced (surrogates); `deliver` puts the values back on the way out. If
# restoration leaked into `record_sent`, `verify` would re-scan a correctly
# restored address, find PII, and report every pseudonymized stream as a leak on
# `nufi_guardrail_stream_unenforced_total` -- the one counter here that is
# supposed to sit at zero and mean something when it does not.


async def _streamed(guard, data, texts):
    """Drive the real iterator hook and return what a client would assemble."""
    from guardrails import streaming as _streaming

    from tests.test_streaming import aiter, content_chunks

    out: list[str] = []
    async for chunk in guard.async_post_call_streaming_iterator_hook(
        user_api_key_dict=_Key(), response=aiter(content_chunks(texts)), request_data=data
    ):
        for _, content, _ in _streaming.iter_deltas(chunk):
            if content:
                out.append(content)
    return "".join(out)


async def test_a_streamed_response_restores_the_users_value(policy_path):
    g2a, g2b = _g2a(policy_path), _g2b(policy_path)
    data = await g2a.async_pre_call_hook(
        _Key(), None, _request(f"sign off with {EMAIL}", stream=True), "acompletion"
    )

    assembled = await _streamed(g2b, data, ["Best regards,\n", "Jane Doe\n", "⟦E1⟧"])

    assert assembled.endswith(EMAIL), assembled
    assert "⟦" not in assembled


@pytest.mark.parametrize("head,tail", [("⟦E1⟧"[:i], "⟦E1⟧"[i:]) for i in range(5)])
async def test_a_surrogate_split_across_a_chunk_boundary_still_restores(
    policy_path, head, tail
):
    """Every split of the token, including the degenerate ones. A boundary buffer
    that got this wrong would emit half a token and then the other half, and the
    client's concatenation would show `⟦E` followed by `1⟧` -- no value restored
    and nothing raised."""
    g2a, g2b = _g2a(policy_path), _g2b(policy_path)
    data = await g2a.async_pre_call_hook(
        _Key(), None, _request(f"a {EMAIL}", stream=True), "acompletion"
    )

    assembled = await _streamed(g2b, data, ["contact ", head, tail, " today"])

    assert assembled == f"contact {EMAIL} today", assembled


async def test_a_streamed_restore_is_not_reported_as_a_leak(policy_path):
    """The reason `deliver` exists. `verify` re-scans what `feed` produced, and a
    restored address is PII by G2b's own detector -- if restoration ran inside
    `feed`, this counter would move on every correct round trip."""
    from guardrails import audit as _audit

    def unenforced() -> float:
        for metric in _audit.REGISTRY.collect():
            if metric.name != "nufi_guardrail_stream_unenforced":
                continue
            return sum(
                s.value for s in metric.samples
                if s.name.endswith("_total") and s.labels.get("control") == "G2b"
            )
        return 0.0

    g2a, g2b = _g2a(policy_path), _g2b(policy_path)
    data = await g2a.async_pre_call_hook(
        _Key(), None, _request(f"a {EMAIL}", stream=True), "acompletion"
    )

    before = unenforced()
    assembled = await _streamed(g2b, data, ["here it is: ", "⟦E1⟧"])

    assert EMAIL in assembled, "the round trip must actually have happened"
    assert unenforced() == before, "a correct restore was reported as an unenforced leak"


async def test_the_session_is_wiped_when_the_stream_ends(policy_path):
    """`apply_guardrail` cannot do this for a stream: it runs before the chunks
    are consumed, so wiping there would destroy the mapping mid-stream."""
    g2a, g2b = _g2a(policy_path), _g2b(policy_path)
    data = await g2a.async_pre_call_hook(
        _Key(), None, _request(f"a {EMAIL}", stream=True), "acompletion"
    )
    assert pseudonymize.shared().active_count() == 1

    await _streamed(g2b, data, ["done ⟦E1⟧"])

    assert pseudonymize.shared().active_count() == 0


async def test_a_streamed_response_with_no_session_is_untouched(policy_path):
    g2b = _g2b(policy_path)
    assembled = await _streamed(g2b, _request("x", stream=True), ["plain ⟦E1⟧ text"])

    assert assembled == "plain ⟦E1⟧ text"


async def test_model_pii_is_still_redacted_while_a_surrogate_is_restored(policy_path):
    """Both jobs, in one stream. Restoration must not become a hole in
    redaction."""
    g2a = _g2a(policy_path)
    data = await g2a.async_pre_call_hook(
        _Key(), None, _request(f"a {EMAIL}", stream=True), "acompletion"
    )

    invented = "someone.else@other-vendor.com"
    g2b = _g2b(policy_path)
    g2b._scanners = [_EmailScanner(needle=invented), _NoopScanner()]

    assembled = await _streamed(g2b, data, [f"yours ⟦E1⟧ and theirs {invented} end"])

    assert EMAIL in assembled
    assert invented not in assembled
    assert "[EMAIL_ADDRESS]" in assembled


async def test_a_stream_ending_mid_token_still_delivers_the_tail(policy_path):
    """The stream ends while the boundary buffer is HOLDING an incomplete token.

    Two things are only reachable through this case, and mutation testing found
    both were uncovered:

      * `flush()` at `final`. Without it the held text never reaches the client
        and is silently dropped, while `record_sent` says it was delivered.
      * the `not delivered` half of the main loop's `content is None` guard. The
        final delta carries no content, so a guard that only checked `emitted`
        would `continue` before `set_delta` and throw the flushed tail away.

    The tail is emitted as-is rather than dropped: a token the model mangled is a
    visible oddity, while swallowing it truncates the answer.
    """
    g2a, g2b = _g2a(policy_path), _g2b(policy_path)
    data = await g2a.async_pre_call_hook(
        _Key(), None, _request(f"a {EMAIL}", stream=True), "acompletion"
    )

    assembled = await _streamed(g2b, data, ["contact ", "⟦E"])

    assert assembled == "contact ⟦E", assembled


async def test_apply_guardrail_does_not_restore_a_second_time_for_a_stream(policy_path):
    """litellm routes the end-of-stream leg through `apply_guardrail` as well, so
    it runs for a streamed request too. It must not act: restoring again would
    double-count `restored_total` against a rewrite litellm discards, and wiping
    the session would destroy the mapping the chunks are still using."""
    g2a, g2b = _g2a(policy_path), _g2b(policy_path)
    data = await g2a.async_pre_call_hook(
        _Key(), None, _request(f"a {EMAIL}", stream=True), "acompletion"
    )

    out = await g2b.apply_guardrail(
        inputs={"texts": ["here: ⟦E1⟧"]}, request_data=data, input_type="response"
    )

    assert out["texts"][0] == "here: ⟦E1⟧", "the streaming leg owns restoration"
    assert pseudonymize.shared().active_count() == 1, "the mapping must survive for the chunks"

    # And the stream that follows still works, which is the point of not wiping.
    assembled = await _streamed(g2b, data, ["here: ⟦E1⟧"])
    assert EMAIL in assembled
