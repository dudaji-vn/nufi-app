# 하이브리드 LLM 파이프라인: 가명화 환경에서 응답 품질 유지 방안 조사

> **목적**: 외부 LLM(Claude, GPT 등)에 민감 데이터를 보내기 전 가명화(pseudonymization)·
> 익명화(anonymization)를 적용하면 응답 품질이 떨어진다. 이 문제를 해소하는 학술 연구·
> 오픈소스 프로젝트·아키텍처 패턴을 정리한다.

---

## 1. 문제 정의

```
사용자 → [민감정보 포함 질문] → 외부 LLM → 고품질 답변
                                 ↑ 비용·개인정보 위험

사용자 → [익명화된 질문]       → 외부 LLM → 품질 저하된 답변
```

- 원문을 그대로 보내면 개인정보(PII) 유출 위험 + API 비용 부담
- 가명화하면 문맥이 깨져 LLM 응답 품질 저하 (특히 이름·주소·금액 등이 답변 핵심일 때)
- **핵심 과제**: 프라이버시를 보호하면서 LLM 응답 정확도를 유지하는 방법

---

## 2. 접근 방식 분류

### 2.1 가역적 가명화 (Reversible Pseudonymization)

**원리**: 민감 엔티티를 일관된 가명(fake)으로 치환 → LLM 호출 → 응답에서 가명을 원래 값으로 복원

