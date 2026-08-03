# NuFi Egress-Audit — Hands-On 튜토리얼 (토이 프로젝트로 감 잡기)

> **이 문서는 무엇인가요?**
> 작은 **토이 프로젝트**("지원데스크 환불 도우미") 하나를 처음부터 끝까지 만들면서,
> NuFi 게이트웨이를 **SDK 한 줄 전환**과 **`nufi-egress` CLI 운영**으로 직접 손에 익히는
> 실습 가이드입니다. 레퍼런스가 아니라 **따라 하며 감을 잡는** 문서예요.
>
> - **레퍼런스(무엇을 어떤 플래그로):** [`CLI.md`](CLI.md) · [`INTEGRATION_GUIDE.md`](INTEGRATION_GUIDE.md)
> - **재현 가능한 데모(검증 결과):** [`DEMO.md`](DEMO.md) · [`history/DEMO_v0.0.3.md`](history/DEMO_v0.0.3.md)
> - **이 문서:** 그 둘을 **이야기(시나리오) 한 줄기**로 엮어 처음 쓰는 사람이 손으로 돌려 보게 함.
>
> ⏱ 소요: 약 20~30분 · 🔌 **네트워크/ root 불필요**(에어갭·CI 에서 그대로 동작 — 외부 LLM 은 stub, 패킷 캡처는 `--simulate` 리플레이로 재현).

---

## 0. 5분 준비

```bash
cd security
python3 -m pip install -r requirements.txt   # 의존성(에어갭이면 이미 설치돼 있을 수 있음)
python3 -m pip install -e .                  # nufi-egress / nufi 명령을 PATH 에 설치(권장)

# 결정론적·경량 백엔드로 고정(에어갭 안전 — 모델 다운로드 불필요)
export EGRESS_NER_BACKEND=gazetteer
```

> **설치 안 해도 됩니다.** 이 문서는 설치형 표기(`nufi-egress …`)를 씁니다. CLI 를 설치하지 않은
> 환경에서의 동치 실행법은 [`CLI.md`](CLI.md)(§표기 규약)에 한 번에 정리돼 있습니다.

설치가 됐는지 확인:

```bash
nufi-egress --help        # 서브커맨드 목록이 보이면 OK
# (별칭) nufi --help 도 동일
```

---

## 1. 우리가 만들 것 — 토이 프로젝트 "환불 도우미"

여러분은 사내 **서빙빌더**입니다. 고객 지원팀이 쓰는 작은 파이썬 스크립트가 있어요:
고객 문의 메시지를 받아 **LLM 으로 요약·답변 초안**을 만듭니다.

문제는, 고객 메시지에 **개인정보(이름·전화·이메일·주민번호)와 가끔 API 키** 가 섞여 있다는 것.
이걸 그대로 **public LLM(OpenAI/Anthropic)** 에 보내면 민감정보가 사외로 나갑니다.

> 🎯 **목표:** 이 스크립트를 코드 거의 안 바꾸고 NuFi 경유로 바꿔서
> ① **강한 PII·비밀은 아예 차단**, ② **약한 PII 는 가명화해서 전송**, ③ **나간 요청은 100% 감사**,
> ④ 게이트웨이를 **우회**하는 직결 트래픽까지 잡아내도록 만든다.

작업은 두 모자를 번갈아 씁니다:

| 파트 | 모자 | 무엇으로 |
|---|---|---|
| A~D | **앱 개발자** | `nufi_client` **SDK** (OpenAI 호환) |
| E | **보안/운영자** | `nufi-egress` **CLI** |
| F | **둘 다** | end-to-end 데모 스크립트 |

---

## 2. Part A — "Before/After": OpenAI 호출을 NuFi 로 한 줄 전환

원래 스크립트는 이렇게 생겼습니다(평범한 OpenAI 호출):

```python
# before.py — 가드 없는 직접 호출
from openai import OpenAI
client = OpenAI()
resp = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "회사 행동강령 3줄 요약해줘"}])
print(resp.choices[0].message.content)
```

NuFi 로 바꾸는 데 필요한 변경은 **import 1줄 + 생성 1줄**뿐입니다(호출부는 그대로):

```python
# after.py — NuFi 경유 (examples/sdk_quickstart.py 와 동일)
from nufi_client import NuFi                       # ← 1줄 교체
client = NuFi()                                     # ← 1줄 교체 (base_url 없으면 in-process)
resp = client.chat.completions.create(             # 호출부는 OpenAI 와 동일
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "회사 행동강령 3줄 요약해줘"}])
print(resp.choices[0].message.content)
print("outcome:", resp.outcome, "| audit:", resp.audit_id)
```

돌려 봅니다:

```bash
python3 examples/sdk_quickstart.py
```

```text
[public-llm stub response]
outcome: forwarded | audit: 5113b05a-8a25-4b04-8f2b-6f56b6d15486
```

**무슨 일이 일어났나요?**
- `NuFi()` 를 `base_url` 없이 만들면 **같은 프로세스 안에서 게이트웨이를 직접 호출**합니다(서버 기동 불필요).
  실제 운영에서는 `NuFi(base_url="http://localhost:4000")` 로 실행 중인 게이트웨이에 HTTP 전송합니다.
- 응답은 OpenAI SDK 와 **똑같은 모양**(`resp.choices[0].message.content`). 에어갭이라 본문은 `[public-llm stub response]`.
- **NuFi 만의 두 필드**가 더 붙습니다: `resp.outcome`(`forwarded`/`blocked`/`transformed`)과
  `resp.audit_id`(이 요청의 감사 레코드 ID). 이 한 요청도 감사 로그에 남았다는 뜻이에요.

> ✅ **체크포인트:** 출력에 `outcome: forwarded` 와 `audit:` UUID 가 보이면 전환 성공.
> (행동강령 요약 같은 **민감정보 없는** 요청이라 `forwarded` — 정상 통과)

