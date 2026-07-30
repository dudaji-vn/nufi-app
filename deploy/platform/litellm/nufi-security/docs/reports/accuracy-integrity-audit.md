# 공개 정확도·성능 수치 무결성 감사 (v0.2.2 과제 1) — 역사적 문서

> **⚠️ 역사적 문서 — 현재 기준값은 아래 권위 파일을 참고하세요.**
> 이 감사는 v0.2.2 시점(n_rows=372) 기준이며, 지적된 드리프트 3건은 후속 릴리스에서
> 모두 해소되었습니다. **현행 수치 권위:** `docs/reports/recall-int8.json`(n=854, v0.4.16
> 기준: pii_recall=0.9908, person_recall=0.9799, CI 하한=0.9591, benign_fp=0).
> 현행 문서 정합 감사는 `tests/test_docs_consistency.py` 가 CI 에서 상시 검증합니다.

목적: 공개 문서(README·SDK·MANUAL·RELEASE_NOTES·CHANGELOG)에 실린 모든 정확도·성능
수치가 커밋된 근거 리포트(`docs/reports/*.json`)와 정확히 일치하는지 전수 대조하고,
드리프트를 식별한다. 보안·컴플라이언스 제품에서 공개 수치의 정직성은 신뢰의 근거다.

기준 리포트(권위): `docs/reports/recall-int8.json` (backend=onnx-int8, split=test,
n_rows=372) · `docs/reports/kr-location-gate.json` · `docs/reports/load-p95.json`.

## 대조표 — 공개 수치 ↔ 근거 리포트

| 지표 | 공개 문서 값 | 근거 리포트 값 | 근거 파일 | 판정 |
|---|---|---|---|---|
| 전체 PII 재현율(recall) | **0.946** [0.906–0.970] (README) | **0.9433** [0.9098, 0.9648] | `recall-int8.json` `scores.pii_recall`, `pii_recall_ci95` | ⚠️ 드리프트 |
| 전체 정밀도(precision) | **0.985** (README) | pii_precision **1.0** · span_precision **0.9925** | `recall-int8.json` `scores.pii_precision`, `span_precision` | ⚠️ 드리프트 |
| 인라인 지연 p95 (512자) | **38 ms** (README·docs/README) | 커밋 리포트에 38ms 없음. 부하 c=1 = **41.0 ms** | `load-p95.json` `concurrency_sweep.1.lat_p95_ms` | ⚠️ 미근거 |
| 주소(KR_LOCATION) 재현율 | 1.000 [Wilson 하한 0.9417] (README·SDK) | 1.0 · ci95_low 0.9417 (test) · 0.9124 (dev) | `kr-location-gate.json` `after_v0.2.0.*` | ✅ 일치 |
| 강한 PII/Secret 재현율 | 1.000 (README) | strong_recall 1.0 · secret_recall 1.0 | `recall-int8.json` | ✅ 일치 |
| 인명(KR_PERSON) 재현율 | 0.9127 [하한 0.8504] (README·CHANGELOG) | person_recall 0.9127 · ci_low 0.8504 | `recall-int8.json` | ✅ 일치 |
| 인명 재현율 test 분자/분모 | 115/126 (CHANGELOG) | person_recall 0.9127 = 115/126 | `recall-int8.json` | ✅ 일치 |
| 온프렘 부하 p95 c=1/c=2 | 41ms / 67ms (CHANGELOG·history) | 41.0 / 66.934 | `load-p95.json` | ✅ 일치 |
| 무해입력 오탐(benign FP) | 0 (README·SDK·gate) | 0.0 (0/90 test · 0/60 dev) | `recall-int8.json` · `kr-location-gate.json` | ✅ 일치 |

## 드리프트 상세 (3건)

세 건 모두 **v0.0.1 헤드라인 수치가 갱신되지 않은 잔상**이다. 그 뒤 골드셋이
n_rows=372 로 성장하고 onnx-int8 baseline 이 커밋 자산으로 고정되면서 실측값이
바뀌었으나, README 상단 요약표의 세 숫자만 옛 값으로 남았다.

1. **전체 PII 재현율 0.946 → 0.9433.** 점추정·신뢰구간 모두 상이(공개 CI 0.906–0.970
   vs 실측 0.9098–0.9648). 방향: **소폭 과대** (0.3%p). 권위 값 = `recall-int8.json`.
2. **정밀도 0.985 → 실측 어느 값과도 불일치.** 커밋 리포트는 record-level 1.0,
   span-level 0.9925 를 제시. 헤드라인은 보수적으로 **span_precision 0.9925 (~0.99)**
   인용 권장. 방향: 실측이 더 좋음(현재 표기는 과소).
3. **인라인 지연 p95 38ms — 커밋 근거 없음.** 어떤 리포트에도 38ms 가 없다. 가장
   근접한 커밋 측정치는 부하 하니스 c=1 = 41.0ms. 방향: **소폭 과대**(성능이 실제보다
   3ms 빠르게 표기). 권장: 41ms 인용 + 근거 `load-p95.json` 명시, 또는 단일샷 인라인
   지연을 별도 리포트로 커밋한 뒤 그 값 인용.

## 영향 받는 공개 사이트

- `README.md` (요약표 3행: 재현율·정밀도·지연)
- `docs/README.md` (한 줄 요약: 0.946 · 38ms)
- `docs/MANUAL.md` (프로즈: 재현율 0.946)
- `docs/DOC_STYLE.md` — 스타일 예시 표(설명용 예시 문자열, 라이브 정확도 주장 아님 → 저순위)

## 교정 방침 (릴리스 승인 후 반영)

- 세 숫자를 권위 리포트 값으로 교체: 재현율 **0.9433 [0.9098, 0.9648]**, 정밀도
  **0.9925(~0.99)**, 지연 p95 **41ms**(부하 c=1) 또는 단일샷 인라인 지연 신규 커밋값.
- 각 수치 옆에 근거 리포트 파일 경로를 명시(추적성).
- **회귀 가드**: 문서의 헤드라인 수치가 커밋 리포트 JSON 값과 벗어나면 `check_docs`
  가 실패하도록 경량 점검 추가(수치↔JSON 키 매핑 화이트리스트 방식). 드리프트 재발 차단.

## 결론

전수 대조 결과 **드리프트 3건**(모두 v0.0.1 잔상), **일치 6건**. KR_LOCATION·KR_PERSON·
benign FP·부하 p95 등 v0.1.0~v0.2.1 에서 새로 공개한 수치는 전부 근거와 일치한다.
교정 대상은 README 요약표 상단 세 줄로 국소적이며, 기능·재현율 변경 없이 문서·가드만
바꾸는 저위험 작업(패치 경계 부합)이다.
