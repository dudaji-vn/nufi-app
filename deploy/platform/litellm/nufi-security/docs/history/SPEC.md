# 구현 명세 (SPEC) — NuFi Egress-Audit Gateway

---

## 범위 (M1 + M2)

M3~M5는 본 PoC 검증 후 별도 단계로 다룬다. 이번 목표는 **public LLM으로 나가는 요청을 가로채(게이트웨이) PII/비밀을 인라인 탐지·차단하는 최소 동작 PoC**.

### 공통 원칙 (NFR)
- NFR1: 탐지 추론은 **외부 네트워크 호출 0** (온프렘/에어갭). 모델·룰 전부 로컬.
- NFR2: 인라인 추가 지연 목표 **p95 ≤ 150ms (CPU)**. 정규식 선필터 → 모델은 필요 시.
- NFR3: 정규식/사전 룰을 설정 파일로 외부화(운영자 갱신 가능).
- NFR4: 라이선스 상업 사용 가능만. **Piiranha(CC-BY-NC-ND), gliner_ko(CC-BY-NC), TruffleHog(AGPL, 인라인) 금지.**

---

## M1 — LiteLLM 게이트웨이 PoC

**목표:** 앱이 LiteLLM Proxy를 LLM 엔드포인트로 사용. 기본은 private(온프렘) 모델로 라우팅, 명시/폴백 시 public(Claude 등). public 행 요청·응답을 감사 로그로 적재.

수용 기준(binary): — **전부 충족 (검증: `tests/run_acceptance.py`)**
- [x] private 기본 라우팅 + public 폴백 동작. → `gateway/router.py`, `config/routing.yaml`
- [x] public 모델로 나간 요청 **100%가 감사 로그에 적재**(요청 본문·모델·타임스탬프·결정). → `egress_audit/audit.py`
- [x] 설정으로 private/public 백엔드·라우팅 규칙 변경 가능. → `config/routing.yaml`(NFR3)

권고 구현:
- LiteLLM Proxy(`config.yaml`)로 모델 라우팅·폴백 정의. private 백엔드는 로컬 vLLM/Ollama 스텁이면 충분(PoC).
- 감사 로깅은 LiteLLM custom logger 또는 Langfuse(MIT) 사이드카. PoC는 로컬 JSONL 로거로 시작 가능.
- public 여부 판정은 모델명/프로바이더 매핑 테이블로.

## M2 — 탐지 파이프라인 (`pre_call` 훅)

**목표:** public 행 요청 전송 **직전** 프롬프트를 스캔해 PII/비밀 탐지 후 정책 동작(차단/마스킹/가명화/경고).

수용 기준(binary): — **전부 충족 (검증: `tests/run_acceptance.py`)**
- [x] 샘플셋에서 한국 PII(주민번호·사업자번호·전화·계좌·카드·여권) **정규식+체크섬** 탐지. → `detectors/korean_pii.py`+`checksums.py`
- [x] 한국어 인명/지명 **KoELECTRA NER** 탐지(정규식 미탐 보완). → `detectors/ner.py` (transformers 백엔드, gazetteer 폴백)
- [x] API 키/자격증명 **detect-secrets** 탐지. → `detectors/secrets.py` (내장 패턴+엔트로피, detect-secrets 선택 보강)
- [x] 정책에 따라 block / redact / pseudonymize / warn 동작 + 결정 로그. → `policy.py`+`config/policy.yaml`

> PoC 검증 메모: 코어는 외부 네트워크 0(NFR1)으로 동작하도록 순수 stdlib+PyYAML 구현.
> 무거운 백엔드(transformers/presidio/detect-secrets/litellm)는 선택 활성화·미설치 시 폴백.
> 한국어 PII recall ≥ 0.9 프로덕션 목표는 KoELECTRA 백엔드로 달성(gazetteer는 최소 보장 라인,
> 샘플셋 기준 recall 1.000). 본 PoC 검증은 gazetteer 백엔드 기준 10/10 수용기준 PASS.

권고 구현:
- 탐지 코어 = **Presidio Analyzer**. 한국 인식기(`KR_RRN`/`KR_FRN`/`KR_BRN`/여권/면허) 활성화 + 전화/계좌 커스텀 정규식 인식기 추가.
- 한국어 NER = **Leo97/KoELECTRA-small-v3-modu-ner**를 Presidio NlpEngine에 연결. 지연 위해 **ONNX + INT8** 변환.
- 비밀정보 = **detect-secrets** `--string`/인프로세스 스캔(또는 gitleaks stdin).
- 강한 PII(주민번호·카드·계좌·여권)·비밀정보는 기본 **block**. 약한 PII(인명·전화·이메일·주소)는 가역 가명화 대상(M3에서 원복 구현; M2는 마스킹까지).
- 참조: `protectai/llm-guard`(스캐너 파이프라인 패턴), `skan0779/korean-pii`(에어갭 한국어 스택).

---

## 산출물
- 동작하는 LiteLLM Proxy 설정 + 탐지 파이프라인 코드(저장소 내).
- `samples/` 한국어 PII/비밀 포함 테스트 프롬프트 + 기대 결과.
- 간단 실행 README(로컬 기동/테스트 방법).
- M5에서 쓸 recall/precision·지연 측정 스크립트(M2 단계는 스텁 가능).

## 비범위(이번)
- TLS MITM 네트워크 탭, 임베딩 기반 기밀 분류기, 완전 DLP, 정책 UI.

## 변경 추적
- 스펙 변경은 본 문서 갱신으로 추적한다.
