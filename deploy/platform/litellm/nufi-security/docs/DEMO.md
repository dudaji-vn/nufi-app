# NuFi 데모 카탈로그

이 저장소의 모든 데모를 한 곳에 모았다. 각 데모는 **이름만 보고 무엇을 시연하는지**
알 수 있도록 기능 이름(`demo_<feature>.sh`)을 쓰며, 실행하면 시나리오별 PASS/FAIL 을
자동 집계한다. 별도 표기가 없으면 **root 불필요 · 외부 네트워크 호출 0**(stub 백엔드 +
gazetteer NER + 임시 픽스처)으로 에어갭/CI 에서 결정적으로 재현된다.

## 한 번에 전부 실행

```bash
cd security
python3 -m pip install -r requirements.txt   # PyYAML·fastapi·uvicorn·httpx
./scripts/demo_all.sh                         # 모든 기능 데모를 차례로 실행 → 집계 PASS/FAIL
```

`demo_all.sh` 는 아래 카탈로그의 데모를 순서대로 돌리고 마지막에 PASS/FAIL/SKIP 을
집계한다. 사전조건(모델 측정 산출물·root)이 없는 데모는 **SKIP**(실패 아님)으로
분류한다.

## 카탈로그

| 데모 | 한 줄 목적 | 시나리오 | 실행법 | 매뉴얼 |
|---|---|---|---|---|
| [`demo.sh`](../scripts/demo.sh) | 게이트웨이 e2e — private 라우팅 · 강한 PII/비밀 차단(403) · 약한 PII 가명화 · 감사 로깅 | 6 | `./scripts/demo.sh` | 본 문서 §부록 |
| [`demo_coverage.sh`](../scripts/demo_coverage.sh) | 감사 커버리지 — "내 트래픽 중 몇 %가 게이트웨이를 통과했나" + 우회 알림 | 3 | `./scripts/demo_coverage.sh` | [`CLI.md#coverage`](CLI.md) |
| [`demo_report.sh`](../scripts/demo_report.sh) | 규정준수 리포트 — 해시체인 무결성 게이트 + 점검항목 커버리지 | 7 | `./scripts/demo_report.sh` | [`REPORTING.md`](REPORTING.md) |
| [`demo_compliance_mapping.sh`](../scripts/demo_compliance_mapping.sh) | 컴플라이언스 매핑 — 한국 규제팩(금융 AI 안내서·망분리·개인정보보호법·신용정보법·ISMS-P) 대비 NuFi 통제 커버리지(직접/부분/범위밖) 자동 산출 + 프레임워크별 소계·`--framework` 필터 + 무결성 게이트 0/1 유지 | 7 | `./scripts/demo_compliance_mapping.sh` | [`REPORTING.md`](REPORTING.md) |
| [`demo_policy_ops.sh`](../scripts/demo_policy_ops.sh) | 정책 운영 — 다중 프로파일 · 경로별 바인딩 · 무재기동 롤백 · 변경 감사 | 4 | `./scripts/demo_policy_ops.sh` | [`OPS_POLICY_AT_SCALE.md`](OPS_POLICY_AT_SCALE.md) |
| [`demo_pseudonymize.sh`](../scripts/demo_pseudonymize.sh) | 가명화 품질 벤치마크 — 가역(원복 정확도·스트리밍 경계·충돌율 0·결정성)/비가역(원복불가·구조보존·일관 치환) 지표 + 강한 식별자·비밀 차단 유지 | 2 | `./scripts/demo_pseudonymize.sh` | [`PRESETS.md`](PRESETS.md) |
| [`demo_audit_separation.sh`](../scripts/demo_audit_separation.sh) | 차등 감사 — public/private 분리 저장 + 패킷 레이어 우회 탭 + 비동기 감사봇 | 6 | `./scripts/demo_audit_separation.sh` | [`history/DEMO_v0.0.5.md`](history/DEMO_v0.0.5.md) |
| [`demo_location_union.sh`](../scripts/demo_location_union.sh) | 주소 유니온 — 주소(KR_LOCATION)에 한해 모델 백엔드 ∪ 확장 규칙 유니온으로 재현율 향상(모델이 놓친 어휘밖·구조적 주소를 규칙이 회복), 인명·기타 채널 불변·오탐 0 | 4 | `./scripts/demo_location_union.sh` | [`reports/kr-location-union.json`](reports/kr-location-union.json) |
| [`demo_pii_routing.sh`](../scripts/demo_pii_routing.sh) | PII 기반 하이브리드 라우팅 — PII 포함 → 로컬 모델 강제, PII 없음 → 클라우드 허용, 비용 추적, 프로바이더 장애 fail-closed 폴백 | 4 | `./scripts/demo_pii_routing.sh` | [`PII_ROUTING.md`](PII_ROUTING.md) |
| [`demo_sdk.sh`](../scripts/demo_sdk.sh) | Python SDK — `from nufi import ...` 한 줄로 탐지·가명화·정책 평가 (임포트·버전 동기화·detect·pseudonymize·mask·redact·Guard.inspect) | 4 | `./scripts/demo_sdk.sh` | [`SDK.md`](SDK.md) |
| [`demo_resilience.sh`](../scripts/demo_resilience.sh) | 게이트웨이 강건성 — 지연 추적(latency_ms)·방어 파싱(content=None·비-dict·큰 프롬프트 잘림)·탐지 타임아웃 fail-closed 차단 | 5 | `./scripts/demo_resilience.sh` | 본 문서 |
| [`demo_sdk_helpers.sh`](../scripts/demo_sdk_helpers.sh) | SDK 편의 함수 — `scan_file`(파일 PII 탐지)·`guard_file`(파일 정책 평가)·`batch_detect`(일괄 탐지) | 5 | `./scripts/demo_sdk_helpers.sh` | [`SDK.md`](SDK.md) |
| [`demo_prompt_injection.sh`](../scripts/demo_prompt_injection.sh) | 프롬프트 인젝션 탐지 — 한국어·영어 18종 패턴 탐지, Guard 통합 차단, PII+인젝션 복합 시나리오, is_injection() 편의 메서드 | 6 (31건) | `./scripts/demo_prompt_injection.sh` | [`PROMPT_INJECTION.md`](PROMPT_INJECTION.md) |
| [`demo_bench_injection.sh`](../scripts/demo_bench_injection.sh) | 인젝션 벤치마크 — 골드셋 38건(인젝션 20+무해 18) recall/precision/F1 측정 + 게이트(≥0.90) | 1 | `./scripts/demo_bench_injection.sh` | [`PROMPT_INJECTION.md`](PROMPT_INJECTION.md) |
| [`demo_scan.sh`](../scripts/demo_scan.sh) | 파일/디렉터리 PII 스캔 — 디렉터리 재귀 스캔·--fail-on-pii·--redact --dry-run·--format sarif | 4 | `./scripts/demo_scan.sh` | [`CLI.md#scan`](CLI.md) |
| [`demo_accuracy.sh`](../scripts/demo_accuracy.sh) | 정확도 재현 — KR_PERSON INT8 Wilson CI 하한 ≥ 0.93(v0.4.16: 0.9591) + 온프렘 p95 표 + 단일 명령 벤치마크(`nufi-egress benchmark`: 정확도+가명화 동시 재현) *(측정 산출물 필요)* | 3 | `./scripts/demo_accuracy.sh` | [`HANDS_ON.md#part-j`](HANDS_ON.md) |
| [`demo_bypass_enforcement.sh`](../scripts/demo_bypass_enforcement.sh) | 우회 차단(ENFORCED) — 격리 netns 에서 실제 egress drop *(root/nft 필요)* | 3 | `sudo bash scripts/demo_bypass_enforcement.sh` | [`history/DEMO_v0.0.5.md`](history/DEMO_v0.0.5.md) |
| [`demo_getting_started.sh`](../scripts/demo_getting_started.sh) | Getting Started 워크플로우 — init·PII 스캔·redact·inspect·route·doctor 를 순서대로 시연 | 8 | `./scripts/demo_getting_started.sh` | [`CLI.md`](CLI.md) |
| [`demo_transform.sh`](../scripts/demo_transform.sh) | 텍스트 변환 — mask(PII→asterisk)·redact(PII→타입 태그)·explain(상세 설명) + 인젝션 비간섭·클린 텍스트 무변환 | 5 | `./scripts/demo_transform.sh` | [`CLI.md`](CLI.md) |
| [`demo_cli_showcase.sh`](../scripts/demo_cli_showcase.sh) | CLI 쇼케이스 — playground·summary·pipeline·mask·redact 5가지 커맨드 빠른 검증 | 5 | `./scripts/demo_cli_showcase.sh` | [`CLI.md`](CLI.md) |
| [`demo_all.sh`](../scripts/demo_all.sh) | 전체 데모 러너 — 위 데모를 차례로 실행하고 집계 PASS/FAIL 출력 | — | `./scripts/demo_all.sh` | 본 문서 |

