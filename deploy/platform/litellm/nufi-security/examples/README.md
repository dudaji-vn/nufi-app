# examples/ — NuFi Python SDK 실행 예시

게이트웨이 없이 Python 코드에서 **NuFi SDK 를 직접 임포트해 쓰는** 방법을 보여주는
독립 실행 스크립트입니다. 각 파일은 `python3 examples/<파일명>` 으로 바로 실행됩니다.

전체 API 문서: [`docs/SDK.md`](../docs/SDK.md) · 자동 검증: `tests/test_examples_smoke.py`

## 예시 목록

| 파일 | 목적 | 주요 API |
|---|---|---|
| [`library_detect.py`](library_detect.py) | 탐지·가명화·Guard·batch_detect 기본 | `detect`, `Detector`, `pseudonymize`, `mask`, `Guard`, `batch_detect` |
| [`sdk_quickstart.py`](sdk_quickstart.py) | OpenAI 호출을 NuFi 경유로 한 줄 전환 | `NuFi()` |
| [`sdk_block_and_audit.py`](sdk_block_and_audit.py) | 민감정보 차단(403) + 감사 레코드 검증 | `NuFi()`, `NuFiBlocked`, `AuditLogger` |
| [`sdk_reversible_roundtrip.py`](sdk_reversible_roundtrip.py) | 가역 가명화 — 원문→가명→복원 | `NuFi().pseudonymize()`, `restore()` |
| [`sdk_streaming.py`](sdk_streaming.py) | 스트리밍 응답 경유 | `NuFi()` streaming |
| [`sdk_file_scan.py`](sdk_file_scan.py) | 파일 단위 PII 탐지·정책 평가 | `scan_file`, `guard_file`, `batch_detect` |
| [`sdk_pii_routing.py`](sdk_pii_routing.py) | PII 기반 로컬/클라우드 라우팅 결정 | `route`, `RoutingDecision` |
| [`sdk_prompt_injection.py`](sdk_prompt_injection.py) | 프롬프트 인젝션 탐지 + Guard 차단 | `detect_injection`, `Guard(check_injection=True)`, `is_injection` |
| [`sdk_compliance_report.py`](sdk_compliance_report.py) | 한국 규제 5종 통제 커버리지 출력 | `compliance_report`, `render_report`, `load_catalog` |
| [`sdk_security_report.py`](sdk_security_report.py) | 디렉터리 스캔 → 보안 리포트(Markdown/JSON) 생성 | `security_report`, `render_security_markdown`, `render_security_json` |
| [`sdk_ci_integration.py`](sdk_ci_integration.py) | CI/pre-commit 통합 — PII·인젝션 검사 + 종료 코드 | `detect`, `detect_injection`, `scan_file` |
| [`api_client.py`](api_client.py) | NuFi HTTP API 직접 호출 클라이언트 예시 | `httpx` |
| [`ci-github-actions.yml`](ci-github-actions.yml) | GitHub Actions 워크플로 예시 — PR/push 시 PII 스캔 자동화 | (YAML 설정) |

## 실행 방법

```bash
# 개별 실행 (게이트웨이 없이)
EGRESS_NER_BACKEND=gazetteer python3 examples/library_detect.py
EGRESS_NER_BACKEND=gazetteer python3 examples/sdk_file_scan.py
EGRESS_NER_BACKEND=gazetteer python3 examples/sdk_compliance_report.py

# 전체 스모크 검증 (9종 자동 테스트)
EGRESS_NER_BACKEND=gazetteer python3 -m pytest tests/test_examples_smoke.py -v
```

## 백엔드 설정

| 환경변수 | 값 | 설명 |
|---|---|---|
| `EGRESS_NER_BACKEND` | `gazetteer` (기본) | 사전 기반 — 외부 의존 0, 에어갭·CI 적합 |
| `EGRESS_NER_BACKEND` | `onnx-int8` | ONNX INT8 — 프로덕션 정확도 (모델 파일 필요) |

`gazetteer` 백엔드로 실행하면 외부 네트워크·모델 파일 없이 모든 예시가 실행됩니다.
프로덕션 정확도(pii_recall 0.9908, person_recall 0.9799)는 `onnx-int8` 백엔드에서 달성됩니다.

---

## 관련 문서

| 문서 | 역할 |
|---|---|
| [`docs/QUICKSTART.md`](../docs/QUICKSTART.md) | 0에서 첫 스캔까지 2분 — 최단 경로 가이드 |
| [`docs/SDK.md`](../docs/SDK.md) | SDK 전체 API 표면·안정성 계층·CLI↔SDK 동등 매핑 |
| [`docs/HANDS_ON.md`](../docs/HANDS_ON.md) | Part G·I — 예시를 실습 맥락에서 정주행 |
| [`docs/REPORTING.md`](../docs/REPORTING.md) | `sdk_compliance_report.py` 배경: 컴플라이언스 리포팅 API |
| [`docs/DEMO.md`](../docs/DEMO.md) | 셸 데모(`scripts/demo_*.sh`) 카탈로그 — 예시와 달리 서버 경유 시나리오 |
