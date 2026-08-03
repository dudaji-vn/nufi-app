"""M3 인수 테스트 — 가역 가명화·원복 + 매핑 Vault.

설계 §8 구현 인수 기준 검증:
- 가역 라운드트립 무손실(비스트리밍 + 스트리밍)
- 원본 평문이 Vault(at-rest)·감사 로그에 평문으로 남지 않음
- 강한 PII/secret 차단은 M2 와 동일(회귀 없음)

pytest 또는 `python3 tests/test_m3_reversible.py` 로 실행.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from egress_audit import MappingVault, ReversibleEgress, StreamingDeanonymizer
from egress_audit.pipeline import Finding
from egress_audit import surrogate as sg


# 고정 KEK(테스트 결정성) — 32바이트.
_KEK = bytes(range(32))


def _vault(**kw):
    return MappingVault(kek=_KEK, **kw)


def _findings(*specs):
    return [Finding(et, txt, s, e, 1.0, "test") for (et, txt, s, e) in specs]


# ── 라운드트립 (비스트리밍) ─────────────────────────────────────────────────
def test_roundtrip_nonstreaming_lossless():
    rev = ReversibleEgress(vault=_vault(), ner_backend="gazetteer")
    src = "연락처 010-1234-5678, 이메일 hong@dudaji.com, 사업자 123-45-67891 확인 바랍니다."
    r = rev.pseudonymize(src, "sess-1")
    assert not r.blocked
    assert r.pseudonymized == 3
    # 원본 PII 가 송신 텍스트에서 사라짐
    for raw in ("010-1234-5678", "hong@dudaji.com", "123-45-67891"):
        assert raw not in r.transformed_text
    assert "⟦" in r.transformed_text
    # public LLM 이 surrogate 를 그대로 보존해 응답했다고 가정 → 무손실 원복
    restored, st = rev.deanonymize(r.transformed_text, "sess-1")
    assert restored == src
    assert st["fallback"] == 0


def test_roundtrip_preserves_surrogates_in_llm_sentence():
    """LLM 이 surrogate 를 문장 속에 재배치해도 원본으로 정확 치환."""
    rev = ReversibleEgress(vault=_vault(), ner_backend="gazetteer")
    src = "010-1234-5678 로 전화하고 hong@dudaji.com 으로 메일 주세요."
    r = rev.pseudonymize(src, "s")
    # 응답: surrogate 순서를 바꿔 인용
    toks = sg._EXACT.findall(r.transformed_text)
    assert len(toks) == 2
    reply = f"메일은 {sg.make_surrogate(*toks[1])}, 전화는 {sg.make_surrogate(*toks[0])} 입니다."
    restored, st = rev.deanonymize(reply, "s")
    assert "hong@dudaji.com" in restored and "010-1234-5678" in restored
    assert st["restored"] == 2


# ── 라운드트립 (스트리밍) ──────────────────────────────────────────────────
def test_streaming_roundtrip_split_tokens():
    vault = _vault()
    # 직접 매핑 적재
    minter = sg.SurrogateMinter(vault, "s")
    sur = minter.mint("KR_PHONE", "010-1234-5678")
    full = f"전화는 {sur} 입니다."
    # 한 글자씩 청크로 분할(최악의 경계: ⟦ 와 ⟧ 가 다른 청크)
    de = StreamingDeanonymizer(vault, "s")
    out = "".join(de.feed(c) for c in full) + de.flush()
    assert out == "전화는 010-1234-5678 입니다."
    assert de.stats["restored"] == 1
    assert de.stats["fallback"] == 0


def test_streaming_arbitrary_chunk_boundaries():
    vault = _vault()
    minter = sg.SurrogateMinter(vault, "s")
    s1 = minter.mint("EMAIL", "a@b.com")
    s2 = minter.mint("KR_PHONE", "010-0000-1111")
    full = f"{s1} 와 {s2} 둘 다 보호됨"
    for size in (1, 2, 3, 5, 7, 13):
        de = StreamingDeanonymizer(vault, "s")
        chunks = [full[i:i + size] for i in range(0, len(full), size)]
        out = "".join(de.feed(c) for c in chunks) + de.flush()
        assert out == "a@b.com 와 010-0000-1111 둘 다 보호됨", f"size={size}"


# ── 세션 스코프 결정성 + 격리 ───────────────────────────────────────────────
def test_session_determinism():
    vault = _vault()
    m = sg.SurrogateMinter(vault, "s")
    a = m.mint("KR_PHONE", "010-1234-5678")
    b = m.mint("KR_PHONE", "010-1234-5678")   # 같은 원본
    c = m.mint("KR_PHONE", "010-9999-8888")   # 다른 원본
    assert a == b                              # 결정성: 같은 surrogate
    assert a != c                              # 다른 원본 → 다른 surrogate


def test_cross_session_isolation():
    vault = _vault()
    sa = sg.SurrogateMinter(vault, "A").mint("KR_PERSON", "김철수")
    sb = sg.SurrogateMinter(vault, "B").mint("KR_PERSON", "이영희")
    # 위치형 surrogate 는 세션마다 독립 카운터 → 같은 토큰 문자열일 수 있으나 파티션 격리.
    assert vault.resolve("A", sa) == "김철수"
    assert vault.resolve("B", sb) == "이영희"
    # 세션 A 의 surrogate 를 세션 B 로 조회하면 A 원본이 절대 새지 않음.
    assert vault.resolve("B", sa) != "김철수"


# ── Vault 암호화(at-rest) · 감사 로그에 평문 없음 ──────────────────────────
def test_vault_no_plaintext_at_rest():
    vault = _vault()
    secret = "010-7777-8888"
    sur = sg.SurrogateMinter(vault, "s").mint("KR_PHONE", secret)
    # 내부 엔트리의 ciphertext 어디에도 원본 바이트가 없어야 함
    entry = vault._sessions["s"].entries[sur]
    assert secret.encode("utf-8") not in entry.ciphertext
    assert isinstance(entry.ciphertext, (bytes, bytearray))
    # 감사 이벤트에 원본 평문/복호값 미기록
    blob = repr(vault.audit_events)
    assert secret not in blob
    # 복호는 정상 동작(권한 경로)
    assert vault.resolve("s", sur) == secret


def test_wrong_kek_cannot_decrypt():
    vault = _vault()
    sur = sg.SurrogateMinter(vault, "s").mint("EMAIL", "x@y.com")
    entry = vault._sessions["s"].entries[sur]
    other = MappingVault(kek=bytes(range(32, 64)))
    # 다른 KEK 로는 DEK 봉인 해제 불가 → 복호 예외
    try:
        other._unwrap(vault._sessions["s"].wrapped_dek)
        assert False, "다른 KEK 로 unwrap 성공하면 안 됨"
    except Exception:
        pass
    assert b"x@y.com" not in entry.ciphertext


# ── TTL / 수명주기 ─────────────────────────────────────────────────────────
def test_ttl_expiry_and_purge():
    clock = {"t": 1000.0}
    vault = _vault(default_ttl=60.0, time_fn=lambda: clock["t"])
    sur = sg.SurrogateMinter(vault, "s").mint("KR_PHONE", "010-1234-5678")
    assert vault.resolve("s", sur) == "010-1234-5678"
    clock["t"] += 61.0                      # TTL 경과
    assert vault.resolve("s", sur) is None  # 만료 → 복호 불가
    assert vault.purge_expired() == 1       # 확정 삭제
    assert vault.active_count("s") == 0


def test_session_purge_secure_wipe():
    vault = _vault()
    m = sg.SurrogateMinter(vault, "s")
    m.mint("KR_PHONE", "010-1234-5678")
    m.mint("EMAIL", "a@b.com")
    assert vault.active_count("s") == 2
    assert vault.purge_session("s") == 2
    assert vault.active_count("s") == 0
    assert "s" not in vault._sessions


# ── 안전망 / 관용 매칭 ─────────────────────────────────────────────────────
def test_residual_surrogate_safety_net():
    """매핑 없는 잔존 surrogate 가 사용자에게 원시 토큰으로 노출되지 않음."""
    vault = _vault()
    sg.SurrogateMinter(vault, "s")  # 세션 생성, 매핑 없음
    out, st = sg.deanonymize("미상 인물 ⟦P9⟧ 언급", vault, "s")
    assert "⟦P9⟧" not in out
    assert "[KR_PERSON]" in out
    assert st["fallback"] == 1


def test_lenient_bracket_variant():
    """LLM 이 ⟦P1⟧ 을 [P1] 로 변형 출력해도 원복(관용 매칭)."""
    vault = _vault()
    sur = sg.SurrogateMinter(vault, "s").mint("KR_PERSON", "홍길동")
    tag, n = sg._EXACT.match(sur).groups()
    variant = f"[{tag}{n}] 님 안녕하세요"
    out, st = sg.deanonymize(variant, vault, "s")
    assert "홍길동" in out
    assert st["restored"] == 1


# ── M2 회귀: 강한 PII/secret 차단 동작 불변 ────────────────────────────────
def test_strong_pii_still_blocked_no_vault_load():
    rev = ReversibleEgress(vault=_vault(), ner_backend="gazetteer")
    r = rev.pseudonymize("주민번호 900101-1234568 와 전화 010-1234-5678", "s")
    assert r.blocked                        # RRN → block(회귀 없음)
    assert r.vault_ref is None              # 차단 시 Vault 적재 안 함
    assert rev.vault.active_count() == 0


def test_secret_still_blocked():
    rev = ReversibleEgress(vault=_vault(), ner_backend="gazetteer")
    r = rev.pseudonymize("키 AKIAIOSFODNN7EXAMPLE 노출", "s")
    assert r.blocked


# ── 게이트웨이 훅 통합(스트리밍 iterator) ───────────────────────────────────
class _FakeDelta:
    def __init__(self, content): self.content = content
class _FakeChoice:
    def __init__(self, content): self.delta = _FakeDelta(content)
class _FakeChunk:
    def __init__(self, content): self.choices = [_FakeChoice(content)]


def test_hook_streaming_integration():
    from gateway.litellm_hook import EgressAuditHook
    from gateway.pii_router import PiiRouter, RoutingDecision, ROUTE_REASON_CLEAN
    hook = EgressAuditHook()
    hook.rev = ReversibleEgress(vault=_vault(), ner_backend="gazetteer")
    # PII 라우팅 비활성화: pseudonymize 경로를 테스트하기 위함 (CMP-250)
    hook.pii_router.route = lambda text, **kw: RoutingDecision(
        target_model="", reason=ROUTE_REASON_CLEAN, pii_detected=False, original_model="")

    async def run():
        pre = await hook.async_pre_call_hook(
            None, None,
            {"model": "claude-3", "messages": [
                {"role": "user", "content": "전화 010-1234-5678 로 연락주세요"}]},
            "completion")
        sid = pre["metadata"]["egress_vault_ref"]
        sent = pre["messages"][-1]["content"]
        assert "010-1234-5678" not in sent and "⟦" in sent
        # LLM 이 surrogate 를 그대로 에코한다고 가정, 글자 단위 스트리밍
        sur = sg._EXACT.search(sent).group(0)
        reply = f"네 {sur} 로 연락드리겠습니다"

        async def gen():
            for c in reply:
                yield _FakeChunk(c)

        out = []
        async for ch in hook.async_post_call_streaming_iterator_hook(
                None, gen(), {"model": "claude-3", "metadata": {"egress_vault_ref": sid}}):
            t = ch.choices[0].delta.content
            if t:
                out.append(t)
        return "".join(out)

    restored = asyncio.run(run())
    assert restored == "네 010-1234-5678 로 연락드리겠습니다"


def test_hook_nonstreaming_integration():
    from gateway.litellm_hook import EgressAuditHook
    from gateway.pii_router import RoutingDecision, ROUTE_REASON_CLEAN
    hook = EgressAuditHook()
    hook.rev = ReversibleEgress(vault=_vault(), ner_backend="gazetteer")
    # PII 라우팅 비활성화: pseudonymize 경로를 테스트하기 위함 (CMP-250)
    hook.pii_router.route = lambda text, **kw: RoutingDecision(
        target_model="", reason=ROUTE_REASON_CLEAN, pii_detected=False, original_model="")

    class _Msg:
        def __init__(self, c): self.content = c
    class _Ch:
        def __init__(self, c): self.message = _Msg(c)
    class _Resp:
        def __init__(self, c): self.choices = [_Ch(c)]

    async def run():
        pre = await hook.async_pre_call_hook(
            None, None,
            {"model": "gpt-4", "messages": [
                {"role": "user", "content": "이메일 hong@dudaji.com 확인"}]},
            "completion")
        sid = pre["metadata"]["egress_vault_ref"]
        sur = sg._EXACT.search(pre["messages"][-1]["content"]).group(0)
        resp = _Resp(f"{sur} 로 답장 보냈습니다")
        await hook.async_post_call_success_hook(pre, None, resp)
        return resp.choices[0].message.content

    assert asyncio.run(run()) == "hong@dudaji.com 로 답장 보냈습니다"


def _run():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"  PASS {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL {fn.__name__}: {e}")
        except Exception as e:  # noqa
            failed += 1
            print(f"  ERROR {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(fns)-failed}/{len(fns)} M3 tests PASS")
    return failed


if __name__ == "__main__":
    sys.exit(1 if _run() else 0)
