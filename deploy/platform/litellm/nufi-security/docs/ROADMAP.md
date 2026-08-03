# NuFi 로드맵 — 한국어 PII·한국 규제 증빙 특화 경량 엔진

> 상태: **재설정 (2026-06-29)** — 독립 프로젝트로 방향을 재정의했다. 이전 "규제 준수 증빙 게이트웨이" 2축은 본 문서로 대체된다. 근거 배경은 금융분야 인공지능 보안 안내서(2026.6) 분석.
> 본 로드맵의 우선순위·자원 배분은 프로젝트 메인테이너 합의로 확정되었다(한국어 PII·규제 증빙 우선, CLI/SDK 경량, 운영 레이어 제외).

---

## 0. 맥락 — 방향 재설정 요약

NuFi는 **독립적인 경량 프로젝트**로, 한국어 PII 탐지와 한국 규제 증빙이라는 두 IP에 집중한다.

- **무엇이 다른가:** 범용 도구가 오픈소스를 조립해 만드는 것과 달리, NuFi는 **직접 구현한 가벼운 파이썬 코드** 그 자체가 의미이자 차별점이다. 외부 의존을 최소화한 코어는 온프렘·에어갭에서 그대로 돈다.
- **형태:** **프론트엔드 없음. CLI + Python SDK 만으로 제공.**
- **버린다:** 운영(ops) 레이어 — 멀티테넌시/RBAC·SLA 모니터링·대시보드. 엔터프라이즈 운영 부담을 덜고 한국 특화 IP에 집중한다.
- **가지고 간다:** 게이트웨이 코어(이그레스 인터셉트·정책 집행)는 **경량 파이썬 구현**으로 유지한다 — 데모와 end-to-end 검증, 그리고 "직접 구현" 차별점의 근거다.

## 1. 포지셔닝

> **NuFi = 한국어 개인정보·한국 규제(금융 AI 가이드라인·망분리·개인정보보호법·신용정보법)에 특화된, 직접 구현한 경량 파이썬 데이터보호·증빙 엔진. CLI/SDK 로 쓰고, 온프렘·에어갭에서 돈다.**

구매/활용 트리거는 두 가지다 — (1) 영어권 도구가 약한 **한국어 고유식별·개인신용정보**를 높은 정확도로 탐지·가명화, (2) 그 처리 이력을 **한국 규제 언어로 자동 증빙**.

## 2. 우선순위 (Value / Effort)

| 우선순위 | 항목 | 규모 | 핵심 가치 |
|---|---|---|---|
| **P0** ✅ | 한국어 PII/DLP 정확도 엔진 강화 | M | 코어 해자 — 한국 고유식별·개인신용정보 탐지 정확도 (v0.4.16: person_recall 0.9799, CI 하한 0.9591) |
| **P1** | 한국 규제 증빙 팩 | S~M | 한국 규제 자동 증빙 → 도입·점검 대응 |
| **P2** ✅ | Python SDK (경량 임포트 API) | S | CLI 외에 라이브러리로 직접 사용 (v0.4.1 구현 완료) |
| **유지** | 게이트웨이 코어 (경량 파이썬 enforcement) | — | 데모·end-to-end 검증·"직접 구현" 차별점 |
| **차기(옵션)** | LLM 라우팅 레이어 (PII 기반 하이브리드 라우팅) | M | PII 민감 요청 로컬 강제 + 비용-품질 최적화 |
| **차기(옵션)** | 가역적 가명화 QA 파이프라인 (프라이버시 보존 LLM 응답) | M | 가명화 후에도 LLM 응답 품질 유지 — 가역적 가명화 + 민감도 라우팅 (v0.6.0: CLI + v0.6.2: 품질 메트릭 리포트 + latency 벤치마크 + v0.9.0: E2E 종합 리포트) |
| **차기(옵션)** | 한국어 생성형 가드레일 | L | 프롬프트 인젝션·탈옥 한국어 탐지 |

### P0 ✅ — 한국어 PII/DLP 정확도 엔진 (M, 코어) — v0.4.16 완료

한국 고유식별(주민등록번호·외국인등록번호·여권·운전면허·계좌·사업자번호)과 개인신용정보 탐지·차단·가명화의 **정확도를 제품 중심축**으로 끌어올린다.

- **목표 산출물:** 공개 가능한 한국어 PII 평가셋 + 탐지 정확도(정밀도/재현율, Wilson 신뢰구간 하한 관리) + 가명화 품질(가역/비가역) 벤치마크.
- **레버리지:** 기존 한국어 PII 엔진 + INT8 per-channel 재양자화 정확도 자산.
- **차별점:** *"한국어 PII는 NuFi가 가장 정확하다"* 를 측정값으로 증명.