> **`compare` 명령 참고:** `nufi-egress compare before.sarif after.sarif` 로 두 스캔 결과의 new/resolved/unchanged 발견을 비교할 수 있습니다. PR 리뷰에서 변경이 새 PII 를 도입했는지 확인하는 데 유용합니다. 상세 플래그는 [`CLI.md#compare`](CLI.md) 참조.

> `demo_bypass_enforcement.sh` 는 `demo_audit_separation.sh --enforce` 경로가 root/nft 가
> 있을 때 호출하는 하위 데모다. 권한이 없으면 차등 감사 데모가 정직하게 SIMULATED 로
> 폴백하므로, 일반 실행에는 추가 권한이 필요 없다.

## Python SDK 예시 (`examples/`)

셸 데모(`scripts/demo_*.sh`)와 달리, `examples/` 는 **Python 코드 안에서 SDK 를 직접
임포트해 쓰는 방법**을 보여주는 독립 실행 스크립트다. `test_examples_smoke.py` 가 전체를
자동 검증한다(스모크 9종).

| 파일 | 목적 |
|---|---|
| [`library_detect.py`](../examples/library_detect.py) | `detect`·`Detector`·`pseudonymize`·`mask`·`Guard`·`batch_detect` 기본 사용 |
| [`sdk_quickstart.py`](../examples/sdk_quickstart.py) | `NuFi()` 한 줄로 OpenAI 호출을 NuFi 경유로 전환 |
| [`sdk_block_and_audit.py`](../examples/sdk_block_and_audit.py) | 민감정보 요청 차단(403) + 감사 레코드 검증 |
| [`sdk_reversible_roundtrip.py`](../examples/sdk_reversible_roundtrip.py) | 가역 가명화 — 원문→가명→복원 라운드트립 |
| [`sdk_streaming.py`](../examples/sdk_streaming.py) | 스트리밍 응답 경유 |
| [`sdk_file_scan.py`](../examples/sdk_file_scan.py) | `scan_file`·`guard_file`·`batch_detect` 파일 단위 탐지·평가 |
| [`sdk_compliance_report.py`](../examples/sdk_compliance_report.py) | `compliance_report`·`render_report`·`load_catalog` — 한국 규제 5종 통제 커버리지 출력 |
| [`sdk_pii_routing.py`](../examples/sdk_pii_routing.py) | `route` — PII 라우팅 결정 (PII→로컬, 클린→클라우드, to_dict) |
| [`sdk_prompt_injection.py`](../examples/sdk_prompt_injection.py) | `detect_injection`·`Guard(check_injection=True)`·`PromptInjectionDetector.is_injection()` — 프롬프트 인젝션 탐지 |
| [`sdk_security_report.py`](../examples/sdk_security_report.py) | 디렉터리 스캔 → 보안 리포트(Markdown/JSON) 생성 |
| [`sdk_ci_integration.py`](../examples/sdk_ci_integration.py) | CI/pre-commit 통합 — PII·인젝션 검사 + 종료 코드 |
| [`api_client.py`](../examples/api_client.py) | NuFi HTTP API 직접 호출 클라이언트 예시 |

