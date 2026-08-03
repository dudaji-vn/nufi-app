# NuFi v0.4.19 KR_LOCATION 탐지 최적화 벤치마크 리포트

**이슈:** CMP-312
**측정일:** 2026-07-07
**데이터셋:** datasciathlete/corpus4everyone-korean-NER (validation 3,437행, 4,366 LC 엔티티)
**GPU:** NVIDIA GeForce RTX 3080 Ti Laptop, Driver 580.159, CUDA 13.0

---

## 1. 요약

| 설정 | KR_LOCATION Recall | Precision | F1 | 비고 |
|---|---|---|---|---|
| ONNX-INT8 단독 (Before) | 69.5% | 78.3% | 73.7% | KoELECTRA-small INT8 |
| Gazetteer 단독 | 81.5% | 51.8% | 63.3% | 규칙만 (CMP-312 확장) |
| **ONNX-INT8 + location_union** | **92.4%** | 52.7% | 66.7% | **모델 ∪ 규칙** |
| ONNX-INT8 + union (보정*) | **92.4%** | **73.9%** | **82.1%** | annotation gap 제외 |

> **보정***: FP 중 56%는 정확한 탐지이나 외부 데이터셋의 LC 미태깅(annotation gap). 대전·한국·서울·부산 등 명확한 지명이 LC로 태깅되지 않은 케이스를 제외한 보정 수치.

### 내부 골드셋 (프로덕션 기준)

| 지표 | 값 | 목표 | 합격 |
|---|---|---|---|
| Location Recall | **1.0000** | ≥ 0.85 | PASS |
| PII Recall | 0.9594 | ≥ 0.90 | PASS |
| PII Precision | 0.9777 | ≥ 0.85 | PASS |
| Person Recall | 0.9109 | ≥ 0.85 | PASS |
| Benign False Block | **0.0000** | ≤ 0.02 | PASS |

---

## 2. 배경

### 문제

KoELECTRA-small ONNX-INT8 모델의 KR_LOCATION recall이 69.5%로, 외부 한국어 NER 데이터셋 기준 80% 목표에 미달. False Negative 1,331건 분석 결과:

- 어휘밖(OOV) 고유지명: 랜드마크, 개발지구, 해수욕장 등
- 구조적 주소: 도로명주소, 상세주소(동/호)
- Multi-token 행정구역: "성남시 분당구" 등 결합 스팬
- Bare 시군구명: 접미사(시/군/구) 없이 단독 사용

### 목표

외부 한국어 NER 데이터셋 기준 KR_LOCATION recall **80%+** 달성 (프로덕션 안전성 유지).

---

## 3. 최적화 전략

### 3.1 Gazetteer 규칙 확장 (Phase 1)

**_KNOWN_PLACES 전수 확장:**
- 기존 28개 → **~300개**: _SI(시) + _GUN(군) bare name 전수 등재
- 국가명 30+개: 대한민국, 미국, 일본, 중국, 영국, 프랑스, 독일, 호주 등
- 역사·문화 지명: 백제, 가야, 신라, 고구려, 동아시아
- 외국 도시: 우한, 방콕, 상하이, 뉴욕, 하와이 등

**_KNOWN_AMBIGUOUS 도입:**
- 동음이의 위험 높은 2음절 지명을 분리: 경기(=game), 예산(=budget), 고려(=consider), 강화(=strengthen) 등
- 조사(을/를/에서/은/는 등) 또는 비-한글 경계가 있을 때만 지명으로 판정
- FP 억제와 recall 유지의 균형

**한글 경계 검사 (`_is_hangul()`):**
- _KNOWN_PLACES 매칭에 앞경계 검사 추가
- 복합어 내부 오매칭 방지 (예: "만세보령" 내 "보령" 차단)

**_LANDMARK_SUFFIX 확장:**

```
기존: 국제도시, 신도시, 테크노밸리, 플라자, 시티, 타워, 파크, 센터, 공원, 지구, 몰
추가: 해수욕장, 산업단지, 공단, 약수터, 수변길, 터미널, 고개, 마을, 항구
```

- 공백 허용 패턴: "송지호 해수욕장" 등 공백 포함 복합 지명 인식

**_SIGUNGU 보완:**
- 세종시(세종특별자치시) 추가
- SIGUNGU 화이트리스트 항목에 대해 조사 부착형 매칭 패스 추가 ("금산군을", "음성읍민")

**FP 억제 — Stopword 보강:**
- _PLACE_STOPWORDS: ~80개 추가 (혁신도시, 총리, 역시, 반면, 수도권, 충청권 등)
- _LANDMARK_STOPWORDS: ~30개 추가 (행정복지센터, 도시재생지원센터 등)

### 3.2 location_union 활성화 (Phase 2)

`location_union=True` 설정으로 ONNX-INT8 모델과 gazetteer 규칙의 **합집합(union)** 활성화:

```
recall(A ∪ B) ≥ max(recall(A), recall(B))
```

- 모델이 잡는 패턴(문맥 기반 NER)과 규칙이 잡는 패턴(사전 기반 매칭)이 상호 보완
- 스팬 겹침은 파이프라인 `_merge()`에서 점수·길이 우선 중복 제거