> 기존 `openai` 클라이언트를 유지하고 싶다면 base_url 심도 있습니다:
> `OpenAI(base_url=NuFi.gateway_base_url(), api_key="nufi-local")`.

---

## 3. Part B — 민감정보가 섞이면? 403 차단 + 감사 1건

이제 고객이 **API 키**를 메시지에 붙여 보냈다고 합시다. 그대로 LLM 에 가면 안 됩니다.

```bash
python3 examples/sdk_block_and_audit.py
```

```text
차단됨(403): entities=['SECRET'] audit_id=aa8fa72f-da98-4f25-8f57-c7623b3db656
감사 적재: 1건 (총 1)
감사 레코드: outcome=blocked is_public=True model=gpt-4o-mini
OK — 403 차단 + 감사 1건 적재 확인
```

스크립트의 핵심부(요지):

```python
from nufi_client import NuFi, NuFiBlocked
client = NuFi(audit_log="/tmp/nufi_sdk_block_demo.jsonl")   # 감사 로그 경로 격리
try:
    client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user",
        "content": "AWS 키 좀 봐줘: AKIAIOSFODNN7EXAMPLE / wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"}])
except NuFiBlocked as e:
    print("차단:", e.entities, e.audit_id)   # → ['SECRET'] …
```

**무슨 일이 일어났나요?**
- 게이트웨이가 본문에서 **비밀(SECRET)** 을 탐지 → **외부로 보내지 않고** `NuFiBlocked`(HTTP 403)로 막았습니다.
- 동시에 **감사 레코드 1건**이 `outcome=blocked` 로 적재됐어요. "막았다"는 사실 자체가 증거로 남습니다.
- 예외 객체 `e` 로 **무엇이(`e.entities`) 왜 막혔는지, 어느 감사 ID(`e.audit_id`)인지** 코드에서 바로 처리할 수 있습니다.

> ✅ **체크포인트:** `entities=['SECRET']` + `감사 적재: 1건`. 강한 PII(주민번호 등)도 같은 방식으로 차단됩니다.
> 비밀·강한 PII 는 **어떤 프리셋에서도 가명화로조차 내보내지 않고 차단**합니다.

---

## 4. Part C — 약한 PII 는 가명화 라운드트립(효용 보존)

전화번호·이메일 같은 **약한 PII** 는 무조건 막으면 업무가 안 됩니다. NuFi 는 이걸 **가역 가명화**로
바꿔 내보내고, 응답에 실려 온 surrogate 를 **원본으로 무손실 복원**합니다.

```bash
python3 examples/sdk_reversible_roundtrip.py
```

```text
원문   : 고객 홍길동님(010-1234-5678, hong@example.com)께 환불 안내 부탁드립니다.
가명화 : 고객 ⟦P1⟧님(⟦T1⟧, ⟦E1⟧)께 환불 안내 부탁드립니다. (치환 3건, blocked=False)
응답복원: 네, 고객 홍길동님(010-1234-5678, hong@example.com)께 환불 안내 부탁드립니다. 내용 확인했습니다. 환불 처리하겠습니다.
OK — 가역 가명화 라운드트립 통과
```

핵심부:

```python
client = NuFi()
original = "고객 홍길동님(010-1234-5678, hong@example.com)께 환불 안내 부탁드립니다."
with client.pseudonymize(original) as rt:      # with 종료 시 세션 매핑 즉시 폐기
    masked = rt.masked                          # ← 이 가명화 텍스트만 외부로 나간다
    # … masked 를 LLM 에 보내고, 응답 llm_response 를 받았다고 가정 …
    restored = rt.restore(llm_response)          # surrogate → 원본 복원
```

**무슨 일이 일어났나요?**
- `홍길동 → ⟦P1⟧`, `010-1234-5678 → ⟦T1⟧`, `hong@example.com → ⟦E1⟧` 로 치환(3건). **외부에는 surrogate 만** 나갑니다.
- `rt.restore(...)` 가 응답 속 surrogate 를 **원본으로 정확히 되돌립니다**(고객은 가명화를 전혀 못 느낌).
- `with` 블록을 벗어나면 **원복 매핑(session)이 즉시 안전 폐기**됩니다 — 매핑이 디스크에 눌러앉지 않아요.

> ✅ **체크포인트:** `가명화` 줄에 `⟦P1⟧⟦T1⟧⟦E1⟧` 이 보이고, `응답복원` 줄에서 원본 이름·전화·이메일이 되살아나면 OK.
> 이게 `init` 프리셋 중 **`pseudonymize-roundtrip`** 의 동작입니다(7절에서 CLI 로 켜 봅니다).

---

## 5. Part D — 스트리밍도 OpenAI 와 똑같이

```bash
python3 examples/sdk_streaming.py
```

```text
[non-stream] [public-llm stub response]
[stream]    [public-llm stub response]
OK — 스트리밍/비스트리밍 동일 출력 확인
```

```python
for chunk in client.chat.completions.create(model="gpt-4o-mini", messages=msgs, stream=True):
    delta = chunk.choices[0].delta.content
    if delta:
        print(delta, end="", flush=True)     # OpenAI 와 동일한 청크 소비 패턴
```

**포인트:** 스트리밍 인터페이스가 OpenAI 와 동일(`delta.content` 누적)하고, 청크 경계는
**surrogate(⟦P1⟧) 를 쪼개지 않게** 잘립니다. 그래서 청크별로 `restore()` 해도 토큰이 깨지지 않아요.

> 여기까지가 **앱 개발자 모자**. 코드 변경은 사실상 `NuFi()` 생성 한 줄이었습니다.

---

## 6. Part E — 운영자 모자: `nufi-egress` CLI 로 게이트웨이 운영

이제 **보안/운영자** 입장입니다. SDK 가 잘 물렸는지 진단하고, 우회 트래픽을 감시하고, 감사
로그를 집계합니다. 전부 `nufi-egress` **한 진입점**으로 합니다.

### 6.1 프리셋으로 정책 켜기 — `init`

```bash
nufi-egress init --list          # 사용 가능한 프리셋
```

