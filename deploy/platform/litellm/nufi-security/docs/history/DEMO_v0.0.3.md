# DEMO — v0.0.3 (Operate) · O1 감사 대시보드 + O2 커버리지 보증

v0.0.3 M1 의 두 기능을 각각 **1-명령 데모**로 시연·자동검증한다. 두 스크립트 모두
`root 불필요`(에어갭/CI) · `외부 네트워크 호출 0` · 끝에 **PASS/FAIL** 판정과 종료코드를 낸다.

| 데모 | 스크립트 | 무엇을 증명하나 |
|---|---|---|
| O2 커버리지 보증 | [`scripts/demo_coverage.sh`](../scripts/demo_coverage.sh) | '내 트래픽 중 X% 가 게이트웨이를 통과'(coverage) + 우회 상시 알림(monitor) |
| O1 감사 대시보드 | [`scripts/demo_dashboards.sh`](../scripts/demo_dashboards.sh) | read-only 데이터소스 4 패널 200 + viewer 렌더 + read-only 보증 |

- 기능 매뉴얼: [`CLI.md#coverage`](CLI.md#coverage) · [`CLI.md#monitor`](CLI.md#monitor) · [`../dashboards/README.md`](../dashboards/README.md).
- 릴리스 DoD: [`RELEASE_CHECKLIST.md`](RELEASE_CHECKLIST.md).

> **사전 요건:** Python 3.10+, `pip install -r requirements.txt`(coverage/monitor·dashboards 는
> stdlib + PyYAML 만으로 동작). 데모는 합성·비-PII 픽스처만 사용한다.

---

## 1) 커버리지 보증 데모 — `scripts/demo_coverage.sh`

```bash
cd security
./scripts/demo_coverage.sh        # root 불필요, --simulate(flow 리플레이)
```

flow tap 의 게이트웨이 경유/우회 분류를 집계해 **커버리지 보증**(coverage)과 **우회 상시
알림**(monitor)을 세 시나리오로 증명한다. 사용 엔진: `capture/coverage.py`(CoverageAggregator),
`capture/bypass_monitor.py`(BypassMonitor).

| # | 시나리오 | 입력 픽스처 | 기대 |
|---|---|---|---|
| C1 | 커버리지 PASS | `samples/flow_clean.jsonl`(전부 게이트웨이 경유) | 100% · 🟢 PASS · exit 0 |
| C2 | 커버리지 누수 탐지 | `samples/flow_replay.jsonl`(우회 2건 섞임) | 50% < 90% · 🔴 FAIL · 우회 2건 플래그 |
| C3 | 우회 상시 알림 | `samples/flow_bypass_burst.jsonl`(우회 버스트) | 알림 2건 발화 + 반복분 4건 suppression |

> **데모 PASS 의 의미:** 각 시나리오의 **출력·종료코드가 설계대로** 인지 검증한다(데모 PASS =
> 기능이 설계대로 동작). C2 의 coverage `exit 1`·C3 의 monitor `exit 1` 은 누수/우회를
> **정확히 플래그**한 것 = 기능이 동작한 것이므로 데모상 **PASS** 다. (CLI 의 비-0 종료코드는
> CI 게이트가 보증 미달을 잡도록 설계된 정상 동작이다.)

### 기대 콘솔 출력 (요약)

```
C1 — 커버리지 PASS: 전부 게이트웨이 경유 → 100% (우회 0)
    내 트래픽 중 100.0% 가 게이트웨이를 통과 (게이트웨이 4 / 관측 4, 우회 0)
    종합: 🟢 PASS  (PASS≥100% · FAIL<90%)
  [PASS] C1 coverage 100% PASS (exit 0) — 보증 충족
C2 — 커버리지 누수 탐지: 우회 2건 섞인 트래픽 → 50% < 90% → FAIL
    내 트래픽 중 50.0% 가 게이트웨이를 통과 (게이트웨이 2 / 관측 4, 우회 2)
      ⚠ 게이트웨이 우회 2건 — 조용한 public 직결 누수(보증 미달).
    종합: 🔴 FAIL  (PASS≥100% · FAIL<90%)
  [PASS] C2 coverage 50% FAIL (exit 1) — 우회 누수를 정확히 플래그
C3 — 우회 알림: 우회 버스트 → 임계 초과 알림 발화 + 반복분 suppression
    관측 8 · 우회 6 · 알림 2 · 억제(suppressed) 4  [threshold=1, cooldown=300s]
  [PASS] C3 monitor 알림 2건 발화 + 억제 4건 — 임계/디바운스 동작
------------------------------------------------------------
요약: 3개 시나리오 중 3 PASS, 0 FAIL
✅ 커버리지 데모 PASS — coverage/monitor 가 전부 설계대로 동작
```

- **종료 코드:** 세 시나리오 전부 기대대로면 `0`, 하나라도 어긋나면 `1`.
- **직접 호출(매뉴얼):** `nufi-egress coverage --simulate samples/flow_clean.jsonl --no-json`
  · `nufi-egress monitor --simulate samples/flow_bypass_burst.jsonl --threshold 1`
  (플래그·임계·JSON 출력은 [`CLI.md#coverage`](CLI.md#coverage)/[#monitor](CLI.md#monitor)).

---

## 2) 감사 대시보드 데모 — `scripts/demo_dashboards.sh`

```bash
cd security
./scripts/demo_dashboards.sh      # root 불필요, 빈 포트 자동 선택
```

read-only 데이터소스(`dashboards.server`)를 동봉 샘플 픽스처로 기동하고, **4 패널 엔드포인트가
200 + 기대 모델**을 반환하며 viewer 가 렌더되는지 **헤드리스(curl)** 로 자동검증한 뒤 서버를
정리한다(EXIT trap). 프로덕션 무변경·쓰기 권한 없음(GET/HEAD 만; 쓰기 메서드는 405).

| # | 점검 | 엔드포인트 | 기대 |
|---|---|---|---|
| D1 | 결정 뷰어 | `/api/decisions` | 200 + 결정 ≥ 1건 |
| D2 | 해시체인 무결성 | `/api/chain` | 200 + `ok=true` |
| D3 | 우회 타임라인 | `/api/bypass?only_bypass=1` | 200 + 우회 ≥ 1건 |
| D4 | 카테고리 추이 | `/api/trend` | 200 + 버킷 ≥ 1 |
| D5 | viewer 렌더 | `/viewer` | 200 + HTML |
| D6 | read-only 보증 | `POST /api/decisions` | 405 |

샘플 픽스처(합성·비-PII, 결정성): `dashboards/sample/audit_chain.jsonl`(체인 부착 감사 3건),
`dashboards/sample/flow-bypass.jsonl`(게이트웨이 정상 1 + 우회 1). 재생성:
`python3 dashboards/sample/_gen_fixtures.py`. *flow 파일명은 어댑터 디렉터리 글롭
`flow-*.jsonl` 과 일치해야 한다(README dir 모드에서 우회 패널이 채워지도록).*

### 기대 콘솔 출력 (요약)

```
 base=http://127.0.0.1:<auto>
  [PASS] D1 결정 뷰어 200 + 결정 3건
  [PASS] D2 해시체인 무결성 200 + ok=true
  [PASS] D3 우회 타임라인 200 + 우회 1건
  [PASS] D4 카테고리 추이 200 + 버킷 3
  [PASS] D5 viewer 렌더 200 + HTML
  [PASS] D6 read-only 보증 — POST → 405
------------------------------------------------------------
요약: 6개 점검 중 6 PASS, 0 FAIL
✅ 대시보드 데모 PASS — 4 패널 200 + viewer 렌더 + read-only 보증
```

- **종료 코드:** 6 점검 전부 통과면 `0`, 하나라도 실패면 `1`.
- **포트:** 기본은 빈 포트 자동 선택(멱등). `PORT=8099 ./scripts/demo_dashboards.sh` 로 지정 가능.
- **브라우저로 직접 보기:** `nufi-egress dashboard --port 8099 --audit dashboards/sample/audit_chain.jsonl --flow-dir dashboards/sample`
  후 `http://127.0.0.1:8099/viewer` (자세히 [`../dashboards/README.md`](../dashboards/README.md)).

---

## 멱등·에어갭

- 두 데모 모두 **반복 실행해도 결과 동일**(coverage 는 격리 tempdir 집계, dashboards 는 빈 포트
  자동 선택 + 본 스크립트가 띄운 서버만 정리).
- **외부 네트워크 호출 0:** flow 는 리플레이 픽스처, 대시보드는 stdlib HTTP + 동봉 픽스처 — 에어갭/CI 그대로 동작.
- **결과 캡처(선택):** 콘솔 캡처가 필요하면 `docs/DEMO_RESULT_v0.0.3.md` 로 저장.
