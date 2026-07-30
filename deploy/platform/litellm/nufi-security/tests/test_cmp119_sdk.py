"""CMP-119 — thin client SDK 수용기준 테스트.

수용기준(binary):
  1. 예제 3~5줄로 기존 OpenAI 호출을 NuFi 경유 전환.   → test_oneline_swap_*
  2. 민감정보 요청 SDK 경유 시 403 차단 + 감사 1건 적재. → test_block_and_audit
  3. 가역 가명화 라운드트립 1건 통과.                    → test_reversible_roundtrip
  4. 비스트리밍·스트리밍 사용법 포함.                    → test_streaming_*
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nufi_client import (ChatCompletion, ChatCompletionChunk, NuFi,  # noqa: E402
                         NuFiBlocked)
from egress_audit import AuditLogger  # noqa: E402

BENIGN = [{"role": "user", "content": "회사 휴가 정책을 3줄로 요약해줘"}]
SECRET = [{"role": "user", "content":
           "AWS 키: AKIAIOSFODNN7EXAMPLE / "
           "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"}]


# --- 수용기준 1: OpenAI 호환 표면(한 줄 교체) ----------------------------
def test_oneline_swap_shape():
    """client.chat.completions.create(...) 형태가 OpenAI 와 동일하게 동작."""
    client = NuFi()
    resp = client.chat.completions.create(model="gpt-4o-mini", messages=BENIGN)
    assert isinstance(resp, ChatCompletion)
    assert resp.choices[0].message.role == "assistant"
    assert isinstance(resp.choices[0].message.content, str)
    assert resp.audit_id  # public 경로 → 감사 적재됨


def test_base_url_shim_normalizes():
    """base_url 심: /v1 유무와 무관하게 동일 엔드포인트로 정규화."""
    from nufi_client.transport import HttpTransport
    assert NuFi.gateway_base_url("http://localhost:4000") == "http://localhost:4000/v1"
    for b in ("http://h:4000", "http://h:4000/", "http://h:4000/v1", "http://h:4000/v1/"):
        assert HttpTransport(b).endpoint == "http://h:4000/v1/chat/completions"


# --- 수용기준 2: 403 차단 + 감사 1건 ------------------------------------
def test_block_and_audit(tmp_path):
    log = tmp_path / "audit.jsonl"
    client = NuFi(audit_log=str(log))
    before = len(AuditLogger(path=str(log)).read_all())

    with pytest.raises(NuFiBlocked) as ei:
        client.chat.completions.create(model="gpt-4o-mini", messages=SECRET)

    err = ei.value
    assert "SECRET" in err.entities
    assert err.audit_id

    records = AuditLogger(path=str(log)).read_all()
    assert len(records) - before == 1          # 정확히 1건 적재
    rec = records[-1]
    assert rec["outcome"] == "blocked" and rec["is_public"] is True
    # 감사 본문에 원문 비밀 평문이 남지 않아야 한다(redacted).
    assert "wJalrXUtnFEMI" not in str(rec["request_body"])


# --- 수용기준 3: 가역 가명화 라운드트립 ----------------------------------
def test_reversible_roundtrip():
    client = NuFi()
    original = "홍길동님 연락처 010-1234-5678, 이메일 hong@example.com 확인 바랍니다."
    with client.pseudonymize(original) as rt:
        assert not rt.blocked
        assert rt.pseudonymized >= 1
        assert rt.masked != original
        assert "010-1234-5678" not in rt.masked   # 원문 PII 가 가려짐
        echoed = f"확인했습니다: {rt.masked}"
        restored = rt.restore(echoed)
        assert "010-1234-5678" in restored
        assert "hong@example.com" in restored
        assert "홍길동" in restored


def test_pseudonymize_blocks_strong_pii():
    """강한 PII/비밀은 가역화 대상이 아니라 차단 핸들로 표시된다."""
    client = NuFi()
    rt = client.pseudonymize("AWS secret wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY "
                             "AKIAIOSFODNN7EXAMPLE")
    assert rt.blocked and rt.pseudonymized == 0
    rt.close()


# --- 수용기준 4: 비스트리밍 / 스트리밍 -----------------------------------
def test_streaming_matches_nonstreaming():
    client = NuFi()
    full = client.chat.completions.create(model="gpt-4o-mini", messages=BENIGN)
    chunks = list(client.chat.completions.create(
        model="gpt-4o-mini", messages=BENIGN, stream=True))
    assert all(isinstance(c, ChatCompletionChunk) for c in chunks)
    streamed = "".join(c.choices[0].delta.content or "" for c in chunks)
    assert streamed == full.choices[0].message.content
    assert chunks[-1].choices[0].finish_reason == "stop"


def test_streaming_blocks_before_yield():
    """스트리밍 요청도 민감정보면 첫 청크 전에 차단된다."""
    client = NuFi()
    with pytest.raises(NuFiBlocked):
        list(client.chat.completions.create(
            model="gpt-4o-mini", messages=SECRET, stream=True))


def test_streaming_preserves_surrogates_for_restore():
    """스트리밍 청크가 surrogate(⟦P1⟧)를 쪼개지 않아 청크별 원복이 가능하다."""
    client = NuFi()
    with client.pseudonymize("홍길동 010-1234-5678") as rt:
        body = {"id": "x", "model": "m", "choices": [{
            "index": 0, "finish_reason": "stop",
            "message": {"role": "assistant", "content": f"확인: {rt.masked}"}}]}
        comp = ChatCompletion.from_body(body)
        restored = "".join(
            rt.restore(c.choices[0].delta.content)
            for c in NuFi._to_stream(comp) if c.choices[0].delta.content)
        assert "홍길동" in restored and "010-1234-5678" in restored