```text
  audit-only               차단·변형 없이 전수 탐지·로깅만. 도입 초기 가시성 확보용(fail-open).
  pseudonymize-roundtrip   약한 PII 를 가역 가명화로 치환·원복(효용 보존), 강한 PII·비밀은 차단 유지(fail-open).
  strict-kr-pii            한국어 PII·비밀·기밀을 최대로 차단. 미지 엔티티 기본 차단, enforcement fail-closed.
```

```bash
nufi-egress init audit-only --dry-run     # 적용 결과 미리보기(파일 미생성)
# 실제 생성: nufi-egress init audit-only --out ./config
```

> **권장 도입 순서:** `audit-only`(관찰만) → 익숙해지면 `pseudonymize-roundtrip`(효용 보존)
> 또는 `strict-kr-pii`(최대 보호). 프리셋 동작 diff 는 [`PRESETS.md`](PRESETS.md).

### 6.2 배선이 제대로 됐나 — `doctor`

```bash
nufi-egress doctor --no-json
```

```text
nufi doctor — 하이브리드 배선 진단
============================================================
[PASS] ✔ config       설정 검증
        라우트 2개·백엔드 3개 (public 2/private 1), 정책 엔티티 19개 — 구조·일관성 정상
[WARN] ▲ reachability private/public 도달성
        미도달 1/3 — 네트워크/권한 제약 가능(dry-run 강등): private-llm@localhost:8000(Connection refused)
[PASS] ✔ gateway      outbound 게이트웨이 통과
        public outbound 이 게이트웨이를 통과·감사 적재됨 (outcome=forwarded, 감사 1건) — 실신호
[FAIL] ✗ bypass       우회 누수 (flow_tap)
        게이트웨이 우회 연결 4/8건 탐지 — 조용한 public 직결 누수
[PASS] ✔ canary       카나리 PII E2E
        합성 PII(KR_RRN) 가 게이트웨이에서 차단되고 감사 적재 GREEN (http 403, blocked=['KR_RRN'])
------------------------------------------------------------
종합: 🔴 RED  (PASS 3 · WARN 1 · FAIL 1 / 5)
```

**읽는 법:** 5개 체크를 PASS/WARN/FAIL 로 보여줍니다. 여기선 일부러 **우회 누수(bypass)** 가
FAIL 로 떴어요 — 다음 단계에서 그걸 직접 파고듭니다. (WARN 은 에어갭이라 private LLM 미도달 — 정상)

### 6.3 캡처 대상 만들기 — `targets`

게이트웨이를 우회하는 트래픽을 보려면, 먼저 **"어떤 목적지를 감시할지"** 를 `routing.yaml`(여러분이
정의한 public LLM 목적지)에서 파생합니다. 그리고 패킷 캡처에 쓸 **BPF 필터** 문자열도 뽑아 줍니다.

```bash
nufi-egress targets --refresh --bpf
```

```text
갱신: …/config/capture_targets.yaml — 목적지 2건
  public 목적지: api.anthropic.com:443 (claude-3-5-sonnet/anthropic)
  public 목적지: api.openai.com:443 (gpt-4o-mini/openai)
BPF: tcp and (dst host api.anthropic.com or dst host api.openai.com) and (dst port 443)
```

**무슨 일이 일어났나요?**
- `routing.yaml` 의 public 목적지를 읽어 `config/capture_targets.yaml` 을 **재생성**(`--refresh`).
- `--bpf` 로 **tcpdump 가 쓸 필터**를 출력. 라이브 캡처 시 이 필터로 "감시 대상 목적지로 가는 TCP" 만 봅니다.

### 6.4 우회 탐지 — `flow-tap`

라이브 캡처는 root/CAP_NET_RAW 가 필요하니, 여기선 **미리 만든 flow 로그를 리플레이**(`--simulate`)해서
root 없이 동일 로직을 재현합니다. 샘플 `samples/flow_replay.jsonl` 은 게이트웨이 경유 2건 + **우회 2건** 이 섞인 트래픽입니다.

```bash
nufi-egress flow-tap --simulate samples/flow_replay.jsonl
```

```text
BPF: tcp and (dst host api.anthropic.com or dst host api.openai.com) and (dst port 443)
flow tap: seen=8 captured=4 dropped=4 (gateway=2 bypass=2)
  ⚠ 게이트웨이 우회 의심 연결 2건 — P2 봇이 high-severity alert 로 승격
```

**무슨 일이 일어났나요?**
- flow 로그의 각 연결을 보고 **게이트웨이(litellm)를 거쳤는지** vs **앱이 직접(`python3`/`curl`) 나갔는지** 판정.
- `bypass=2` — 게이트웨이를 우회한 직결 연결 2건을 잡았습니다. 이게 6.2 `doctor` 의 FAIL 정체예요.

> flow 로그 한 줄은 이런 모양입니다(`src_ip`/`dst_host`/`process` 등):
> ```json
> {"ts":"…","src_ip":"127.0.0.1","dst_host":"api.anthropic.com","dst_port":443,"process":"litellm","bytes":2048}
> ```

### 6.5 "내 트래픽 중 몇 %가 게이트웨이를 통과?" — `coverage`

`flow-tap` 의 판정을 **커버리지 보증 리포트**로 집계합니다. CI 게이트로 쓰기 좋아요(미달 시 종료코드 1).

깨끗한 트래픽(우회 0):

```bash
nufi-egress coverage --simulate samples/flow_clean.jsonl --no-json
```

```text
내 트래픽 중 100.0% 가 게이트웨이를 통과 (게이트웨이 4 / 관측 4, 우회 0)
종합: 🟢 PASS  (PASS≥100% · FAIL<90%)
```

우회가 섞인 트래픽:

```bash
nufi-egress coverage --simulate samples/flow_replay.jsonl --no-json
```

