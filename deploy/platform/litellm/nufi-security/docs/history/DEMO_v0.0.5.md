# DEMO — v0.0.5 (Operate 완성) · B1 정책 운영 자동화 + B2 정확도 마무리

v0.0.5 의 두 트랙을 각각 **1-명령 데모/재현 스크립트**로 시연·자동검증한다. 두 스크립트 모두
`root 불필요`(에어갭/CI) · `외부 네트워크 호출 0` · 끝에 **PASS/FAIL** 판정과 종료코드를 낸다.

| 데모 | 스크립트 | 무엇을 증명하나 |
|---|---|---|
| B1 정책 운영 자동화 | [`scripts/demo_policy_ops.sh`](../scripts/demo_policy_ops.sh) | 다중 프로파일·경로별 묶기·무재기동 되돌리기·변경 감사 |
| B2 정확도 마무리 | [`scripts/demo_accuracy.sh`](../scripts/demo_accuracy.sh) | INT8 KR_PERSON Wilson CI 하한 ≥ 0.85 재현 + 온프렘 p95 표 |

- 기능 매뉴얼: [`OPS_POLICY_AT_SCALE.md`](OPS_POLICY_AT_SCALE.md) · [`CLI.md#policy`](CLI.md#policy).
- 릴리스 DoD: [`RELEASE_CHECKLIST.md`](RELEASE_CHECKLIST.md).
- 이전 버전 데모: [`DEMO_v0.0.3.md`](DEMO_v0.0.3.md)(O1·O2).

> **사전 요건:** Python 3.10+, `pip install -r requirements.txt`. **B1 데모는 stdlib + PyYAML +
> gazetteer NER 만으로 동작**(모델 불필요·에어갭 안전). **B2 재현 데모는 커밋된 측정 산출물**
> (`docs/reports/*.json`)을 목표선에 대조하므로 모델 스택 없이도 PASS/FAIL 을 낸다 — 실제
> 모델 재측정 경로는 §2 하단 참조. 데모는 합성·비-PII 픽스처만 사용한다.

---

## 1) 정책 운영 자동화 데모 — `scripts/demo_policy_ops.sh`

```bash
cd security
./scripts/demo_policy_ops.sh        # root 불필요, config 를 임시 디렉터리로 격리(저장소 무오염)
```

한 게이트웨이에서 **여러 정책 프로파일을 동시 운영**하고, 경로/테넌트별로 **묶고**(binding),
정책 버전을 **무재기동**으로 되돌리며(rollback), **누가·언제·무엇을** 바꿨는지 변경 감사
로그(추가전용 해시 체인)로 남기는 것을 4 시나리오로 증명한다. 엔진: `enforcement/policy_ops.py`
(`ProfileRegistry`·`PolicyVersionStore`·`PolicyOpsManager`·`PolicyChangeAudit`).

| # | 시나리오 | 입력 | 기대 |
|---|---|---|---|
| P1 | 두 프로파일 동시 운영 | 같은 전화번호 입력 | `default`=통과(exit 0) / `strict`=차단(exit 1) |
| P2 | 경로별 묶기 1건 | `tenant-acme → strict` | `policy list` 에 묶기 노출·영속 |
| P3 | 버전 되돌리기(무재기동) | strict v1(차단)→v2(완화) 후 rollback | v1 복원 + 같은 가드 원자 스왑(generation 0→1) |
| P4 | 변경 감사 + 해시 체인 | bind/snapshot/rollback | 4건 기록 + 체인 무결성 OK(변조탐지) |

> **데모 PASS 의 의미:** `inspect` 의 차단 시 `exit 1` 은 게이트가 PII 를 **정확히 차단**한
> 정상 신호다(데모상 PASS). P3 의 `generation 0→1` 은 프로세스 재기동 없이 라이브 룰셋이
> 원자적으로 교체됐음을 뜻한다(무재기동 되돌리기 — 핫리로드 메커니즘 재사용).

### 기대 콘솔 출력 (요약)

```
P1 — 두 프로파일 동시 운영: 같은 전화번호 입력에 다른 결정
    경로 nufi-default → 프로파일 default: 통과(allow/transform) (findings=1, actions={'pseudonymize': 1})
    경로 tenant-acme → 프로파일 strict: 차단(blocked) (findings=1, actions={'block': 1})
  [PASS] P1 default=통과(exit 0) / strict=차단(exit 1) — 한 게이트웨이 다중 정책
  [PASS] P2 묶기 1건(tenant-acme → strict) 반영 — list 에 노출
P3 — 버전 되돌리기(무재기동): strict v1(차단)→v2(완화) 후 v1 로 rollback
    [policy rollback] strict v2→v1 무재기동 적용 (generation 0→1, fingerprint=…)
  [PASS] P3 v2→v1 무재기동 되돌리기(generation 0→1) — 완화→차단 라이브 반영
  [PASS] P4 bind/snapshot/rollback 기록 + 해시 체인 OK(변조탐지)
------------------------------------------------------------
요약: 4개 시나리오 중 4 PASS, 0 FAIL
✅ 정책 운영 자동화 데모 PASS
```

- **종료 코드:** 4 시나리오 전부 기대대로면 `0`, 하나라도 어긋나면 `1`.
- **직접 호출(매뉴얼):** `nufi-egress policy {list,bind,snapshot,versions,rollback,audit,inspect}`
  — 플래그·종료코드·상태 경로 격리(`POLICY_*` 환경변수)는 [`CLI.md#policy`](CLI.md#policy),
  운영 개념·설계 불변식은 [`OPS_POLICY_AT_SCALE.md`](OPS_POLICY_AT_SCALE.md).

---

## 2) 정확도 마무리 재현 — `scripts/demo_accuracy.sh`

```bash
cd security
./scripts/demo_accuracy.sh     # root 불필요, 커밋된 측정 산출물 대조(모델 스택 불필요)
```

세 버전(v0.0.1→v0.0.3)에 걸쳐 남아 있던 유일한 품질 미달 지표(INT8 한국어 인명 신뢰구간)를
이번 버전에서 해결했음을 재현·검증한다. 두 산출물을 목표선에 대조한다.

| # | 항목 | 산출물 | 기대 |
|---|---|---|---|
| A1 | KR_PERSON Wilson CI 하한 | per-channel INT8 recall 리포트 ([`docs/reports/`](reports/)) | 하한 ≥ 0.85 |
| A2 | 온프렘 p95 표 | INT8 부하 p95 리포트 ([`docs/reports/`](reports/)) | INT8 c≤2 p95 ≤ 목표(150ms) |

**A1 — 근본 원인과 해결:** per-tensor INT8 동적 양자화가 양자화 노이즈로 KR_PERSON 인명
3건을 잃어 Wilson CI 하한을 0.860→**0.832**(<0.85)로 떨군 회귀를, **채널별(per-channel)
동적 양자화**(`scripts/export_onnx_int8.py` 의 `M5_QUANT_PER_CHANNEL` 기본 ON — 가중치
출력채널별 스케일)로 복원했다. 결과: KR_PERSON recall **0.9127**(115/126), Wilson
**CI95 [0.8504, 0.9506]** → 하한 **0.850 ≥ 0.85** 충족. 정합성 가드:
[`tests/test_cmp145_int8_consistency.py`](../tests/test_cmp145_int8_consistency.py)
(INT8↔FP32 KR_PERSON 무손실 검증, 모델 스택 미설치 시 침묵 금지 skip).

**A2 — 온프렘 p95 표:** INT8 백엔드 부하 측정(512자 입력, 동시성 sweep)을 운영 기준 p95
표로 인용. 단일~중간 동시성(c≤2)에서 p95 가 목표(150ms) 이내 — c=1 **41ms**, c=2 **67ms**.
고동시성(c≥4)은 워커 풀 스케일아웃(추론 풀)으로 흡수한다. FP32 대비 약 3× 빠름
(FP32 부하 p95 리포트는 [`docs/reports/`](reports/) 참조).

### 기대 콘솔 출력 (요약)

```
A1 — KR_PERSON 신뢰구간: per-channel INT8 Wilson CI 하한 ≥ 0.85
    backend=onnx-int8  KR_PERSON recall=0.9127 (115/126)  Wilson CI95=[0.8504, 0.9506]
  [PASS] A1 KR_PERSON CI 하한 ≥ 0.85 — per-tensor 0.832 회귀를 per-channel 이 복원
A2 — 온프렘 p95 표: INT8 부하 p95 지연(동시성 sweep)
       동시성   p50(ms)   p95(ms)   p99(ms)  throughput(req/s)  판정
         1      29.8      41.0      46.0               32.4  ✅≤목표
         2      47.7      66.9     110.0               39.7  ✅≤목표
  [PASS] A2 온프렘 p95 표 — INT8 c≤2 p95 목표 이내(고동시성은 워커 스케일아웃 권고)
------------------------------------------------------------
요약: 2개 항목 중 2 PASS, 0 FAIL
✅ 정확도 숙제 종결 재현 PASS
```

> **실제 모델 재측정(선택 · 모델 스택 필요):** 측정 라이브러리는 `~/.cache/m5_libs`(PYTHONPATH
> 로드), INT8 ONNX 산출은 `~/.cache/m5_onnx_int8`. per-channel INT8 재생성 →
> `PYTHONPATH=~/.cache/m5_libs python3 scripts/export_onnx_int8.py`, recall 재측정 →
> `scripts/bench_m5.py`.
> 위 재현 데모는 **커밋된 측정 증거**가 목표선을 충족하는지 결정론적으로 검증한다(에어갭 안전).

---

## 멱등·에어갭

- 두 데모 모두 **반복 실행해도 결과 동일** — B1 은 격리 tempdir 운영(저장소 파일 무오염),
  B2 는 커밋된 JSON 산출물 대조(부동소수 비교 없음).
- **외부 네트워크 호출 0:** B1 은 gazetteer NER + 동봉 정책, B2 는 stdlib + 커밋 리포트 —
  에어갭/CI 그대로 동작.
- **결과 캡처(선택):** 콘솔 캡처가 필요하면 `docs/DEMO_RESULT_v0.0.5.md` 로 저장.
