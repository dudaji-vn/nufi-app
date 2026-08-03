# gateway/ — LLM Egress Gateway

LLM 요청을 수신하고 보안 감사·라우팅을 적용한 뒤 적절한 백엔드로 전달하는 게이트웨이 모듈.

## 모듈 구조

| 파일 | 설명 |
|------|------|
| `app.py` | FastAPI 진입점. `/v1/chat/completions` (OpenAI 호환) + `/health` 엔드포인트 |
| `core.py` | HTTP-독립 핵심 로직 — 인젝션 탐지, PII 라우팅, egress 검사, 감사 로깅 |
| `router.py` | YAML 기반 모델→백엔드 라우팅 (`Router`, `RouteDecision`, `PIIRoutingConfig`) |
| `pii_router.py` | PII 기반 하이브리드 라우팅 — PII 탐지 시 로컬 모델로 전환, 비용 추적 |
| `litellm_hook.py` | LiteLLM Proxy 콜백 훅 — Phase 0→2 파이프라인 전체를 LiteLLM 라이프사이클에 통합 |
| `complexity_classifier.py` | 프롬프트 복잡도 분류기 — 가중 피처 기반 0.0–1.0 스코어링, 강/약 모델 선택 |
| `ab_testing.py` | A/B 테스트 프레임워크 — SHA-256 해싱 기반 결정적 variant 할당, 메트릭 수집 |
| `cost_dashboard.py` | 실시간 비용 모니터링 — PII/복잡도 라우팅 절감 효과 집계, ASCII 리포트 |
| `__init__.py` | 패키지 공개 API: `Router`, `RouteDecision`, `PIIRoutingConfig` 재노출 |

## 실행 경로

### 1. 단독 FastAPI 서버 (PoC / 테스트)

```bash
uvicorn gateway.app:app --port 8000
```

`app.py` → `core.py (Gateway.process)` → `router.py` 흐름.
빠른 검증·통합 테스트용. Phase 2 기능(복잡도 라우팅, A/B 테스트)은 포함되지 않음.

### 2. LiteLLM Proxy 콜백 (운영 경로)

```yaml
# config/litellm_config.yaml
litellm_settings:
  callbacks: gateway.litellm_hook.egress_audit_hook
```

`litellm_hook.py` → `router.py` + `pii_router.py` + `complexity_classifier.py` + `ab_testing.py` + `cost_dashboard.py` 전체 파이프라인 통합.
운영 환경에서는 이 경로를 사용.

## 관련 설정 파일

| 파일 | 용도 |
|------|------|
| `config/routing.yaml` | 모델별 백엔드·프로바이더 매핑, egress 분류, PII 라우팅 기본값 |
| `config/pii_routing.yaml` | PII 라우팅 상세 설정 (로컬/클라우드 모델, 인젝션 검사 플래그) |
| `config/complexity_routing.yaml` | 복잡도 분류 가중치, 임계값, A/B 테스트 실험 정의 |
| `config/litellm_config.yaml` | LiteLLM Proxy 모델·콜백 설정 |

## Phase 2 기능

- **PII 라우팅** (`pii_router.py`): 개인정보 탐지 시 자동으로 로컬 모델 전환, 비용 절감 추적
- **복잡도 분류** (`complexity_classifier.py`): 한/영 피처 기반 프롬프트 난이도 판별 → 강/약 모델 자동 선택
- **A/B 테스트** (`ab_testing.py`): 라우팅 전략 variant 비교 실험, 결정적 할당
- **비용 대시보드** (`cost_dashboard.py`): 라우팅별 실제 vs 기준 비용 비교, 절감율 리포트

## 주요 환경 변수

| 변수 | 설명 |
|------|------|
| `NUFI_CHECK_INJECTION` | 인젝션 탐지 활성화 (`1`/`0`) |
| `NUFI_DETECT_TIMEOUT_MS` | 탐지 타임아웃 (밀리초) |
| `NUFI_MAX_PROMPT_BYTES` | 프롬프트 최대 크기 |
| `NUFI_LOCAL_MODEL` / `NUFI_CLOUD_MODEL` | PII 라우팅 로컬/클라우드 모델명 |
| `NUFI_COMPLEXITY_CONFIG` | 복잡도 설정 파일 경로 오버라이드 |
| `NUFI_OUTPUT_GUARD` | 출력측 가드레일 활성화 |
| `NUFI_FAIL_CLOSED` | 오류 시 차단 모드 |
| `EGRESS_NER_BACKEND` | NER 백엔드 선택 (`auto`/`onnx-int8`/`transformers`/`gazetteer`) |