```text
내 트래픽 중 50.0% 가 게이트웨이를 통과 (게이트웨이 2 / 관측 4, 우회 2)
  ⚠ 게이트웨이 우회 2건 — 조용한 public 직결 누수(보증 미달).
    · 10.20.30.55/python3 → api.anthropic.com:443 (claude-3-5-sonnet)
    · 10.20.30.71/curl → api.openai.com:443 (gpt-4o-mini)
종합: 🔴 FAIL  (PASS≥100% · FAIL<90%)
```

> ✅ **체크포인트:** clean → 🟢 PASS, replay → 🔴 FAIL(우회 출처가 IP/프로세스까지 찍힘). 누가 우회하는지 한눈에 보입니다.

### 6.6 우회를 실시간 알림으로 — `monitor`

```bash
nufi-egress monitor --simulate samples/flow_bypass_burst.jsonl --threshold 1
```

```text
관측 8 · 우회 6 · 알림 2 · 억제(suppressed) 4  [threshold=1, cooldown=300s]
  🔔 ALERT high 10.20.30.55/python3 → api.anthropic.com:443 (윈도 1건/임계 1)
  🔔 ALERT high 10.20.30.71/curl → api.openai.com:443 (윈도 1건/임계 1)
  · 동일 키 반복 우회 4건은 suppression(쿨다운)으로 억제됨.
종합: 🔴 FAIL
```

**포인트:** 같은 (출처→목적지) 의 반복 우회는 **쿨다운으로 억제(suppression)** 해서 알림 폭주를 막습니다.
6건 우회 중 **고유 2건만 알림**, 나머지 4건은 억제. 알림은 `logs/alerts.jsonl` 에 적재됩니다.

### 6.7 감사 로그 집계 — `audit query`

지금까지 쌓인 감사 로그를 **outcome/엔티티별로 집계**하고, 필요하면 **해시 체인 무결성**까지 검증합니다.

```bash
nufi-egress audit query
```

```text
감사 로그: …/logs/egress_audit.jsonl  (총 45행)
  outcome 분포: {'blocked': 11, 'transformed': 6, 'forwarded': 28}
  차단 11건 — 엔티티별:
    SECRET               17
    KR_RRN               2
    KR_PERSON            1
```

```bash
nufi-egress audit query --verify-chain --json    # 변조탐지(M5 §4.3) + 기계용 JSON
```

**포인트:** `forwarded`(통과)·`transformed`(가명화)·`blocked`(차단) 분포가 한눈에. `--verify-chain` 은
추가전용 해시 체인이 끊겼는지(=로그 변조) 검사하고, 끊겼으면 **종료코드 1** 로 CI 를 떨굽니다.

> `audit` 서브커맨드는 봇도 겸합니다: `audit once`(큐 1회 드레인) · `audit daemon`(상시) · `audit report`(지연 p95).

### 6.8 로그는 어디에 쌓이나 — 직접 보기 & 실시간 `tail -f`

집계(`audit query`)도 좋지만, **무슨 일이 벌어지는지 실시간으로 눈으로 보고 싶을 때**가 있죠.
모든 로그는 저장소 루트의 **`logs/`** 아래에 쌓입니다(모두 append-only JSONL — 한 줄 = 한 사건).

| 로그 | 경로 | 무엇 | 누가 쓰나 |
|---|---|---|---|
| **감사 로그(메인)** | `logs/egress_audit.jsonl` | public 전송/차단/가명화 **모든 결정**(1건=1줄) | 게이트웨이 · SDK |
| **알림** | `logs/alerts.jsonl` | 우회/감사봇 **high-severity 알림** | `monitor` · 감사봇 |
| **감사 findings** | `logs/audit_findings.jsonl` | 비동기 감사봇이 찾아낸 finding | `audit daemon`/`once` |
| **flow 캡처** | `logs/packets/public/flow-YYYY-MM-DD.jsonl` | 패킷 레이어 연결 기록 | `flow-tap --live` |
| **본문 dump(옵션)** | `logs/packets/public/dump-YYYY-MM-DD.jsonl` | `retain_raw` 켤 때만 — public 원문 | 게이트웨이 |
| **분리 메시지** | `logs/messages/{private,public}/` | private/public in·out 본문(차등 감사) | message store |
| **enforcement** | `logs/enforcement.jsonl` | BLOCK/허용 집행 결정 | enforcement 모듈 |
| **봇 오프셋(상태)** | `logs/audit_state/offsets.json` | 큐 소비 위치(재시작 이어보기) | 감사봇 |

> 메인 감사 로그 경로는 **`EGRESS_AUDIT_LOG`** 환경변수로 바꿀 수 있습니다(기본 `<repo>/logs/egress_audit.jsonl`).
> 봇 계열 경로(findings/alerts/state/packets)는 `config/audit_profiles.yaml` 에서 정의합니다.

#### 실시간으로 보면서 활동하기 (터미널 2개)

**터미널 A — 지켜보기.** 감사 로그(+알림)를 `tail -f` 로 따라갑니다:

```bash
tail -f logs/egress_audit.jsonl logs/alerts.jsonl
```

JSON 한 줄이 길어 눈에 안 들어오면, **한 줄 요약**으로 흘려보세요(jq 없이 stdlib 만):

```bash
tail -f logs/egress_audit.jsonl | python3 -c 'import sys, json
for ln in sys.stdin:
    ln = ln.strip()
    if not ln: continue
    d = json.loads(ln)
    pub = "public" if d.get("is_public") else "private"
    print(d.get("ts",""), " ", pub, " ", d.get("outcome",""), " ", d.get("model",""))'
# 예) 2026-06-28T10:45:36+0900   public   forwarded   gpt-4o-mini
```

**터미널 B — 활동.** Part A~E 에서 한 걸 다시 돌리면, **터미널 A 에 줄이 실시간으로 떨어집니다**:

