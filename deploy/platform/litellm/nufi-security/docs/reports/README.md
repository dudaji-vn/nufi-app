# docs/reports — 측정·분석 보고서 인덱스

이 폴더는 정확도 측정·갭 분석·릴리스 게이트·오차 분석 보고서를 담습니다.

## 현행 권위 데이터

| 파일 | 내용 | 상태 |
|---|---|---|
| [`recall-int8.json`](recall-int8.json) | 전체 정확도 기준 리포트 (onnx-int8, split=test, **n=854, v0.4.16**) | ✅ **현행 권위** |
| [`kr-location-gate.json`](kr-location-gate.json) | KR_LOCATION 유니온 게이트 판정 (recall=1.0, CI 하한 0.9417) | ✅ 현행 |
| [`kr-location-union.json`](kr-location-union.json) | KR_LOCATION 모델∪규칙 유니온 상세 (live onnx-int8, n=62) | ✅ 현행 |
| [`pseudonymize-quality.json`](pseudonymize-quality.json) | 가명화 품질 하니스 결과 | ✅ 현행 |
| [`load-p95.json`](load-p95.json) | 온프렘 부하 p95 (c=1: 41ms, c=2: 67ms) | ✅ 현행 |
| [`baseline-int8.json`](baseline-int8.json) | 공개 골드셋(I1) 베이스라인 (onnx-int8, 정보성) | 참고 |
| [`CMP-199-credit-coverage.json`](CMP-199-credit-coverage.json) | 신용정보 엔터티 클래스 커버리지 측정 | 참고 |
| [`kr-location-fn-dump.json`](kr-location-fn-dump.json) | KR_LOCATION FN 목록 덤프 (오차 분석용 원자료) | 역사적 |
| [`kr-location-union-onnx-skip.json`](kr-location-union-onnx-skip.json) | KR_LOCATION 유니온 ONNX 스킵 케이스 기록 | 역사적 |
| [`kr-person-fn-dump.json`](kr-person-fn-dump.json) | KR_PERSON FN 목록 덤프 (오차 분석용 원자료) | 역사적 |

## 분석 보고서

| 파일 | 내용 | 시점 |
|---|---|---|
| [`CMP-172-pii-accuracy-gap-analysis.md`](CMP-172-pii-accuracy-gap-analysis.md) | 엔터티별 정확도 갭 분석 + 연동 구조 (v0.4.16 현행화) | 현행 |
| [`kr-person-error-analysis.md`](kr-person-error-analysis.md) | KR_PERSON FN 분석 + v0.4.16 결과 추적 §7 | 현행 |
| [`kr-location-gate.md`](kr-location-gate.md) | KR_LOCATION v0.2.0 릴리스 게이트 판정 보고서 | v0.2.0 완료 |
| [`kr-location-ci-narrowing.md`](kr-location-ci-narrowing.md) | KR_LOCATION Wilson CI 좁히기 (P6, n 24→62) | v0.2.0 완료 |
| [`kr-location-error-analysis.md`](kr-location-error-analysis.md) | KR_LOCATION FN 분류·우선순위 (P2/P3 완료) | 역사적 ✅ |
| [`accuracy-integrity-audit.md`](accuracy-integrity-audit.md) | 공개 수치 무결성 감사 (v0.2.2, 드리프트 해소됨) | 역사적 ✅ |
| [`CMP-238-llm-routing-research.md`](CMP-238-llm-routing-research.md) | LLM 라우팅 솔루션 조사 | 조사 |
| [`CMP-246-llm-routing-market-research.md`](CMP-246-llm-routing-market-research.md) | LLM 라우팅 시장 조사 | 조사 |
| [`CMP-252-productivity-review.md`](CMP-252-productivity-review.md) | 생산성 검토 (완료) | 완료 |

## v0.4.16 핵심 수치 요약

`recall-int8.json` 기준 (onnx-int8, split=test, n=854):

| 지표 | 값 |
|---|---|
| 전체 PII 재현율 | **0.9908** |
| KR_PERSON 재현율 | **0.9799** (Wilson CI 하한 **0.9591** ✅ ≥0.93) |
| KR_LOCATION 재현율 | **1.0000** (Wilson CI 하한 0.9417 ✅ ≥0.90) |
| 12개 클래스 전부 CI95 하한 | **≥ 0.90** ✅ |
| benign_false_block | **0.0** |
| 온프렘 지연 p95 (512자, c=1) | **41 ms** |

## recall-int8.json 키 구조 안내

보고서 JSON 을 코드에서 읽을 때 사용하는 주요 키:

```python
import json

with open("docs/reports/recall-int8.json") as f:
    r = json.load(f)

# 전체 요약
r["scores"]["pii_recall"]          # 전체 PII 재현율 (0.0~1.0)
r["scores"]["pii_recall_ci95"]     # Wilson 95% 신뢰구간 [lower, upper]
r["scores"]["pii_precision"]       # 정밀도
r["scores"]["strong_recall"]       # 강한 PII(주민·여권·카드 등) 재현율

# 클래스별 상세 (per_class_recall)
for cls, val in r["scores"]["per_class_recall"].items():
    print(cls, val["recall"], val["ci95_lower"])

# 지연
r["latency"]["p95_ms"]             # p95 지연 (ms, 512자 입력 기준)
r["latency"]["concurrency"]        # 측정 동시성

# 허용 판정
r["acceptance_pass"]               # bool — 릴리스 게이트 통과 여부
r["acceptance"]                    # 각 항목(pii_recall·ci_low·false_block·latency) 판정 dict
```

SDK 에서 접근: `from nufi import compliance_report` — 리포트 집계에서 이 파일이 자동 참조됩니다.

---

## 주요 리포트 상세 — 목적 · 생성 · 참조

### recall-int8.json

| 항목 | 내용 |
|---|---|
| **목적** | KoELECTRA INT8(ONNX) 모델의 PII 엔터티별 재현율·정밀도·신뢰구간을 측정하여 릴리스 게이트 판정 근거를 제공 |
| **생성 시점** | 모델 업데이트 또는 골드셋 변경 시 CI/수동 실행 |
| **생성 명령** | `python3 scripts/demo_accuracy.sh` 또는 `nufi-egress benchmark accuracy --json-out docs/reports/recall-int8.json` |
| **참조 문서** | [`../HANDS_ON.md`](../HANDS_ON.md) Part J, [`../SDK.md`](../SDK.md) `compliance_report` |

### pseudonymize-quality.json

| 항목 | 내용 |
|---|---|
| **목적** | 가명화(pseudonymization) 품질 게이팅 — 변환 정확성·포맷 보존·역변환 가능 여부 벤치마크 |
| **생성 시점** | 가명화 로직 변경 시 |
| **생성 명령** | `python3 scripts/bench_pseudonymize.py --json-out docs/reports/pseudonymize-quality.json` |
| **참조 문서** | [`../HANDS_ON.md`](../HANDS_ON.md), `scripts/demo_pseudonymize.sh` |

### load-p95.json

| 항목 | 내용 |
|---|---|
| **목적** | 인라인 지연 측정(p95) — 동시성 스윕별 레이턴시를 기록하여 성능 SLA 판정 근거 제공 |
| **생성 시점** | 성능 관련 변경 또는 릴리스 전 |
| **생성 명령** | `python3 scripts/bench_load.py --requests 200 --sustain-seconds 10 --json-out docs/reports/load-p95.json` |
| **참조 문서** | [`../HANDS_ON.md`](../HANDS_ON.md), [`../SDK.md`](../SDK.md) |

### kr-location-gate.json / kr-location-gate.md

| 항목 | 내용 |
|---|---|
| **목적** | KR_LOCATION 주소 유니온(모델∪규칙) 경로의 재현율·CI 하한을 측정하여 릴리스 게이트 판정 |
| **생성 시점** | 주소 패턴·모델 변경 시 |
| **생성 명령** | `python3 scripts/demo_accuracy.sh` (recall-int8 과 함께 산출) |
| **참조 문서** | [`kr-location-ci-narrowing.md`](kr-location-ci-narrowing.md), [`kr-location-error-analysis.md`](kr-location-error-analysis.md) |

### accuracy-integrity-audit.md

| 항목 | 내용 |
|---|---|
| **목적** | 공개 문서에 인용된 정확도 수치가 근거 리포트(JSON)와 일치하는지 무결성 감사 |
| **생성 시점** | v0.2.2 시점 1회 감사 완료(역사적) |
| **생성 명령** | 수동 작성 (정합성 검사는 `python3 scripts/check_docs.py` 로 자동 수행) |
| **참조 문서** | [`../ARCHITECTURE.md`](../ARCHITECTURE.md), `scripts/check_docs.py` |

---

## 관련 문서

| 문서 | 역할 |
|---|---|
| [`../REPORTING.md`](../REPORTING.md) | 컴플라이언스 매핑 리포트 API — 이 보고서들을 증빙으로 연결하는 방법 |
| [`../HANDS_ON.md`](../HANDS_ON.md) | Part J — 정확도 벤치마크를 직접 재현하는 실습 |
| [`../SDK.md`](../SDK.md) | `compliance_report`·`load_catalog` API로 수치를 코드에서 접근 |
| [`../../samples/gold/README.md`](../../samples/gold/README.md) | 골드셋 포맷·로드·필터링 — 보고서 수치의 입력 데이터 |
