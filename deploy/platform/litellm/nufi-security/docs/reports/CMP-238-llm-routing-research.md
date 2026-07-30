# CMP-238: LLM 라우팅 솔루션 조사 보고서

> 작성일: 2026-07-03 | 작성자: CEO Agent

## 요약

LLM 라우팅은 질문의 복잡도·민감도·비용 요건에 따라 최적의 모델로 자동 분배하는 기술이다. 2026년 현재 시장이 빠르게 성숙하고 있으며, IDC 예측에 따르면 2028년까지 상위 AI 기업의 70%가 동적 모델 라우팅을 채택할 전망이다. **NuFi의 하이브리드(로컬+클라우드) 아키텍처에 라우팅 레이어를 도입하면 비용 47-80% 절감과 PII 보호 강화를 동시에 달성할 수 있다.**

---

## 1. 시장 현황

### 1.1 시장 규모 및 트렌드

- OpenRouter: 2026년 5월 기준 사용자 800만 명, 월 ~100조 토큰 처리
- 주요 VC 투자: Martian (Accenture 지원), Not Diamond, Unify AI 등
- IDC FutureScape 2026: "AI의 미래는 모델 라우팅" — 멀티모델 아키텍처가 표준화 추세

### 1.2 라우팅이 해결하는 문제

| 문제 | 라우팅 솔루션 |
|------|-------------|
| 비용 과다 | 간단한 질문은 저가 모델로 → 최대 85% 비용 절감 |
| 레이턴시 | 지역·모델별 최적 경로 선택 |
| 가용성 | 장애 시 자동 폴백 |
| PII 보안 | 민감 데이터 감지 → 로컬 모델로 강제 라우팅 |
| 품질 | 복잡한 질문만 고성능 모델로 → 품질 유지 |

---

## 2. 주요 솔루션 비교

### 2.1 매니지드 서비스

| 솔루션 | 특징 | 모델 수 | 가격 모델 | 장점 | 단점 |
|--------|------|---------|----------|------|------|
| **OpenRouter** | 통합 API 게이트웨이 | 315+ | Pay-as-you-go (5.5% 수수료) | 최대 모델 커버리지, OpenAI 호환 API | 셀프호스팅 불가, 데이터가 외부 통과 |
| **Not Diamond** | ML 기반 지능형 라우터 | 주요 모델 | SaaS | 프롬프트별 최적 모델 선택, 커스텀 라우터 학습 가능 | 벤더 종속 |
| **Martian** | 모델 해석성 기반 라우팅 | 주요 모델 | SaaS | 20-97% 비용 절감 (자체 주장), 특허 기술 | 블랙박스적, 비용 불투명 |
| **Unify AI** | 실시간 벤치마크 기반 | 주요 모델 | SaaS | 10분 간격 벤치마크 갱신 | 규모 작음 |
| **Portkey** | AI 게이트웨이 + 관측성 | 200+ | Freemium | 가드레일, 캐싱, 로깅 내장 | 라우팅 지능은 제한적 |

### 2.2 오픈소스 / 셀프호스팅

| 솔루션 | GitHub Stars | 특징 | 라이선스 | NuFi 적합성 |
|--------|-------------|------|---------|------------|
| **LiteLLM** | ~20k+ | 140+ 프로바이더 통합, OpenAI 호환 프록시, 예산 제어, 가드레일 | MIT | ⭐⭐⭐⭐⭐ |
| **RouteLLM** (LMSYS) | ~4k+ | 비용-품질 트레이드오프 최적화, ML 분류기 기반, Chatbot Arena 데이터 학습 | Apache 2.0 | ⭐⭐⭐⭐ |
| **Bifrost** (Maxim AI) | - | 고성능 게이트웨이, MCP 지원, 거버넌스 | Apache 2.0 | ⭐⭐⭐ |
| **Apache APISIX** | ~14k+ | 기존 API 게이트웨이에 AI 플러그인 추가 | Apache 2.0 | ⭐⭐⭐ |
| **Envoy AI Gateway** | - | K8s 네이티브, Envoy 기반 | Apache 2.0 | ⭐⭐⭐ |

---

## 3. 기술 심층 분석

### 3.1 라우팅 기법 Top 5

1. **규칙 기반 (Rule-based)**: 키워드/패턴 매칭으로 모델 선택. 구현 간단, 유연성 낮음
2. **ML 분류기 (Classifier)**: 프롬프트를 분류하여 모델 배정. RouteLLM이 대표적
3. **비용-품질 최적화**: 임계값 파라미터로 비용/품질 균형 조절
4. **컨텍스트 기반**: PII 감지, 데이터 민감도에 따른 라우팅 (하이브리드 아키텍처에 핵심)
5. **적응형 (Adaptive)**: 실시간 성능 데이터로 라우팅 결정 갱신