```bash
python3 examples/sdk_quickstart.py        # → A 에  … forwarded  gpt-4o-mini   (민감정보 없음 → 통과)

# 기본 NuFi() 로 비밀 섞어 호출 → A 에 blocked 한 줄
python3 -c "from nufi_client import NuFi, NuFiBlocked
try: NuFi().chat.completions.create(model='gpt-4o-mini', messages=[{'role':'user','content':'키 AKIAIOSFODNN7EXAMPLE / wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY'}])
except NuFiBlocked as e: print('blocked', e.entities)"
#                                         → A 에  … blocked    gpt-4o-mini

nufi-egress monitor --simulate samples/flow_bypass_burst.jsonl --threshold 1
#                                         → logs/alerts.jsonl 에 🔔 ALERT 2줄 추가(터미널 A 에 보임)
```

**무슨 일이 일어났나요?**
- 게이트웨이/SDK 를 한 번 호출할 때마다 `logs/egress_audit.jsonl` 에 **딱 한 줄**이 붙습니다(통과=forwarded, 가명화=transformed, 차단=blocked).
- `monitor`/감사봇이 우회를 잡으면 `logs/alerts.jsonl` 에 알림이 붙고요. 두 파일을 같이 `tail -f` 하면 **"요청 흐름 + 경보"** 를 한 화면에서 봅니다.

> ⚠️ **두 가지 주의**
> - `examples/sdk_block_and_audit.py` 는 일부러 **격리된 임시 로그**(`/tmp/nufi_sdk_block_demo.jsonl`)에 쓰므로 메인 로그(`logs/egress_audit.jsonl`)에는 안 보입니다. 메인 로그에서 차단을 보려면 위처럼 **기본 `NuFi()`** 로 호출하세요.
> - `./scripts/demo.sh` 는 시작할 때 메인 감사 로그를 **초기화(truncate)** 합니다. 데모 중 실시간으로 보려면 `tail -F`(대문자 — 파일 재생성 추적)를 쓰세요: `tail -F logs/egress_audit.jsonl`.

> ✅ **체크포인트:** 터미널 B 에서 호출할 때마다 터미널 A 에 `forwarded`/`blocked` 줄이 즉시 뜨면 성공.
> 이게 운영 중 **"지금 무엇이 나가고 무엇이 막히는지"** 를 어깨너머로 보는 가장 빠른 방법입니다.

---

### 6.9 여러 정책을 한 게이트웨이에서 — `policy`

부서·테넌트마다 다른 강도의 정책을 **하나의 게이트웨이**에서 동시에 운영하고, 위험한 정책
변경을 **프로세스 재기동 없이 되돌리는**(rollback) 운영자 작업을 실습합니다. 토이로 격리해서
돌려 보겠습니다(저장소 무오염 — `POLICY_*` 환경변수로 상태 경로를 임시 디렉터리에 둡니다).

```bash
# 격리된 운영 상태(실습용 — 저장소 config 를 안 건드림)
export POLICY_BINDINGS_OVERLAY=/tmp/ho_binds.yaml
export POLICY_VERSIONS_DIR=/tmp/ho_versions
export POLICY_CHANGE_LOG=/tmp/ho_changes.jsonl
SAMPLE="연락처 010-1234-5678 로 회신 바랍니다."   # 단일 KR_PHONE

# ① 프로파일·묶기 현황 보기 (default = base 완화, strict = 차단 프리셋)
nufi-egress policy list

# ② 같은 입력, 두 프로파일의 다른 결정 — 한 게이트웨이 다중 정책
nufi-egress policy inspect nufi-default "$SAMPLE"   # default → 통과(가명화)  exit 0
nufi-egress policy bind  tenant-acme strict          # 경로 묶기(영속)
nufi-egress policy inspect tenant-acme "$SAMPLE"     # strict  → 차단        exit 1

# ③ 되돌리기 지점 박제 → (정책을 바꿨다고 치고) → 무재기동 되돌리기
nufi-egress policy snapshot strict --note "기준선 v1"
#   … config/profiles/strict/policy.yaml 을 수정하고 다시 snapshot 하면 v2 …
nufi-egress policy rollback strict                   # 직전 버전으로 generation++ 원자 스왑

# ④ 누가·언제·무엇을 바꿨나 + 변조탐지
nufi-egress policy audit --verify-chain              # 체인 BROKEN 이면 exit 1
```

**무슨 일이 일어났나요?**
- `inspect` 의 `exit 1`(strict 차단)은 게이트가 PII 를 **정확히 막은** 정상 신호입니다.
- `rollback` 의 `generation 0→1` 은 **프로세스 재기동 없이** 라이브 룰셋이 원자적으로 교체된
  것 — 운영 중 잘못된 정책 배포를 즉시 되돌리는 안전장치입니다(무재기동 핫리로드).
- 모든 변경(bind/snapshot/rollback)은 추가전용 **해시 체인** 감사 로그에 남아, 임의 수정·
  삭제가 `--verify-chain` 으로 탐지됩니다.

> ✅ **체크포인트:** `policy list` 에 `tenant-acme → strict` 묶기가 보이고, rollback 후 같은
> 입력이 다시 차단되면 성공. 1-명령 자동 채점은 `./scripts/demo_policy_ops.sh`(4/4 PASS),
> 운영 개념·설계 불변식은 [`OPS_POLICY_AT_SCALE.md`](OPS_POLICY_AT_SCALE.md).

### 6.10 제출용 리포트로 묶기 — `report`

지금까지 쌓인 측정·감사 로그를 감사관·구매자에게 낼 수 있는 **규정준수 리포트**로 묶습니다.
새 측정을 돌리지 않고 이미 있는 산출물만 읽어 Markdown/HTML/JSON 을 만듭니다.

```bash
# 규정준수: 정책 변경 감사(+해시체인) · 차단/가명화 · 우회 요약을 한 장으로
nufi-egress report compliance --audit samples/sla/audit_decisions.jsonl \
  --change-log samples/sla/policy_changes.jsonl --flow samples/sla/flow_bypass.jsonl --format md

# 점검항목 커버리지: 안내서·망분리 점검항목 대비 충족 현황을 같은 리포트에 매핑
nufi-egress report compliance --audit samples/sla/audit_decisions.jsonl \
  --change-log samples/sla/policy_changes.jsonl --flow samples/sla/flow_bypass.jsonl \
  --controls --customer "Acme Corp" --format md
```

