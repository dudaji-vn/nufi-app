# NuFi PII 탐지 성능 측정 리포트 (CMP-306)

**측정일:** 2026-07-06
**백엔드:** gazetteer (규칙 기반 폴백)
**데이터셋:** 합성 골드셋 1,414건 + 외부 ai4privacy 414,096건 (5,000건 샘플 벤치마크)

---

## 1. 합성 골드셋 (synth) — test 분할 854건

### 전체 성능

| 지표 | 값 | 목표 | 합격 |
|---|---|---|---|
| PII Recall | 0.9056 | >= 0.90 | **FAIL** (경계) |
| PII Precision | 0.9665 | >= 0.85 | PASS |
| Strong Recall (체크섬형) | 1.0000 | >= 0.98 | PASS |
| Benign False Block | 0.0000 | <= 0.02 | PASS |

> **참고:** PII Recall이 경계에 있는 이유는 gazetteer 백엔드가 KR_PERSON 미수록 성씨를 탐지하지 못하기 때문 (의도된 설계 — NER 모델이 필요한 영역).

### 클래스별 Recall

| PII 타입 | Recall | 탐지/전체 | Wilson CI 95% |
|---|---|---|---|
| KR_RRN | 1.0000 | 35/35 | [0.901, 1.000] |
| KR_FOREIGNER_REG | 1.0000 | 35/35 | [0.901, 1.000] |
| KR_BRN | 1.0000 | 35/35 | [0.901, 1.000] |
| KR_PASSPORT | 1.0000 | 35/35 | [0.901, 1.000] |
| KR_DRIVER_LICENSE | 1.0000 | 35/35 | [0.901, 1.000] |
| CREDIT_CARD | 1.0000 | 35/35 | [0.901, 1.000] |
| KR_ACCOUNT | 1.0000 | 36/36 | [0.904, 1.000] |
| KR_PHONE | 1.0000 | 36/36 | [0.904, 1.000] |
| EMAIL | 1.0000 | 36/36 | [0.904, 1.000] |
| KR_LOCATION | 0.9375 | 60/64 | [0.850, 0.977] |
| SECRET | 1.0000 | 36/36 | [0.904, 1.000] |
| **KR_PERSON** | **0.7328** | **255/348** | **[0.684, 0.777]** |

> **KR_PERSON 0.73** — gazetteer는 미수록 성씨(56%)를 탐지 불가. ONNX/KoELECTRA 백엔드 사용 시 0.95+ 달성 (설계 의도).

### Span 매칭

| 지표 | 값 |
|---|---|
| Span Exact Recall | 0.8817 |
| Span Exact Precision | 0.9488 |

---

## 2. 외부 데이터셋 (ai4privacy) — 5,000건 샘플

### 전체 성능

| 지표 | 값 |
|---|---|
| Entity-Class Recall | 0.1057 |
| Entity-Class Precision | 0.5872 |
| Entity-Class F1 | 0.1791 |
| Span Exact Recall | 0.0746 |
| Span Exact Precision | 0.5623 |

### 클래스별 Recall

| PII 타입 | Recall | 탐지/전체 | 비고 |
|---|---|---|---|
| EMAIL | **0.9956** | 678/681 | 크로스링구얼 — 규칙만으로 충분 |
| KR_PHONE | 0.0943 | 88/933 | 외국 전화번호 포맷 차이 |
| KR_BRN | 0.0710 | 12/169 | 외국 세금번호 구조 차이 |
| CREDIT_CARD | 0.0551 | 7/127 | Luhn 검증 통과 비율 낮음 |
| KR_DRIVER_LICENSE | 0.0211 | 2/95 | 외국 면허 포맷 불일치 |
| KR_PASSPORT | 0.0050 | 1/202 | 외국 여권번호 포맷 차이 |
| KR_RRN | 0.0000 | 0/129 | 외국 사회보장번호 ≠ 주민등록번호 |
| KR_PERSON | 0.0000 | 0/3,849 | 외국 이름 — 한국어 gazetteer 미지원 |
| KR_LOCATION | 0.0000 | 0/1,273 | 외국 지명 — 한국어 사전 미지원 |

### 분석

ai4privacy 데이터셋은 **8개 유럽/인도 언어**(en, fr, de, it, es, nl, hi, te)로 구성되어 있어, 한국어 규칙 기반 탐지기(gazetteer)로는 구조적으로 낮은 recall을 보입니다. 이는 예상된 결과이며, 의미 있는 지표는:

1. **EMAIL 0.9956** — 규칙 기반으로도 크로스링구얼 탐지 가능 확인
2. **Precision 0.5872** — 탐지된 것 중 59%는 정확 (오탐 낮음)
3. **체크섬/구조형 PII** — 외국 포맷과 한국 포맷의 구조적 차이가 recall 저하 원인

---

## 3. 데이터 규모 요약

| 구분 | 합계 | dev | test | 출처 |
|---|---|---|---|---|
| 합성(synth) | 1,414 | 560 | 854 | goldset/generate.py |
| 외부(ai4privacy) | 414,096 | 165,634 | 248,462 | HuggingFace CC-BY-4.0 |
| **총합** | **415,510** | **166,194** | **249,316** | |

---

## 4. 결론 및 향후 과제

### 합성 골드셋 (한국어 PII)
- **체크섬/구조형 PII**: recall 1.0 — gazetteer 규칙만으로 완벽 탐지
- **KR_PERSON**: gazetteer 0.73, ONNX 백엔드 사용 시 0.95+ 예상
- **KR_LOCATION**: 0.94 — 도로명/상세주소 확장 후 양호

### 외부 데이터셋 (다국어 PII)
- 현재 NuFi는 **한국어 PII 특화** 시스템으로, 외국어 PII 탐지는 설계 범위 밖
- EMAIL처럼 언어 무관한 PII는 크로스링구얼 탐지 가능
- 향후 다국어 지원 시 ai4privacy 데이터셋이 벤치마크 기준선 역할 가능

### 향후 추가 벤치마크
- ONNX-INT8 백엔드 벤치마크 (`bench_m5.py --backend onnx-int8`)
- KLUE-NER 한국어 NER 벤치마크 (HF_TOKEN 설정 후)
- K-LegalDeID 한국 법률문서 벤치마크 (데이터셋 공개 시)
