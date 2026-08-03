# E2E 가명화 품질 벤치마크 리포트

**Date**: 2026-07-08
**Issue**: CMP-357 (parent: CMP-346)
**Pipeline**: `scripts/bench_pseudonymize_e2e.py` (CMP-351)
**LLM Backend**: mock (ANTHROPIC_API_KEY 미설정 — mock 모드 대체)

## 개요

원문→LLM→원문응답 vs 가명화→LLM→원복응답을 자동 비교하는 E2E 벤치마크.
CMP-350 한국어 PII QA 평가셋(170건: PII 150건 + Control 20건)을 입력으로 사용.

## 종합 결과

| 지표 | 달성값 | 목표 | 판정 |
|------|--------|------|------|
| Utility Retention (ROUGE-L) | **0.9971** | ≥ 0.90 | **PASS** |
| Exact Match Rate | **0.9706** (165/170) | — | — |
| PII Protection Rate | **1.0000** (290/290) | == 1.00 | **PASS** |
| Roundtrip Fidelity | **0.9828** (285/290) | ≥ 0.95 | **PASS** |

**종합: PASS** — 전 지표 목표 달성. CMP-357 인명 호모그래프 오탐 차단으로 legal 카테고리 degraded 5건 전량 해소.

## 타입별 분석

| PII 타입 | 건수 | 보호율 | 원복 충실도 | 비고 |
|----------|------|--------|-------------|------|
| EMAIL | 50 | **1.0000** | 0.9000 | 원복 일부 미달 |
| KR_BRN | 25 | **1.0000** | **1.0000** | 완벽 |
| KR_LOCATION | 25 | **1.0000** | **1.0000** | 완벽 |
| KR_PERSON | 135 | **1.0000** | **1.0000** | 완벽 |
| KR_PHONE | 55 | **1.0000** | **1.0000** | CMP-357 오탐 해소로 완벽 |

### 핵심 발견

1. **legal 카테고리 degraded 5건 전량 해소** — CMP-357에서 `_PERSON_STOPWORDS` 추가로 "담당"이 인명으로 오탐되던 문제 수정.
   - 원인: "담당 변호사"에서 "담당"(성씨 "담" + "당")이 `_PERSON_TITLE_RE`에 매치 → 불필요한 surrogate ⟦P1⟧ 생성 → MockLLM 매핑 교란
   - 수정: `_PERSON_STOPWORDS` frozenset에 "담당" 등 일반명사 호모그래프 등록
2. **KR_PHONE 원복 충실도 0.9091 → 1.0** — 동일 원인(surrogate 매핑 어긋남)이 전화번호 원복을 방해하던 것도 해소.
3. **EMAIL 원복 일부 미달**(0.9000) — 별도 이슈, 이번 CMP-357 범위 밖.

## 카테고리별 분석

| 카테고리 | 샘플 수 | Exact Match | 평균 ROUGE-L |
|----------|---------|-------------|--------------|
| payment | 28 | **28 (100%)** | 1.0000 |
| customer_service | 29 | **29 (100%)** | 1.0000 |
| hr | 28 | **28 (100%)** | 1.0000 |
| document_summary | 29 | **29 (100%)** | 1.0000 |
| medical | 28 | 23 (82.1%) | 0.9821 |
| legal | 28 | **28 (100%)** | **1.0000** |

- **legal**: CMP-357 이전 5건 품질 저하 → 전량 해소, 100% Exact Match 달성.

## 레이턴시 오버헤드

| 단계 | p50 | p95 |
|------|-----|-----|
| 가명화 | 0.4ms | 0.6ms |
| 원복 | 0.0ms | 0.1ms |

가명화/원복 처리 레이턴시는 sub-millisecond 수준으로 LLM 호출 대비 무시 가능.

## 개선 이력

| 버전 | 변경 내용 | 영향 |
|------|-----------|------|
| v0.8.0 (CMP-352) | 초기 벤치마크 | KR_PERSON 보호율 0.8148 |
| CMP-353 | 문맥 게이팅 강화 | KR_PERSON 보호율 1.0 |
| CMP-354 | KR_LOCATION 복합 지명 개선 | roundtrip fidelity 0.84→1.0 |
| v0.8.1 (CMP-355) | 전 지표 PASS | ROUGE-L 0.9871, degraded 5건 잔존 |
| **CMP-357** | **인명 호모그래프 오탐 차단** | **ROUGE-L 0.9971, degraded 0건** |

## 산출물

- 벤치마크 JSON: `docs/reports/pseudonymize-e2e-quality.json`
- 평가셋: `data/pii_qa_eval.jsonl` (170건)
- 평가셋 설명: `data/pii_qa_eval_README.md`
- 파이프라인: `scripts/bench_pseudonymize_e2e.py`