**무슨 일이 일어났나요?**
- `report compliance` 는 변경 감사·감사 로그 두 **해시체인**을 검증해, 변조가 탐지되면
  `exit 1` 로 제출을 막습니다.
- `--controls` 를 더하면 **금융보안원 안내서·망분리 + 개인정보보호법·신용정보법·ISMS-P** 점검항목 대비
  NuFi 통제 충족 현황을 **같은 리포트의 기존 증빙에서 자동 산출**한 매핑 표가 붙습니다. 한 행 =
  **요구사항 → NuFi 통제 → 충족 여부 → 증빙 출처**, 롤업 배지로 직접 N(충족/미충족)·부분 N·범위밖 N.
  - **직접(direct)** 은 차단/가명화 결정·무결 체인 증빙으로 충족/미충족을 **자동판정**(✅/❌),
    **부분(partial)** 🟡 · **범위밖(out_of_scope)** ⛔ 은 정적 라벨로 솔직하게 구분합니다.
  - `--framework pipa` / `--framework cia` / `--framework isms-p` 로 규제별 필터링 가능(반복 허용).
  - 커버리지는 **정보성** — 무결성 게이트 종료코드(정상 0 · 변조 1)를 **바꾸지 않습니다**.
    끄려면 `--no-controls`, 통제 카탈로그 교체는 `--catalog FILE`.

> ✅ **체크포인트:** 1-명령 자동 채점은 `./scripts/demo_report.sh`(권한 불필요)와
> `./scripts/demo_compliance_mapping.sh`(점검항목 커버리지 5/5 PASS), 명령 전체 옵션·입력
> 스키마는 [`REPORTING.md`](REPORTING.md)(점검항목 커버리지는 §2).

### 6.11 PII 기반 하이브리드 라우팅 — PII 면 로컬, 아니면 클라우드 *(v0.4.0 신규)*

PII 가 포함된 요청은 클라우드로 보내지 않고 **로컬 모델로 강제 전환**하는 라우팅 레이어를
체험합니다. 기존 egress 감사(차단/가명화)보다 **앞단**에서 실행되어 PII 유출 경로 자체를
없앱니다.

```bash
# 데모 실행 — LiteLLM 불필요, 4 시나리오 자동 PASS/FAIL
python3 scripts/demo_pii_routing.py
```

데모가 보여주는 시나리오:

1. **PII 포함 요청** → 🔒 LOCAL 모델로 강제 (`outcome=pii_routed`)
2. **PII 없는 요청** → ☁️ CLOUD 모델 허용 (기존 라우팅 유지)
3. **비용 추적** → 로컬 vs 클라우드 요청별 비용 비교
4. **프로바이더 장애** → fail-closed 로 로컬 폴백

**무슨 일이 일어났나요?**
- PII 감지가 라우팅 **최우선 레이어**로 동작합니다. 주민번호·전화번호 같은 PII 가 하나라도
  포함되면 클라우드 경로에 도달하지 않고 로컬 모델로 갑니다.
- PII 없는 요청은 기존 private/public 라우팅을 그대로 따릅니다.
- `config/routing.yaml` 의 `pii_routing` 섹션에서 활성화/비활성화, 로컬 백엔드, 감지 대상
  엔티티를 설정합니다.

> ✅ **체크포인트:** `python3 scripts/demo_pii_routing.py` 가 4/4 PASS 이면 성공.
> 상세 설정은 [`PII_ROUTING.md`](PII_ROUTING.md).

---

## 7. Part F — 한 번에 끝까지: end-to-end 데모

지금까지 조각조각 만져 본 걸 **실제 HTTP 게이트웨이**에 대해 한 번에 돌려 봅니다. 6개 시나리오를
띄우고 PASS/FAIL 을 채점합니다(멱등·빈 포트 자동 선택·외부 의존 0).

```bash
./scripts/demo.sh
```

채점하는 6개 시나리오:

1. **private 기본 라우팅** — 외부 미전송(감사 0건)
2. **public 폴백 + 주민등록번호(강한 PII)** → 403 차단, `entities=[KR_RRN]`
3. **public 폴백 + API 키(비밀)** → 403 차단, `entities=[SECRET]`
4. **public 폴백 + 약한 PII(전화/이메일)** → 가명화 후 전송(200)
5. **감사 로그** — public 전송 100% 기록, private 0건
6. **자동 테스트** — acceptance(10/10) · unit · bench(recall·p95)

> 이건 Part A~E 에서 본 SDK 동작(차단/가명화/감사)을 **서버 경유**로 재확인하는 셈입니다.
> 더 좁은 데모도 있습니다: `./scripts/demo_coverage.sh`(커버리지).

---

## 7b. Part G — 라이브러리로 직접 쓰기 (Python SDK)

게이트웨이 없이, 코드 안에서 NuFi 엔진을 직접 임포트해 쓸 수 있습니다.
`from nufi import ...` 한 줄이면 됩니다.

```python
# 1) 탐지 — 텍스트에서 한국어 PII 찾기
from nufi import detect

findings = detect("김민수님 계좌번호 110-123-456789")
for f in findings:
    print(f"{f.entity_type}: {f.text}")
# KR_PERSON: 김민수
# KR_ACCOUNT: 110-123-456789
```

```python
# 2) 가명화 — 원본을 알아볼 수 없게
from nufi import pseudonymize, mask, redact

pseudonymize("KR_PERSON", "김민수")   # → <KR_PERSON_fa2a85f7c4>
mask("900101-1234567", keep_tail=4)    # → ******-***4567
redact("KR_RRN")                       # → <KR_RRN_REDACTED>
```

```python
# 3) 탐지+정책 한 번에 — Guard
from nufi import Guard

result = Guard().inspect("김민수님 계좌번호 110-123-456789")
print(result.blocked)        # True/False
print(result.findings)       # 탐지 결과
print(result.decision)       # 정책 판정 (차단/가명화/경고)
```

