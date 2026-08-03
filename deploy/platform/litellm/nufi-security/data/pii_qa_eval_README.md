# PII QA 평가셋 (pii_qa_eval.jsonl)

LLM 가명화 품질을 정량 평가하기 위한 한국어 PII 포함 QA 데이터셋.

## 목적

가명화(pseudonymization)를 거쳐 LLM에 전송했을 때 응답 품질이 원문과 동일한지
정량적으로 측정하기 위한 기준 데이터.

## 데이터 구조

각 행은 JSONL 형식이며 다음 필드를 포함:

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | string | 고유 식별자 (`pii_qa_001` ~ `pii_qa_170`) |
| `question` | string | PII를 포함한 질문 |
| `expected_answer` | string | 기대 응답 (PII 포함) |
| `pii_entities` | array | PII 엔티티 목록 (대조군은 빈 배열) |
| `category` | string | 비즈니스 시나리오 카테고리 |

### pii_entities 구조

| 필드 | 타입 | 설명 |
|------|------|------|
| `type` | string | PII 타입 (KR_PERSON, KR_PHONE, EMAIL, KR_LOCATION, KR_BRN) |
| `value` | string | PII 값 |
| `start` | int | question 내 시작 오프셋 (0-indexed) |
| `end` | int | question 내 종료 오프셋 (exclusive) |

## 통계

- **총 샘플 수:** 170
- **PII 포함 샘플:** 150 (88.2%)
- **대조군 (PII 없음):** 20 (11.8%)
- **PII가 expected_answer에 포함된 샘플:** 150 (100% of PII samples)

### 카테고리 분포

| 카테고리 | 샘플 수 | 설명 |
|----------|---------|------|
| customer_service | 29 | 고객 상담 |
| document_summary | 29 | 계약서/문서 요약 |
| hr | 28 | 인사/HR 관련 |
| legal | 28 | 법률 상담 |
| medical | 28 | 의료/건강 상담 |
| payment | 28 | 환불/결제 처리 |

### PII 타입 분포

| PII 타입 | 출현 수 | 설명 |
|----------|---------|------|
| KR_PERSON | 135 | 한국인 이름 |
| KR_PHONE | 55 | 전화번호 |
| EMAIL | 50 | 이메일 주소 |
| KR_BRN | 25 | 사업자등록번호 |
| KR_LOCATION | 25 | 지명/주소 |

## 생성

```bash
python3 scripts/gen_pii_qa_eval.py
```

고정 시드(20260708)로 결정적 생성. 동일 실행 → 동일 데이터셋.

## 검증 테스트

```bash
pytest tests/test_pii_qa_eval.py -v
```

스키마 검증, 오프셋 정확도, 카테고리/PII 타입 커버리지, 대조군 비율 검증.

## 라이선스

합성 데이터 (실고객 데이터 0). 내부 평가 전용.