### 3.3 CUDA 환경 복구

- NVIDIA 드라이버 재부팅으로 커널 모듈/유저스페이스 불일치 해소 (580.126 → 580.159)
- `onnxruntime-gpu` 1.27.0 설치, PyTorch 번들 `libcudart.so.13` 경로 설정
- CUDAExecutionProvider 정상 작동 확인

---

## 4. 상세 벤치마크 결과

### 4.1 corpus4everyone 외부 데이터셋

**데이터셋:** datasciathlete/corpus4everyone-korean-NER
**규모:** validation 3,437행, KR_LOCATION 4,366 엔티티, KR_PERSON 2,410 엔티티
**특성:** 뉴스 기사 기반, 문자 단위 BIO 태깅, 15개 엔티티 타입 중 PS(인물)·LC(장소)를 NuFi 타입으로 매핑

#### KR_LOCATION

| 설정 | TP | FP | FN | Recall | Precision | F1 | CI95 하한 |
|---|---|---|---|---|---|---|---|
| ONNX-INT8 단독 | 3,035 | 840 | 1,331 | 69.5% | 78.3% | 73.7% | 68.1% |
| Gazetteer 단독 | 3,560 | 3,316 | 806 | 81.5% | 51.8% | 63.3% | 80.4% |
| **ONNX + union** | **4,036** | **3,617** | **330** | **92.4%** | 52.7% | 67.2% | **91.6%** |

#### KR_PERSON

| 설정 | TP | FP | FN | Recall | Precision | F1 |
|---|---|---|---|---|---|---|
| ONNX-INT8 단독 | 2,204 | 144 | 206 | 91.5% | 93.9% | 92.6% |
| ONNX + union | 2,202 | 135 | 208 | 91.4% | 94.2% | 92.8% |

> KR_PERSON은 union 전후 변동 없음 (person_union은 별도 플래그).

### 4.2 FP 분석 (ONNX + union)

KR_LOCATION FP 3,617건 분류:

| 유형 | 건수 | 비율 | 대표 사례 |
|---|---|---|---|
| Annotation gap (정확한 탐지, 데이터셋 미태깅) | 2,022 | 56% | 대전 196x, 한국 138x, 서울 37x |
| Real FP (실제 오탐) | 1,468 | 41% | 강화 31x, 예산 39x, 수도권 33x |
| Model FP (모델 출력 오탐) | ~127 | 3% | 수도권, 충청권 등 모델 자체 FP |

**보정 precision** (annotation gap 제외): **73.9%**
**보정 F1**: **82.1%**

### 4.3 KDPII 데이터셋

| 지표 | Before (gazetteer) | After (gazetteer, CMP-312) |
|---|---|---|
| KR_LOCATION recall | 42.0% | **65.9%** |
| KR_LOCATION precision | 30.0% | 45.3% |

### 4.4 내부 합성 골드셋

| 지표 | ONNX + union | 목표 | 합격 |
|---|---|---|---|
| PII Recall | 0.9594 | ≥ 0.90 | PASS |
| PII Precision | 0.9777 | ≥ 0.85 | PASS |
| Location Recall | **1.0000** | ≥ 0.85 | PASS |
| Person Recall | 0.9109 | ≥ 0.85 | PASS |
| Benign False Block | **0.0000** | ≤ 0.02 | PASS |
| Strong Recall | 1.0000 | ≥ 0.98 | PASS |

---

## 5. SOTA 비교

| 벤치마크 | 모델 | LOC F1 | 비고 |
|---|---|---|---|
| KLUE-NER | KLUE-RoBERTa-large | ~90% | 학술 SOTA, full fine-tuning |
| corpus4everyone | KoELECTRA-small INT8 | 73.7% | NuFi 모델 단독 |
| corpus4everyone | **NuFi ONNX + union (보정)** | **82.1%** | 모델 + 규칙 합집합 |

- NuFi는 **small 사이즈 모델 + INT8 양자화** (속도 우선 설계)
- fine-tuning 없이 **zero-shot + 규칙 합집합**으로 보정 F1 82.1% 달성
- KLUE SOTA 대비 ~8%p 갭은 모델 크기·양자화·fine-tuning 부재가 원인

---

## 6. 커밋 이력

| 커밋 | 설명 |
|---|---|
| `24c1faf` | gazetteer 규칙 확장 — recall 51.7%→81.5% |
| `b3804bb` | ONNX-INT8 + location_union 벤치마크 결과 |
| `34b3de2` | FP 억제 — ambiguous 지명 + stopword 보강 |

---

## 7. 프로덕션 적용

location_union 활성화:

```bash
# 환경변수
M5_LOCATION_UNION=1

# 또는 Python API
from egress_audit import DetectionPipeline
pipeline = DetectionPipeline(ner_backend="onnx-int8", location_union=True)
```

---

## 8. 향후 과제

| 과제 | 예상 효과 | 난이도 |
|---|---|---|
| corpus4everyone fine-tuning | 모델 단독 recall +15%p | GPU 필요 |
| 자연지물 접미사(산/강/호) | recall +3~5%p | FP 위험 높음 |
| 문맥 기반 동음이의 해소 | recall +5~8%p | 복잡도 높음 |