데모: `./scripts/demo_sdk.sh` (4/4 PASS). 전체 API 는 [`SDK.md`](SDK.md) 참고.
독립 실행 예시 12종은 [`examples/README.md`](../examples/README.md) 를 보세요.

---

## 7c. Part H — 게이트웨이 강건성 설정 *(v0.4.2 신규)*

v0.4.2에서 게이트웨이 코어에 **탐지 타임아웃**, **프롬프트 크기 제한**, **지연 추적**이
추가되었습니다.

### 환경변수로 조정

```bash
# 탐지 타임아웃 (밀리초, 기본 5000ms). 초과 시 fail-closed(차단).
export NUFI_DETECT_TIMEOUT_MS=3000

# 프롬프트 최대 크기 (바이트, 기본 512KB). 초과 시 잘라서 탐지.
export NUFI_MAX_PROMPT_BYTES=262144   # 256KB

PORT=4000 ./scripts/run_gateway.sh
```

### 지연 확인

```bash
# 게이트웨이 응답 헤더에 X-NuFi-Latency-Ms 가 포함됩니다.
curl -sv localhost:4000/v1/chat/completions \
  -d '{"model":"nufi-default","messages":[{"role":"user","content":"안녕"}]}' \
  2>&1 | grep -i x-nufi-latency
# < X-NuFi-Latency-Ms: 0.3
```

### 방어 파싱

비정상 요청(content 가 null, 메시지가 dict 가 아닌 경우 등)은 안전하게 처리됩니다.
큰 프롬프트는 `NUFI_MAX_PROMPT_BYTES` 까지만 탐지하고 나머지는 잘립니다.

데모: `./scripts/demo_resilience.sh` (5/5 PASS).

---

## 7d. Part I — SDK 편의 함수 *(v0.4.6 신규)*

v0.4.6에서 파일 단위·일괄 탐지를 한 줄로 끝내는 편의 함수 3종이 추가되었습니다.

```python
from nufi import scan_file, guard_file, batch_detect

# 1) 파일에서 PII 찾기
findings = scan_file("customer_data.txt")
for f in findings:
    print(f"{f.entity_type}: {f.text}")

# 2) 파일을 외부로 보내도 되는지 판정
result = guard_file("proposal.md")
if result.blocked:
    print("차단:", result.decision.actions)

# 3) 여러 텍스트 한 번에 탐지 (Detector 재사용으로 효율적)
all_findings = batch_detect(["텍스트1", "텍스트2", "텍스트3"])
for i, findings in enumerate(all_findings):
    print(f"텍스트{i+1}: {len(findings)}건")
```

데모: `./scripts/demo_sdk_helpers.sh` (5/5 PASS). API 문서는 [`SDK.md`](SDK.md) §2.7 참고.
독립 실행 예시: [`examples/sdk_file_scan.py`](../examples/sdk_file_scan.py).

---

## 7e. Part J — 정확도 벤치마크 직접 확인 *(v0.4.16 기준)*

NuFi 가 인용하는 재현율(recall) 수치를 직접 재현하고 싶을 때 사용합니다.

### 골드셋 정합 검증 (해시 체크, ~1초)

커밋된 골드셋이 `generate.py` 로 재생성한 것과 정확히 일치하는지 확인합니다.

```bash
python3 goldset/generate.py --verify
# → VERIFY OK  content_hash=<해시>  (불일치 시 MISMATCH 출력)
```

### 단위 테스트 + 문서 정합 (307개, ~50초)

```bash
python3 -m pytest tests/ -q
# → 307 passed, 1 warning
```

주요 테스트 그룹:

| 테스트 파일 | 검증 내용 |
|------------|----------|
| `test_goldset_invariants.py` | 골드셋 불변 조건 (미수록 성씨 누수·비율·해시) |
| `test_cmp145_int8_consistency.py` | ONNX-int8 재현율 수용 기준 (CI 하한 0.93+) |
| `test_repo_docs_are_consistent.py` | README·보고서 수치가 recall-int8.json 과 일치 |
| `test_doc_style_guard.py` | 공개 문서 스타일 가드 |
| `test_examples_smoke.py` | examples/ 스크립트 스모크 9종 (library_detect·sdk_quickstart·sdk_block_and_audit·sdk_reversible_roundtrip·sdk_streaming·sdk_file_scan·sdk_compliance_report·sdk_security_report·sdk_ci_integration) |

### 전체 벤치마크 재실행 (ONNX 백엔드, ~5분)

```bash
python3 scripts/bench_m5.py \
    --backend onnx-int8 --person-union --location-union \
    --split test --json-out docs/reports/recall-int8.json
```

**v0.4.16 기대 결과:**

| 지표 | 수치 | 수용 기준 |
|------|------|----------|
| `pii_recall` | 0.9908 | ≥ 0.90 ✅ |
| `person_recall` | 0.9799 | ≥ 0.85 ✅ |
| `person_recall_ci_low` | 0.9591 | ≥ 0.93 ✅ |
| `location_recall` | 1.0 | ≥ 0.85 ✅ |
| `secret_recall` | 1.0 | ≥ 0.90 ✅ |
| `benign_false_block` | 0.0 | ≤ 0.02 ✅ |
| `acceptance_pass` | true | — |

결과 권위 파일: `docs/reports/recall-int8.json`

### 가명화 품질 벤치마크 (~30초)

```bash
python3 scripts/bench_pseudonymize.py \
    --json-out docs/reports/pseudonymize-quality.json
# → acceptance_pass: true
```

---

## 8. 정리 — 치트시트 & 다음 단계

여기까지 했으면 여러분은 **앱(SDK) + 운영(CLI)** 양쪽을 다 손에 익혔습니다.

### SDK 치트시트 (앱 개발자)