```bash
# 전체 예시 한 번에 검증 (스모크)
EGRESS_NER_BACKEND=gazetteer python3 -m pytest tests/test_examples_smoke.py -v
```

---

## 부록 — 게이트웨이 e2e 상세(`demo.sh`)

하이브리드 LLM 환경에서 **public LLM으로 나가는 요청을 게이트웨이가 가로채 PII/비밀을
인라인 탐지·차단·가명화**하고 **public 전송을 100% 감사 로깅**하는 동작을 시연한다.

수동 단계별 재현:

```bash
cd security
python3 -m pip install -r requirements.txt   # 코어는 stdlib+PyYAML만으로도 동작

python3 tests/run_acceptance.py              # 수용기준 10/10
python3 tests/test_unit.py                   # 단위 8/8
python3 scripts/bench.py --ner gazetteer     # recall/지연
PORT=4000 ./scripts/run_gateway.sh           # 게이트웨이 기동 (OpenAI 호환 /v1/chat/completions)
```

### A. private 기본 라우팅 — 외부 미전송
```
$ curl localhost:4000/v1/chat/completions -d '{"model":"nufi-default","messages":[{"role":"user","content":"내부 회의록 요약해줘"}]}'
→ model: private-llm | content: [private-llm stub response]
→ 감사 로그(외부전송 기록) 건수: 0   ← private 경로는 외부로 안 나가므로 기록 없음
```

