# `nufi_client` — NuFi 얇은 Python 클라이언트

**한 줄**만 바꿔 기존 OpenAI 호출을 NuFi Egress-Audit 게이트웨이 경유로
전환하는 얇은 SDK. 게이트웨이 `/v1/chat/completions` 를 재사용한다(OpenAI 호환).

## 빠른 시작 (서버 불필요)

```python
from nufi_client import NuFi

client = NuFi()                                   # in-process 게이트웨이
resp = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "휴가 정책 요약"}])
print(resp.choices[0].message.content)
```

`NuFi()` 는 같은 프로세스의 게이트웨이를 직접 호출하므로 서버 기동 없이 동작한다
(예제·테스트·노트북에 적합).

## 기존 OpenAI 클라이언트 — base_url 심

이미 `openai` 패키지를 쓰고 있다면 **base_url 만 교체**한다(코드 변경 최소):

```python
from openai import OpenAI
from nufi_client import NuFi

client = OpenAI(base_url=NuFi.gateway_base_url(), api_key="nufi-local")
# 게이트웨이 기동: PORT=4000 ./scripts/run_gateway.sh
```

또는 NuFi 얇은 클라이언트를 HTTP 모드로:

```python
client = NuFi(base_url="http://localhost:4000")   # 실행 중인 게이트웨이로 HTTP
```

## 민감정보 차단 (403) + 감사

민감정보(비밀/강한 PII 등)가 섞이면 게이트웨이가 송신을 차단하고 감사 1건을 적재한다.
SDK 는 이를 `NuFiBlocked` 예외로 올린다.

```python
from nufi_client import NuFi, NuFiBlocked

try:
    client.chat.completions.create(model="gpt-4o-mini", messages=msgs)
except NuFiBlocked as e:
    print(e.entities, e.audit_id)   # 예: ['SECRET'], 감사 레코드 id
```

## 가역 가명화 라운드트립

약한 PII 는 가역 surrogate(`⟦P1⟧`)로 치환해 외부로 내보내고, 응답에서 원본으로 복원한다.
세션 매핑은 `with` 종료 시 즉시 폐기된다.

```python
with client.pseudonymize("홍길동 010-1234-5678") as rt:
    masked = rt.masked                 # "⟦P1⟧ ⟦T1⟧"  ← 외부로 나가는 값
    restored = rt.restore(llm_output)  # 응답 내 surrogate → 원본 복원
```

## 스트리밍 / 비스트리밍

```python
# 비스트리밍
resp = client.chat.completions.create(model="gpt-4o-mini", messages=msgs)

# 스트리밍 (OpenAI 와 동일하게 delta.content 누적)
for chunk in client.chat.completions.create(
        model="gpt-4o-mini", messages=msgs, stream=True):
    print(chunk.choices[0].delta.content or "", end="")
```

## 예제 / 테스트

- `examples/sdk_quickstart.py` — 한 줄 전환
- `examples/sdk_block_and_audit.py` — 403 차단 + 감사 1건
- `examples/sdk_reversible_roundtrip.py` — 가역 라운드트립
- `examples/sdk_streaming.py` — 스트리밍/비스트리밍
- `tests/test_cmp119_sdk.py` — 수용기준 테스트

> 통합 가이드(SDK + doctor + presets + deploy 묶음): [`docs/INTEGRATION_GUIDE.md`](../docs/INTEGRATION_GUIDE.md).

---

## 관련 문서

| 문서 | 역할 |
|---|---|
| [`docs/SDK.md`](../docs/SDK.md) | `nufi` 파사드(고수준 SDK) API — `detect`·`Guard`·`pseudonymize`·편의함수 |
| [`docs/INTEGRATION_GUIDE.md`](../docs/INTEGRATION_GUIDE.md) | 통합 경로 택일 → 프리셋 → doctor 검증 순서 |
| [`examples/README.md`](../examples/README.md) | `nufi_client` 를 직접 쓰는 독립 실행 예시 4종 인덱스 |