| 구분 | 내용 |
|---|---|
| 대표 도구 | **Microsoft Presidio** + LangChain `PresidioReversibleAnonymizer` |
| 작동 방식 | NER(Named Entity Recognition) + 패턴 매칭으로 PII 탐지 → Faker 라이브러리로 타입 일관적 가명 생성 → 매핑 테이블 보관 → 응답 후 역치환 |
| 장점 | 구현이 단순, LangChain 생태계 통합, 다국어 지원 |
| 한계 | 문맥이 가명에 의존하는 경우(예: "김 부장님과 박 대리님 관계는?") 응답 품질 저하 가능 |
| 참고 | [LangChain Presidio Reversible Anonymizer 문서](https://python.langchain.com/docs/guides/privacy/presidio_data_anonymization/reversible), [DZone 가이드](https://dzone.com/articles/llm-pii-anonymization-guide) |

**오픈소스**:
- [**CleanPrompt**](https://github.com/takashiishida/cleanprompt) — 프롬프트 내 민감정보를 NER+정규식으로 치환하고, LLM 응답 후 역치환하는 경량 라이브러리
- [**Microsoft Presidio**](https://github.com/microsoft/presidio) — 텍스트·이미지·구조화 데이터에서 PII 탐지·삭제·마스킹·가명화를 지원하는 프레임워크

### 2.2 프라이버시 보존 질의응답 (Privacy-Preserving QA)

**원리**: 질문에서 고위험 민감정보는 치환하고, 저위험 텍스트는 난독화(obfuscation)만 적용 → 외부 LLM 호출 → 응답에서 민감정보 복원 + 최종 답변 생성

| 구분 | 내용 |
|---|---|
| 대표 연구 | **PRIV-QA** (2025, Li et al.) |
| 작동 방식 | Hide Module(H): 고위험 PII 치환 + 저위험 텍스트 난독화 → 클라우드 LLM 호출 → Recover Module(R): 민감정보 복원 + 최종 응답 생성 |
| 데이터셋 | **SensitiveQA** — 57k 중·영 대화 쌍 (프라이버시 민감 질의응답) |
| 성과 | 프라이버시 보호와 응답 품질 양립을 실험적으로 입증 |
| 참고 | [논문 (arXiv 2502.13564)](https://arxiv.org/abs/2502.13564), [GitHub](https://github.com/ligw1998/priv-qa) |

### 2.3 활성화 벡터 기반 복원 (Activation Steering)

**원리**: 로컬 모델에서 민감 정보의 "복원 벡터"를 사전 인코딩 → 외부 LLM에는 민감정보를 제거한 입력만 전송 → 응답 생성 시 활성화 조향(activation steering)으로 원래 문맥 복원

| 구분 | 내용 |
|---|---|
| 대표 연구 | **PrivacyRestore** (2024, arXiv 2406.01394) |
| 작동 방식 | 준비 단계: 민감 스팬(span)을 복원 벡터로 인코딩 → 추론 단계: 민감정보 제거된 입력을 LLM에 전송 → 활성화 조향으로 민감 문맥 복원 |
| 장점 | 플러그앤플레이 방식, 모델 재학습 불필요 |
| 한계 | LLM 내부 활성화에 접근 가능해야 함 (API 전용 서비스에서는 적용 어려움) |
| 참고 | [논문 (arXiv 2406.01394)](https://arxiv.org/abs/2406.01394) |

### 2.4 로컬-클라우드 하이브리드 라우팅

**원리**: 민감도에 따라 요청을 로컬 소형 LLM과 클라우드 대형 LLM으로 분기

```
사용자 질문
  ↓
[민감도 분류기] ──── 고민감 ──→ 로컬 소형 LLM (온프렘)
  │                              (정확도↓ but 데이터 유출 없음)
  └──── 저민감 ────→ 클라우드 대형 LLM
                      (정확도↑, PII 없는 안전한 질의)
```

| 구분 | 내용 |
|---|---|
| 핵심 기술 | 민감도 기반 라우팅(sensitivity-based routing) + 로컬 SLM(Small Language Model) |
| 참고 연구 | [Privacy Guard & Token Parsimony by Prompt and Context Handling and LLM Routing](https://arxiv.org/pdf/2603.28972), [Hybrid Cloud-Local LLM Architecture Guide](https://www.sitepoint.com/hybrid-cloudlocal-llm-the-complete-architecture-guide-2026/) |
| 장점 | 민감 데이터가 네트워크를 떠나지 않음, 비용 절감 |
| 한계 | 로컬 모델 품질이 사용자 기대에 미달할 수 있음; 라우팅 정확도에 의존 |

### 2.5 LLM 기반 온프레미스 가명화 (Anonymous-by-Construction)

**원리**: 로컬 LLM을 사용하여 조직 내부에서 PII를 현실적이고 타입 일관적인 대체값으로 치환 → 데이터가 외부로 나가지 않음

| 구분 | 내용 |
|---|---|
| 대표 연구 | **Anonymous-by-Construction** (2026, arXiv 2603.17217) |
| 작동 방식 | 온프레미스 LLM이 PII를 탐지하고 현실적 대체값 생성 → 전체 파이프라인이 조직 내부에서 실행 |
| 장점 | 데이터 이탈(egress) 자체를 방지, 대체값이 자연스러워 후속 분석 품질 유지 |
| 참고 | [논문 (arXiv 2603.17217)](https://arxiv.org/html/2603.17217v1) |

---

## 3. 정량적 성과 요약

| 접근 방식 | 프라이버시 보호율 | 응답 품질 손실 | 비고 |
|---|---|---|---|
| 가역적 가명화 (Presidio) | 엔티티 마스킹 97–99% | 10점 만점에 ~1점 하락 | ACL 2025 PrivateNLP 벤치마크 |
| PRIV-QA | 고위험 PII 보호 | 최소 품질 저하 입증 | 중·영 57k 데이터셋 실험 |
| PrivacyRestore | 민감 스팬 제거 | 활성화 조향으로 복원 | 모델 내부 접근 필요 |
| 하이브리드 라우팅 | 고민감 데이터 외부 미전송 | 로컬 모델 품질 의존 | 70B 성능을 1/10 VRAM으로 달성 사례 |

---

## 4. NuFi 적용 관점 — 권장 아키텍처

NuFi의 기존 이그레스 감사(egress audit) 파이프라인과 통합 가능한 **3단계 하이브리드 접근**을 권장한다:

```
┌─────────────────────────────────────────────────┐
│  1단계: NuFi PII 탐지 엔진 (기존 인프라)         │
│  - 한국어 NER + 가제티어 + 정규식               │
│  - 민감도 등급 분류 (고/중/저)                   │
├─────────────────────────────────────────────────┤
│  2단계: 민감도 기반 분기                          │
│  ┌─ 고민감 → 로컬 SLM (온프렘) 직접 응답        │
│  ├─ 중민감 → 가역적 가명화 → 클라우드 LLM       │
│  └─ 저민감 → 클라우드 LLM 직접 전송             │
├─────────────────────────────────────────────────┤
│  3단계: 응답 후처리                               │
│  - 가명 역치환 (매핑 테이블 참조)                │
│  - 해시체인 감사 로그 기록                       │
└─────────────────────────────────────────────────┘
```

**왜 이 구조인가**:
- 1단계는 NuFi가 이미 보유한 PII 탐지 엔진을 그대로 활용
- 2단계의 가역적 가명화는 Presidio/PRIV-QA 연구에서 97–99% 보호율 + 최소 품질 손실 입증
- 로컬 SLM 폴백은 고민감 데이터의 외부 유출을 원천 차단
- 3단계 역치환으로 최종 사용자에게는 원래 맥락의 답변 제공

---

## 5. 벤치마크 계획 — 가명화 적용 전후 LLM 응답 품질 비교

### 5.1 목표

**일관적 가명화(consistent pseudonymization)를 적용했을 때와 적용하지 않았을 때의 LLM 응답 품질 차이**를 정량적으로 측정하여, 가명화가 실용적인 수준에서 품질을 유지하는지 입증한다.

### 5.2 실험 설계

```
                    원문 질의 (PII 포함)
                    ┌────────┴────────┐
              [A] 원문 그대로       [B] 가역적 가명화 적용
                    │                     │
              외부 LLM 호출          외부 LLM 호출
                    │                     │
              응답 A (기준선)        응답 B′ (가명 포함)
                                          │
                                    역치환 (de-pseudonymize)
                                          │
                                    응답 B (복원된 답변)
                    └────────┬────────┘
                    품질 비교: A vs B
```

- **독립변수**: 가명화 적용 여부 (원문 / 일관적 가명화 / 단순 마스킹)
- **종속변수**: 응답 정확도, 의미 유사도, 유창성
- **통제**: 동일 LLM, 동일 프롬프트 템플릿, 동일 temperature 설정

### 5.3 활용 데이터셋 (공신력 있는 공개 데이터셋)

| 데이터셋 | 언어 | 규모 | 특징 | 용도 |
|---|---|---|---|---|
| [**SensitiveQA**](https://github.com/ligw1998/priv-qa) (PRIV-QA) | 중·영 | 57k 대화쌍 | 프라이버시 민감 질의응답 전용, 고/저위험 PII 포함 | 프라이버시 보존 QA 정확도 평가 |
| [**PII-Bench**](https://arxiv.org/abs/2502.18545) | 영어 | 2,842 샘플 | 55개 세분화 PII 유형, 단일·다자 시나리오 | PII 탐지 정확도 + 질의 맥락 보존 평가 |
| [**KorQuAD 1.0/2.0**](https://korquad.github.io/) | 한국어 | 70k/100k | SQuAD 형식 한국어 기계독해, 공신력 높음 | 한국어 QA에 PII를 삽입하여 가명화 전후 비교 |
| [**TAB** (Text Anonymization Benchmark)](https://github.com/NorskRegnesentral/text-anonymization-benchmark) | 영어 | 법원 판결문 | 포괄적 개인정보 주석, 프라이버시·유틸리티 평가 메트릭 제공 | 문서 수준 가명화 유틸리티 평가 |
| [**MedPriv-Bench**](https://arxiv.org/abs/2603.14265) | 영어 | 의료 QA | 의료 오픈엔드 QA에서 프라이버시-유틸리티 트레이드오프 전용 | 도메인 특화 가명화 품질 평가 |

**한국어 벤치마크 구성 방법**: KorQuAD에 한국어 PII(인명·주소·전화번호·주민등록번호 등)를 삽입한 변형 데이터셋을 생성하여, NuFi PII 엔진으로 가명화 전후 EM(Exact Match)·F1을 비교한다.

### 5.4 평가 지표 (Evaluation Metrics)

| 지표 | 측정 대상 | 산출 방법 |
|---|---|---|
| **EM (Exact Match)** | 정답 일치율 | 가명화 전후 정답 일치 비율 비교 |
| **F1 Score** | 토큰 수준 정밀도·재현율 | QA 태스크 표준 평가 |
| **ROUGE-L** | 요약·장문 응답 품질 | 생성된 응답과 기준 응답 간 최장 공통 부분수열 |
| **BERTScore** | 의미적 유사도 | 임베딩 기반 의미 유사도 (언어 무관) |
| **Perplexity** | 유창성 | 가명화된 프롬프트의 자연스러움 (낮을수록 좋음) |
| **PII 보호율** | 프라이버시 | 원문 PII 중 실제 가명화된 비율 |
| **유틸리티 유지율** | 종합 | (가명화 후 점수 / 원문 점수) × 100% |

### 5.5 활용 가능한 오픈소스 도구

| 도구 | 역할 | 링크 |
|---|---|---|
| **Microsoft Presidio** | PII 탐지 + 가역적 가명화 엔진 | [GitHub](https://github.com/microsoft/presidio) |
| **LangChain PresidioReversibleAnonymizer** | 가명화 파이프라인 통합 | [문서](https://python.langchain.com/docs/guides/privacy/presidio_data_anonymization/reversible) |
| **CleanPrompt** | 경량 프롬프트 가명화·역치환 | [GitHub](https://github.com/takashiishida/cleanprompt) |
| **PRIV-QA** | 차등 난독화 + 응답 복원 프레임워크 | [GitHub](https://github.com/ligw1998/priv-qa) |
| **ProSan** (The Fire Thief) | 동적 프라이버시-유용성 균형 프롬프트 가명화 | [arXiv:2406.14318](https://arxiv.org/abs/2406.14318) |
| **NuFi PII 엔진** (자체) | 한국어 PII 탐지 + 가명화 | 기존 `egress_audit/detectors/` |

### 5.6 기대 산출물

```
┌─────────────────────────────────────────────────────────────┐
│  벤치마크 결과 비교표 (예시)                                  │
├─────────────┬──────────┬──────────────┬──────────────────────┤
│  조건        │ EM / F1  │ ROUGE-L      │ PII 보호율           │
├─────────────┼──────────┼──────────────┼──────────────────────┤
│ 원문 (기준)  │ 0.82     │ 0.78         │ 0% (보호 없음)       │
│ 단순 마스킹  │ 0.45     │ 0.41         │ 99%                  │
│ 일관적 가명화│ 0.79     │ 0.75         │ 97%                  │
│ PRIV-QA     │ 0.80     │ 0.76         │ 98%                  │
└─────────────┴──────────┴──────────────┴──────────────────────┘
  → 일관적 가명화: 원문 대비 유틸리티 유지율 96%+, PII 보호율 97%+
```

이 비교표가 핵심 산출물이다. 단순 마스킹(`[REDACTED]`) 대비 일관적 가명화가 얼마나 응답 품질을 보존하는지를 정량적으로 보여준다.

---

## 6. 추가 참고 자료

### 논문
1. **PRIV-QA** — Li et al. (2025). *Privacy-Preserving Question Answering for Cloud Large Language Models*. [arXiv:2502.13564](https://arxiv.org/abs/2502.13564) / [GitHub](https://github.com/ligw1998/priv-qa)
2. **PrivacyRestore** — (2024). *Privacy-Preserving Inference in LLMs via Privacy Removal and Restoration*. [arXiv:2406.01394](https://arxiv.org/abs/2406.01394)
3. **Anonymous-by-Construction** — (2026). *An LLM-Driven Framework for Privacy-Preserving Text*. [arXiv:2603.17217](https://arxiv.org/html/2603.17217v1)
4. **Balancing Privacy and Utility** — ACL 2025 PrivateNLP. *Balancing Privacy and Utility in Personal LLM Writing Tasks*. [ACL Anthology](https://aclanthology.org/2025.privatenlp-main.3/)
5. **Privacy Guard & Token Parsimony** — (2026). *LLM Routing for Privacy and Efficiency*. [arXiv:2603.28972](https://arxiv.org/pdf/2603.28972)
6. **Robust Utility-Preserving Text Anonymization** — ACL 2025. [ACL Anthology](https://aclanthology.org/2025.acl-long.1404.pdf)
7. **ProSan (The Fire Thief)** — (2024). *Balancing Usability and Privacy in Prompts*. [arXiv:2406.14318](https://arxiv.org/abs/2406.14318) — MedQA Accuracy, SAMSum ROUGE-L, CodeAlpaca CodeBLEU 기반 가명화 전후 비교 방법론
8. **PII-Bench** — (2025). *Evaluating Query-Aware Privacy Protection Systems*. [arXiv:2502.18545](https://arxiv.org/abs/2502.18545) — 55개 PII 유형, 2,842 샘플 평가 프레임워크
9. **MedPriv-Bench** — (2026). *Benchmarking Privacy-Utility Trade-off in Medical Open-End QA*. [arXiv:2603.14265](https://arxiv.org/abs/2603.14265)

### 오픈소스
1. [**Microsoft Presidio**](https://github.com/microsoft/presidio) — PII 탐지·삭제·마스킹·가명화 프레임워크
2. [**CleanPrompt**](https://github.com/takashiishida/cleanprompt) — LLM 프롬프트 가명화·역치환 라이브러리
3. [**PRIV-QA**](https://github.com/ligw1998/priv-qa) — 프라이버시 보존 QA 프레임워크 + SensitiveQA 데이터셋
4. [**LangChain PresidioReversibleAnonymizer**](https://python.langchain.com/docs/guides/privacy/presidio_data_anonymization/reversible) — LangChain 파이프라인 내 가역적 가명화

---

## 7. 결론

가명화로 인한 응답 품질 저하는 **해결 가능한 문제**다. 최근 연구들은 97–99% PII 보호율에서
10점 만점 기준 약 1점 이내의 품질 손실만 발생함을 입증했다. 핵심 전략은:

1. **가역적 가명화**: 타입 일관적 가명 치환 + 응답 후 역치환 (가장 실용적, 즉시 적용 가능)
2. **민감도 기반 라우팅**: 고민감 질의는 로컬 모델, 저민감 질의는 클라우드 LLM으로 분기
3. **PRIV-QA 방식**: 고위험/저위험 구분 후 차등 난독화 + 응답 복원 (학술적으로 가장 체계적)

NuFi는 이미 PII 탐지 엔진과 이그레스 감사 파이프라인을 보유하고 있으므로, 가역적 가명화
계층을 추가하는 것이 가장 빠른 통합 경로다.