### B. public 폴백 + 주민등록번호(강한 PII) → **차단(403)**
```
$ EGRESS_PRIVATE_DOWN=1 curl -w "HTTP %{http_code}" .../v1/chat/completions \
    -d '{"model":"nufi-default","messages":[{"role":"user","content":"김민수님 주민번호 900101-1234568 으로 신청서 작성해줘"}]}'
HTTP 403
{"error":{"type":"egress_blocked","message":"민감정보 탐지로 public LLM 전송이 차단되었습니다.",
          "decision":{"blocked":true,"action_counts":{"pseudonymize":1,"block":1},"finding_count":2},
          "entities":["KR_RRN"]}}
```
→ 인명(김민수)은 가명화 대상, 주민번호(KR_RRN)는 차단 → 요청 전체 public 전송 차단.

### C. public 폴백 + API 키(비밀) → **차단(403)**
```
$ EGRESS_PRIVATE_DOWN=1 curl -w "HTTP %{http_code}" .../v1/chat/completions \
    -d '{...content":"이 키로 배포해줘 sk-ant-api03-AbCdEf...01"}]}'
HTTP 403
{"error":{"type":"egress_blocked","decision":{"action_counts":{"block":1},"finding_count":1},"entities":["SECRET"]}}
```

### D. public 폴백 + 약한 PII(전화/이메일) → 가명화 후 전송(200)
```
$ EGRESS_PRIVATE_DOWN=1 curl -w "HTTP %{http_code}" .../v1/chat/completions \
    -d '{...content":"연락처 정리: 010-1234-5678, hong@dudaji.com 으로 회신"}]}'
HTTP 200   ← 전화/이메일은 pseudonymize(비차단) 정책 → 본문 가명화 후 public 전송
```

### 감사 로그 (`logs/egress_audit.jsonl`) — public 전송 100% 기록
```json
{"ts":"...","model":"claude-3-5-sonnet","is_public":true,"outcome":"forwarded"}
{"ts":"...","model":"claude-3-5-sonnet","is_public":true,"outcome":"blocked"}
```

### 정책 (운영자 갱신 가능 — `config/policy.yaml`)

- 강한 PII(주민번호·외국인등록·여권·면허·카드·계좌)·비밀정보 = **block**
- 약한 PII(사업자번호·전화·이메일·인명) = **pseudonymize**, 지명 = **warn**
- 차단 동작이 하나라도 결정되면 요청 전체를 public 전송 차단

### 요지

1. **민감하면 private, 어쩔 수 없으면 public** — 기본 private 라우팅, 폴백/명시 시에만 public.
2. **public 직전 인라인 감사** — 정규식+체크섬(강한 PII·비밀) + 경량 NER(한국어 인명/지명).
3. **유출 차단** — 강한 PII/비밀은 403 차단, 약한 PII는 가명화 후 전송.
4. **전량 감사 로깅** — public 전송은 결정과 함께 100% 기록.
5. **에어갭/저지연** — 외부 의존 0, p95 < 1ms(gazetteer 백엔드 기준).

---

## 관련 문서

| 문서 | 역할 |
|---|---|
| [`HANDS_ON.md`](HANDS_ON.md) | Part F(게이트웨이 e2e)·G(SDK 직접 임포트)·H(강건성)·I(편의함수)·J(벤치마크) — 실습 정주행 |
| [`examples/README.md`](../examples/README.md) | Python SDK 독립 실행 예시 12종 인덱스 |
| [`CLI.md`](CLI.md) | 데모에서 쓰는 모든 서브커맨드 전체 플래그·종료코드 |
| [`INTEGRATION_GUIDE.md`](INTEGRATION_GUIDE.md) | 데모 확인 후 실서비스 배선으로 넘어가는 통합 진입점 |
| [`REPORTING.md`](REPORTING.md) | `demo_report.sh`·`demo_compliance_mapping.sh` 배경: 컴플라이언스 리포팅 |
| [`PII_ROUTING.md`](PII_ROUTING.md) | `demo_pii_routing.sh` 배경: PII 기반 하이브리드 라우팅 |