```python
from nufi_client import NuFi, NuFiBlocked

client = NuFi()                                   # in-process (서버 불필요)
# client = NuFi(base_url="http://localhost:4000") # 실행 중 게이트웨이로 HTTP

resp = client.chat.completions.create(model="gpt-4o-mini", messages=msgs)
resp.outcome      # forwarded | transformed | blocked
resp.audit_id     # 이 요청의 감사 ID

try:
    client.chat.completions.create(...)
except NuFiBlocked as e:
    e.entities, e.audit_id                        # 무엇이 왜 막혔나

with client.pseudonymize(text) as rt:             # 약한 PII 가역 가명화
    rt.masked                                     # ← 외부로 나가는 surrogate 텍스트
    rt.restore(llm_response)                      # surrogate → 원본 복원
```

### CLI 치트시트 (운영자)

```bash
nufi-egress init audit-only --out ./config      # 정책 프리셋 적용
nufi-egress doctor --no-json                     # 배선 5체크 진단
nufi-egress targets --refresh --bpf              # 캡처 대상 + BPF 필터
nufi-egress flow-tap --simulate FLOW.jsonl       # 우회 탐지(리플레이)
nufi-egress coverage --simulate FLOW.jsonl       # '내 트래픽 X% 통과' 보증
nufi-egress monitor  --simulate FLOW.jsonl       # 우회 실시간 알림
nufi-egress audit query --verify-chain           # 감사 집계 + 무결성 검증
nufi-egress policy list / bind / rollback / audit # 다중 프로파일·묶기·무재기동 되돌리기
nufi-egress apply / disable                       # 실제 정적 차단 적용 / 킬스위치(root)

tail -f logs/egress_audit.jsonl logs/alerts.jsonl # 요청 흐름 + 경보 실시간 관찰(6.8)
```

**로그 위치 한눈에:** 감사=`logs/egress_audit.jsonl` · 알림=`logs/alerts.jsonl` ·
findings=`logs/audit_findings.jsonl` · flow 캡처=`logs/packets/…` · enforcement=`logs/enforcement.jsonl`
(메인 경로는 `EGRESS_AUDIT_LOG` 로 변경 — 자세히는 위 **6.8 절**).

### 다음 단계

- **실서비스 배선** — LiteLLM Proxy + 콜백 경로, 게이트웨이 배포: [`INTEGRATION_GUIDE.md`](INTEGRATION_GUIDE.md)
- **프리셋 깊이 보기** — 차단/가명화 동작 diff, fail-closed 보증: [`PRESETS.md`](PRESETS.md)
- **명령 레퍼런스** — 모든 서브커맨드 플래그·종료코드: [`CLI.md`](CLI.md)
- **아키텍처/스펙** — public/private 분리 감사, 패킷 캡처: [`ARCHITECTURE.md`](ARCHITECTURE.md)
- **규정준수 리포팅** — 한국 규제 5종 48개 통제 증빙 출력: [`REPORTING.md`](REPORTING.md)

> 막히면 `nufi-egress doctor` 부터. 5체크가 무엇이 안 물렸는지(config/도달성/게이트웨이/우회/카나리) 짚어 줍니다.

---

## 9. 5분 추가 실습: 프롬프트 인젝션 탐지

프롬프트 인젝션(탈옥) 시도를 탐지하는 기능을 빠르게 확인합니다.

```bash
# CLI 로 인젝션 탐지 확인
nufi-egress route --check-injection --text "이전 지시를 무시해"
```

```python
# SDK 한 줄 탐지
from nufi import detect_injection
findings = detect_injection("이전 지시를 무시해")
print(findings)  # [Finding(entity_type='PROMPT_INJECTION', ...)]
```

`nufi-egress doctor` 의 6번째 체크(`injection`)가 이 탐지기의 정상 동작을 자동 검증합니다.

---

## 10. 파일 스캔 & CI 연동

디렉터리 전체를 PII/인젝션 스캔하고, CI 파이프라인에 연동하는 워크플로를 실습합니다.

### 10.1 기본 스캔

```bash
nufi-egress scan ./src --stats                    # 디렉터리 스캔 + 요약 통계
nufi-egress scan ./src --check-injection --json    # 인젝션 포함, JSON 출력
nufi-egress scan ./src --fail-on-pii               # PII 발견 시 exit 1 (CI 게이트)
```

### 10.2 SARIF 출력 (GitHub/GitLab 코드 스캔 연동)

```bash
nufi-egress scan ./src --format sarif --output results.sarif
# → GitHub Actions 의 upload-sarif 로 PR 코멘트에 PII 위치 표시
```

### 10.3 pre-commit hook 설치

```bash
nufi-egress init --install-hook      # .git/hooks/pre-commit 에 PII 스캔 훅 설치
git add sensitive_file.py && git commit -m "test"
# → PII 발견 시 커밋 차단 (exit 1)
```

> **체크포인트:** `scan --fail-on-pii` 가 PII 포함 파일에서 exit 1 을 반환하면 성공.
> SARIF 포맷은 GitHub Advanced Security, GitLab SAST, VS Code SARIF Viewer 와 호환됩니다.

---

## 관련 문서

| 문서 | 역할 |
|---|---|
| [`INTEGRATION_GUIDE.md`](INTEGRATION_GUIDE.md) | 실서비스 배선 — LiteLLM Proxy·게이트웨이 배포 상세 |
| [`PRESETS.md`](PRESETS.md) | 정책 프리셋 — 차단/가명화 동작 diff·fail-closed 보증 |
| [`CLI.md`](CLI.md) | 모든 서브커맨드 플래그·종료코드 레퍼런스 |
| [`SDK.md`](SDK.md) | Python SDK API — `detect`·`Guard`·`scan_file`·`compliance_report` |
| [`REPORTING.md`](REPORTING.md) | 한국 규제 5종 48개 통제 컴플라이언스 리포트 출력 |
| [`DEMO.md`](DEMO.md) | 전체 기능 데모 카탈로그·1-명령 PASS/FAIL |
| [`examples/README.md`](../examples/README.md) | Python SDK 예시 12종 인덱스 |