### 3.2 RouteLLM 상세 (가장 유관)

- LMSYS (Chatbot Arena 팀) 개발
- 4가지 사전학습 라우터: Matrix Factorization (권장), Similarity-weighted, BERT, Causal LLM
- **성과**: MT Bench 기준 GPT-4 품질 95% 유지하면서 비용 85% 절감
- **임계값**: 0~1 사이 단일 파라미터로 강모델/약모델 비율 조절
- OpenAI 호환 서버로 바로 배포 가능

### 3.3 하이브리드 아키텍처와의 시너지

NuFi는 이미 로컬+클라우드 하이브리드를 사용하므로, 라우팅 레이어 도입 시:

```
요청 → [PII 감지] → PII 있음 → 로컬 모델 (강제)
                   → PII 없음 → [복잡도 분류] → 단순 → 저가 모델
                                              → 복잡 → 고성능 모델
```

- **PII 감지가 최우선 라우팅 규칙**으로 작동 → NuFi의 보안 미션과 완벽 정렬
- 복잡도 분류는 RouteLLM의 ML 분류기 활용 가능
- LiteLLM으로 프록시 레이어 구축 + RouteLLM 분류기 결합이 최적 조합

---

## 4. NuFi 적용 권고안

### 4.1 추천 스택

| 레이어 | 솔루션 | 역할 |
|--------|--------|------|
| 프록시/게이트웨이 | **LiteLLM** (셀프호스팅) | 통합 API, 폴백, 예산 관리, 로깅 |
| 지능형 라우팅 | **RouteLLM** (커스텀 학습) | 비용-품질 최적화, 프롬프트 복잡도 분류 |
| PII 라우팅 | **NuFi 자체 PII 감지** | PII 포함 요청 → 로컬 강제 라우팅 |

### 4.2 도입 단계

1. **Phase 1 — 프록시 도입** (1-2주): LiteLLM 프록시 셋업, 기존 모델 통합, 폴백/로깅 활성화
2. **Phase 2 — PII 라우팅** (1주): NuFi PII 감지를 라우팅 규칙으로 연동
3. **Phase 3 — 지능형 라우팅** (2-3주): RouteLLM 분류기 도입, 자체 데이터로 임계값 캘리브레이션
4. **Phase 4 — 최적화** (지속): 비용/품질 모니터링, 라우터 재학습, 모델 추가

### 4.3 예상 효과

- **비용**: 47-80% 절감 (단순 질의를 저가 모델로 라우팅)
- **보안**: PII 민감 요청의 로컬 처리 보장
- **가용성**: 프로바이더 장애 시 자동 폴백
- **유연성**: 새 모델 추가 시 코드 변경 없이 설정만으로 가능

### 4.4 리스크

- RouteLLM 분류기의 한국어 프롬프트 성능 검증 필요 (영어 데이터로 학습됨)
- LiteLLM 프록시 운영 부담 (but 성숙한 프로젝트로 리스크 낮음)
- 라우팅 레이턴시 추가 (10ms 미만으로 무시 가능 수준)

---

## 5. 참고 자료

- [OpenRouter 공식 가격](https://openrouter.ai/pricing)
- [RouteLLM GitHub (LMSYS)](https://github.com/lm-sys/RouteLLM)
- [LiteLLM 가이드](https://a2a-mcp.org/blog/what-is-litellm)
- [Braintrust: Best LLM Routers 2026](https://www.braintrust.dev/articles/best-llm-routers-2026)
- [Not Diamond: Top 10 AI Gateways 2026](https://www.notdiamond.ai/blog/the-top-10-ai-gateways-for-the-multi-model-future-2026)
- [IDC: The Future of AI is Model Routing](https://www.idc.com/resource-center/blog/the-future-of-ai-is-model-routing/)
- [Felicis: Routing the Future](https://www.felicis.com/insight/model-routing)
- [Hybrid Cloud-Edge LLM Routing](https://tianpan.co/blog/2026-04-10-hybrid-cloud-edge-llm-inference-routing)
- [EdenAI: Best LLM Routers 2026](https://www.edenai.co/post/best-llm-routers)
- [Maxim AI: Top 5 LLM Router Solutions](https://www.getmaxim.ai/articles/top-5-llm-router-solutions-in-2026/)
- [TrueFoundry: AI Gateway Guide 2026](https://www.truefoundry.com/blog/a-definitive-guide-to-ai-gateways-in-2026-competitive-landscape-comparison)