### P1 ✅ — 한국 규제 증빙 팩 (S~M) — v0.4.0 완료

기존 `report compliance` 컴플라이언스 매핑을 **한국 규제 전반으로 확장**한다.

- **목표 산출물:** 금융 AI 가이드라인·망분리 + **개인정보보호법·신용정보법·ISMS-P** 점검항목 → NuFi 통제 매핑·충족 상태·증빙 출처. 변조탐지 해시체인 감사로그가 증빙의 기반.
- **달성 (v1.2 카탈로그, v0.4.0):** 한국 규제 5종 **48개 통제 완성** — fsec-ai·net-sep·PIPA·CIA·ISMS-P. PIPA 10항목(6 direct/2 partial/2 oos) · CIA 7항목(4/1/2) · ISMS-P 11항목(5/2/4). 모든 direct 항목 자동 판정 검증 완료. `nufi-egress report compliance` · `compliance_report()` SDK API 로 출력.
- **종료코드:** 기존 무결성 게이트(0 정상 / 1 변조) 유지. 커버리지는 정보성으로 신규 비-0 없음.

### P2 ✅ — Python SDK (S) — v0.4.1(파사드) + v0.4.6(편의 함수) 완료

CLI(`nufi-egress`)에 더해, 엔진·게이트웨이를 코드에서 직접 임포트해 쓰는 **경량 파이썬 SDK** 표면을 정리한다(탐지·가명화·정책 평가·증빙 리포트를 함수/클래스로 노출). 프론트엔드는 만들지 않는다.

- **v0.4.1:** `from nufi import detect, Guard, pseudonymize` 파사드 패키지(`nufi/`).
- **v0.4.6:** `scan_file`·`guard_file`·`batch_detect` 편의 함수 추가.
- **v0.4.16 패치:** 12종 독립 실행 예시(`examples/`), `Finding.__repr__` 개선, 문서 교차링크.

### 차기(옵션) — LLM 라우팅 레이어 (M)

NuFi의 PII 감지를 라우팅 규칙의 첫 번째 레이어로 활용하여, PII 민감 요청은 로컬 모델로 강제 라우팅하고 나머지는 비용-품질 최적화로 분배하는 **하이브리드 LLM 라우팅**을 도입한다.

- **목표 산출물:** LiteLLM 프록시 + RouteLLM 분류기 + NuFi PII 라우팅 규칙 통합.
- **레버리지:** 기존 PII 감지 엔진(P0 자산)이 라우팅 규칙의 핵심 입력.
- **차별점:** 범용 라우터와 달리, *한국어 PII 감지를 라우팅의 최우선 규칙으로* 사용해 보안과 비용 최적화를 동시에 달성.
- **조사 근거:** [LLM 라우팅 조사 보고서](reports/llm-routing-research.md).

### 차기(옵션) — 가역적 가명화 QA 파이프라인 (M)

외부 LLM(Claude, GPT 등)에 민감 데이터를 보내기 전 **가명화하면서도 응답 품질을 유지**하는 파이프라인을 구축한다. 가명화로 인한 품질 저하는 해결 가능한 문제로, 최근 연구에서 97–99% PII 보호율에 약 1점(10점 만점) 이내 품질 손실만 발생함이 입증되었다.

- **목표 산출물:** (1) **가명화 전후 LLM 응답 품질 비교표** — 원문/단순 마스킹/일관적 가명화 조건별 EM·F1·ROUGE-L·BERTScore·PII 보호율 정량 비교 (SensitiveQA 57k, KorQuAD 70k 등 공신력 있는 공개 데이터셋 사용). (2) NuFi PII 탐지 엔진 기반 가역적 가명화(reversible pseudonymization) 계층 + 민감도 기반 로컬/클라우드 LLM 라우팅 + 응답 역치환 후처리.
- **레버리지:** 기존 PII 탐지 엔진(P0 자산) + 이그레스 감사 파이프라인 + LLM 라우팅 레이어(차기 옵션).
- **핵심 접근:** (1) 가역적 가명화 — 타입 일관적 가명 치환 후 역치환(Presidio/CleanPrompt 참고), (2) PRIV-QA 방식 — 고위험/저위험 PII 차등 난독화 + 응답 복원, (3) 로컬-클라우드 하이브리드 라우팅 — 고민감 질의는 로컬 SLM으로 분기.
- **차별점:** 한국어 PII 탐지 정확도(P0)를 기반으로, 범용 도구 대비 한국어 맥락에서 높은 가명화-복원 정합성 확보.
- **조사 근거:** [하이브리드 LLM 프라이버시-정확도 조사](research/HYBRID_LLM_PRIVACY_ACCURACY.md).

### 유지 — 게이트웨이 코어

이그레스 인터셉트·정책 집행은 경량 파이썬 구현으로 유지한다. 데모·end-to-end 검증과 "오픈소스 조립이 아닌 직접 구현"이라는 차별점의 근거다. 단, 새 운영 기능은 더하지 않는다.

## 3. 버림 (운영 레이어 제거 완료)

다음은 코드베이스에서 **제거 완료**되었다(필요 시 별도 결정으로 부활):

- 멀티테넌시 / RBAC (엔터프라이즈 운영) — `enforcement/access.py`, `--tenant`, `--role`, 종료코드 3 제거
- SLA 리포팅 · 알림 (운영 모니터링) — `report sla`, `--alert`, `--webhook`, `--all-tenants` 제거
- 대시보드 · 프론트엔드 (UI 표면)

운영 부담을 제거하고 CLI/SDK 경량 형태와 한국 특화 IP에 자원을 집중한다.

## 4. 범위 밖 (Won't — 초점 보호)

판단형 적대적 robustness, 데이터·모델 오염, 공급망 SBOM, AI 보안 교육, 제3자 독립 검증, 조직 절차 등은 다루지 않는다(P1 증빙에서 "범위 밖"으로 투명 표기).

## 5. 시퀀싱

```
P0 (한국어 PII 정확도 엔진, M) ──▶ P1 (한국 규제 증빙 팩, S~M) ──▶ P2 (Python SDK, S)
유지: 게이트웨이 코어(경량)
차기 옵션: LLM 라우팅 레이어(M) · 가역적 가명화 QA(M) · 한국어 가드레일(L)
```

P0(코어 정확도)를 먼저 끌어올려 해자를 굳히고, P1로 한국 규제 증빙을 확장, P2로 SDK 사용성을 더한다. 차기 옵션 중 LLM 라우팅은 P0 PII 감지 자산을 레버리지하므로 P0 완료 이후 진행이 자연스럽다.

## 6. 현재 달성 수치 (v0.10.0 기준)

아래 수치는 커밋된 측정 산출물(`docs/reports/`)에서 기계로 추출됩니다.

| 목표 | 목표값 | 달성 | 근거 |
|---|---|---|---|
| 전체 PII 재현율 | ≥ 0.90 | **0.9908** ✅ | `recall-int8.json` |
| 인명(KR_PERSON) 재현율 | ≥ 0.93 CI 하한 | **0.9799** (CI 하한 0.9591) ✅ | `recall-int8.json` |
| 주소(KR_LOCATION) 재현율 | ≥ 0.90 | **1.0000** (CI 하한 0.9417) ✅ | `kr-location-gate.json` |
| 인라인 지연 p95 (512자, CPU) | ≤ 150 ms | **41 ms** ✅ | `load-p95.json` |
| 오탐(benign false-positive) | 낮을수록 ✅ | **0 / 90** ✅ | `recall-int8.json` |
| 12개 클래스 Wilson CI95 하한 ≥ 0.90 | 전부 | **12 / 12** ✅ | `recall-int8.json` |
| 한국 규제 증빙 통제 | 48개 | **48개 완성** (direct 25 / partial 11 / oos 12) ✅ | `compliance_catalog.yaml` |
| SDK 예시 | — | **12종** 독립 실행 가능 ✅ | `examples/README.md` |
| 인젝션 재현율 (recall) | ≥ 0.95 | **1.0000** ✅ | `injection-benchmark.json` |
| 인젝션 정밀도 (precision) | ≥ 0.95 | **1.0000** ✅ | `injection-benchmark.json` |
| 인젝션 F1 | — | **1.0000** ✅ | `injection-benchmark.json` |
| Benign FP rate | ≤ 0.05 | **0.0000** ✅ | `injection-benchmark.json` |
| 테스트 통과 | — | **926 collected** ✅ | `pytest` |
| 데모 PASS | — | **11 / 11** ✅ | `demo_all.sh` |
| 가역 가명화 CLI | — | **v0.6.2** ✅ | `pseudonymize` + `scan --pseudonymize` + self-check + latency benchmark |
| 가역 가명화 latency p95 | ≤ 200 ms (16K자) | **191.7 ms** ✅ | `bench_pseudonymize.py` |
| pre-commit hooks | — | **v0.6.1** ✅ | `nufi-scan`, `nufi-scan-strict`, `nufi-pseudonymize` |
| selftest 체크 | — | **11 / 11** ✅ | `nufi-egress test` |
| guard 통합 CLI | — | **v0.7.1** ✅ | `nufi-egress guard` (scan + enforce + pseudonymize 원스텝) |
| scan 출력 포맷 | — | **4종** ✅ | `--format text\|json\|sarif\|csv` (v0.7.0) |
| scan --watch | — | **v0.7.3** ✅ | 디렉터리 실시간 감시 모드 |
| scan --recursive | — | **v0.7.4** ✅ | 디렉터리 재귀 스캔 + 집계 리포트 |
| scan --diff | — | **v0.7.5** ✅ | git diff 기반 변경분만 스캔 |
| guard --ci | — | **v0.7.5** ✅ | CI 파이프라인 전용 모드 (GitHub Actions annotation) |
| nufi-egress init | — | **v0.7.6** ✅ | 프로젝트 설정 생성기 (nufi.yaml, CI workflow) |
| doctor 체크 | — | **11개** ✅ | 자가진단 체크 6→11개 강화 (v0.7.6) |
| scan --profile | — | **v0.7.7** ✅ | 스캔 프로파일 프리셋 (strict/standard/minimal/financial) |
| scan --summary | — | **v0.7.7** ✅ | 집계 대시보드 (타입별·심각도별 ASCII 바 차트) |
| E2E 가명화 Utility (ROUGE-L) | ≥ 0.90 | **0.9871** ✅ | `pseudonymize-e2e-quality.json` (mock LLM) |
| E2E PII Protection Rate | == 1.00 | **1.0000** ✅ | CMP-353 KR_PERSON 문맥 게이팅 강화 |
| E2E Roundtrip Fidelity | ≥ 0.95 | **0.9655** ✅ | CMP-354 KR_LOCATION 복합 지명 개선 |
| E2E 벤치마크 파이프라인 | — | **v0.8.0** ✅ | `bench_pseudonymize_e2e.py` (mock/claude/openai) |
| 한국어 PII QA 평가셋 | ≥ 250건 | **255건** ✅ | `data/pii_qa_eval.jsonl` (6개 카테고리 + edge case: 복합PII·테이블·코드·장문) |
| E2E 종합 리포트 | — | **v0.9.0** ✅ | [`PSEUDONYMIZE_E2E_REPORT.md`](reports/PSEUDONYMIZE_E2E_REPORT.md) |
| 스트리밍 가명화 | — | **v0.10.0** ✅ | `deanonymize_stream()` + CLI `--stream` (청크 경계 버퍼링) |
| 가명화 REST API | — | **v0.10.0** ✅ | POST /pseudonymize, POST /deanonymize, DELETE /sessions |

## 7. 거버넌스 · 리스크

- **설계·구현 분리:** 설계·명세와 구현 트랙을 분리해, 명세 확정 후 구현을 진행한다.
- **OKR 연결 공백:** 본 로드맵은 아직 회사 목표·핵심결과에 연결되어 있지 않다(goalId=null). 리더십 연결 결정 필요.
- ~~**포지셔닝 정합:**~~ ✅ 완료 — README·문서 전반이 경량·CLI/SDK·한국특화 방향으로 정렬됨.

---

## 관련 문서

| 문서 | 역할 |
|---|---|
| [`RELEASE_NOTES.md`](RELEASE_NOTES.md) | 각 버전·패치에서 무엇이 달라졌나 (P0~P2 완료 이력) |
| [`../CHANGELOG.md`](../CHANGELOG.md) | 기술 변경 전체 이력 |
| [`REPORTING.md`](REPORTING.md) | P1 규제 증빙 팩 구현 결과 — 컴플라이언스 리포팅 |
| [`SDK.md`](SDK.md) | P2 Python SDK 구현 표면 |
| [`PII_ROUTING.md`](PII_ROUTING.md) | 차기 P3 — LLM 라우팅 Phase 1 구현 현황 |
| [`research/SOLUTION_FOCUS_OPTIONS.md`](research/SOLUTION_FOCUS_OPTIONS.md) | 2축 집중 결정의 배경 분석 |
| [`research/HYBRID_LLM_PRIVACY_ACCURACY.md`](research/HYBRID_LLM_PRIVACY_ACCURACY.md) | 차기 — 가역적 가명화 QA 파이프라인 조사 근거 |
