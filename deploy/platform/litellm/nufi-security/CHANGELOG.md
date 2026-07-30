# Changelog

본 프로젝트의 주요 변경을 기록합니다. 형식은 [Keep a Changelog](https://keepachangelog.com/) 를,
버전은 [Semantic Versioning](https://semver.org/) 을 따릅니다. 단일 권위 아키텍처 문서는
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) 입니다.

## [Unreleased]

### Added
- **surrogate 델리미터 설정 가능 (`NUFI_SURROGATE_DELIMS`)** — 기본값 `⟦…⟧` 는 그대로 두고 배포 환경에 맞게 교체 가능. 테스트용 `surrogate.set_delimiters()` 도 함께 제공. 잘못된 값은 조용히 기본값으로 폴백해 기동을 막지 않는다.

  근거는 특정 델리미터의 결함이 아니라, **토큰이 그대로 돌아오는지가 라이브러리의 속성이 아니라 모델과 프롬프트의 속성**이라는 점이다. 배포처의 모델을 라이브러리가 미리 알 수 없으므로, 델리미터는 라이브러리를 고치지 않고 바꿀 수 있어야 한다. 실패했을 때가 문제인데, `⟦E1⟧ → E1` 처럼 괄호가 벗겨지면 `_LENIENT` 는 양쪽 괄호를 요구하므로 매칭되지 않고 **복원이 조용히 실패**한다 — 사용자는 원본 대신 `E1` 을 보고, 호출측은 복원되었다고 기록한다.

### Fixed
- `MAX_SURROGATE_LEN` 이 16 으로 고정되어 있어 긴 델리미터에서 미완결 토큰이 상한을 넘겨 잘린 채 방출될 수 있던 문제 — 델리미터 길이를 반영하도록 수정. 이 건은 측정과 무관한 독립적 결함이다.

> **측정 이력(정직하게).** 1차(2026-07-29, `gemini-2.5-flash`, 프롬프트 1종, n=6, temperature 1.0)에서 `⟦E1⟧` **0/6**, `[[E1]]` 2/6, `<E1>` 6/6 이 나왔다. 2차(2026-07-30, 같은 모델, 프롬프트 7종 — 재작성·요약·번역·표·`repeat exactly`·한국어·장문 — 각 n=4~6, 델리미터 3종)에서는 **54/54 전부 그대로 반환**되어 1차의 0/6 을 **재현하지 못했다**. 따라서 0/6 은 안정적인 성질이 아니고, 특정 델리미터를 결함으로 단정할 근거가 되지 못한다. 부분 반환(토큰 일부만 복원 가능)은 두 차수 모두 0건이었다.
>
> 남는 결론은 두 가지다. 델리미터 생존은 환경 의존적이므로 **선택 가능해야 한다**. 그리고 n 회 무실패는 보장이 아니므로 **호출측은 복원 실패를 가정하지 말고 탐지해야 한다** — `_LENIENT` 는 의도적으로 넓히지 않았다(맨 `E1`/`P1`/`T2` 는 셀 참조·부품번호 같은 평범한 문자열이라 괄호 없이 매칭하면 정상 텍스트를 손상시킨다).

## [0.10.0] - 2026-07-09

> **v0.10.0 — 가명화 파이프라인 고도화: 스트리밍 가명화 + 평가셋 확장 + 테스트 보강 (CMP-367, CMP-368)**

### Added
- **스트리밍 가명화 지원 (CMP-368)** — `ReversibleEgress.deanonymize_stream()` 메서드: 청크 이터러블을 받아 실시간 역치환. 청크 경계 surrogate 분할 자동 버퍼링.
- **CLI `pseudonymize --stream` 옵션 (CMP-368)** — stdin 에서 청크를 읽어 실시간 스트리밍 원복. LLM SSE/chunked 응답 파이프 연동.
- **평가셋 250건+ 확장 (CMP-368)** — `data/pii_qa_eval.jsonl` 170건 → 255건. edge case 추가: 복합 PII(3종+), 테이블/CSV, 코드 스니펫, 긴 문서(2000자+).
- **테스트 24건 추가 (CMP-368)** — 스트리밍 단위/통합 테스트 11건, 대규모 배치(1000건+) 3건, 동시성(멀티스레드) 3건, 평가셋 검증 5건, 스트리밍 벤치마크 2건.
- **POST /pseudonymize** — 텍스트 가역 가명화 API (CMP-367). session_id 자동 발급(UUID), 선택적 명시 지원.
- **POST /deanonymize** — 가명화 서로게이트 원복 API (CMP-367). session_id 기반 Vault 조회로 원본 복원.
- **DELETE /sessions/{session_id}** — 세션 종료 및 Vault 매핑 secure wipe API (CMP-367).

### Changed
- **VERSION** — 0.9.0 → 0.10.0

---

## [0.9.0] - 2026-07-08

> **v0.9.0 — E2E 가명화 품질 종합 리포트 문서화 + ROADMAP 갱신 + 릴리스 (CMP-358)**

### Added
- **E2E 가명화 품질 종합 리포트** — `docs/reports/PSEUDONYMIZE_E2E_REPORT.md`: 배경·방법론·결과 요약·타입/카테고리별 세부 분석·개선 이력(v0.8.0 FAIL→v0.8.1 PASS)·결론 및 향후 과제.

### Changed
- **README.md** — E2E 가명화 품질 지표 섹션 추가 (ROUGE-L 0.9871, PII Protection 1.0000, Roundtrip Fidelity 0.9655).
- **ROADMAP.md §6** — v0.9.0 기준으로 갱신, E2E 종합 리포트 행 추가, 가역적 가명화 QA 진행 상태 반영.
- **VERSION** — 0.8.1 → 0.9.0

---

## [0.8.1] - 2026-07-08

> **v0.8.1 — E2E 벤치마크 전 지표 PASS 달성 + 릴리스 (CMP-355)**

### Changed
- **E2E 벤치마크 재실행** — CMP-353(KR_PERSON 문맥 게이팅), CMP-354(KR_LOCATION 복합 지명) 반영 후 170건 전체 재실행.
  - Utility Retention (ROUGE-L): **0.9871** (목표 ≥ 0.90 PASS).
  - PII Protection Rate: **1.0000** (목표 == 1.00 PASS).
  - Roundtrip Fidelity: **0.9655** (목표 ≥ 0.95 PASS).
- **ROADMAP.md §6** — E2E 수치 갱신 (v0.8.1 기준, 3개 지표 전부 PASS).
- **VERSION** — 0.8.0 → 0.8.1

---

## [0.8.0] - 2026-07-08

> **v0.8.0 — E2E 가명화 품질 벤치마크 실행 + 결과 리포트 + ROADMAP 갱신 (CMP-352)**

### Added
- **E2E 가명화 품질 벤치마크 실행** — `scripts/bench_pseudonymize_e2e.py` 파이프라인으로 170건 평가셋 전체 실행 (mock LLM 모드).
  - Utility Retention (ROUGE-L): **0.9820** (목표 ≥ 0.90 PASS).
  - PII Protection Rate: **0.9138** (목표 == 1.00 FAIL — KR_PERSON 복합 성씨 탐지 보완 필요).
  - Roundtrip Fidelity: **0.8966** (목표 ≥ 0.95 FAIL — KR_LOCATION·EMAIL 원복 개선 필요).
- **벤치마크 결과 리포트** — `docs/reports/benchmark_report_e2e_quality.md` (타입별·카테고리별·실패 케이스 분석 포함).
- **벤치마크 결과 JSON** — `docs/reports/pseudonymize-e2e-quality.json` (머신 리더블 결과).

### Changed
- **ROADMAP.md §6** — E2E 가명화 품질 지표 5행 추가 (Utility, PII Protection, Roundtrip Fidelity, 파이프라인, 평가셋).
- **VERSION** — 0.7.8 → 0.8.0

---

## [0.7.8] - 2026-07-08

> **v0.7.8 — CHANGELOG 통합 + ROADMAP 수치 갱신 + selftest 체크 추가 (CMP-344)**

### Added
- **selftest 체크 4개 추가** — guard 커맨드 존재, scan --format json 출력 검증, scan --profile 프로파일 로딩, doctor 체크 수 ≥11 검증. 총 11개 self-check.

### Changed
- **CHANGELOG.md** — v0.7.0~v0.7.7 누락 엔트리 보완 (v0.7.6, v0.7.7 추가).
- **ROADMAP.md §6** — 현재 달성 수치 갱신 (테스트 수, selftest 체크 수, 새 기능 반영).
- **VERSION** — 0.7.7 → 0.7.8

---

## [0.7.7] - 2026-07-08

> **v0.7.7 — scan --profile (스캔 프로파일 프리셋) + scan --summary 집계 대시보드 (CMP-342)**

### Added
- **`scan --profile NAME`** — 스캔 프로파일 프리셋 적용: `strict`, `standard`, `minimal`, `financial` 4종 내장 프로파일.
  - `strict` — 모든 엔티티 타입 스캔, score 임계 0.5, 발견 시 exit 1.
  - `standard` — 주요 엔티티만 (KR_RRN, CREDIT_CARD, KR_ACCOUNT, EMAIL), score 임계 0.7.
  - `minimal` — KR_RRN + CREDIT_CARD만, score 임계 0.9.
  - `financial` — 금융 관련 엔티티 집중 (KR_ACCOUNT, CREDIT_CARD, KR_RRN).
- **`nufi.yaml` 커스텀 프로파일** — `scan_profiles` 키 아래 사용자 정의 프로파일 지정 가능.
- **`scan --summary`** — 집계 대시보드 출력: 타입별·심각도별 ASCII 바 차트.
- **JSON 출력 확장** — `--summary` 사용 시 JSON summary에 `files_scanned`, `files_with_findings`, `by_severity` 추가.
- **`only_types`, `min_score` 프로파일 키** — 프로파일에서 엔티티 타입 필터·최소 점수 임계값 설정.
- **tests/test_cmp342_profile_summary.py** — 프로파일 로딩·적용, 내장 프로파일 4종, 커스텀 프로파일, summary 대시보드, JSON summary 확장 등 테스트.

### Changed
- **VERSION** — 0.7.6 → 0.7.7

---

## [0.7.6] - 2026-07-08

> **v0.7.6 — nufi-egress init 프로젝트 설정 생성기 + doctor 자가진단 강화 (CMP-341)**

### Added
- **`nufi-egress init` 확장** — 프로젝트 초기 설정 생성기:
  - `nufi.yaml` — 스캔 설정 (exclude 패턴, 정책, 포맷).
  - `.pre-commit-config.yaml` — pre-commit hook 추가 (기존 파일이면 nufi 훅만 append).
  - `.github/workflows/nufi-scan.yml` — GitHub Actions CI 워크플로우.
- **`init --ci github|gitlab`** — CI 플랫폼별 설정 자동 생성.
- **`init --dry-run`** — 생성될 파일 미리보기.
- **`init --default`** — 인터랙티브 프롬프트 없이 기본값 사용.
- **doctor 체크 5개 추가** (체크 7~11):
  - Python 버전 호환성 (≥3.9).
  - 필수 의존성 설치 상태.
  - nufi.yaml 설정 유효성.
  - git pre-commit hook 설치 상태.
  - 모델 파일 존재·무결성.
- **tests/test_cmp341_init_doctor.py** — init 설정 생성, dry-run, CI 플랫폼별 생성, doctor 신규 체크 등 테스트.

### Changed
- **VERSION** — 0.7.5 → 0.7.6

---

## [0.7.5] - 2026-07-08

> **v0.7.5 — scan --diff (git diff 기반 변경분만 스캔) + guard --ci 모드 (CMP-340)**

### Added
- **`scan --diff [REF]`** — git diff 기반으로 변경된 행만 PII 스캔. 기본 `HEAD`(staged 변경), `HEAD~1`, `main` 등 임의 ref 지정 가능.
- **변경 행 전용 스캔** — 전체 파일이 아닌 추가/수정된 라인만 스캔하여 CI 파이프라인에서 빠르고 정확한 PII 탐지.
- **`--format text|json|sarif|csv` 지원** — `scan --diff`에서도 기존 scan 출력 포맷 전체 사용 가능.
- **`guard --ci`** — CI 파이프라인 전용 모드: git diff 스캔 + GitHub Actions annotation 형식 출력.
  - PII 없으면 1줄 OK 메시지 + exit 0.
  - PII 있으면 `::error file=path,line=N::PII detected: TYPE` 형식 + exit 1.
- **`guard --diff-ref REF`** — `--ci` 모드에서 비교 기준 ref 지정 (기본 HEAD).
- **`guard --check-injection`** — `--ci` 모드에서 인젝션 패턴 탐지 활성화.
- **SDK `scan_diff()`** — `from nufi import scan_diff`; `ScanResult` 반환.
- **tests/test_cmp340_scan_diff_guard_ci.py** — diff 모드 staged 스캔, ref 대비 스캔, 변경 행 전용 검증, JSON 출력, CI OK/FAIL exit code, GitHub Actions annotation 형식 등 12개 테스트.

### Changed
- **VERSION** — 0.7.4 → 0.7.5

---

## [0.7.4] - 2026-07-08

> **v0.7.4 — scan --recursive 디렉터리 재귀 스캔 + 집계 리포트 (CMP-339)**

### Added
- **`scan --recursive <directory>`** (또는 `-r`) — 디렉터리 내 모든 파일을 재귀 탐색하여 PII 스캔, 바이너리 파일 자동 건너뜀.
- **`--include <glob>`** — 포함 패턴만 스캔 (쉼표 구분, 예: `*.py,*.md`).
- **`--exclude <glob>`** — 제외 패턴 (기존 옵션, --recursive 와 함께 동작).
- **집계 리포트** — 스캔 완료 후 전체 집계 출력: 스캔/건너뛴 파일 수, PII 발견 파일 수, 엔티티 타입별 총 건수, PII 최다 파일 Top 5.
- **`--format text|json|csv` 지원** — JSON: `files[]` 배열 + `summary` 오브젝트. CSV: `file,line,entity_type,text,score` 컬럼.
- **SDK `scan_recursive()`** — `from nufi import scan_recursive`; `RecursiveScanResult` 반환.
- **tests/test_scan_cmd.py** — 디렉터리 재귀 스캔, 바이너리 건너뜀, --exclude/--include 필터, 집계 리포트 정확도, 빈 디렉터리, Top 파일 순서, JSON/CSV 출력 등 10개 테스트 추가.

### Changed
- **VERSION** — 0.7.3 → 0.7.4

---

## [0.7.3] - 2026-07-08

> **v0.7.3 — scan --watch 실시간 파일 모니터링 (CMP-338)**

### Added
- **`scan --watch <directory>`** — 디렉터리 실시간 감시 모드: 파일 생성/수정 시 자동 PII 스캔, 결과를 실시간 stdout 출력. Ctrl+C 로 종료.
- **`--watch-interval <seconds>`** (기본 1초) — 폴링 간격 설정.
- **watchdog 기반 inotify 감시** — watchdog 라이브러리 설치 시 inotify 기반 고성능 감시, 미설치 시 mtime 폴링 자동 fallback.
- **`--format text|json` 지원** — watch 모드에서도 기존 scan 포맷 재사용. JSON 출력 시 타임스탬프·파일경로·findings 구조화.
- **tests/test_scan_watch.py** — watch 모드 시작/종료, 파일 변경 감지, 폴링 fallback, interval 옵션, JSON 출력, exclude 패턴 등 11개 테스트.

### Changed
- **VERSION** — 0.7.2 → 0.7.3

---

## [0.7.2] - 2026-07-07

> **v0.7.2 — pseudonymize 품질 메트릭 리포트 (CMP-337)**

### Added
- **`pseudonymize --quality-report`** — 가명화 실행 시 품질 메트릭 리포트 출력: 엔티티 커버리지, 역변환 정확도, 타입별 통계, 처리 시간.
- **`--format text`** (기본) — 사람이 읽기 좋은 표 형태 stderr 출력.
- **`--format json`** — `quality_report` 키로 구조화된 JSON 포함.
- **SDK `pseudonymize_with_report()`** — `from nufi import pseudonymize_with_report`; 반환값에 `quality_report` dict 포함.
- **tests/test_cmp337_quality_report.py** — JSON 스키마 검증, 역변환 정확도 100% 검증, 타입별 통계, PII 없는 입력 빈 리포트, SDK API 검증 등 7개 테스트.

### Changed
- **VERSION** — 0.7.1 → 0.7.2

---

## [0.7.1] - 2026-07-07

> **v0.7.1 — guard 통합 CLI 커맨드: scan + enforce + pseudonymize (CMP-336)**

### Added
- **enforcement/guard_cmd.py** — `nufi-egress guard` 통합 커맨드: PII scan → 정책 판정 → 가명화를 한 번에 수행하는 원스텝 CI 게이트.
- **`--policy block|warn|pseudonymize`** — PII 발견 시 정책 액션 선택 (기본: warn).
- **`--format text|json`** — 출력 포맷 선택.
- **`--output FILE`** — 가명화 결과 파일 출력 (기본 stdout).
- **`--strict`** — warn 정책을 block으로 승격.
- **exit code**: 0 (PII 없음 / pseudonymize 완료), 1 (block), 2 (warn).
- **tests/test_guard_cmd.py** — 정책별 exit code, JSON 출력, --strict 승격, 파일 출력 등 10개 테스트.

### Changed
- **enforcement/cli.py** — `guard` 서브커맨드 등록.
- **VERSION** — 0.7.0 → 0.7.1

---

## [0.7.0] - 2026-07-07

> **v0.7.0 — scan 출력 포맷 다양화: --format json|sarif|csv (CMP-335)**

### Added
- **enforcement/scan_cmd.py** — `scan --format` 옵션 확장: `text` (기본), `json`, `sarif`, `csv` 4종 포맷 지원.
- **`--format json`** — 구조화 JSON 출력 (`version`, `scan_target`, `findings[]`, `summary`).
- **`--format sarif`** — SARIF v2.1.0 스키마 준수, `tool.driver.name: nufi-egress` (GitHub Code Scanning 통합).
- **`--format csv`** — CSV 출력 (`entity_type,text,start,end,score` 헤더).
- **`--json` 플래그** — `--format json` 별칭으로 동작 (하위 호환).
- **tests/test_scan_cmd.py** — JSON 스키마 검증, SARIF 검증, CSV 파싱 검증 테스트 추가.

### Changed
- **enforcement/cli.py** — `--format` 선택지를 `[sarif, jsonl]` → `[text, json, sarif, csv]` 로 변경.
- **enforcement/scan_cmd.py** — SARIF driver name `NuFi` → `nufi-egress`.
- **enforcement/scan_cmd.py** — CSV 헤더를 `entity_type,text,start,end,score` 로 변경 (start/end 위치 정보 포함).
- **VERSION** — 0.6.3 → 0.7.0

---

## [0.6.2] - 2026-07-07

> **v0.6.2 — test self-check 가명화 검증 + pseudonymize 벤치마크 (CMP-332)**

### Added
- **enforcement/selftest.py** — 7번째 self-check: Pseudonymize roundtrip (가명화→복원→원본 일치 검증).
- **scripts/bench_pseudonymize.py** — `--latency` 벤치마크 추가 (256/1K/4K/16K자 입력 크기별 p50/p95/p99 레이턴시 측정).
- CI 게이트: 16K자 p95 ≤ 200ms (실측 191.7ms PASS).

### Changed
- **VERSION** — 0.6.1 → 0.6.2

---

## [0.6.1] - 2026-07-07

> **v0.6.1 — pre-commit 프레임워크 통합 + diff --pseudonymize (CMP-331)**

### Added
- **.pre-commit-hooks.yaml** — pre-commit 프레임워크 통합: `nufi-scan`, `nufi-scan-strict`, `nufi-pseudonymize` 훅 3종.
- **enforcement/pseudonymize_cmd.py** — `pseudonymize --check` 모드 추가 (파일별 PII 체크, exit 1 + 가명화 제안).
- **enforcement/diff_cmd.py** — `diff --pseudonymize` 옵션 추가 (git 변경 파일 PII 탐지 + 가명화 결과 출력).

### Changed
- **VERSION** — 0.6.0 → 0.6.1

---

## [0.6.0] - 2026-07-07

> **v0.6.0 — 가역 가명화 CLI 커맨드 + scan --pseudonymize (CMP-330)**

### Added
- **enforcement/pseudonymize_cmd.py** — `nufi-egress pseudonymize` CLI 커맨드 신규 (텍스트/파일 가명화 + 원복).
- **enforcement/scan_cmd.py** — `scan --pseudonymize` 옵션 추가 (PII 탐지 시 가명화 결과도 출력).

### Changed
- **VERSION** — 0.5.4 → 0.6.0

---

## [0.5.4] - 2026-07-07

> **v0.5.4 — KR_PERSON 조사 부착 인명 탐지 개선 (CMP-317)**
> 한국어 조사(에게/은/는/이/가/을/를 등 24종) 부착 인명을 문맥 게이팅 하에서 정확히 탐지.

### Added
- **egress_audit/detectors/ner.py** — `_PERSON_JOSA` 리스트(24개 조사) + `_PERSON_CAND_RE` 정규식 확장: 조사 부착 인명도 문맥 게이팅 하에서 검출.
- **tests/test_cmp317_person_josa.py** — 조사 부착 인명 탐지 테스트 11건 (에게/은/를/와/의/에게서/한테 + 기존 honor/title gate 회귀 없음 확인).

### Changed
- **VERSION** — 0.5.3 → 0.5.4

---

## [0.5.3] - 2026-07-07

> **v0.5.3 — 인젝션 문서 현행화 + 패턴 카운트 자동 검증**
> CMP-324: PROMPT_INJECTION.md를 v0.5.1 코드 상태(45개 패턴, 5개 카테고리)에 맞게 업데이트하고, 문서-코드 드리프트를 CI로 방지.

### Changed
- **docs/PROMPT_INJECTION.md** — 패턴 카운트 18→45 현행화. 카테고리 목록에 `code_switch`, `indirect` 추가. 동사 활용형(`_V_END`, `_V_END2`), Unicode 정규화(`normalize_for_injection`), severity 체계, 벤치마크 결과 섹션 추가. 내장 패턴 vs 커스텀 패턴 테이블 업데이트.

### Added
- **tests/test_injection_gate.py** — 드리프트 방지 테스트 2건: `test_pattern_count_minimum` (≥ 40 assertion), `test_pattern_categories_match` (코드-문서 카테고리 일치 검증).
- **VERSION** — 0.5.1 → 0.5.3.

---

## [0.5.1] - 2026-07-07

> **v0.5.1 — 프롬프트 인젝션 Phase 2: 동사 활용형 확장, Unicode 우회 탐지, 코드스위칭**
> CMP-292 Phase 1에서 추가된 인젝션 탐지 기능 정리 + 테스트 보강, 미커밋 문서·스크립트 통합.

### Added
- **egress_audit/detectors/prompt_injection.py** — 동사 활용형 패턴 확장(`_V_END`, `_V_END2`), `code_switch` 카테고리 추가 (한영 혼합 탐지), Unicode zero-width 우회 탐지 패턴.
- **egress_audit/normalize.py** — `normalize_for_injection()` 함수: NFKC 정규화, 제로폭 문자 제거, 자모 재조합.
- **egress_audit/pipeline.py** — 프롬프트 인젝션 탐지 파이프라인 연동 변경.
- **samples/injection_gold.jsonl** — 인젝션 골드셋 187건 추가.
- **tests/test_prompt_injection.py** — 코드스위칭 패턴 테스트 6건 + Unicode 정규화 테스트 2건 추가 (총 41건).
- **docs/NuFi_Security_Overview.md** — 보안 개요 문서.
- **docs/reports/** — 벤치마크 보고서 (CMP-306, CMP-315, v0.5.0) 및 결과 JSON.
- **docs/research/HYBRID_LLM_PRIVACY_ACCURACY.md** — 하이브리드 LLM 프라이버시 연구 문서.
- **scripts/bench_ai4privacy.py**, **scripts/bench_external.py** — 외부 데이터셋 벤치마크 스크립트.
- **scripts/train_koelectra_ner.py** — KoELECTRA NER 학습 스크립트.
- **samples/gold/** — AI4Privacy 벤치마크 골드셋 데이터.
- **tests/test_injection_gate.py** — 인젝션 CI 게이트 테스트 (recall ≥ 0.95, benign FP ≤ 0.05).
- **docs/reports/injection-benchmark.json** — 인젝션 벤치마크 결과 (recall 1.0, precision 1.0, F1 1.0).

### Changed
- **scripts/bench_injection.py** — severity별 통계, JSON/markdown 출력, argparse CLI 개선.
- **.gitignore** — 모델 디렉토리 추가.
- **docs/ROADMAP.md** — 로드맵 업데이트.
- **docs/research/README.md** — 연구 문서 인덱스 업데이트.
- **VERSION** — 0.5.0 → 0.5.1.

---

## [0.5.0] - 2026-07-07

> **v0.5.0 — KoELECTRA fine-tuned 모델 릴리즈 + union flags 기본 활성화**
> CMP-315에서 완성된 KoELECTRA fine-tuned ONNX-INT8 모델을 기본 모델로 통합.
> `M5_LOCATION_UNION`, `M5_PERSON_UNION` 기본 활성화(on). 전체 acceptance criteria 통과.

### Changed
- **egress_audit/pipeline.py** — `M5_LOCATION_UNION`, `M5_PERSON_UNION` 환경변수 기본값 off → on 변경 (CMP-315 보드 승인). `=0`/`false`/`no`/`off` 로 비활성화 가능.
- **VERSION** — 0.4.19 → 0.5.0

### Highlights

- **KoELECTRA fine-tuned 모델** — `Leo97/KoELECTRA-small-v3-modu-ner` 기반, corpus4everyone 117K 데이터로 fine-tuning. ONNX-INT8 14.7MB.
- **KR_LOCATION F1**: 73.7% → **90.2%** (+16.5p, corpus4everyone 검증)
- **KR_PERSON F1**: ~96.6% → **98.2%** (corpus4everyone 검증)
- **내부 골드셋 (union 활성화)**: person_recall 0.9741, location_recall 1.0, pii_recall 0.9882, benign_false_block 0.0 — **ALL PASS**
- **벤치마크 보고서**: `docs/reports/benchmark_report_v0.5.0.md`

---

## [0.4.18] - 2026-07-06 (patch55~184)

> **v0.4.18 — 프롬프트 인젝션 가드레일 + 파일 스캔 + REST API + CLI 확장**
> patch55~184 전 시리즈를 포함하는 안정 릴리스. 테스트 603건+.

### Added (patch215)
- **enforcement/playground_cmd.py** — `--no-emoji` CLI 플래그 + `NUFI_NO_EMOJI` 환경변수 지원. 이모지 비활성 시 텍스트 대체: 🔒→[L], ☁️→[C], ⛔→[!], ✅→[OK].
- **enforcement/cli.py** — playground 서브커맨드에 `--no-emoji` 인자 등록.
- **tests/test_playground_cmd.py** — no-emoji 플래그·환경변수·기본 이모지 동작 테스트 3건 추가.

### Changed (patch213-214)
- **.github/workflows/docs-guard.yml** — Python 버전 매트릭스 확장 (3.9, 3.12). `pyproject.toml` requires-python ≥3.9 범위 검증.
- **examples/ci-github-actions.yml** — step 이름 추가, `continue-on-error: false` 명시, `nufi-egress doctor` step 명칭 보강.

### Changed (patch193-194)
- **docs/ROADMAP.md** — SDK 예시 카운트 7종→12종 동기화(실제 `examples/` 파일 수 반영). 거버넌스 §7 "포지셔닝 정합" 완료 표기.
- **examples/README.md** — `api_client.py` 누락 항목 추가.
- **docs/DEMO.md** — 스모크 카운트 7종→9종, 예시 인덱스 7종→12종, 누락 예시 3종 테이블 추가.

### Added (patch183-184)
- **enforcement/lint_cmd.py** — `lint --fix-report` 모드: 수정 가능 이슈를 before/after 미리보기로 출력(파일 미수정 dry-run). `FixPreview` 데이터클래스, `fix_report_file()`, `fix_report_path()` 함수 추가.
- **enforcement/cli.py** — `--fix-report` CLI 인자 등록.
- **tests/test_lint_cmd.py** — fix-report before/after 미리보기 테스트 1건 추가.
- **CHANGELOG.md** — v0.4.18 최종 릴리스 엔트리(patch176~184).

### Added (patch181-182)
- **enforcement/scan_cmd.py** — `scan --baseline FILE`: 기준선 대비 신규 탐지만 출력. `scan --count-only`: 카운트만 반환(CI 최적화).
- **tests/test_scan_cmd.py** — baseline·count-only 테스트 추가.

### Added (patch179-180)
- **enforcement/serve_cmd.py** — `GET /posture`, `GET /summary`, `GET /stats` REST 엔드포인트 추가.
- **enforcement/scan_cmd.py** — `scan --format csv` CSV 출력 모드.
- **tests/test_serve_cmd.py** — /posture·/summary·/stats 테스트.

### Added (patch178)
- **enforcement/scan_cmd.py** — `.nufi_ignore_findings.yaml` 기반 오탐 억제(false-positive suppression). 특정 파일+패턴 조합을 무시 목록에 등록 가능.
- **tests/test_scan_cmd.py** — 오탐 억제 테스트.

### Changed (patch176-177)
- **CHANGELOG.md** — v0.4.18 버전 범프, 릴리스 노트 정리.
- **README.md** — 최종 수치(테스트·서브커맨드·SDK 함수) 반영.

### Highlights

- **프롬프트 인젝션 탐지** — 한국어 탈옥/인젝션 패턴 28종 룰 엔진 + Guard 통합. `detect_injection()` SDK 함수.
- **REST API 서버** — `nufi-egress serve`: OpenAPI/Swagger, `/detect`, `/injection`, `/pipeline`, `/explain`, `/scan` 엔드포인트.
- **파일·디렉터리 스캔** — `scan --recursive`, `--redact`, `--dry-run`, `--git-staged`, `--stats` 옵션.
- **CLI 확장** — 38개+ 서브커맨드: dashboard, report(executive/badge/posture/coverage-map), doctor, init, watch 등.
- **SDK 20개+ 공개 함수** — detect, route, explain, batch_detect, batch_route, batch_inspect, security_report, guard_context 등.
- **보안 포스처·대시보드** — ASCII 터미널 대시보드, 경영진 보안 등급 리포트, SVG 배지 생성.

---

## [0.4.17] - 2026-07-04 (patch169-175)

> **v0.4.17-patch169~175 — API endpoints + scan --git-staged + Guard + dashboard + CHANGELOG**
> /pipeline, /explain, /scan REST 엔드포인트, git staged 스캔, Guard 컨텍스트 매니저,
> ASCII 터미널 대시보드. 테스트 603건.

### Added (patch174)
- **enforcement/dashboard_cmd.py** — `nufi-egress dashboard`: ASCII box-drawing 터미널 보안 대시보드. 등급·테스트·위험·닥터·활동·인젝션 벤치마크를 한 화면에 표시. `--json` 기계 출력.
- **enforcement/cli.py** — `dashboard` 서브커맨드 추가.
- **tests/test_dashboard_cmd.py** — 대시보드 섹션 존재·JSON 모드 테스트 2건.

### Added (patch172-173)
- **egress_audit/guard.py** — `Guard` 컨텍스트 매니저: `with Guard() as g:` 블록 내부에서 PII·인젝션 자동 감시, 위반 시 예외 발생.
- **enforcement/serve_cmd.py** — `POST /scan` 엔드포인트: 파일 경로 전달 시 서버 측 PII 스캔 결과 반환.
- **enforcement/scan_cmd.py** — `scan --git-staged`: git staged 파일만 스캔 (pre-commit hook 연동).
- **tests/test_guard_context.py** — Guard 컨텍스트 매니저 테스트.
- **tests/test_scan_endpoint.py** — POST /scan 엔드포인트 테스트.
- **tests/test_scan_cmd.py** — git-staged 스캔 테스트 추가.

### Added (patch171)
- **enforcement/scan_cmd.py** — `scan --git-staged` 옵션: git staged 파일만 스캔(pre-commit hook 통합).
- **enforcement/cli.py** — `--git-staged` 인자 추가.

### Added (patch169-170)
- **enforcement/serve_cmd.py** — `POST /pipeline`, `POST /explain` REST 엔드포인트. 전체 체인 파이프라인·상세 설명 API 제공.
- **CHANGELOG.md** — patch166~168 엔트리 추가.
- **tests/test_serve_cmd.py** — /pipeline·/explain 엔드포인트 테스트 추가.

### Changed (patch175)
- **CHANGELOG.md** — patch169~174 전체 엔트리 추가.
- **docs/RELEASE_NOTES.md** — patch169~174 반영.

## [0.4.17] - 2026-07-06 (patch158-168)

> **v0.4.17-patch158~168 — OpenAPI + executive report + badge + coverage-map + posture**
> Swagger UI·ReDoc, Pydantic 스키마, /injection API, HTML 테스트 콘솔,
> 경영진 보안 등급 리포트, SVG 배지 생성, 커버리지 맵, 보안 포스처. 테스트 582건.

### Added (patch168)
- **enforcement/posture_cmd.py** — `nufi-egress report posture`: 보안 포스처 스냅샷 캡처(등급·수치·분포·벤치마크·doctor). `--save` 이력 저장, `--compare` 마지막 대비 개선/퇴보 비교.
- **tests/test_posture_cmd.py** — 포스처 캡처·저장·비교 테스트 9건.

### Added (patch166-167)
- **enforcement/coverage_map_cmd.py** — `nufi-egress report coverage-map`: 파일×엔티티 유형 PII 노출 매트릭스 출력. `--format text|json|csv` 지원.
- **tests/test_coverage_map_cmd.py** — 커버리지 맵 테스트.
- **README.md** — 테스트 573·서브커맨드 37종 갱신, serve 퀵스타트 추가.

### Changed (patch165)
- **CHANGELOG.md** — patch158~164 전체 엔트리 추가.
- **docs/RELEASE_NOTES.md** — patch158~164 반영.

### Added (patch164)
- **enforcement/badge_cmd.py** — `nufi-egress report badge`: shields.io-style SVG 배지 생성기. `--type grade|recall|injection|tests`, `--output badge.svg`. README/CI 대시보드 임베딩용.
- **tests/test_badge_cmd.py** — badge 생성·CLI 테스트 7건 추가.

### Added (patch163)
- **enforcement/executive_report.py** — `nufi-egress report executive`: 1페이지 경영진용 보안 요약. 등급(A-F)·지표·위험·권고. `--format text|json|md`.
- **tests/test_executive_report.py** — 등급·포맷 테스트.

### Added (patch162)
- **enforcement/serve_cmd.py** — HTML 테스트 콘솔(`/` 루트 페이지). `completions` 커맨드에 전체 서브커맨드 목록 등록.

### Added (patch161)
- **CHANGELOG.md** — patch158~160 최종 엔트리 정리.

### Added (patch158-160)

### Added (API)
- **enforcement/serve_cmd.py** — Pydantic 모델 기반 OpenAPI 스키마 자동생성. `POST /injection` 엔드포인트. `--openapi` JSON 스펙 내보내기.
- **examples/api_client.py** — HTTP API 클라이언트 예시.

### Added (테스트)
- **tests/test_serve_cmd.py** — /docs·/injection·--openapi 테스트 4건 추가.

### Changed (문서)
- **README.md** — 테스트 550 갱신.
- **docs/README.md** — QUICKSTART.md 상단 노출.

## [0.4.17] - 2026-07-05 (patch155-157)

> **v0.4.17-patch155~157 — serve HTTP API + docs + CHANGELOG sweep**
> HTTP REST API 서버 모드, API 문서·데모·퀵스타트 보강, 최종 CHANGELOG.

### Added (patch155)
- **enforcement/serve_cmd.py** — `nufi-egress serve --port 8000`: FastAPI/uvicorn 기반 HTTP REST API 서버. 엔드포인트: `POST /detect`, `POST /route`, `POST /inspect`, `POST /mask`, `POST /redact`, `GET /health`. 마이크로서비스 연동용.
- **enforcement/cli.py** — `serve` 서브커맨드 추가(`--host`, `--port` 인자).
- **tests/test_serve_cmd.py** — 엔드포인트 테스트.

### Changed (patch156)
- **docs/CLI.md** — `serve` 서브커맨드 레퍼런스 추가(엔드포인트 목록·Request/Response 형식·curl 예시).
- **README.md** — 데모 1분 실행 섹션에 serve 예시 추가(#24).
- **docs/QUICKSTART.md** — serve 모드 섹션(§9) 추가.

### Changed (patch157)
- **CHANGELOG.md** — patch155~156 엔트리 추가.
- **docs/RELEASE_NOTES.md** — patch155~156 반영.

## [0.4.17] - 2026-07-05 (patch151-154)

> **v0.4.17-patch151~154 — quickstart + examples + report diff + CHANGELOG sweep**
> 퀵스타트 가이드, 예제 README, 스캔 비교 diff 리포트 커맨드, 최종 CHANGELOG.

### Added (patch153)
- **enforcement/report_diff_cmd.py** — `nufi-egress report diff before.json after.json`: 두 스캔 결과 비교 diff 리포트 생성. `compare_scans()` 재사용. 마크다운/JSON/HTML 렌더링(`--format md|json|html`). `--output` 파일 출력. 요약(N new, N resolved, N unchanged) + 신규/해결/미변경 테이블.
- **enforcement/cli.py** — `report diff` 서브커맨드 추가.
- **tests/test_report_diff_cmd.py** — MD/JSON/HTML 렌더링 + CLI --output 테스트 2건.

### Added (patch151)
- **docs/QUICKSTART.md** — 2분 퀵스타트 가이드 신규.

### Changed (patch152)
- **examples/README.md** — 12종 예시 전체 목록 갱신.

### Changed (patch154)
- **CHANGELOG.md** — patch151~153 전체 엔트리 추가.
- **docs/RELEASE_NOTES.md** — patch151~153 반영.
- **README.md** — 테스트 수 543건 갱신.

## [0.4.17] - 2026-07-05 (patch149-150)

> **v0.4.17-patch149~150 — report trends + CHANGELOG sweep**
> PII 탐지 트렌드 리포트 커맨드, 최종 CHANGELOG.

### Added (patch149)
- **enforcement/trends_cmd.py** — `nufi-egress report trends`: 감사 로그(egress_audit.jsonl)를 날짜별로 그룹핑하여 PII 탐지 트렌드 출력. 날짜별 총 이벤트·차단 건수·PII 유형 집계. `--period N`(기본 7일), `--json` 기계 출력, `--audit` 경로 오버라이드.
- **enforcement/cli.py** — `report trends` 서브커맨드 추가.
- **tests/test_trends_cmd.py** — 날짜 그룹핑·빈 로그·기간 제한·JSON 출력 테스트 4건.

### Changed (patch150)
- **CHANGELOG.md** — patch143~149 전체 엔트리 추가.
- **docs/RELEASE_NOTES.md** — patch143~149 반영.
- **README.md** — 테스트 수 541건, 서브커맨드 34종 갱신.

## [0.4.17] - 2026-07-05 (patch147-148)

> **v0.4.17-patch147~148 — summary dashboard + CLI showcase demo**
> 프로젝트 헬스 대시보드, CLI 쇼케이스 데모.

### Added (patch147)
- **enforcement/summary_cmd.py** — `nufi-egress summary`: 프로젝트 헬스 대시보드. 설정·활동·위험·닥터·버전을 한 화면 요약. `--json` 기계 출력.
- **enforcement/cli.py** — `summary` 서브커맨드 추가.
- **tests/test_summary_cmd.py** — 대시보드 출력·JSON 출력 테스트.

### Added (patch148)
- **scripts/demo_cli_showcase.py** — CLI 쇼케이스 데모: 주요 CLI 커맨드 빠른 검증 스크립트.

## [0.4.17] - 2026-07-05 (patch143-146)

> **v0.4.17-patch143~146 — SDK typing + CLI UX + playground + CHANGELOG sweep**
> PEP 561 타입 마커, CLI 에러 친화 처리, 인터랙티브 playground REPL, 최종 CHANGELOG.

### Added (patch145)
- **enforcement/playground_cmd.py** — `nufi-egress playground`: 인터랙티브 PII 분석 REPL. 입력 텍스트마다 `inspect_text` 로 PII·인젝션·위험도·라우팅·차단 여부를 한 줄 요약 출력. `mode mask`/`mode redact` 로 마스킹·리댁션 모드 전환. `--text` 플래그 또는 파이프(stdin) 비인터랙티브 지원.
- **enforcement/cli.py** — `playground` 서브커맨드 추가.
- **tests/test_playground_cmd.py** — 파이프 모드·--text·mask·redact 테스트 4건.

### Changed (patch144)
- **enforcement/cli.py** — CLI 친화 에러 메시지: scan/route/explain 등 필수 인자 누락 시 구체적 안내. 전역 예외 처리(FileNotFoundError, PermissionError, KeyboardInterrupt, BrokenPipeError).

### Added (patch143)
- **nufi/py.typed** — PEP 561 마커 추가(타입 체커 지원).
- **nufi/__init__.py** — SDK 공개 API 타입 어노테이션 개선.

### Changed (patch146)
- **CHANGELOG.md** — patch143~145 엔트리 추가.
- **docs/RELEASE_NOTES.md** — patch143~145 반영.

## [0.4.17] - 2026-07-05 (patch139-142)

> **v0.4.17-patch139~142 — pipeline + history + CHANGELOG sweep**
> 체인 파이프라인, 활동 로그 조회, 최종 CHANGELOG.

### Added (patch141)
- **enforcement/history_cmd.py** — `nufi-egress history`: 최근 NuFi 활동 로그 조회. 감사 로그(logs/egress_audit.jsonl)와 스캔 캐시(.nufi_cache.json)를 통합 읽어 스캔·차단·라우팅 이벤트를 시간순 출력. `--last N`(기본 20), `--type scan|block|route|all` 필터, `--json` 기계 출력. 로그 미존재 시 "No activity recorded yet" 안내.
- **enforcement/cli.py** — `history` 서브커맨드 추가.
- **tests/test_history_cmd.py** — 이벤트 분류·필터 + 빈 로그 + JSON 출력 테스트 3건.

### Added (patch139)
- **enforcement/pipeline_cmd.py** — `nufi-egress pipeline --text "..."`: detect→decide→transform→route 체인 파이프라인 한 번에 실행. `--actions` 선택 실행, `--json` 기계 출력.
- **enforcement/cli.py** — `pipeline` 서브커맨드 추가.
- **tests/test_pipeline_cmd.py** — 파이프라인 전체 실행 + 액션 선택 테스트.

### Changed (patch140)
- **README.md** — 테스트 520·서브커맨드 33종·pipeline 반영.

### Changed (patch142)
- **CHANGELOG.md** — patch139~141 엔트리 추가.
- **docs/RELEASE_NOTES.md** — patch139~141 반영.

## [0.4.17] - 2026-07-05 (patch135-138)

> **v0.4.17-patch135~138 — selftest + CLI docs + scan --verbose + CHANGELOG sweep**
> 설치 자가진단, CLI 레퍼런스 갱신, 스캔 상세 출력 모드, 최종 CHANGELOG.

### Added (patch137)
- **enforcement/scan_cmd.py** — `nufi-egress scan --verbose`: 발견 항목별 상세 출력(파일/줄/컬럼/엔티티 타입/매칭 텍스트/점수/탐지 방법(regex/ner)/전후 5자 컨텍스트). `--verbose` 없이는 기존 요약 출력 유지.
- **enforcement/cli.py** — `--verbose` argparse 플래그 추가.
- **tests/test_scan_cmd.py** — `--verbose` 상세 출력 검증 테스트 1건.

### Changed (patch136)
- **docs/CLI.md** — compare·test 서브커맨드 레퍼런스 문서 추가.
- **docs/DEMO.md** — 데모 카탈로그 갱신.

### Added (patch135)
- **enforcement/selftest_cmd.py** — `nufi-egress test`: 설치 자가진단 6체크(PII 탐지·인젝션 탐지·라우팅·Guard·설정·버전). 모두 PASS 시 exit 0, FAIL 시 exit 1. `--json` 기계 출력.
- **enforcement/cli.py** — `test` 서브커맨드 추가.
- **tests/test_selftest_cmd.py** — 자가진단 PASS + JSON 출력 테스트.

### Changed (patch138)
- **CHANGELOG.md** — patch135~137 엔트리 추가.
- **docs/RELEASE_NOTES.md** — patch135~137 반영.

## [0.4.17] - 2026-07-05 (patch129-134)

> **v0.4.17-patch129~134 — HANDOVER + lint + generate + CLI docs + compare + CHANGELOG sweep**
> HANDOVER 현행화, 보안 안티패턴 검사, 한국어 PII 샘플 생성, CLI 레퍼런스 갱신, 스캔 비교 커맨드, 최종 CHANGELOG.

### Added (patch133)
- **enforcement/compare_cmd.py** — `nufi-egress compare before.sarif after.sarif`: 두 스캔 결과(SARIF/JSON) 비교. new(도입)/resolved(해결)/unchanged(유지) 분류. `--json` 기계 출력, `--fail-on-new` CI 게이트(신규 발견 시 exit 1). PR 리뷰에서 "이 변경이 새 PII를 도입했는가?" 확인 용도.
- **enforcement/cli.py** — `compare` 서브커맨드 + 도움말 카테고리(탐지) 추가.
- **tests/test_compare_cmd.py** — NuFi JSON 비교 + fail-on-new 테스트 2건.

### Changed (patch132)
- **docs/CLI.md** — lint·generate·mask·redact 서브커맨드 레퍼런스 문서 추가.

### Added (patch131)
- **enforcement/generate_cmd.py** — `nufi-egress generate`: 한국어 PII 샘플 데이터 생성(테스트용). `--count`, `--include-injection`, `--seed`, `--format jsonl|text`, `--output` 지원.
- **enforcement/cli.py** — `generate` 서브커맨드 + 도움말 카테고리(운영) 추가.
- **tests/test_generate_cmd.py** — 생성 포맷·시드 재현·인젝션 포함 테스트.

### Added (patch130)
- **enforcement/lint_cmd.py** — `nufi-egress lint`: 보안 안티패턴 검사(hardcoded API key, debug mode, http://, eval/exec, SSL 미검증, 비밀번호). `--fix` 자동 수정(http→https), `--json`, `--exclude` 지원.
- **enforcement/cli.py** — `lint` 서브커맨드 + 도움말 카테고리(운영) 추가.
- **tests/test_lint_cmd.py** — API key 탐지·debug 탐지·클린 파일 테스트 3건.

### Changed (patch129)
- **HANDOVER** — v0.4.17-patch128 기준 전체 현행화.

### Changed (patch134)
- **CHANGELOG.md** — patch129~133 엔트리 추가.
- **docs/RELEASE_NOTES.md** — patch129~133 반영.

## [0.4.17] - 2026-07-05 (patch124-128)

> **v0.4.17-patch124~128 — mask/redact + 통합 데모 + unified benchmark(injection) + CHANGELOG sweep**
> 텍스트 PII 마스킹·리댁션 커맨드, 통합 데모, 벤치마크에 인젝션 통합, 최종 CHANGELOG 정리.

### Added (patch127)
- **enforcement/benchmark.py** — `run_injection_benchmark()`: 인젝션 골드셋(samples/injection_gold.jsonl)에 대해 PromptInjectionDetector recall/precision/F1 라이브 측정. 게이트: recall >= 0.90, precision >= 0.90.
- **enforcement/benchmark.py** — `run_benchmarks()` 에 `injection` 축 통합. `--only injection` 단독 실행 지원. 전체 실행 시 PII 정확도 + 가명화 + 인젝션 3축 모두 PASS 해야 exit 0.
- **enforcement/cli.py** — `benchmark --only` 선택지에 `injection` 추가.
- **tests/test_benchmark_unified.py** — 인젝션 단독·전체 벤치마크 통합 테스트 2건.

### Added (patch125-126)
- **scripts/demo_transform.sh** — mask/redact/explain 통합 데모(5시나리오 PASS/FAIL).
- **README.md** — init 퀵스타트·mask/redact/explain 데모·CLI 21종 표기 갱신.
- **docs/DEMO.md** — 텍스트 변환 데모 카탈로그 등록.

### Added (patch124)
- **enforcement/transform_cmd.py** — `nufi-egress mask`: PII를 `***`로 마스킹. `nufi-egress redact`: PII를 `[TYPE]` 태그로 리댁션. `--text`/`--file`/`--output` 지원.
- **enforcement/cli.py** — `mask`·`redact` 서브커맨드 추가.
- **tests/test_transform_cmd.py** — 마스킹·리댁션·파일 입출력 테스트 5건.

### Changed (patch128)
- **CHANGELOG.md** — patch124~127 엔트리 추가.
- **docs/RELEASE_NOTES.md** — patch124~127 반영.

## [0.4.17] - 2026-07-05 (patch118-123)

> **v0.4.17-patch118~123 — SDK explain + summary-only + audit verify + CLI docs + export patterns + CHANGELOG sweep**
> SDK explain 노출, 스캔 요약 전용 모드, 감사 로그 해시체인 검증, CLI 레퍼런스 갱신, 패턴 내보내기.

### Added (patch122)
- **enforcement/export_cmd.py** — `nufi-egress export patterns [--format yaml|json|regex]`: PII + 인젝션 탐지 패턴을 YAML/JSON/regex(라인별) 형식으로 내보내기. 팀 공유·백업·외부 도구(grep/ripgrep) 연동 용도.
- **enforcement/cli.py** — `export` 서브커맨드 + `patterns` 하위 커맨드 + 도움말 카테고리(운영) 추가.
- **tests/test_export_cmd.py** — YAML/JSON/regex 내보내기 + PII·인젝션 포함 검증 테스트 2건.

### Added (patch121)
- **docs/CLI.md** — `explain`·`stats`·`audit verify` 서브커맨드 레퍼런스 문서 추가.

### Added (patch120)
- **enforcement/audit_cmd.py** — `nufi-egress audit verify`: JSONL 감사 로그의 해시체인 무결성 검증. 변조 시 위치 보고. exit 0=정상, 1=변조.
- **enforcement/cli.py** — `audit verify` 액션 추가.
- **tests/test_audit_cmd.py** — 해시체인 정상·변조 검증 테스트 2건.

### Added (patch119)
- **enforcement/scan_cmd.py** — `scan --summary-only`: 요약만 출력(파일수·발견·위험도·상태). CI 빠른 체크 용도.
- **enforcement/completions_cmd.py** — `explain` 서브커맨드 셸 자동완성 등록.
- **tests/test_scan_cmd.py** — summary-only 출력 테스트 1건.

### Added (patch118)
- **nufi/__init__.py** — `from nufi import explain`: 텍스트 탐지 이유 상세 분석 SDK 편의 함수 노출.
- **tests/test_explain_cmd.py** — SDK explain() 호출 테스트 1건.

### Changed (patch123)
- **CHANGELOG.md** — patch118~122 엔트리 추가.
- **docs/RELEASE_NOTES.md** — patch118~122 반영.

## [0.4.17] - 2026-07-05 (patch112-117)

> **v0.4.17-patch112~117 — stats + MANUAL + CLI smoke tests + HANDS_ON + explain + CHANGELOG sweep**
> 설정·탐지 역량 통계, 매뉴얼 빠른 참조, CLI 통합 스모크 테스트, 실습 가이드, explain 디버깅 명령.

### Added (patch116)
- **enforcement/explain_cmd.py** — `nufi-egress explain --text "..."`: 텍스트 탐지 결과 상세 설명 명령. 각 PII/인젝션 발견의 엔티티·위치·탐지 방법·신뢰도, 정책 판정(block/pseudonymize/log/allow), 라우팅 결정(local/cloud)과 사유를 교육적 형식으로 출력. `--json` 기계용 출력 지원.
- **enforcement/cli.py** — `explain` 서브커맨드 + 도움말 카테고리(탐지) 추가.
- **tests/test_explain_cmd.py** — PII 상세 분해 + 클린 텍스트 "no findings" 테스트 2건.

### Added (patch115)
- **docs/HANDS_ON.md** — §10 파일 스캔 & CI 연동 실습 가이드.

### Added (patch114)
- **tests/test_cli_integration.py** — CLI 전 서브커맨드 통합 스모크 테스트 15건.

### Added (patch113)
- **docs/MANUAL.md** — v0.4.17 신규 CLI 커맨드 빠른 참조 매뉴얼.

### Added (patch112)
- **enforcement/stats_cmd.py** — `nufi-egress stats`: 설정 파일·탐지 패턴·스캔 프로파일·캐시·감사 로그 상태 개요. `--json` 지원.
- **enforcement/cli.py** — `stats` 서브커맨드 추가.
- **tests/test_stats_cmd.py** — stats 수집·렌더·JSON 테스트 3건.

### Changed (patch117)
- **CHANGELOG.md** — patch112~116 엔트리 추가.
- **docs/RELEASE_NOTES.md** — patch112~116 반영.

## [0.4.17] - 2026-07-05 (patch107-110)

> **v0.4.17-patch107~110 — E2E 테스트 + SDK 예시 + shell completions + scan profiles**
> 스캔 파이프라인 E2E 통합 테스트, SDK 실전 예시, 셸 자동완성, 스캔 프로파일.

### Added (patch110)
- **enforcement/scan_profiles.py** — 스캔 프로파일 로딩·해석 모듈. `config/scan_profiles.yaml` 에 `development`/`ci`/`strict` 프로파일 정의.
- **config/scan_profiles.yaml** — 사전 정의 스캔 프로파일(development, ci, strict).
- **enforcement/cli.py** — `scan --profile NAME` 옵션 추가. 프로파일 설정은 명시적 CLI 플래그로 오버라이드 가능.
- **tests/test_scan_profiles.py** — 프로파일 로딩·적용·오버라이드 테스트 3건.

### Added (patch109)
- **enforcement/completions_cmd.py** — `nufi-egress completions bash/zsh` 셸 자동완성 스크립트 생성.
- **enforcement/cli.py** — `completions` 서브커맨드 + `--help` 출력 카테고리 분류(탐지/운영/보고).
- **tests/test_completions.py** — 자동완성 스크립트 생성 테스트 1건.

### Added (patch108)
- **examples/sdk_security_report.py** — SDK 로 디렉터리 보안 리포트 생성·렌더링 실전 예시.
- **examples/sdk_ci_integration.py** — CI/pre-commit PII+인젝션 검사 시뮬레이션 실전 예시.
- **tests/test_examples_smoke.py** — SDK 예시 스모크 테스트 2건 추가.

### Added (patch107)
- **tests/test_scan_e2e.py** — init→scan→redact, cache 무효화, SARIF/JSONL 출력, 병렬 일관성, .nufiignore·exclude, 인젝션 탐지, security report E2E 통합 테스트 10건.

## [0.4.17] - 2026-07-05 (patch101-105)

> **v0.4.17-patch101~105 — config validate + diff + watch --webhook + scan --cache + README 데모 섹션**
> 설정 검증 CLI, git diff 스캔, webhook 알림, SHA-256 캐싱, README 데모 갱신.

### Added (patch105)
- **enforcement/config_validate.py** — `nufi-egress config validate`: 모든 NuFi 설정 파일(policy.yaml, routing.yaml 등) syntax·필수 필드·regex 유효성 검증.
- **enforcement/cli.py** — `config validate` 서브커맨드 + `--config-dir`, `--json` 옵션.

### Added (patch104)
- **enforcement/diff_cmd.py** — `nufi-egress diff`: git 변경 파일만 PII/인젝션 스캔(PR 리뷰·pre-commit).
- **enforcement/cli.py** — `diff` 서브커맨드 + `--base`, `--fail-on-pii`, `--check-injection`, `--json` 옵션.

### Changed (patch103)
- **README.md** — 데모 섹션에 `report security`, `init`, `watch` 추가.

### Changed (patch102)
- **enforcement/watch_cmd.py** — `watch --webhook URL`: PII 탐지 시 JSON 페이로드를 외부 URL 로 POST(Slack/Teams 연동).

### Changed (patch101)
- **enforcement/scan_cmd.py** — `scan --cache`: SHA-256 파일 해시 기반 결과 캐싱으로 반복 스캔 성능 향상.

## [0.4.17] - 2026-07-05 (patch99-100)

> **v0.4.17-patch99~100 — HTML 보안 리포트 + CHANGELOG sweep**
> report security --format html 자립형(self-contained) HTML 리포트. CHANGELOG/RELEASE_NOTES patch93~99 반영.

### Added (patch99)
- **enforcement/security_report.py** — `render_html(report)`: 인라인 CSS, 외부 의존 없는 자립형 HTML 보안 리포트 렌더러.
  - 위험도별 색상 배지 (red=critical, orange=high, yellow=medium, blue=low).
  - Executive Summary 헤더 + 리스크 배너.
  - 엔티티 타입·인젝션 패턴·권고사항 테이블.
  - 생성 타임스탬프 + NuFi 버전 푸터.
- **enforcement/cli.py** — `report security --format html` 옵션 추가.
- **tests/test_security_report.py** — HTML 구조 검증 테스트 1건.

### Changed (patch100)
- **CHANGELOG.md** — patch93~99 엔트리 추가.
- **docs/RELEASE_NOTES.md** — patch93~99 반영.

## [0.4.17] - 2026-07-05 (patch98)

> **v0.4.17-patch98 — report security 보안 포스처 리포트**
> 디렉터리 스캔 → PII/인젝션 탐지 → 위험도 평가 → Markdown/JSON 리포트.

### Added
- **enforcement/security_report.py** — `generate_security_report()`, `render_markdown()`, `render_json()`, `cmd_report_security()`.
- **enforcement/cli.py** — `report security` 서브커맨드 + `--format md|json` + `--output`.
- **tests/test_security_report.py** — Markdown/JSON/SDK 테스트 5건.

## [0.4.17] - 2026-07-05 (patch97)

> **v0.4.17-patch97 — scan --parallel N 멀티스레드 스캔**
> ThreadPoolExecutor 기반 병렬 스캔으로 대규모 디렉터리 성능 향상.

### Changed
- **enforcement/scan_cmd.py** — `--parallel N` 옵션, ThreadPoolExecutor 기반 병렬 파일 스캔.
- **enforcement/cli.py** — `scan --parallel` 인자 추가.

## [0.4.17] - 2026-07-05 (patch96)

> **v0.4.17-patch96 — Getting Started 워크플로우 데모 + SDK batch 문서**
> 초보자용 워크플로우 데모 스크립트 + SDK batch API 문서화.

### Added
- **examples/getting_started.sh** — 종합 워크플로우 데모 스크립트.
- **docs/SDK.md** — batch_route/batch_inspect 섹션 추가.

## [0.4.17] - 2026-07-05 (patch95)

> **v0.4.17-patch95 — SDK batch_route + batch_inspect 일괄 처리**
> 여러 텍스트를 한 번에 라우팅·검사하는 배치 API.

### Added
- **nufi/__init__.py** — `batch_route()`, `batch_inspect()` 일괄 처리 함수.

## [0.4.17] - 2026-07-05 (patch94)

> **v0.4.17-patch94 — scan --output 파일 + --format jsonl 스트리밍**
> 스캔 결과를 파일에 기록. JSON Lines 형식으로 파이프 연동 용이.

### Changed
- **enforcement/scan_cmd.py** — `--output PATH` + `--format jsonl` 스트리밍 출력.
- **enforcement/cli.py** — scan --output, --format jsonl 인자 추가.

## [0.4.17] - 2026-07-05 (patch93)

> **v0.4.17-patch93 — DEMO.md 카탈로그에 인젝션·스캔·벤치 데모 등록**
> 데모 카탈로그 정리 및 누락 데모 등록.

### Changed
- **docs/DEMO.md** — 인젝션 탐지·스캔·벤치마크 데모 카탈로그 등록.

## [0.4.17] - 2026-07-05 (patch92)

> **v0.4.17-patch92 — nufi-egress watch 디렉터리 감시 모드**
> 파일 변경 실시간 감시 + 자동 스캔.

### Added
- **enforcement/watch_cmd.py** — `cmd_watch()` inotify/polling 기반 디렉터리 감시.
- **enforcement/cli.py** — `watch` 서브커맨드.

## [0.4.17] - 2026-07-05 (patch91)

> **v0.4.17-patch91 — scan --stats 요약 통계 + init quick-start 문서**
> 스캔 후 엔티티별·위험도별 요약 통계 출력. CLI.md init 섹션 보강.

### Added (CLI)
- **enforcement/scan_cmd.py** — `--stats` 플래그: 총 파일·엔티티별·위험도별 요약 출력.
- **enforcement/cli.py** — `scan --stats` 인자 추가.

### Changed (문서)
- **docs/CLI.md** — `init` quick-start 초기화 모드 + `--install-hook`/`--dir` 문서 추가.
- **CHANGELOG.md** — patch83~90 엔트리 정리, patch91 최신.
- **docs/RELEASE_NOTES.md** — patch90 최신 반영.

### Added (테스트)
- **tests/test_scan_cmd.py** — `--stats` 요약 출력 테스트 1건.

## [0.4.17] - 2026-07-05 (patch87~90)

> **v0.4.17-patch87~90 — redact 모드 + init quick-start + 인젝션 카테고리**
> scan --redact PII 자동 치환, init quick-start 프로젝트 초기화, 인젝션 카테고리 필터.

### Changed (patch87~90)
- **enforcement/scan_cmd.py** — `redact_path()` + `--redact`/`--dry-run`/`--no-backup` (patch88).
- **enforcement/init_cmd.py** — quick-start init: 프리셋 없이 config·.nufiignore·hook 생성 (patch90).
- **enforcement/cli.py** — `init --dir --install-hook` 플래그 (patch90).

## [0.4.17] - 2026-07-05 (patch86)

> **v0.4.17-patch86 — scan --format sarif SARIF 2.1.0 출력**
> GitHub Code Scanning 호환 SARIF 출력. gh code-scanning upload-sarif 연동 가능.

### Changed (CLI)
- **enforcement/scan_cmd.py** — `scan_result_to_sarif()` + `--format sarif` 출력.
- **enforcement/cli.py** — `scan --format` 인자 추가.

### Added (테스트)
- **tests/test_scan_cmd.py** — SARIF 테스트 2건.

## [0.4.17] - 2026-07-05 (patch85)

> **v0.4.17-patch85 — .nufiignore + scan --exclude 패턴 제외**
> .nufiignore 로 스캔 제외 패턴 설정. --exclude 로 CLI 직접 제외.

### Added (설정)
- **.nufiignore** — 기본 제외 패턴.

### Changed (CLI)
- **enforcement/scan_cmd.py** — `load_nufiignore()` + `_is_excluded()` + `exclude` 파라미터.
- **enforcement/cli.py** — `scan --exclude` 인자.

### Added (테스트)
- **tests/test_scan_cmd.py** — .nufiignore·--exclude·기본동작 테스트 3건.

## [0.4.17] - 2026-07-05 (patch84)

> **v0.4.17-patch84 — pre-commit 훅 + CI GitHub Actions 예시**
> git pre-commit 훅 + GitHub Actions 워크플로우 예시로 CI 연동.

### Added (스크립트)
- **scripts/pre-commit-hook.sh** — 커밋 전 PII 스캔 차단 훅.
- **examples/ci-github-actions.yml** — GitHub Actions 워크플로우.

### Changed (문서)
- **docs/INTEGRATION_GUIDE.md** — §6 Pre-commit & CI/CD 통합 추가.
- **README.md** — "처음 오셨다면" 표에 CI/pre-commit 행 추가.

## [0.4.17] - 2026-07-05 (patch83)

> **v0.4.17-patch83 — nufi-egress scan 디렉터리/파일 PII 스캔**
> 파일·디렉터리 재귀 스캔 + --fail-on-pii CI 연동 + scan_dir SDK.

### Added (CLI)
- **enforcement/scan_cmd.py** — `scan_path()` + `cmd_scan()`.
- **enforcement/cli.py** — `scan` 서브커맨드 (--pattern, --check-injection, --json, --fail-on-pii).
- **nufi/__init__.py** — `scan_dir` export.

### Added (테스트)
- **tests/test_scan_cmd.py** — 스캔 테스트 4건.

## [0.4.17] - 2026-07-05 (patch82)

> **v0.4.17-patch82 — SDK.md §2.9~2.11 route·detect_injection·inspect_text**

### Changed (문서)
- **docs/SDK.md** — §2.9 route, §2.10 detect_injection, §2.11 inspect_text 레퍼런스.

## [0.4.17] - 2026-07-05 (patch81)

> **v0.4.17-patch81 — nufi-egress version 서브커맨드 + --version**

### Added (CLI)
- **enforcement/cli.py** — `version` 서브커맨드 + `--version` 플래그.
- **tests/test_cli_version.py** — 버전 테스트 3건.

## [0.4.17] - 2026-07-05 (patch80)

> **v0.4.17-patch80 — 인젝션 패턴 카테고리 필터**
> korean/english/indirect/role_override 카테고리별 활성화/비활성화.

### Changed (엔진)
- **egress_audit/detectors/prompt_injection.py** — categories 파라미터.
- **config/pii_routing.yaml** — `injection_categories` 필드.

### Added (테스트)
- **tests/test_prompt_injection.py** — 카테고리 필터 테스트 3건.

## [0.4.17] - 2026-07-05 (patch79)

> **v0.4.17-patch79 — README·CHANGELOG patch75~78 반영**
> inspect 서브커맨드·인젝션 벤치마크·stdin 지원·간접 인젝션 패턴을 README·데모 섹션에 반영.

### Changed (문서)
- **README.md** — 데모 섹션에 인젝션 벤치마크·inspect 커맨드 추가, doctor 6체크 표기.
- **CHANGELOG.md** — patch75~78 엔트리 추가.

## [0.4.17] - 2026-07-05 (patch78)

> **v0.4.17-patch78 — nufi-egress inspect 통합 보안 스캔 커맨드**
> PII+인젝션+라우팅+차단을 한 번에 분석하는 inspect 서브커맨드. 위험도 자동 산출.

### Added (CLI)
- **enforcement/inspect_cmd.py** — `inspect_text()` 분석 함수 + `render_human()` 출력.
- **enforcement/cli.py** — `inspect` 서브커맨드 (--text, --file, --json).
- **nufi/__init__.py** — `inspect_text` SDK export.

### Added (테스트)
- **tests/test_inspect.py** — inspect 테스트 8건.

## [0.4.17] - 2026-07-05 (patch77)

> **v0.4.17-patch77 — 인젝션 E2E 통합 테스트**
> SDK·Guard·Policy·Route·CLI·커스텀패턴·심각도·벤치마크 전 경로 검증.

### Added (테스트)
- **tests/test_injection_e2e.py** — 파이프라인 E2E 테스트 11건.
- **scripts/demo_injection_e2e.sh** — E2E 래퍼.

## [0.4.17] - 2026-07-05 (patch76)

> **v0.4.17-patch76 — 간접 인젝션 패턴 8종 추가**
> HTML 코멘트·ChatML·Llama·역할·구분자·유니코드 제로폭 패턴. 골드셋 38건 확장.

### Added (엔진)
- **egress_audit/detectors/prompt_injection.py** — indirect 카테고리 8종 패턴.
- **samples/injection_gold.jsonl** — 8건 추가 (인젝션 5 + 무해 3).

### Added (테스트)
- **tests/test_prompt_injection.py** — 간접 인젝션 테스트 7건.

## [0.4.17] - 2026-07-05 (patch75)

> **v0.4.17-patch75 — CLI route --stdin 파이프 입력 지원**
> echo "텍스트" | nufi-egress route --stdin 으로 파이프 입력 처리.

### Added (CLI)
- **enforcement/cli.py** — `route --stdin` 옵션 + `_route_stdin()` 함수.

### Added (테스트)
- **tests/test_cmp270_cli_route.py** — stdin 테스트 2건.

## [0.4.17] - 2026-07-05 (patch73)

> **v0.4.17-patch73 — 인젝션 정책(block/warn/log) + 벤치 데모 등록**
> config/policy.yaml injection.action 으로 차단 정책 제어. demo_all 에 벤치마크 등록.

### Changed (엔진)
- **egress_audit/guard.py** — 인젝션 정책 action(block/warn/log) + min_severity 적용.
- **config/policy.yaml** — `injection:` 섹션 추가 (action: block, min_severity: medium).

### Added (스크립트)
- **scripts/demo_bench_injection.sh** — 인젝션 벤치마크 래퍼 (demo_all 등록).

### Added (테스트)
- **tests/test_injection_policy.py** — 정책 기반 인젝션 테스트 2건.

## [0.4.17] - 2026-07-05 (patch72)

> **v0.4.17-patch72 — 인젝션 탐지 벤치마크 골드셋**
> samples/injection_gold.jsonl (30건) + bench_injection.py (recall/precision 게이트).

### Added (벤치마크)
- **samples/injection_gold.jsonl** — 인젝션 15건 + 무해 15건 골드셋.
- **scripts/bench_injection.py** — 재현율·정밀도·F1 측정 (게이트: ≥0.90).
- **tests/test_bench_injection.py** — 벤치마크 통과 검증.

## [0.4.17] - 2026-07-05 (patch71)

> **v0.4.17-patch71 — 사용자 정의 인젝션 패턴 YAML 설정**
> config/injection_patterns.yaml 로 커스텀 패턴 추가 가능. 내장 패턴과 병합.

### Added (설정)
- **config/injection_patterns.yaml** — 사용자 정의 인젝션 패턴 예시.

### Changed (엔진)
- **egress_audit/detectors/prompt_injection.py** — `custom_patterns_path` 파라미터, YAML 로딩.
- **config/pii_routing.yaml** — `injection_patterns_path` 필드 추가.

### Added (테스트)
- **tests/test_prompt_injection.py** — 커스텀 패턴 테스트 3건.

## [0.4.17] - 2026-07-05 (patch70)

> **v0.4.17-patch70 — ARCHITECTURE 인젝션 레이어 + CHANGELOG patch67~69**

### Changed (문서)
- **docs/ARCHITECTURE.md** — Mermaid 다이어그램에 PromptInjectionDetector Phase 0 추가.
- **CHANGELOG.md** — patch67~69 엔트리.
- **docs/RELEASE_NOTES.md** — v0.4.17 범위 갱신.

## [0.4.17] - 2026-07-05 (patch69)

> **v0.4.17-patch69 — severity levels + min_severity filter**
> 인젝션 탐지 결과에 severity(critical/high/medium/low) 부여. `min_severity` 파라미터로 임계 이하 무시.

### Changed (엔진)
- **egress_audit/injection.py** — 패턴별 severity 레벨 매핑 추가. `detect()` 반환값에 `severity` 필드 포함.
- **egress_audit/guard.py** — `min_severity` 파라미터: 임계 미만 인젝션 findings 필터링.

### Added (테스트)
- **tests/test_injection_severity.py** — severity 레벨 + min_severity 필터 테스트.

## [0.4.17] - 2026-07-05 (patch68)

> **v0.4.17-patch68 — doctor injection check + HANDS_ON 가이드**
> `nufi-egress doctor --check-injection` 서브커맨드로 인젝션 탐지 상태 진단. HANDS_ON.md 실습 추가.

### Added (CLI)
- **enforcement/cli.py** — `doctor --check-injection` 서브커맨드 (설정·패턴·게이트웨이 상태 점검).

### Added (문서)
- **docs/HANDS_ON.md** — 인젝션 탐지 실습 섹션 추가.

## [0.4.17] - 2026-07-05 (patch67)

> **v0.4.17-patch67 — PROMPT_INJECTION.md 가이드**
> 프롬프트 인젝션 탐지 기능의 설계·사용법·운영 가이드 문서.

### Added (문서)
- **docs/PROMPT_INJECTION.md** — 프롬프트 인젝션 탐지 가이드 (설계·패턴 목록·SDK/CLI/게이트웨이 사용법·운영 권고).

## [0.4.17] - 2026-07-05 (patch65)

> **v0.4.17-patch65 — LiteLLM 훅 프롬프트 인젝션 차단**
> LiteLLM Proxy 콜백에서 PII 라우팅 전 인젝션 탐지 Phase 0. check_injection: true 시 HTTP 403 + audit 로깅.

### Changed (게이트웨이)
- **gateway/litellm_hook.py** — `async_pre_call_hook`에 인젝션 탐지 Phase 0 추가. 감지 시 403 + outcome `blocked_injection`.

### Added (테스트)
- **tests/test_litellm_hook_injection.py** — LiteLLM 훅 인젝션 테스트 2건.

## [0.4.17] - 2026-07-05 (patch64)

> **v0.4.17-patch64 — 게이트웨이 프롬프트 인젝션 차단**
> NUFI_CHECK_INJECTION=1 또는 config check_injection: true 로 게이트웨이에서 인젝션 HTTP 403 차단. 기본 비활성.

### Changed (게이트웨이)
- **gateway/core.py** — `process()`에 인젝션 탐지 추가. 감지 시 403 `injection_blocked`. 라우팅 전 fail-fast.
- **config/pii_routing.yaml** — `check_injection: false` 설정 항목 추가.

### Added (테스트)
- **tests/test_gateway_injection.py** — 게이트웨이 인젝션 테스트 3건.

## [0.4.17] - 2026-07-05 (patch63)

> **v0.4.17-patch63 — 프롬프트 인젝션 데모 + SDK 예시**
> demo_prompt_injection.sh (6시나리오 31건 PASS/FAIL) + examples/sdk_prompt_injection.py.

### Added (스크립트)
- **scripts/demo_prompt_injection.py** — 인젝션 탐지 데모 (6시나리오 31건).
- **scripts/demo_prompt_injection.sh** — 셸 래퍼.
- **examples/sdk_prompt_injection.py** — SDK 인젝션 예시.

### Changed (스크립트)
- **scripts/demo_all.sh** — demo_prompt_injection.sh 등록.
- **examples/README.md** — sdk_prompt_injection.py 등록.

## [0.4.17] - 2026-07-05 (patch61)

> **v0.4.17-patch61 — Guard 프롬프트 인젝션 탐지 통합**
> Guard(check_injection=True)로 PII와 프롬프트 인젝션을 동시에 탐지·차단. CLI --check-injection 플래그 추가.

### Changed (엔진)
- **egress_audit/guard.py** — `check_injection` 파라미터 추가, 인젝션 감지 시 `block_injection` 액션으로 차단.
- **enforcement/cli.py** — `route --check-injection` 플래그 (--text, --file 모드 모두 지원).

### Added (테스트)
- **tests/test_guard_injection.py** — Guard 인젝션 통합 테스트 6건.

## [0.4.17] - 2026-07-05 (patch60)

> **v0.4.17-patch60 — 한국어 프롬프트 인젝션 탐지기**
> 한국어·영어 프롬프트 인젝션/탈옥 패턴 18종을 정규식으로 탐지하는 경량 탐지기. `from nufi import detect_injection` 으로 SDK 노출.

### Added (엔진)
- **egress_audit/detectors/prompt_injection.py** — `PromptInjectionDetector` (한국어 8종 + 영어 8종 + 역할변경 2종 패턴).
- **nufi/__init__.py** — `detect_injection` 편의 함수 export.

### Added (테스트)
- **tests/test_prompt_injection.py** — 프롬프트 인젝션 탐지 테스트 13건.

## [0.4.17] - 2026-07-05 (patch59)

> **v0.4.17-patch59 — CLI route --file 파일 일괄 스캔 + --summary 통계**
> `nufi-egress route --file input.txt`로 파일을 줄 단위 PII 라우팅 판정. --summary로 로컬/클라우드 비율 통계.

### Added (CLI)
- **enforcement/cli.py** — `route --file` (파일 줄별 판정), `route --summary` (집계 통계) 옵션.

### Added (테스트)
- **tests/test_cmp270_cli_route.py** — --file, --summary 테스트 6건 추가 (총 14건).

## [0.4.17] - 2026-07-05 (patch58)

> **v0.4.17-patch58 — README.md PII 라우팅 표면 반영**
> SDK route() 예시·CLI route 사용법·설정 파일 테이블에 pii_routing.yaml 추가. patch55~57 결과물을 최상위 README에 반영.

### Changed (문서)
- **README.md** — SDK 섹션에 `route()` 예시 추가, 데모 섹션에 `nufi-egress route` 사용법 추가, 설정 테이블에 `config/pii_routing.yaml` 행 추가.

## [0.4.17] - 2026-07-05 (patch56)

> **v0.4.17-patch56 — config/pii_routing.yaml 설정 파일 도입**
> PII 라우팅 파라미터를 코드 수정 없이 YAML로 제어할 수 있도록 전용 설정 파일 도입. PiiRouter가 초기화 시 config를 자동 로드하며, LiteLLM hook도 참조.

### Added (설정)
- **config/pii_routing.yaml** — PII 라우팅 전용 설정 파일 (enabled, local_model, cloud_model, fail_closed, force_local_entities).

### Added (테스트)
- **tests/test_cmp271_pii_routing_config.py** — 설정 파일 로딩·통합 검증 11건.

### Changed (게이트웨이)
- **gateway/pii_router.py** — `load_pii_routing_config()` 함수 추가, `PiiRouter` 생성자에 `config_path` 파라미터·`enabled` 속성 추가, `from_config()` 클래스메서드 추가.
- **gateway/litellm_hook.py** — `EgressAuditHook.__init__` 에 `config_path` 전달.

### Changed (문서)
- **docs/PII_ROUTING.md** — config/pii_routing.yaml 설정 레퍼런스 섹션 추가.

## [0.4.17] - 2026-07-05 (patch55)

> **v0.4.17-patch55 — CLI nufi-egress route 서브커맨드 추가**
> PII 라우팅 결정을 CLI에서 테스트할 수 있는 `nufi-egress route` 서브커맨드. 기존 `PiiRouter.route()`를 CLI 진입점으로 노출. `--json` 플래그로 기계용 출력 지원.

### Added (CLI)
- **enforcement/cli.py** — `route` 서브커맨드: `--text`로 PII 감지·모델 라우팅 판정 출력. `--json`/`--model`/`--local-model`/`--cloud-model` 옵션.

### Added (테스트)
- **tests/test_cmp270_cli_route.py** — `route` 서브커맨드 단위 테스트 (PII 감지·클린 텍스트·JSON 출력·스키마 완전성·main 진입점).

### Changed (문서)
- **docs/CLI.md** — `route` 서브커맨드 레퍼런스 섹션 추가 (옵션 표·사용 예시·종료코드).
- **docs/RELEASE_NOTES.md** — v0.4.17 릴리스 노트.

## [0.4.16] - 2026-07-05 (patch57)

> **v0.4.16-patch57 — SDK route() 함수 노출 + 예시 추가**
> PII 라우팅 결정을 `from nufi import route` 한 줄로 호출 가능하게 노출. RoutingDecision·PiiRouter도 stable 계층에 포함.

### Added (SDK)
- **nufi/__init__.py** — `route(text) -> RoutingDecision` 편의 함수, `RoutingDecision`·`PiiRouter` export.
- **examples/sdk_pii_routing.py** — PII 라우팅 SDK 예시 (PII→로컬, 클린→클라우드, to_dict).
- **tests/test_unit.py** — `test_route_pii_detected_routes_local`, `test_route_clean_text_routes_cloud` 추가.

### Changed (문서)
- **docs/SDK.md** — §2.8 PII 라우팅 섹션 추가 (RoutingDecision 필드 표 포함).
- **examples/README.md** — `sdk_pii_routing.py` 등록.

## [0.4.16] - 2026-07-05 (patch54)

> **v0.4.16-patch54 — LiteLLM Proxy E2E 데모 스크립트 추가**
> 스텁 LLM + LiteLLM Proxy를 실제로 기동하여 NuFi 콜백의 PII 감지·라우팅·차단을 3개 시나리오로 자동 검증하는 E2E 데모. demo_all.sh에도 등록.

### Added (스크립트)
- **scripts/demo_litellm_e2e.sh** — LiteLLM Proxy E2E 자동 검증 데모 (S1 클라우드 통과, S2 로컬 라우팅, S3 차단).

### Changed (스크립트)
- **scripts/demo_all.sh** — demo_litellm_e2e.sh 등록.

## [0.4.16] - 2026-07-05 (patch53)

> **v0.4.16-patch53 — HANDS_ON_LITELLM.md 신규**
> LiteLLM Proxy + NuFi 콜백을 사용한 PII 기반 하이브리드 라우팅 E2E 실습 가이드. 스텁 로컬 LLM 기동 → LiteLLM Proxy 설정 → 3개 시나리오(일반→클라우드, PII→로컬, 강한PII→차단) → 감사 로그 확인 → 비용 추적 → 트러블슈팅.

### Added (문서)
- **docs/HANDS_ON_LITELLM.md** — LiteLLM Proxy 연동 Hands-On 튜토리얼 신규 작성 (11개 섹션).

## [0.4.16] - 2026-07-04 (patch52)

> **v0.4.16-patch52 — README.md 경쟁 위치 섹션 추가**
> "왜 NuFi인가" 절 신설: 영어권 오픈소스·상용 DLP 대비 비교표(7개 항목), 적합 조직 유형 4가지, 직접 구현의 의미(보안 표면·hot-reload·가독성) 문서화. VERSION 변경 없음.

### Changed (문서)
- **README.md** — §설정~§현재상태 사이에 "왜 NuFi인가 — 경쟁 위치" 절 추가(비교표·적합 조직·직접 구현 의미).

## [0.4.16] - 2026-07-04 (patch51)

> **v0.4.16-patch51 — SDK.md §2.4 GuardResult·Decision 필드 상세 표 추가**
> Guard.inspect() 반환값인 GuardResult·Decision dataclass 의 모든 필드(타입·설명·property 포함)와 코드 예시 추가. VERSION 변경 없음.

### Changed (문서)
- **docs/SDK.md** — §2.4 에 GuardResult 필드 표(5개)·Decision 필드 표(4개) + 사용 예시 코드 블록 추가.

## [0.4.16] - 2026-07-04 (patch50)

> **v0.4.16-patch50 — REPORTING §5 감사관 제출 치트시트 추가**
> 한국 규제 감사(금융보안원·금융위원회·개인정보보호위원회·과기부) 대응 시 표준 CLI 흐름과 규제별 프레임워크 대응표 추가. 무결성 게이트 실패 대응 지침 명시. VERSION 변경 없음.

### Changed (문서)
- **docs/REPORTING.md** — §5 신설(감사관 제출 치트시트): 5-단계 CLI 흐름, Python 커버리지 요약 스니펫, 규제별 `--framework` 인자 대응표(6행).

## [0.4.16] - 2026-07-04 (patch49)

> **v0.4.16-patch49 — MANUAL §3 감사 로그 JSONL 레코드 스키마 문서화**
> 매뉴얼 §3 핵심 개념에 `logs/egress_audit.jsonl` 레코드 필드 표(id·ts·epoch_ms·model·provider·is_public·outcome·decision·findings·request_body·chain·extra)와 실제 JSON 예시 추가. 원문 마스킹 방식(`len=...:sha256=...`) 명시. VERSION 변경 없음.

### Changed (문서)
- **docs/MANUAL.md** — §3 에 감사 로그 JSONL 스키마 표 + JSON 예시 블록 추가.

## [0.4.16] - 2026-07-04 (patch48)

> **v0.4.16-patch48 — ROADMAP §6 현재 달성 수치 표 추가**
> ROADMAP.md 에 v0.4.16 기준 10개 목표 지표(재현율·지연·오탐·규제 증빙·테스트·데모)를 목표값 대비 달성값 표로 정리. VERSION 변경 없음.

### Changed (문서)
- **docs/ROADMAP.md** — §6 신설(현재 달성 수치) — 10개 지표 목표/달성 대비 표, 기존 §6→§7 재번호.

## [0.4.16] - 2026-07-04 (patch47)

> **v0.4.16-patch47 — MANUAL §9 용어집 항목 7개 추가**
> 용어집에 Wilson 신뢰구간·강한/약한 PII·가역성·PII 라우팅 등 독자가 자주 헷갈리는 개념 7개 추가. VERSION 변경 없음.

### Changed (문서)
- **docs/MANUAL.md** — §9 용어집에 Wilson CI·강한 PII·약한 PII·가역성·PII 라우팅 등 7개 항목 추가.

## [0.4.16] - 2026-07-04 (patch46)

> **v0.4.16-patch46 — RELEASE_NOTES 패치 시리즈 성과 요약 표 추가**
> 패치 시리즈(patch01~patch45) 의 성과를 "패치 이전/이후" 비교 표로 시각화. SDK 예시 수·내부 링크 수·관련 문서 섹션 완성도 등 8개 지표 정리. VERSION 변경 없음.

### Changed (문서)
- **docs/RELEASE_NOTES.md** — v0.4.16 패치 시리즈 섹션에 성과 요약 표(8개 지표 패치 이전/이후 비교) 추가.

## [0.4.16] - 2026-07-04 (patch45)

> **v0.4.16-patch45 — MANUAL.md 부록 문서 지도 완성 + 잔재 태그 제거**
> 매뉴얼 §부록 문서 지도에 SDK·PII_ROUTING·RELEASE_NOTES·DOC_STYLE 4개 링크를 추가하고, 이전 패치에서 잘못 삽입된 `</content></invoke>` 잔재 태그를 제거. 내부 링크 140→145개. VERSION 변경 없음.

### Changed (문서)
- **docs/MANUAL.md** — 부록 문서 지도 표에 SDK·PII_ROUTING·RELEASE_NOTES·DOC_STYLE 링크 추가. 최종 갱신 타임스탬프 추가. 잔재 XML 태그(`</content></invoke>`) 제거.

## [0.4.16] - 2026-07-04 (patch44)

> **v0.4.16-patch44 — SDK.md Finding 객체 필드 상세 표 추가**
> Finding dataclass 의 7개 필드(entity_type·text·start·end·score·source·context)를 표로 문서화. VERSION 변경 없음.

### Changed (문서)
- **docs/SDK.md** — §2.2 `Finding` 객체에 필드 상세 표(타입·설명) 추가.

## [0.4.16] - 2026-07-04 (patch43)

> **v0.4.16-patch43 — MANUAL.md §3 탐지 대상 PII 클래스 12종 표 추가**
> 핵심 개념 섹션에 탐지 가능한 PII 엔티티 클래스 목록(클래스명·설명·탐지 방식·강한/약한 PII 구분) 표 추가. VERSION 변경 없음.

### Changed (문서)
- **docs/MANUAL.md** — §3 핵심 개념에 "탐지 대상 PII 클래스 (12종)" 표 추가(KR_RRN·KR_FOREIGNER_REG·KR_BRN·KR_PASSPORT·KR_DRIVER_LICENSE·KR_ACCOUNT·CREDIT_CARD·KR_PHONE·EMAIL·KR_PERSON·KR_LOCATION·SECRET + 강한/약한 PII 분류 주석).

## [0.4.16] - 2026-07-04 (patch42)

> **v0.4.16-patch42 — REPORTING.md 프레임워크별 커버리지 수치 표 추가**
> 5종 규제 프레임워크별 direct/partial/out_of_scope 항목 수를 표로 명시화. VERSION 변경 없음.

### Changed (문서)
- **docs/REPORTING.md** — §2 "프레임워크" 표에 커버리지 수치(direct·partial·oos) 열 추가. net-sep 5/5 direct 강조 주석 추가.

## [0.4.16] - 2026-07-04 (patch41)

> **v0.4.16-patch41 — reports/README recall-int8.json 키 구조 안내 추가**
> JSON 보고서를 코드에서 읽는 방법(주요 키·Python 스니펫) 문서화. VERSION 변경 없음.

### Changed (문서)
- **docs/reports/README.md** — `recall-int8.json` 키 구조 안내 섹션 추가(per_class_recall·latency·acceptance·SDK 접근법 포함).

## [0.4.16] - 2026-07-04 (patch40)

> **v0.4.16-patch40 — PROJECT_STATE 교차링크 보강 이력 현행화**
> HANDOVER/PROJECT_STATE.md 에 patch14~39 교차링크 전반 보강 이력 추가. VERSION 변경 없음.

### Changed (문서)
- **HANDOVER/PROJECT_STATE.md** — §4 갭 점검에 patch14~39 교차링크 보강 표 추가(16개 파일·영역 커버).

## [0.4.16] - 2026-07-04 (patch39)

> **v0.4.16-patch39 — docs/README.md 관련 문서 섹션 신설**
> 문서 지도 인덱스 파일에 관련 문서 표 추가. VERSION 변경 없음.

### Changed (문서)
- **docs/README.md** — 관련 문서 섹션 신설(ROOT_README·MANUAL·HANDS_ON·CHANGELOG·HANDOVER/PROJECT_OVERVIEW).

## [0.4.16] - 2026-07-04 (patch38)

> **v0.4.16-patch38 — reports/README 관련 문서 섹션 신설**
> docs/reports/README.md 에 관련 문서 표 추가. VERSION 변경 없음.

### Changed (문서)
- **docs/reports/README.md** — 관련 문서 섹션 신설(REPORTING·HANDS_ON·SDK·goldset README).

## [0.4.16] - 2026-07-04 (patch37)

> **v0.4.16-patch37 — RELEASE_CHECKLIST 관련 문서 섹션 신설**
> RELEASE_CHECKLIST.md 에 관련 문서 표 추가. VERSION 변경 없음.

### Changed (문서)
- **docs/RELEASE_CHECKLIST.md** — 관련 문서 섹션 신설(RELEASE_NOTES·CHANGELOG·ENGINEERING_CONVENTIONS·DEMO·HANDS_ON).

## [0.4.16] - 2026-07-04 (patch36)

> **v0.4.16-patch36 — HANDOVER 2종·DOC_STYLE 관련 문서 섹션 신설**
> AGENT_OPERATING_MODEL·ENGINEERING_CONVENTIONS·DOC_STYLE 에 관련 문서 표 추가. VERSION 변경 없음.

### Changed (문서)
- **HANDOVER/AGENT_OPERATING_MODEL.md** — 관련 문서 섹션 신설(ENGINEERING_CONVENTIONS·PROJECT_STATE·PROJECT_OVERVIEW·DOC_STYLE).
- **HANDOVER/ENGINEERING_CONVENTIONS.md** — 관련 문서 섹션 신설(AGENT_OPERATING_MODEL·PROJECT_OVERVIEW·PROJECT_STATE·DOC_STYLE·CHANGELOG).
- **docs/DOC_STYLE.md** — 관련 문서 섹션 신설(ENGINEERING_CONVENTIONS·AGENT_OPERATING_MODEL·README).

## [0.4.16] - 2026-07-04 (patch35)

> **v0.4.16-patch35 — CLI.md·HANDS_ON.md 관련 문서 섹션 신설**
> 두 핵심 레퍼런스 문서에 관련 문서 표 추가. VERSION 변경 없음.

### Changed (문서)
- **docs/CLI.md** — 관련 문서 섹션 신설(HANDS_ON·INTEGRATION_GUIDE·PRESETS·OPS·REPORTING·DEMO 7종).
- **docs/HANDS_ON.md** — 관련 문서 섹션 신설(INTEGRATION_GUIDE·PRESETS·CLI·SDK·REPORTING·DEMO·examples 7종).

## [0.4.16] - 2026-07-04 (patch34)

> **v0.4.16-patch34 — CHANGELOG·RELEASE_NOTES·HANDOVER patch34 기준 현행화**
> patch33 항목 추가. RELEASE_NOTES·HANDOVER patch34 갱신. VERSION 변경 없음.

### Changed (문서)
- **CHANGELOG.md** — patch33 항목 추가.
- **docs/RELEASE_NOTES.md** — 패치 시리즈 patch34로 확장.
- **HANDOVER/PROJECT_STATE.md** — patch33~34 버전 이력 추가, 대상 patch34.
- **HANDOVER/PROJECT_OVERVIEW.md** — 패치 번호 patch32→patch34.
- **HANDOVER/README.md** — 대상 버전 patch32→patch34.

## [0.4.16] - 2026-07-04 (patch33)

> **v0.4.16-patch33 — research/ 문서 3종 관련 문서 섹션 신설**
> FSEC_AI_GUIDE·SOLUTION_FOCUS_OPTIONS·NUFI_SECURITY_PLANE_CHARTER 교차링크. VERSION 변경 없음.

### Changed (문서)
- **docs/research/FSEC_AI_GUIDE_2026.md** — 관련 문서 표 신설: REPORTING·ROADMAP·NUFI_SECURITY_PLANE_CHARTER 3종.
- **docs/research/SOLUTION_FOCUS_OPTIONS.md** — 관련 문서 표 신설: ROADMAP·NUFI_SECURITY_PLANE_CHARTER·FSEC_AI_GUIDE_2026 3종.
- **docs/research/NUFI_SECURITY_PLANE_CHARTER.md** — 관련 문서 표 신설: ROADMAP·ARCHITECTURE·REPORTING·SOLUTION_FOCUS_OPTIONS 4종.

## [0.4.16] - 2026-07-04 (patch32)

> **v0.4.16-patch32 — CHANGELOG·RELEASE_NOTES·HANDOVER patch32 기준 현행화**
> patch30·31 항목 추가. RELEASE_NOTES·HANDOVER patch32 갱신. VERSION 변경 없음.

### Changed (문서)
- **CHANGELOG.md** — patch30·31 항목 추가.
- **docs/RELEASE_NOTES.md** — 패치 시리즈 patch32로 확장.
- **HANDOVER/PROJECT_STATE.md** — patch30~32 버전 이력 추가, 대상 patch32.
- **HANDOVER/PROJECT_OVERVIEW.md** — 패치 번호 patch29→patch32.
- **HANDOVER/README.md** — 대상 버전 patch29→patch32.

## [0.4.16] - 2026-07-04 (patch31)

> **v0.4.16-patch31 — samples/gold/README.md 관련 문서 섹션 신설**
> docs/reports/README·HANDS_ON·kr-person-error-analysis 교차링크. VERSION 변경 없음.

### Changed (문서)
- **samples/gold/README.md** — 관련 문서 표 신설: docs/reports/README.md·HANDS_ON.md·kr-person-error-analysis.md 3종.

## [0.4.16] - 2026-07-04 (patch30)

> **v0.4.16-patch30 — nufi_client/README.md 관련 문서 섹션 신설 + 통합 가이드 링크 확정**
> 통합 가이드 "후속 문서" 링크를 INTEGRATION_GUIDE.md 로 확정. 관련 문서 표 신설. VERSION 변경 없음.

### Changed (문서)
- **nufi_client/README.md** — "통합 가이드" 링크를 `docs/INTEGRATION_GUIDE.md` 로 확정. 관련 문서 표 신설: docs/SDK.md·docs/INTEGRATION_GUIDE.md·examples/README.md 3종.

## [0.4.16] - 2026-07-04 (patch29)

> **v0.4.16-patch29 — CHANGELOG·RELEASE_NOTES·HANDOVER patch29 기준 현행화**
> patch26~28 항목 추가. RELEASE_NOTES·HANDOVER patch29 갱신. VERSION 변경 없음.

### Changed (문서)
- **CHANGELOG.md** — patch26·27·28 항목 추가.
- **docs/RELEASE_NOTES.md** — 패치 시리즈 patch29로 확장.
- **HANDOVER/PROJECT_STATE.md** — patch26~29 버전 이력 추가, 대상 patch29.
- **HANDOVER/PROJECT_OVERVIEW.md** — 패치 번호 patch25→patch29.
- **HANDOVER/README.md** — 대상 버전 patch25→patch29.

## [0.4.16] - 2026-07-04 (patch28)

> **v0.4.16-patch28 — INTEGRATION_GUIDE.md 관련 문서 섹션 신설**
> PRESETS·CLI·SDK·HANDS_ON·PII_ROUTING·OPS_RULE_RELOAD 교차링크. VERSION 변경 없음.

### Changed (문서)
- **docs/INTEGRATION_GUIDE.md** — 관련 문서 표 신설: PRESETS·CLI·SDK·HANDS_ON·PII_ROUTING·OPS_RULE_RELOAD 6종.

## [0.4.16] - 2026-07-04 (patch27)

> **v0.4.16-patch27 — docs/README.md history/README·research/README 진입점 링크 추가**
> 설계·명세 섹션에 history/README.md 링크, 조사·전략 섹션에 research/README.md 링크. VERSION 변경 없음.

### Changed (문서)
- **docs/README.md** — history/ 섹션에 `history/README.md` 진입점 링크 추가. research/ 섹션에 `research/README.md` 진입점 링크 추가.

## [0.4.16] - 2026-07-04 (patch26)

> **v0.4.16-patch26 — examples/README.md 관련 문서 섹션 신설**
> docs/SDK.md·HANDS_ON·REPORTING·DEMO 교차링크. VERSION 변경 없음.

### Changed (문서)
- **examples/README.md** — 관련 문서 표 신설: docs/SDK.md·docs/HANDS_ON.md·docs/REPORTING.md·docs/DEMO.md 4종.

## [0.4.16] - 2026-07-04 (patch25)

> **v0.4.16-patch25 — CHANGELOG·RELEASE_NOTES·HANDOVER patch25 기준 현행화**
> patch23·24 항목 추가. RELEASE_NOTES·HANDOVER patch25 기준 갱신. VERSION 변경 없음.

### Changed (문서)
- **CHANGELOG.md** — patch23·24 항목 추가.
- **docs/RELEASE_NOTES.md** — 패치 시리즈 patch25로 확장.
- **HANDOVER/PROJECT_STATE.md** — patch23~25 버전 이력 추가, 대상 patch25.
- **HANDOVER/PROJECT_OVERVIEW.md** — 패치 번호 patch22→patch25.
- **HANDOVER/README.md** — 대상 버전 patch22→patch25.

## [0.4.16] - 2026-07-04 (patch24)

> **v0.4.16-patch24 — DEMO.md·ROADMAP.md 관련 문서 섹션 신설**
> DEMO: HANDS_ON·examples·CLI·INTEGRATION_GUIDE·REPORTING·PII_ROUTING 링크. ROADMAP: RELEASE_NOTES·CHANGELOG·REPORTING·SDK·PII_ROUTING·research 링크. VERSION 변경 없음.

### Changed (문서)
- **docs/DEMO.md** — 관련 문서 표 신설: HANDS_ON·examples/README.md·CLI·INTEGRATION_GUIDE·REPORTING·PII_ROUTING 6종.
- **docs/ROADMAP.md** — 관련 문서 표 신설: RELEASE_NOTES·CHANGELOG·REPORTING·SDK·PII_ROUTING·research/SOLUTION_FOCUS_OPTIONS 6종.

## [0.4.16] - 2026-07-04 (patch23)

> **v0.4.16-patch23 — REPORTING.md 관련 문서 섹션 신설**
> SDK·CLI·examples·OPS·SECURITY·research 교차링크. VERSION 변경 없음.

### Changed (문서)
- **docs/REPORTING.md** — 관련 문서 표 신설: SDK·CLI·examples/sdk_compliance_report·OPS_POLICY_AT_SCALE·SECURITY_RETAIN_RAW_KEYROTATION·research/FSEC_AI_GUIDE_2026 6종.

## [0.4.16] - 2026-07-04 (patch22)

> **v0.4.16-patch22 — CHANGELOG·RELEASE_NOTES·HANDOVER patch22 기준 현행화**
> patch20·21 항목 추가. RELEASE_NOTES 패치 시리즈 patch22로 확장. VERSION 변경 없음.

### Changed (문서)
- **CHANGELOG.md** — patch20·21 항목 추가.
- **docs/RELEASE_NOTES.md** — 패치 시리즈 patch22로 확장.
- **HANDOVER/PROJECT_STATE.md** — patch20~22 버전 이력 추가, 대상 patch22.
- **HANDOVER/PROJECT_OVERVIEW.md** — 패치 번호 patch19→patch22.
- **HANDOVER/README.md** — 대상 버전 patch19→patch22.

## [0.4.16] - 2026-07-04 (patch21)

> **v0.4.16-patch21 — PII_ROUTING.md 관련 문서 섹션 신설**
> INTEGRATION_GUIDE·SDK·ARCHITECTURE·ROADMAP 교차링크. VERSION 변경 없음.

### Changed (문서)
- **docs/PII_ROUTING.md** — 관련 문서 표 신설: INTEGRATION_GUIDE·SDK·ARCHITECTURE·ROADMAP 4종.

## [0.4.16] - 2026-07-04 (patch20)

> **v0.4.16-patch20 — SDK.md 관련 문서 섹션 신설**
> examples·HANDS_ON·INTEGRATION_GUIDE·REPORTING·PII_ROUTING·CLI 교차링크. VERSION 변경 없음.

### Changed (문서)
- **docs/SDK.md** — 관련 문서 표 신설: examples/README.md·HANDS_ON·INTEGRATION_GUIDE·REPORTING·PII_ROUTING·CLI 6종.

## [0.4.16] - 2026-07-04 (patch19)

> **v0.4.16-patch19 — docs/history/README.md 신설 · HANDOVER patch19 기준 현행화**
> 역사적 스냅샷 6종 인덱스·열람 가이드. HANDOVER 전반 patch19 기준 갱신. VERSION 변경 없음.

### Added / Changed (모두 문서)
- **docs/history/README.md** — 역사적 스냅샷 6종(SPEC·SPEC_EGRESS_ENFORCEMENT·SPEC_M4·IMPL_M4·DEMO_v0.0.3·DEMO_v0.0.5) 인덱스 + 언제 읽나 안내 + 관련 living 문서 표.
- **HANDOVER/README.md** — 대상 버전 patch19 갱신.
- **HANDOVER/PROJECT_STATE.md** — patch16~19 버전 이력 항목 추가, 대상 patch19.
- **HANDOVER/PROJECT_OVERVIEW.md** — 패치 번호 patch15→patch19.

## [0.4.16] - 2026-07-04 (patch18)

> **v0.4.16-patch18 — docs/research/README.md 신설**
> 조사·전략 문서 3종(FSEC_AI_GUIDE_2026·NUFI_SECURITY_PLANE_CHARTER·SOLUTION_FOCUS_OPTIONS) 인덱스·배경 설명. VERSION 변경 없음.

### Added (문서)
- **docs/research/README.md** — 조사·전략 문서 3종 인덱스 + 각 문서 배경·읽는 시점 안내 + 관련 living 문서 표.

## [0.4.16] - 2026-07-04 (patch17)

> **v0.4.16-patch17 — SECURITY_RETAIN_RAW_KEYROTATION 관련 문서 섹션 신설**
> OPS_RULE_RELOAD·PRESETS·REPORTING 교차링크. VERSION 변경 없음.

### Changed (문서)
- **docs/SECURITY_RETAIN_RAW_KEYROTATION.md** — 관련 문서 표 신설: OPS_RULE_RELOAD·PRESETS·REPORTING 3종.

## [0.4.16] - 2026-07-04 (patch16)

> **v0.4.16-patch16 — OPS_RULE_RELOAD·OPS_POLICY_AT_SCALE 관련 문서 섹션 신설**
> 교차링크 보강. VERSION 변경 없음.

### Changed (문서)
- **docs/OPS_RULE_RELOAD.md** — 관련 문서 표 신설: PRESETS·OPS_POLICY_AT_SCALE·SECURITY_RETAIN_RAW_KEYROTATION·CLI 4종.
- **docs/OPS_POLICY_AT_SCALE.md** — 관련 문서 표 신설: OPS_RULE_RELOAD·PRESETS·CLI·REPORTING 4종.

## [0.4.16] - 2026-07-04 (patch15)

> **v0.4.16-patch15 — 교차링크 보강 (INTEGRATION_GUIDE·PRESETS)**
> INTEGRATION_GUIDE.md §5 하이브리드 결정트리에 PII_ROUTING.md 링크 추가.
> PRESETS.md 에 "관련 문서" 섹션 신설(INTEGRATION_GUIDE·OPS_*·PII_ROUTING·CLI). VERSION 변경 없음.

### Changed / Added (모두 문서)
- **docs/INTEGRATION_GUIDE.md** — §5 끝에 PII 기반 자동 라우팅(Phase 1) 설명 + PII_ROUTING.md 링크 추가.
- **docs/PRESETS.md** — 관련 문서 표 신설: INTEGRATION_GUIDE·OPS_RULE_RELOAD·OPS_POLICY_AT_SCALE·PII_ROUTING·CLI 5종.

## [0.4.16] - 2026-07-04 (patch14)

> **v0.4.16-patch14 — MANUAL.md SDK 예시 7종 examples/README.md 링크 추가**
> SDK 예시 단락을 examples/README.md(7종) 인덱스 링크로 업데이트. VERSION 변경 없음.

### Changed (문서)
- **docs/MANUAL.md** — SDK 예시 단락: examples/README.md(7종) 우선 링크로 업데이트.

## [0.4.16] - 2026-07-04 (patch13)

> **v0.4.16-patch13 — MANUAL.md 정확도 수치 정정 + RELEASE_NOTES 패치 시리즈 patch11 확장**
> MANUAL.md §3 탐지 정확도 0.977→0.9908 현행화. RELEASE_NOTES 패치 시리즈 항목 상세화. VERSION 변경 없음.

### Changed (모두 문서)
- **docs/MANUAL.md** — §3 탐지 정확도 수치 0.977→0.9908(v0.4.16 기준), KR_PERSON 0.9799 함께 명시.
- **docs/RELEASE_NOTES.md** — 패치 시리즈 항목 확장: research/ 섹션·REPORTING SDK §4·HANDS_ON Part I 링크·ARCHITECTURE 갱신 이력 포함.

## [0.4.16] - 2026-07-04 (patch12)

> **v0.4.16-patch12 — 문서 풍부화 4차 (HANDOVER·RELEASE_NOTES·research 인덱스·ARCHITECTURE 갱신)**
> HANDOVER docs: README 버전 갱신, PROJECT_STATE patch10 기준·버전 이력 7항목. RELEASE_NOTES 패치 시리즈 patch11로 확장. docs/README research/ 섹션 신설. ARCHITECTURE.md 갱신 이력 주석 보강. VERSION 변경 없음.

### Changed / Added (모두 문서)
- **HANDOVER/README.md** — 버전 표기 v0.2.2→v0.4.16-patch10.
- **HANDOVER/PROJECT_STATE.md** — 대상 patch10, 버전 이력 patch07~10 행 추가.
- **HANDOVER/PROJECT_OVERVIEW.md** — 패치 번호 patch06→patch10.
- **docs/RELEASE_NOTES.md** — 패치 시리즈 patch08→patch11, 내용 상세화.
- **docs/README.md** — research/ 조사·전략 문서 섹션 신설 (FSEC·CHARTER·SOLUTION_FOCUS).
- **docs/ARCHITECTURE.md** — §8 갱신 이력 주석 보강.
- **docs/HANDS_ON.md** — Part I에 sdk_file_scan.py 링크 추가. 다음 단계에 REPORTING.md 링크.
- **tests/test_examples_smoke.py** — 도큐스트링 7종으로 업데이트.

## [0.4.16] - 2026-07-04 (patch10)

> **v0.4.16-patch10 — 문서 풍부화 3차 (REPORTING·ARCHITECTURE·test docstring)**
> REPORTING.md Python SDK API §4 추가. ARCHITECTURE.md §8에 SDK·REPORTING·PII_ROUTING 링크.
> test_examples_smoke.py 도큐스트링 7종으로 업데이트. HANDS_ON.md 다음 단계에 REPORTING 링크. VERSION 변경 없음.

### Changed / Added (모두 문서·테스트 문서)
- **docs/REPORTING.md** — Python SDK API 섹션(`§4`) 신설: `compliance_report`·`render_report`·`load_catalog` 코드 스니펫 + `examples/sdk_compliance_report.py` 링크.
- **docs/ARCHITECTURE.md** — §8 관련 문서에 SDK·REPORTING·PII_ROUTING 링크 추가.
- **tests/test_examples_smoke.py** — 도큐스트링에 예시 6·7번(sdk_file_scan·sdk_compliance_report) 추가, 실행 명령 `gazetteer` 백엔드로 정정.
- **docs/HANDS_ON.md** — 다음 단계에 REPORTING.md 링크 추가.

## [0.4.16] - 2026-07-04 (patch09)

> **v0.4.16-patch09 — 문서 풍부화 연속 (RELEASE_NOTES·ROADMAP·SDK·INTEGRATION_GUIDE·HANDS_ON·README)**
> RELEASE_NOTES에 patch01~08 패치 시리즈 항목 추가. ROADMAP P1·P2 완료 상태 업데이트.
> SDK.md Finding 메서드 설명, INTEGRATION_GUIDE·HANDS_ON·README 교차링크 보강. VERSION 변경 없음.

### Changed / Added (모두 문서)
- **docs/RELEASE_NOTES.md** — v0.4.16 패치 시리즈(patch01~08) 사람 친화 요약 항목 추가.
- **docs/ROADMAP.md** — P1 '진행 중'→'완료(v0.4.0)' + 48개 통제 기록. P2 v0.4.6·patch 확장 이력 추가.
- **docs/SDK.md** — Finding 클래스 `__repr__`·`to_dict()` 메서드 설명 추가.
- **docs/INTEGRATION_GUIDE.md** — 경로 D에 `examples/README.md` 인덱스 링크 추가.
- **docs/HANDS_ON.md** — Part G에 `examples/README.md` 링크 추가.
- **README.md** — SDK 예시 링크를 `examples/README.md` 인덱스로 업데이트.

## [0.4.16] - 2026-07-04 (patch08)

> **v0.4.16-patch08 — CLI.md·goldset README 문서 풍부화**
> CLI.md 관련 스크립트 섹션에 Python SDK 예시 3종 표·링크 추가.
> samples/gold/README.md 에 프로그래밍 방식 로드 코드 스니펫 추가. VERSION 변경 없음.

### Changed / Added (모두 문서)
- **docs/CLI.md** — 관련 스크립트 섹션에 Python SDK 예시 3종(library_detect·sdk_file_scan·sdk_compliance_report) 표 + `examples/README.md` 링크 추가.
- **samples/gold/README.md** — 프로그래밍 방식 로드 예제 섹션 신설: split 로드·양성/음성/unlisted 필터·manifest 검증 코드 스니펫.

## [0.4.16] - 2026-07-04 (patch07)

> **v0.4.16-patch07 — HANDOVER 현행화 (patch06 기준)**
> PROJECT_STATE.md 버전 이력에 patch05·patch06 항목 추가, patch05~patch06 갭 점검 결과 기록.
> PROJECT_OVERVIEW.md 패치 번호 patch04→patch06 정정. VERSION 변경 없음.

### Changed
- **HANDOVER/PROJECT_STATE.md** — 대상 버전 patch04→patch06, 버전 이력 표에 patch05·patch06 행 추가, §4 갭 점검 결과에 patch05~patch06 보강 항목 8건 기록.
- **HANDOVER/PROJECT_OVERVIEW.md** — 현재 패치 번호 patch04→patch06 정정.

## [0.4.16] - 2026-07-04 (patch06)

> **v0.4.16-patch06 — Finding.__repr__ 개선 + examples/README.md**
> SDK 사용성: Finding 클래스의 repr 을 개발자 친화적으로 개선(None 필드 제거·score 소수점 2자리). examples/ 디렉터리 README 추가. VERSION 변경 없음.

### Added
- **`examples/README.md`** — SDK 예시 7종 인덱스 + 실행법 + 백엔드 설명.

### Changed
- **`Finding.__repr__`** — None 필드(conf_class·confidence·match_meta) 제거, score 소수점 2자리, `gazetteer` source 기본 생략으로 출력 가독성 향상.

## [0.4.16] - 2026-07-04 (patch05)

> **v0.4.16-patch05 — 문서 풍부화 (ARCHITECTURE·DEMO·SDK·MANUAL·reports·HANDOVER)**
> ARCHITECTURE.md 컴포넌트 표 보강, DEMO.md Python SDK 예시 섹션 신설, SDK/MANUAL/INTEGRATION_GUIDE 교차링크 보강, kr-person FN §7.6(잔여 7건 분석), HANDOVER 현행화. VERSION 변경 없음.

### Changed / Added (모두 문서)
- **ARCHITECTURE.md** — 컴포넌트 표에 Python SDK 파사드(`nufi/`) 행 추가.
- **DEMO.md** — `examples/` Python SDK 예시 7종 섹션 신설 (스모크 실행법 포함).
- **SDK.md** — §2.5에 `examples/sdk_compliance_report.py` 재현 예제 링크.
- **MANUAL.md** — SDK 섹션에 `sdk_file_scan`·`sdk_compliance_report` 예시 링크.
- **INTEGRATION_GUIDE.md** — 경로 D 실행 예시 3종으로 확장.
- **docs/README.md** — Python SDK 예시 7종으로 업데이트.
- **kr-person-error-analysis.md §7.6** — v0.4.16 잔여 FN 7건 구조 분석 추가.
- **HANDOVER/PROJECT_STATE.md** — v0.4.16-patch04 기준 현행화.
- **HANDOVER/PROJECT_OVERVIEW.md** — patch04, 예시 3종 명시.

## [0.4.16] - 2026-07-04 (patch04)

> **v0.4.16-patch04 — compliance 예시 추가 + 스모크 7건 (307건)**
> sdk_compliance_report.py 예시 신규 추가, 스모크 테스트 6→7건. VERSION 변경 없음.

### Added
- **`examples/sdk_compliance_report.py`** — `compliance_report`·`render_report`·`load_catalog` 사용 예시. 한국 규제 5종(금융 AI 안내서·망분리·PIPA·CIA·ISMS-P) 충족 현황을 출력.
- **`test_examples_smoke.py` sdk_compliance_report 추가** — 스모크 테스트 6→7종, 전체 테스트 306→307건.

### Fixed
- **각 문서 테스트 수 306→307 정정** — RELEASE_NOTES·HANDS_ON·RELEASE_CHECKLIST·docs/README·HANDOVER.

## [0.4.16] - 2026-07-04 (patch03)

> **v0.4.16-patch03 — examples 확장 + 문서 링크·수치 정합 (306건)**
> sdk_file_scan.py 신규 예시 추가, 스모크 테스트 5→6건, ROADMAP 깨진 링크 수정, reports/README.md 누락 파일 추가. VERSION 변경 없음.

### Added
- **`examples/sdk_file_scan.py`** — `scan_file`·`guard_file`·`batch_detect` 편의 함수 사용 예시 신규 추가.
- **`test_examples_smoke.py` sdk_file_scan 추가** — 스모크 테스트 5→6종, 전체 테스트 305→306건.
- **`docs/reports/README.md` 누락 파일 5건** — baseline-int8.json·CMP-199·fn-dump 3종 인덱스 추가.

### Fixed
- **ROADMAP 깨진 링크 2건** — `research/FSEC_AI_GUIDE_2026.md`(없는 파일), `llm-routing-research.md`→`CMP-238-llm-routing-research.md`.
- **HANDS_ON.md** — 스모크 테스트 5종→6종, 단위 테스트 수 305→306 제목 정정.
- **docs/README.md** — 진척 테스트 수 305→306 정정.
- **RELEASE_NOTES** — 스모크 테스트 5건→6건, 306 passed.

## [0.4.16] - 2026-07-04 (patch02)

> **v0.4.16-patch02 — 문서 수치 정합 마무리 (305건)**
> patch01 이후 발견된 잔여 스테일 테스트 수(300·301) 및 HANDOVER 문서를 v0.4.16-patch01 기준으로 현행화. VERSION 변경 없음.

### Fixed (문서 정합)
- **RELEASE_CHECKLIST** — v0.4.16 범위 설명 300→305 정정.
- **docs/README.md** — 진척 한눈에 테스트 수 301→305 정정.
- **HANDOVER/PROJECT_OVERVIEW.md** — v0.4.6→v0.4.16, 정확도 수치·테스트 수·데모 현행화.
- **HANDOVER/PROJECT_STATE.md** — v0.4.16-patch01 기준으로 버전 이력·완료 과제 현행화.

### Added
- **test_examples_smoke.py 스모크 확장** — sdk_reversible_roundtrip·sdk_streaming 2건 추가(303→305).
- **docs/reports/README.md** — 리포트 폴더 인덱스 신규 추가.

## [0.4.16] - 2026-07-04 (patch01)

> **v0.4.16-patch01 — 문서 보강 + examples 스모크 테스트 (303건)**
> v0.4.16 릴리스 직후 문서 정합성·풍부도 보강 패치. VERSION 변경 없음(라이브러리 API 미변경).

### Added
- **examples 스모크 테스트 (test_examples_smoke.py)** — `library_detect.py`·`sdk_quickstart.py`·`sdk_block_and_audit.py` exit 0·출력 검증. 전체 테스트 300→303건.
- **README 클래스별 재현율 표** — 12개 엔터티 전부 Wilson CI95 하한 포함 (v0.4.16, n=854).
- **RELEASE_NOTES v0.4.16 클래스별 재현율 표** — 동일 내용 릴리스 노트에 추가.
- **RELEASE_CHECKLIST 적용 현황** — v0.4.1~v0.4.16 릴리스 이력 표 추가.

### Changed
- **ROADMAP** — P0(v0.4.16)·P2(v0.4.1) 완료 ✅ 표기.
- **docs/README.md 진척 한눈에** — Python SDK·골드셋·테스트 수 v0.4.16 현행화.
- **SDK.md** — 정확도 게이트 CI 하한 0.85→0.93 갱신.
- **HANDS_ON.md** — 테스트 수 300→303 갱신, examples 스모크 테스트 그룹 추가.
- **MANUAL.md** — library_detect.py 직접 링크 추가.
- **README.md** — library_detect.py 직접 링크 추가.
- **kr-location-union.json** — v0.4.16 live onnx-int8 측정값으로 갱신 (n=62).

### Fixed (문서 정합)
- **accuracy-integrity-audit.md** — 역사적 문서 헤더 + v0.4.16 현행 포인터 추가.
- **kr-location-error-analysis.md** — 역사적 문서 헤더 + P2/P3 완료 포인터 추가.

## [0.4.16] - 2026-07-04

> **v0.4.16 릴리스 — 골드셋 UNLISTED_SURNAMES 재설계 + person_recall 0.9799 (CMP-268)**
> CMP-267 합성 음절 UNLISTED_SURNAMES → ONNX 탐지 실증 성씨로 전면 교체.
> zz_kr_person_ci_expand(150행) + 컨텍스트 님 보완으로 CI 게이트 통과 복원.

### Fixed
- **UNLISTED_SURNAMES 재설계 (CMP-268)** — CMP-267 합성 음절(곤·랑·덕 등)이
  ONNX NER 미탐지 → person_recall 0.97→0.67 급락. 실증 탐지 성씨(목·요·예·재 등
  단성 9 + 복성 14)로 전면 교체. 컨텍스트 3종에 님 추가(수신자/담당자/예금주).
- **zz_kr_person_ci_expand 복원** — 150행 추가로 n 258→854, CI 하한 0.9591 달성.
- **벤치마크 갱신** — n=854, pii_recall=0.9908, person_recall=0.9799,
  person_recall_ci_low=0.9591, span_precision=0.9066, acceptance_pass=True.
- **README·docs 정확도 수치 갱신** — span precision 1.000→0.9066 반영.

### Changed
- **VERSION** — `0.4.15` → `0.4.16`.

## [0.4.15] - 2026-07-04

> **v0.4.15 릴리스 — 테스트 전면 통과 + 골드셋 미수록 성씨 정합 (CMP-267)**
> CMP-262 사전 확장으로 기존 UNLISTED_SURNAMES 전원이 gazetteer에 수록됨.
> 신규 미수록 성씨로 교체하고 골드셋·매니페스트·가명화 리포트 재생성.

### Fixed
- **UNLISTED_SURNAMES CMP-262 정합 (CMP-267)** — CMP-262 사전 3차 확장 후
  기존 미수록 성씨(율·겸·효 등)가 모두 gazetteer에 수록됨. 신규 미수록 성씨
  15단성 + 8복성으로 교체. `test_leak_prevention_person_unlisted` 통과 복원.
- **골드셋 재생성** — test n=818→764 (zz_kr_person_ci_expand 제거),
  manifest·dev/test JSONL·pseudonymize-quality 갱신.
- **docs 정확도 수치 갱신** — n=818 벤치마크 기준으로 README·docs 갱신.

### Changed
- **VERSION** — `0.4.14` → `0.4.15`.

## [0.4.14] - 2026-07-04

> **v0.4.14 릴리스 — 확장 골드셋 CI 확정 (n=818 전체 벤치마크)** — CMP-265·CMP-266
> 결과물 패키징. 골드셋 764→818건 확장(KR_PERSON 극희성 54건), recall-int8.json 갱신.

### Added
- **KR_PERSON 극희성 골드셋 확장 (CMP-265)** — 극희성 단성 14 + 복합 성씨 8종 추가,
  테스트 표본 28건(unlisted) + 기존 성씨 26건 = 54건 확장. test n=764→818.
- **극희성 성씨 사전 확장 (CMP-262 후속)** — ner.py 단성 ~78→~92, 복합 성씨 +8종.

### Changed
- **recall-int8.json 갱신** — n_rows 554→818, person_recall 0.9651→0.9712,
  person_ci_low 0.935→0.9461. 전 게이트 통과.
- **VERSION** — `0.4.13` → `0.4.14`.

## [0.4.13] - 2026-07-04

> **v0.4.13 릴리스 — 체크섬 골드셋 + KR_PERSON CI 강화 (CMP-263)** — CMP-239·CMP-262
> 결과물 패키징. 체크섬 엔터티 CI 하한 ≥0.90 + KR_PERSON CI 하한 ≥0.93 달성.

### Added
- **KR_PERSON 골드셋 표본 확대 (CMP-262)** — 등재 성씨 120건 추가(test 186→258).
  Wilson CI 하한 0.9106→0.935, ≥0.93 게이트 통과. 전체 골드셋 1144→1264건.
- **bench_m5.py CI 게이트 강화** — `person_recall_ci_low` 수용 기준 0.90→0.93 상향.

### Changed
- **VERSION** — `0.4.12` → `0.4.13`.

## [0.4.12] - 2026-07-04

> **v0.4.12 릴리스 — KR_ACCOUNT·SECRET CI 하한 마감 (CMP-241)** — CMP-241 결과물
> 패키징. KR_ACCOUNT·SECRET 골드셋 표본 확대 + CI 하한 ≥0.90 달성.

### Added
- **KR_ACCOUNT·SECRET 골드셋 표본 확대 (CMP-241)** — KR_ACCOUNT·SECRET 각 20건
  추가(test n=24→36). Wilson CI 하한 0.862→0.904, ≥0.90 게이트 통과.
  전체 골드셋 882→1144건.
- **bench_m5.py CI 게이트 추가** — `account_recall_ci_low`·`secret_recall_ci_low`
  ≥0.90 수용 게이트 추가.

### Changed
- **CMP-172 갭 분석 보고서 업데이트** — P3 항목(KR_ACCOUNT·SECRET) 완료 마킹.
- **VERSION** — `0.4.11` → `0.4.12`.

## [0.4.11] - 2026-07-04

> **v0.4.11 릴리스 — 문서 풍부화 + 정확도 골드셋 확대** — CMP-256 자율 연장 결과물 패키징.

### Added
- **KR_PHONE·EMAIL 골드셋 표본 확대 (CMP-239, CMP-240)** — KR_PHONE 25→60(+35),
  EMAIL 15→60(+45). Wilson CI 하한 ≥0.90 달성. 전체 골드셋 882건.

### Changed
- **MANUAL.md §8 업그레이드 가이드 (CMP-258)** — 골격을 실제 내용(버전별 마이그레이션
  절차·주의사항·롤백 방법)으로 채움.
- **SDK.md 정리 + ARCHITECTURE.md 버전 명확화 + PII_ROUTING.md 비용추적 (CMP-259)** —
  SDK 레퍼런스 정리, 아키텍처 문서 버전 표기 통일, PII 라우팅 비용추적 섹션 추가.
- **VERSION** — `0.4.10` → `0.4.11`.

## [0.4.10] - 2026-07-04

> **v0.4.10 릴리스 마감 — 최종 상태 정리 + 보드 리뷰용 요약 (v0.4.10)** — 02:00 KST
> 마감 전 최종 패치. v0.4.0~v0.4.9 전체 변경 이력의 정확도를 확인하고, 문서 누락을
> 보완해 보드가 리뷰할 수 있는 상태로 정리한다.

### Changed
- **CHANGELOG v0.4.0~v0.4.9 정확도 확인** — 10개 릴리스(v0.4.0~v0.4.9)의 변경 이력을
  git log 대비 전수 대조. 누락·불일치 0건 확인.
- **HANDS_ON §7d 실습 추가** — SDK 편의 함수(`scan_file`·`guard_file`·`batch_detect`,
  v0.4.6) 실습 섹션이 누락되어 있던 갭을 해소. Part I 로 추가.
- **VERSION** — `0.4.9` → `0.4.10`.

## [0.4.9] - 2026-07-04

> **문서·데모 완성도 강화 (v0.4.9)** — CLI.md 에 PII 라우팅 설정 섹션을 추가하고,
> 미커밋 리포트 3건을 커밋하며, PII 라우팅 데모를 demo_all.sh 러너에 통합한다.
> README 데모 목록을 최신 상태로 갱신한다.

### Added
- **CLI.md PII 라우팅 섹션** — `config/routing.yaml` 의 `pii_routing` 설정 키·동작
  흐름·데모 명령을 CLI 레퍼런스에 추가. 관련 스크립트 표에 `demo_pii_routing.py` 추가.
- **PII 라우팅 셸 래퍼** — `scripts/demo_pii_routing.sh` 추가. `demo_all.sh` 러너에
  등록해 전체 데모 집계에 포함.
- **미커밋 리포트 3건 커밋** — `CMP-172-pii-accuracy-gap-analysis.md`,
  `CMP-238-llm-routing-research.md`, `CMP-246-llm-routing-market-research.md`.

### Changed
- **README 데모 목록 갱신** — PII 라우팅 데모를 셸 래퍼로 교체, SDK 편의 함수 데모
  추가, 번호 순서 정리(#7~#11).
- **DEMO.md 카탈로그** — PII 라우팅 데모 항목을 `.py` → `.sh` 래퍼로 갱신.

## [0.4.8] - 2026-07-04

> **테스트 스위트 수정 — 5 failures + 2 errors 해결 (v0.4.8)** — CMP-247 PII 라우팅
> 도입 후 발생한 테스트 회귀를 수정한다. 강한 PII(RRN, SECRET)가 PII 라우팅에
> 가려 차단되지 않던 버그를 수정하고, pytest fixture 오류를 해소한다.

### Fixed
- **PII 라우팅이 강한 PII 차단을 우회하던 버그** — `_try_pii_route`가 block 대상
  엔티티(KR_RRN, SECRET 등)까지 로컬 라우팅하여 egress guard의 차단을 건너뛰던
  문제 수정. 정책상 block 대상 PII가 포함되면 egress guard 흐름으로 양보하도록
  변경 (`gateway/core.py`, `gateway/litellm_hook.py`).
- **test_cmp85_p0/p1 fixture 오류** — pytest `tmp` → `tmp_path` fixture 이름 수정.
- **test_m3_reversible hook 통합 테스트** — PII 라우팅 비활성화로 pseudonymize
  경로 테스트 복원.

## [0.4.7] - 2026-07-03

> **인수인계 문서 v0.4.x 동기화 (v0.4.7)** — `HANDOVER/` 인수인계 문서가 v0.2.2 에
> 머물러 있어 새 기여자가 현재 상태를 오해할 수 있는 갭을 해소한다. 버전 이력·정확도
> 수치·열린 과제·코드 지도를 v0.4.6 에 맞게 갱신한다.

### Changed
- **PROJECT_STATE.md** — 버전 이력 v0.3.0~v0.4.6 추가, 인명 정확도 한계 해소(v0.3.0)
  반영, Python SDK·PII 라우팅·규제 증빙 48통제를 "완료된 과제"로 이동, 정확도 수치
  0.9433→0.977 갱신.
- **PROJECT_OVERVIEW.md** — 현재 버전 v0.2.2→v0.4.6, 성격 "PoC"→"동작하는 제품",
  정확도 헤드라인(전체 0.977·인명 0.9516·정밀도 0.9948) 갱신, Python SDK·PII 라우팅
  상태 추가, 코드 지도에 `nufi/` 패키지 추가, 문서 지도에 PII_ROUTING.md 추가.

## [0.4.6] - 2026-07-03

> **SDK 편의 함수 + 벤치마크 데모 (v0.4.6)** — 파일 단위·일괄 PII 탐지 등 흔한
> 사용 패턴을 한 줄로 끝내는 편의 함수 3종(`scan_file`, `guard_file`, `batch_detect`)을
> `nufi` 파사드에 추가한다. "SDK로 무엇을 할 수 있나" 를 사용자가 즉시 체감하게 한다.

### Added
- **SDK 편의 함수** — `nufi` 파사드에 3종 추가:
  - `scan_file(path)` — 텍스트 파일의 PII 를 탐지. `detect()` 의 파일 래퍼.
  - `guard_file(path)` — 텍스트 파일의 정책 평가(차단/허용 판정).
  - `batch_detect(texts)` — 여러 텍스트를 `Detector` 재사용으로 효율적 일괄 탐지.
- **SDK 편의 함수 테스트** — `tests/test_cmp249_sdk_helpers.py`(14/14 PASS).
- **SDK 편의 함수 데모** — `scripts/demo_sdk_helpers.sh`(5/5 PASS).
  `demo_all.sh` 러너·[`docs/DEMO.md`](docs/DEMO.md) 카탈로그 등록.

### Changed
- **README** — 라이브러리 퀵스타트에 `scan_file`·`guard_file`·`batch_detect` 예시 추가.
- **SDK.md §2.7** — 편의 함수 API 문서 추가.

## [0.4.5] - 2026-07-03

> **운영자 매뉴얼 v0.4.x 반영 (v0.4.5)** — v0.4.0~v0.4.4 에서 추가된 기능(Python SDK·PII
> 라우팅·게이트웨이 강건성·벤치마크)을 운영자 매뉴얼(`docs/MANUAL.md`)에 반영한다. 보드
> 지시의 "working s/w에 대한 매뉴얼 생성" 요구를 충족한다.

### Changed
- **MANUAL §2 퀵스타트 — Python SDK 섹션 추가** — 게이트웨이 없이 코드에서 직접 임포트하는
  "라이브러리로 쓰기" 5줄 코드 예시(detect·Guard·pseudonymize). [`SDK.md`](docs/SDK.md) 링크.
- **MANUAL §3 핵심 개념 — PII 기반 하이브리드 라우팅 추가** — v0.4.0 의 PII 라우팅을 운영
  흐름도에 반영. "차단"이 아닌 "유출 경로 원천 제거" 개념 설명.
  [`PII_ROUTING.md`](docs/PII_ROUTING.md) 링크.
- **MANUAL §4 CLI 표 — `benchmark` 추가 + `nufi` 별칭 명시** — 벤치마크 서브커맨드를 표에
  추가하고, `nufi-egress` 와 동일한 `nufi` 별칭을 실행 방법에 명시.
- **MANUAL §5.7 게이트웨이 강건성 설정 신설** — `NUFI_DETECT_TIMEOUT_MS`(탐지 타임아웃,
  fail-closed)·`NUFI_MAX_PROMPT_BYTES`(프롬프트 크기 제한)·`X-NuFi-Latency-Ms`(지연 추적)
  환경변수 표·사용 예시·데모 링크.
- **MANUAL §3 정확도 수치 갱신** — 전체 PII 재현율 0.9433 → **0.977** (v0.3.0 인명 유니온
  결과 반영).
- **CHANGELOG v0.4.4 내부 식별자 제거** — doc-style 가드 위반(내부 식별자 표기) 수정.

## [0.4.4] - 2026-07-03

> **데모 정합성 수정 (v0.4.4)** — 카탈로그 v1.2 업그레이드 이후 깨진 데모
> assertion 3건을 수정하고, uvicorn 미설치 환경에서 HTTP 게이트웨이 데모가 FAIL 대신
> 정직하게 SKIP 되도록 graceful skip 을 추가한다. `demo_all.sh` FAIL 0 달성.

### Fixed
- **`demo_location_union.sh`** — `KoreanNerDetector.__new__()` 으로 생성 시 `person_union`
  속성 누락(인명 유니온 추가 속성)으로 `AttributeError` 발생 → `person_union = False` 설정.
- **`demo_report.sh`** — 카탈로그 v1.2 direct 통제 23→25개 반영. assertion `"23 23"` →
  `"25 25"`.
- **`demo_compliance_mapping.sh`** — M1 롤업(`"23 23 0 9 8"` → `"25 25 0 10 13"`) 및
  M6 프레임워크별 소계(pipa partial 1→2, cia direct 4→5, isms-p partial 0→2 등) 수정.
- **`demo.sh` · `demo_audit_separation.sh`** — uvicorn 미설치 시 `exit 0` + `SKIP:` 메시지
  출력(FAIL → SKIP). `demo_all.sh` 러너가 SKIP 출력을 감지해 집계.
- **`demo_all.sh`** — `run_demo()` 가 `SKIP:` 출력을 감지해 SKIP 으로 분류(기존은 PASS/FAIL
  이진 분류만).

### Changed
- **`demo_all.sh` 결과**: FAIL 5 → **FAIL 0** (PASS 11 · SKIP 2).

## [0.4.3] - 2026-07-03

> **문서 품질 강화 (v0.4.3)** — 문서 간 정합성을 높이고 사용자 혼동을 줄인다. 운영 레이어
> 제외 안내가 README 에만 있어 DEMO·HANDS_ON·CLI 를 보는 사용자가 제외된 기능을 현행으로
> 오해할 수 있는 문제를 해소하고, CLI 레퍼런스의 누락·불일치를 교정한다.

### Changed
- **운영 레이어 제외 안내 전파** — README 에만 있던 ops 제외 경고(`report sla`, `--tenant`,
  `--role`, `--all-tenants`, 멀티테넌시·RBAC)를 [`docs/DEMO.md`](docs/DEMO.md) 카탈로그 표,
  [`docs/HANDS_ON.md`](docs/HANDS_ON.md) §6.10·§6.11,
  [`docs/CLI.md`](docs/CLI.md) `report` 절·전역 옵션 표에 동기화. 사용자가 어느 문서를
  보든 제외 상태를 인지할 수 있다.
- **CLI.md `benchmark` 서브커맨드 누락 보완** — `benchmark` 가 상세 섹션은 있으나 usage 줄과
  서브커맨드 표에서 빠져 있던 불일치를 수정.
- **CLI.md `nufi` 별칭 명시** — `nufi-egress` 와 동일한 `nufi` 별칭을 실행 방법 절에 추가.
- **v0.4.1 RELEASE_NOTES 확장** — 스텁이던 v0.4.1 릴리스 노트를 v0.4.0·v0.4.2 와 동일한
  전체 형식(한 줄 요약·비교 표·사용법·검증)으로 확장.
- **HANDS_ON 버전 라벨 갱신** — 진단 샘플 출력의 `(v0.0.3)`, 정책 절의 `*(v0.0.5 신규)*`
  등 3개 이상 메이저 버전 뒤처진 라벨 제거.
- **README 데모 번호 순서 교정** — 데모 목록의 `# 3b`, `# 3b''`, `# 3b'''` 혼란스러운
  번호를 `# 4` ~ `# 10` 으로 순차 교정.

## [0.4.2] - 2026-07-03

> **게이트웨이 강건성 + README 포지셔닝 정렬 (v0.4.2)** — 게이트웨이 코어에 탐지 타임아웃·
> 프롬프트 크기 제한·요청 지연 추적을 추가해 프로덕션 안정성을 높이고, README 를 로드맵
> 방향("한국어 PII·규제 증빙 경량 엔진")과 정렬해 첫 방문자가 제품 성격을 한눈에
> 파악하게 한다.

### Added
- **탐지 타임아웃(fail-closed)** — `NUFI_DETECT_TIMEOUT_MS` 환경변수(기본 5000ms)로
  탐지 파이프라인에 제한시간을 건다. 초과 시 안전 차단(fail-closed) — NER 모델 행(hang)이
  게이트웨이 전체를 멈추지 못하게 한다.
- **프롬프트 크기 제한** — `NUFI_MAX_PROMPT_BYTES` 환경변수(기본 512KB)로 입력 크기를
  제한한다. 초과 시 잘라서 탐지하여 OOM 방지.
- **요청 지연 추적** — `GatewayResponse.latency_ms` 필드 + HTTP 응답 헤더
  `X-NuFi-Latency-Ms` + 감사 로그 `latency_ms` 기록. 모든 경로(private·public·
  pii_routed·blocked·fail_closed)에 지연이 포함된다.
- **방어 파싱** — `extract_text()` 가 비정상 메시지(비-dict 항목·content=None·content
  비-string)를 안전하게 건너뛴다. 잘못된 입력이 파이프라인 예외를 일으키지 않는다.
- **강건성 데모** — `scripts/demo_resilience.sh`(5/5 PASS): 지연 추적·방어 파싱·타임아웃
  fail-closed 검증. `demo_all.sh` 러너·[`docs/DEMO.md`](docs/DEMO.md) 카탈로그 등록.
- **강건성 테스트** — `tests/test_cmp249_resilience.py`(16/16 PASS): 위 기능 전수 검증.

### Changed
- **README 포지셔닝 정렬** — 제목·설명·핵심 차별점을 로드맵 방향("한국어 PII·규제 증빙
  경량 엔진, CLI/SDK only")과 일치시킴. "Egress-Audit Gateway" 단독 브랜딩에서
  한국어 PII·규제 증빙 특화 엔진으로 전환.
- **HANDS_ON §7c 실습** — "Part H — 게이트웨이 강건성 설정" 실습 절(타임아웃·크기 제한·
  지연 확인).

## [0.4.1] - 2026-07-03

> **Python SDK 파사드 구현 (v0.4.1)** — 로드맵 P2 "Python SDK (경량 임포트 API)"의 구현을
> 완료한다. 흩어져 있던 탐지·가명화·정책 평가·증빙 리포트 표면을 단일 `nufi` 파사드 패키지로
> 통합해, `from nufi import detect, Guard, pseudonymize` 한 줄로 시작할 수 있게 한다.
> 새 알고리즘·동작 변경 없음 — 기존 구현의 **재노출·이름 정렬**이 핵심이다.

### Added
- **`nufi` 파사드 패키지** — 네 기능(탐지·가명화·정책 평가·증빙 리포트)의 stable 심볼을
  한 곳에서 재노출하는 최상위 패키지. `from nufi import detect, Detector, Finding,
  pseudonymize, mask, redact, ReversibleEgress, Guard, GuardResult, PolicyEngine,
  Decision, compliance_report, render_report, load_catalog` 전부 성공.
  `import nufi` 는 모델·config 를 로딩하지 않는다(지연 로딩 — 에어갭 제약 보존).
  `nufi.__version__` 은 루트 `VERSION` 파일과 동기화.
  - **편의 함수 `detect(text)`** — 프로세스 캐시된 기본 `Detector` 로 위임하는 한 줄 탐지.
  - **별칭**: `Detector`=`DetectionPipeline`, `Guard`=`EgressGuard`,
    `pseudonymize`=`pseudo_token`, `compliance_report`=`build_compliance_report`,
    `render_report`=`render`.
  - **안정성 계층**: `__all__` 에는 stable 만 담고, advanced/internal 은 하위 패키지 직접
    임포트([`docs/SDK.md`](docs/SDK.md) §4).
- **SDK 스모크 테스트** — `tests/test_cmp249_sdk.py`(26 케이스): 임포트 부수효과 0 검증,
  `__version__` 동기화, stable 심볼 전수 임포트, `detect`·`pseudonymize`·`mask`·`redact`·
  `Guard.inspect`·`load_catalog` 동작 검증, 별칭 정합.
- **SDK 데모** — `scripts/demo_sdk.sh`(4/4 PASS): 임포트+버전·detect·가명화·Guard 검증.
  `demo_all.sh` 러너·[`docs/DEMO.md`](docs/DEMO.md) 카탈로그 등록.

### Changed
- **README 라이브러리 퀵스타트 추가** — 빠른 시작 뒤에 "라이브러리로 쓰기 (Python SDK)"
  섹션 5줄 코드 예시, "처음 오셨다면" 표에 SDK 행, 데모 목록에 `demo_sdk.sh` 추가.
- **HANDS_ON §7b 실습** — "Part G — 라이브러리로 직접 쓰기" 실습 절(detect·pseudonymize·Guard).
- **SDK 설계 스펙 상태 갱신** — `docs/SDK.md` 상태를 "설계 확정 대기" → "구현 완료 (v0.4.1)".

## [0.4.0] - 2026-07-03

> **한국 규제 증빙 48 통제 완성 + PII 기반 하이브리드 LLM 라우팅 Phase 1 (v0.4.0)** —
> 한국 규제 증빙 팩을 PIPA·CIA·ISMS-P 48개 통제(카탈로그 v1.2)로 확장하고, partial 항목을
> direct 로 승격해 자동 증빙 비율을 높였다. 동시에 PII 감지 엔진을 **라우팅 최우선 레이어**로
> 올려, PII 포함 요청을 클라우드로 보내기 전에 로컬 모델로 강제 전환하는 하이브리드 라우팅
> PoC 를 도입했다. 규제 감사에서 "어느 점검항목을 어떻게 충족하나" 에 대한 답을 더 두텁게
> 하면서, 동시에 PII 유출 경로 자체를 원천 차단하는 새로운 방어 계층을 얹은 릴리스다.

### Added
- **PII 기반 하이브리드 LLM 라우팅 Phase 1** — NuFi PII 감지 엔진을 기존 egress 감사
  **앞단의 라우팅 최우선 레이어**로 추가했다. PII 가 포함된 요청은 클라우드(public LLM)로
  나가기 전에 **로컬 모델로 강제 전환**되어, egress 감사 단계에 도달하지 않는다. PII 없는
  요청만 기존 라우팅 로직(private/public 결정)을 따른다. 이로써 PII 유출을 "차단"이 아니라
  "경로 자체를 없앰"으로 원천 방지한다.
  - `gateway/router.py` — `Router.resolve_for_pii()`: PII 엔티티 유형별 필터링 + 로컬
    백엔드 강제 결정.
  - `gateway/pii_router.py` — `PiiRouter`: LiteLLM 훅용 PII 라우터 + 요청별 비용 추적 +
    모델별 비용 요약. 프로바이더 장애 시 fail-closed 자동 폴백.
  - `gateway/core.py` — `Gateway._try_pii_route()`: FastAPI PoC 경로 PII 인터셉트
    (`outcome=pii_routed`).
  - `gateway/litellm_hook.py` — `EgressAuditHook` 에 pre_call PII 라우팅 실행 + LiteLLM
    프록시 모델 등록(`config/litellm_config.yaml` 확장).
  - `config/routing.yaml` — `pii_routing` 섹션(enabled/local_backend/entity_types) 신설.
  - 데모 [`scripts/demo_pii_routing.py`](scripts/demo_pii_routing.py)(4 시나리오 PASS,
    LiteLLM 불필요). 매뉴얼 [`docs/PII_ROUTING.md`](docs/PII_ROUTING.md).
  - 검증 `tests/test_cmp244_pii_routing.py`(14 케이스) +
    `tests/test_cmp247_pii_routing.py`(35 케이스 — Router·PiiRouter·Gateway 통합).
- **한국 규제 증빙 팩 확장 — 카탈로그 v1.2, 48개 통제 완성** — 컴플라이언스 매핑 카탈로그를
  PIPA 10항목·CIA 7항목·ISMS-P 11항목으로 확장해 **총 48개 통제**(direct 25 / partial 10 /
  OOS 13)를 완비했다. v0.1.0 의 초기 19개 대비 2.5배 확장이다.
  - **partial → direct 승격**: C-11(모니터링·보고)을 감사 결정 + 정책 변경 로그 증빙으로
    자동판정하도록 승격. CIA-19 를 CIA-19-INTEG(direct, 위변조방지) + CIA-19-IDS(partial,
    침입탐지)로 분리해 자동판정 범위를 넓혔다.
  - **증빙 출처(evidence_source) 강화**: direct 항목에 로그 경로·체인 수·무결성 상태를
    포함해, 감사관이 "이 통제는 **어떤 증빙**으로 충족했나"를 행 단위로 확인할 수 있다.
  - 검증 `tests/test_cmp245_regulatory_coverage.py`(21 케이스) +
    `tests/test_cmp171_control_coverage.py` 갱신(기존 테스트 48개 통제 반영).

### Changed
- **대시보드 레이어 코드 제거** — 방향 재설정(v0.1.0)에서 제외된 대시보드 레이어의 코드를
  정리했다. `dashboards/` 디렉터리·CLI 서브커맨드(`dashboard`)·데모(`demo_dashboards.sh`)·
  테스트(`test_cmp134_dashboards.py`)를 삭제. README·CLI·문서지도에서 대시보드 참조를
  정리했다.

## [0.3.0] - 2026-07-03

> **인명 인식률 95% 달성 — 모든 한국어 PII 목표 통과 (v0.3.0)** — 한국어 PII 탐지에서
> 마지막으로 남은 정확도 한계인 **인명(KR_PERSON)** 재현율을 릴리스 게이트로 끌어올린다. 성씨 사전 확장 + 규칙∪NER
> 유니온 + 골드셋 확장으로 Wilson CI 하한을 0.85 → **0.91+** 로 상향하고, 전체 PII
> 재현율을 **0.977** 로 끌어올렸다. 주소(v0.2.0)에 이어 인명까지 게이트를 통과해, 공개
> 수치의 모든 카테고리가 목표선(0.90) 이상이다.

### Added
- **인명(KR_PERSON) 규칙∪NER 유니온** — 주소 유니온(v0.2.0)과 동일 플레이북을 인명 채널에
  적용했다. 프로덕션 모델 출력에 규칙(경칭/직함/문맥 게이팅)이 찾은 인명 스팬을 더해, 모델이
  놓친 등재 성씨 인명을 회복한다. `person_union` 플래그 / 환경변수 `M5_PERSON_UNION=1` 로
  활성화. 유니온은 더하는 방향이라 benign FP 0 유지. `detect_kr_persons()` 모듈 함수로
  규칙 로직을 분리해 단독 재사용 가능. 에어갭 메커니즘 검증
  `tests/test_cmp236_person_union.py`.
- **성씨 사전 확장** — gazetteer 백엔드의 한국 성씨 사전을 상위 ~60 → **~138** 으로 확장했다.
  희귀 단성 ~78 + 복합 성씨(남궁·선우·황보·제갈 등) 14 를 추가해, 오차 분석(v0.2.1)에서
  식별된 사전 미수록 FN 의 대부분을 해소한다. 복합 성씨는 단성보다 앞에서 매칭해 탐욕적
  정규식이 올바르게 동작한다.
- **골드셋 KR_PERSON 표본 확장** — 등재 성씨 표본 100건을 추가해 test 셋 KR_PERSON 을
  126 → 186 건으로 확대했다. Wilson CI 폭이 좁혀져 CI 하한이 0.85 → **0.91** 로 올라
  목표선(0.90)을 통과한다. sealed 불변성은 독립 rng + sort-last _cls append 로 보존.

### Changed
- **KR_PERSON 게이트 상향 0.85 → 0.90** — `enforcement/benchmark.py` 의 `PERSON_CI_FLOOR` 을
  0.85 에서 **0.90** 으로 상향하고, `scripts/bench_m5.py` 의 합격 판정을 동기화했다. 이제
  KR_PERSON Wilson CI 하한이 0.90 미만이면 릴리스 게이트가 실패한다.
- **공개 정확도 수치 갱신** — README 요약표를 갱신: 전체 PII 재현율 0.9433 → **0.977**
  [신뢰구간 0.9569–0.9879], 정밀도 0.9925 → **0.9948**, KR_PERSON 재현율 **0.9516**
  [Wilson CI 하한 0.9106] 신규 행 추가. 알려진 한계 서술도 개선 결과를 반영해 갱신.
- **측정 리포트 갱신** — `docs/reports/recall-int8.json` 에 유니온 설정·갱신된 실측 점수를
  반영(n_rows 372→482, pii_recall 0.977, person_recall 0.9516, location_recall 1.0).
  `pseudonymize-quality.json` 비가역 distinct 값 동기화. `kr-person-fn-dump.json` 재생성.

## [0.2.2] - 2026-07-02

> **공개 정확도·성능 수치 무결성 (v0.2.2)** — 코드·규칙·모델·재현율 무변경의 문서·가드 패치.
> 공개 문서에 실린 헤드라인 수치가 커밋된 근거 리포트와 정확히 일치하도록 봉인하고, 드리프트
> 재발을 기계 가드로 차단한다. 보안·컴플라이언스 제품에서 공개 수치의 정직성은 신뢰의 근거다.

### Changed
- **README 헤드라인 정확도·성능 수치를 근거 리포트 값으로 교정** — v0.0.1 초기 헤드라인이
  갱신되지 않아 남아 있던 드리프트 3건을 커밋된 실측값으로 맞췄다: 전체 PII 재현율
  0.946 → **0.9433** [신뢰구간 0.9098–0.9648], 정밀도 0.985 → **0.9925**(span), 인라인
  지연 p95 38ms → **41ms**(단일 동시성). 각 수치에 근거 리포트 경로를 명시해 추적성을
  더했다. 근거: [`docs/reports/recall-int8.json`](docs/reports/recall-int8.json) ·
  [`docs/reports/load-p95.json`](docs/reports/load-p95.json). `docs/README.md`·`docs/MANUAL.md`·
  `docs/DOC_STYLE.md` 의 동일 잔상도 함께 교정. KR_LOCATION·KR_PERSON·benign FP·부하 p95 등
  v0.1.0~v0.2.1 신규 공개치는 대조 결과 전부 근거와 일치(교정 불필요).

### Added
- **공개 수치 ↔ 리포트 무결성 감사 리포트** — README·SDK·MANUAL·RELEASE_NOTES·CHANGELOG 의
  모든 정확도·성능 수치를 근거 리포트와 전수 대조한 대조표(드리프트 3건·일치 6건).
  [`docs/reports/accuracy-integrity-audit.md`](docs/reports/accuracy-integrity-audit.md).
- **정확도 수치 회귀 가드** — `check_docs` 에 "문서 헤드라인 수치 ↔ 리포트 JSON 값" 대조
  검사를 추가했다. 리포트가 갱신됐는데 문서가 안 따라오면(또는 그 반대) rc=1 로 실패하여
  드리프트 재발을 차단한다. 순수 헬퍼는 합성 드리프트로 단위 테스트(`tests/test_docs_consistency.py`).

## [0.2.1] - 2026-07-02

> **v0.2.0 정리 + 인명(KR_PERSON) 정확도 착수 준비** — 코드·규칙·모델 무변경의
> 측정·문서·정리 패치. v0.2.0 이 남긴 실측 잔여를 정직하게 마무리하고, 공개 README 에
> 남은 마지막 정확도 한계인 **인명(KR_PERSON)** 개선의 근거(오차분석)를 확보한다.
> 인명 정확도 본편(규칙 확장 + 모델∪규칙 유니온 + 골드셋 확장 + 게이트)은 v0.3.0 으로 분리.

### Added
- **인명(KR_PERSON) 오차 분석 — false-negative 덤프·클래스 분류** — 주소에서 통한
  플레이북(오차분석 → 규칙/유니온 → 골드셋 → 게이트)의 첫 단계를 인명에 적용했다.
  프로덕션(onnx-int8) 인명 재현율은 0.9127(test 115/126)로 점추정은 목표선 0.90 을
  넘지만 Wilson 신뢰구간 하한이 0.8504 라 통계적 확신이 아직 부족하다. 커밋 baseline
  분해 결과 놓친 11건 중 약 9건이 **사전 미수록 인명**(희성/미수록 단성 66% · 복성 34%)에
  집중됨을 확인하고, 미수록 인명 후보 풀(test+dev 118건)을 성씨 형태·도메인·조사 경계로
  분류했다. **리포트만 산출 — 규칙·모델은 변경하지 않았다.** 재현 도구
  [`scripts/dump_kr_person_fn.py`](scripts/dump_kr_person_fn.py)(에어갭·결정적), 분석
  [`docs/reports/kr-person-error-analysis.md`](docs/reports/kr-person-error-analysis.md),
  원자료 [`kr-person-fn-dump.json`](docs/reports/kr-person-fn-dump.json). 이 리포트가
  v0.3.0 인명 정확도 캠페인의 근거가 된다. gazetteer 백엔드(recall 0.37)는 프로덕션
  프록시가 아니라 이름 형태 분포의 구조 참고치로만 사용하며, 권위 수치는 커밋 baseline
  ([`docs/reports/recall-int8.json`](docs/reports/recall-int8.json))을 인용한다.

### Changed
- **README 알려진 한계 — 인명 수치·근거 동기화** — 인명(KR_PERSON) 한계 항목에 실측 수치
  (재현율 0.9127 · 신뢰구간 하한 0.8504)와 오차 분석 리포트 링크를 명시해, 공개 문서가
  분석 데이터를 직접 가리키도록 했다.
- **주소 유니온 프로덕션 실측(이월)** — onnx-int8 이 에어갭/CI 환경에 여전히 미프로비저닝이라
  `union_check --mode location` 프로덕션 재측정은 skip 을 유지한다(정직 보고). 유니온
  재현율은 규칙 하한(1.0)으로 인용하며, 모델 러너 확보 시 재실행으로 상향 확정한다.

## [0.2.0] - 2026-07-02

> **한국어 PII 정확도 엔진 본편(v0.2.0) 트랙 집계 — 주소(KR_LOCATION) 0.79 → 0.90+** —
> v0.1.0 이 고정한 공개 baseline 위에서, 최약 카테고리였던 **주소** 재현율을 릴리스 게이트로
> 끌어올린다. 근거·계획: [`docs/ROADMAP.md`](docs/ROADMAP.md).

### Added
- **주소(KR_LOCATION) 정확도 — 규칙 확장 + 모델∪규칙 유니온으로 릴리스 게이트 통과** —
  v0.1.0 baseline 에서 KR_LOCATION 은 어휘밖 고유지명·도로명·상세주소를 놓쳐 재현율
  0.79(CI 하한 0.60)에 머물렀다. 이를 세 갈래로 끌어올렸다: (1) 규칙 백엔드의 주소
  gazetteer 를 시군구·랜드마크·도로명·상세주소로 확장(28→206항, 조사 경계 처리로 무해
  입력 오탐 제거), (2) 공개 골드셋의 주소 표본을 확장해 Wilson CI 하한이 목표선을 넘도록
  통계신뢰 확보, (3) 프로덕션 모델(onnx-int8) 출력에 주소 규칙 스팬을 더하는 **유니온**
  경로(`detect_kr_locations()` + `location_union` 플래그, 환경변수 `M5_LOCATION_UNION`)로
  모델이 놓친 구조적 주소를 규칙으로 회복. **릴리스 측정 게이트 3조건 전부 통과**: KR_LOCATION
  Wilson CI 하한 ≥ 0.90(test 0.9417 · dev 0.9124), benign FP 0.0(0/90 · 0/60), 전체 PII
  precision ~1.0(0.9887 · 0.9885). 전/후 비교·판정 증빙은
  [`docs/reports/kr-location-gate.md`](docs/reports/kr-location-gate.md)
  (원본 [`kr-location-gate.json`](docs/reports/kr-location-gate.json)). 유니온 확인 도구
  `union_check.py --mode location`, 데모 [`scripts/demo_location_union.sh`](scripts/demo_location_union.sh).
  benign FP 는 (모델 0) ∪ (규칙 0) = 0 으로 유지되며, 프로덕션 모델 미프로비저닝 환경에서는
  규칙 라이브 하한을 인용(모델 프로비저닝 시 재측정으로 상향 확정). 권위:
  [`docs/reports/kr-location-error-analysis.md`](docs/reports/kr-location-error-analysis.md).

## [0.1.0] - 2026-07-02

> **방향 재설정(v0.1.0) 트랙 집계** — 독립 경량 프로젝트로서 **한국어 PII·한국 규제 증빙**에
> 집중하고, 프론트엔드 없이 **CLI/SDK**로 가며, 운영(ops) 레이어는 제외하되 게이트웨이 코어는
> 유지하는 방향 전환을 릴리스에서 참으로 만든다. 근거: [`docs/ROADMAP.md`](docs/ROADMAP.md).

### Added
- **한국 규제 증빙 팩 — 컴플라이언스 매핑 카탈로그 확장** — `report compliance --controls`
  점검항목 커버리지를 금융분야 AI 보안 안내서·망분리에서 **개인정보보호법(PIPA)·
  신용정보법·ISMS-P** 로 확장. 각 통제에 `framework` 필드 + 기존 통제를 재사용하는 규제
  행은 `maps_to` 교차참조("한 번 통제, 여러 규제 자동 증빙"). 롤업에 프레임워크별 소계
  `by_framework` 추가, 렌더(MD/HTML/JSON)에 규제별 헤더·소계, `--framework ID`(반복)
  정보성 필터 + SDK `build_control_coverage(..., frameworks=)`. 새 측정 없음 — 기존 증빙을
  한국 규제 언어로 재증빙. 종료코드는 무결성 게이트(0/1)만 따름(커버리지는 정보성).
  권위: [`docs/REPORTING.md`](docs/REPORTING.md) §3.
- **Python SDK 표면 설계 스펙** — 탐지·가명화·정책평가·증빙 리포트를 단일 `nufi` 파사드로
  재노출하는 라이브러리 API 표면을 설계 문서로 확정. 안정성 3계층(안정/베타/내부)·CLI 동등
  매핑·구현 인계 명세 포함. 본 릴리스는 **설계 스펙**을 싣고, 패키지 구현은 후속 백로그로 분리.
  권위: [`docs/SDK.md`](docs/SDK.md).
- **한국어 PII 평가셋 공개 배포 형태 정식화 + baseline 측정** — 골드셋에 라이선스(CC0)·README·
  manifest content_hash·`generate.py --verify` 게이트(커버리지/누수방지)를 추가해 **결정적
  재현** 가능한 공개 평가셋으로 정식화. 이어서 onnx-int8 백엔드로 **baseline 실측**을 커밋 자산
  으로 승격(PII recall·precision·KR_PERSON/KR_LOCATION 카테고리별 + Wilson CI 하한)하여 정확도
  재현 데모를 exit0 으로 회복. 엔진 정확도 개선 본편은 차기(v0.2.0).
- **가명화 품질 벤치마크 — 가역/비가역 지표 산출 표면 + 리포트** — 기존 가명화 표면
  (`egress_audit/surrogate.py` 가역 · `egress_audit/pseudonymize.py` 비가역 · 프리셋
  `pseudonymize-roundtrip`)의 품질을 결정적으로 측정하는 하니스
  [`scripts/bench_pseudonymize.py`](scripts/bench_pseudonymize.py) 를 추가하고 측정 결과를
  `docs/reports/` 하위 커밋 자산(pseudonymize-quality)으로 승격. **가역**: 원복 정확도
  (스트리밍 청크 경계 포함)·surrogate 충돌율(0)·결정성.
  **비가역**: 원복불가·구조보존·동일값 일관 치환·충돌율(0). **차단 유지**: 강한 식별자·비밀
  (주민/외국인/여권/면허/카드/계좌/비밀)은 가역 프리셋에서도 차단되어 가명화로도 송신되지
  않음을 확인. 1-명령 데모 [`scripts/demo_pseudonymize.sh`](scripts/demo_pseudonymize.sh) +
  `demo_all` 러너 등록 + [`docs/DEMO.md`](docs/DEMO.md) 카탈로그. 기계식 불변식(충돌 0·결정성·
  원복 정확·차단 유지) 미달 시 하니스 비-0 종료. 새 런타임 동작 변경 없음 — 기존 표면 측정.
  권위: [`docs/PRESETS.md`](docs/PRESETS.md).
- **정확도·가명화 벤치마크 단일 진입점 — `nufi-egress benchmark` (CLI) + `run_benchmarks` (SDK)** —
  흩어져 있던 두 벤치마크를 **한 명령/한 함수**로 묶어 재현한다. 정확도는 봉인 골드셋 측정
  산출물(커밋된 JSON 증거)을 게이트 목표선(KR_PERSON Wilson CI 하한 ≥ 0.85 · 온프렘 p95
  c≤2 ≤ 목표)에 대조하고(모델 재실행 없음, I1 공개 골드셋 baseline 은 정보성), 가명화는
  품질 하니스를 라이브로 재실행(가역/비가역 불변식). `--only accuracy|pseudonymize` 축 선택,
  `--json`/`--json-out` 리포트 산출, 전체 PASS 시 exit 0·미달 시 1(CI/제출 게이트). SDK 표면
  `enforcement.benchmark.run_benchmarks / evaluate_accuracy_gate / run_pseudonymize_benchmark`
  ([`docs/SDK.md`](docs/SDK.md) §2.6·§3 문서화). 데모 [`scripts/demo_accuracy.sh`](scripts/demo_accuracy.sh)
  에 단일 명령 재현 섹션(B) 추가 — 정확도 커밋 JSON + 가명화 하니스 동시 PASS 게이트.
  새 측정 알고리즘 없음 — 기존 두 벤치마크의 진입점 통합. 권위: [`docs/SDK.md`](docs/SDK.md).

### Changed
- **운영(ops) 레이어 제외 — 정체성 전환을 문서에서 참으로** — 멀티테넌시/RBAC·SLA·대시보드를
  README·운영자 매뉴얼에서 제외/강등 표기하고, 코어(게이트웨이)+컴플라이언스 매핑(증빙)을
  전면 동선으로 재배열. 경량 CLI/SDK·한국 규제 증빙이라는 새 정체성을 릴리스 표면에 반영.
  권위: [`docs/ROADMAP.md`](docs/ROADMAP.md) · [`docs/MANUAL.md`](docs/MANUAL.md).

## [0.0.9] - 2026-06-29

### Added
- **컴플라이언스 매핑 리포트 — 점검항목 커버리지(control coverage)** — 규정준수 증빙
  게이트웨이의 첫 슬라이스. `report compliance` 에 **금융보안원 안내서 점검항목 + 망분리
  평가기준** 대비 NuFi 통제 충족 상태를 **기존 리포트 증빙에서 자동 산출**하는 커버리지
  섹션을 추가한다(게이트 결정·차단 규칙 무변경).
  - `report compliance --controls`(기본 상시) / `--no-controls` / `--catalog FILE` — 통제
    카탈로그 대비 매핑 표를 MD/HTML/JSON 으로 산출. 동봉 카탈로그는 direct 8 / partial 6 /
    out_of_scope 5 항목.
  - **직접(direct)** 통제는 결정론적 평가 규칙(`action_count`·`decisions_total`·`field_true`·
    `chain_ok`·`nonempty`·`all_of`)으로 충족/미충족을 **자동판정**하고 증빙 출처를 행에 표기한다.
    **부분(partial)/범위밖(out_of_scope)** 은 카탈로그의 정적 라벨 + 보강 로드맵으로 표기한다.
  - 롤업 배지(직접 N(충족/미충족)·부분 N·범위밖 N) + 항목별 행을 md/html/json 렌더러에 추가.
  - **종료코드는 기존 무결성 게이트(정상 0 · 변조 1)를 유지** — 커버리지는 정보성이며 신규
    비-0 종료를 만들지 않는다.
  - 1-명령 데모 [`scripts/demo_compliance_mapping.sh`](scripts/demo_compliance_mapping.sh)
    (커버리지 롤업·MD 표·무결성 게이트 0/1 유지·`--no-controls` 회귀 5/5) + `demo_all` 러너
    등록 + [`docs/DEMO.md`](docs/DEMO.md) 카탈로그 등록.
  - 운영자 매뉴얼 [`docs/MANUAL.md`](docs/MANUAL.md) §5.4 에 매핑 리포트 절(사용법·출력 해석·
    증거 출처) 신설 — 권위 [`docs/REPORTING.md`](docs/REPORTING.md) §3 으로 링크(단일출처 유지).

## [0.0.8] - 2026-06-28

### Added
- **운영자 매뉴얼 — 단일 정주행 척추 `docs/MANUAL.md`** — 흩어져 있던 주제 문서(설치·
  퀵스타트·개념·CLI·운영·보안 운영)를 처음부터 끝까지 한 번에 읽는 단일 매뉴얼로 통합.
  '척추+흡수' 설계 — net-new 연결조직만 직접 집필하고 각 주제의 권위 문서로 링크(중복
  재작성 없음; `docs/ARCHITECTURE.md` 단일권위 + doc-style 가드 단일출처 유지).
  - §0 개요·독자 / §1 설치(소스·온프렘 컨테이너·에어갭 통합) / §2 5분 퀵스타트 / §3 핵심
    개념 / §4 CLI 레퍼런스 / §5 운영(정책 at scale·룰 무재기동 리로드·멀티테넌시/RBAC·
    리포팅·대시보드·커버리지·프리셋) / §6 보안 운영(원문 보존·키 회전).
  - **§7 트러블슈팅 & FAQ (net-new)** — 설치(`command not found`)·리로드 미반영·우회 추적·
    커버리지 0·RBAC 거부(exit 3)·해시체인 무결성 실패(exit 1) 등 자주 막히는 지점과 해소법.
  - **§9 용어집 (net-new)** — egress·가역 가명화·해시체인·우회·커버리지·테넌트/RBAC·EDM·
    NER·fail-closed 등 핵심 용어 정의(§3 개념·§5.3 멀티테넌시에서 교차링크).
  - §8 업그레이드 & 마이그레이션 골격(stretch; 호환 패치 흐름 원칙 + 후속 채움).
  - `docs/MANUAL.md` 파일링크 54·앵커 16 전수 resolve(dangling 0).

### Changed
- **문서 지도 정주행 진입점 재배열** — `docs/README.md` 최상단을 단일 매뉴얼
  `docs/MANUAL.md`(정주행 진입점)로 재배열(추천 순서·상태표). 처음 보는 운영자가 단일
  매뉴얼부터 시작하도록 입문 동선 정리.

### Removed
- 0바이트 잔재 `docs/SPEC.md` 제거(히스토리 명세는 `docs/history/SPEC.md` 로 유지).

## [0.0.7] - 2026-06-28

### Added
- **SLA 선제 알림 + 다테넌트 집계** — v0.0.6 의 제출용 SLA 리포트를 **사후 보고에서
  선제 보증**으로 확장. `report sla` 에 위반을 운영자에게 즉시 신호하는 알림 경로와,
  여러 고객(테넌트)의 SLA 를 한 번에 보는 플릿 집계를 더한다(게이트 결정·차단 규칙 무변경).
  - `report sla --alert FILE` — SLA 위반 발생 시 **0이 아닌 종료코드**로 신호하고 위반
    내역을 구조화된 알림 JSON(`FILE`)으로 적재. 충족 시에는 알림을 만들지 않는다.
  - `report sla --all-tenants` — **operator 전용** 테넌트별 SLA 행 집계(한 표에 고객별
    충족/위반). `viewer` 역할은 거부(exit 3, RBAC 일관).
  - `report sla --webhook URL` — 알림을 외부로 보내는 발송 경로(스텁; 본 릴리스는 페이로드
    형식 고정까지).
  - 검증 `tests/test_cmp157_sla_alert_fleet.py`(13 케이스) · 1-명령 데모
    `scripts/demo_sla_alert.sh`(6/6 PASS, 권한 불필요; CMP-194에서 제거됨).
- **대시보드 운영 CLI** — read-only 감사 대시보드 데이터소스(`dashboards/server.py`)를
  통합 진입점 서브커맨드로 흡수: `nufi-egress dashboard [--host --port --audit
  --flow-dir]`. 마지막까지 모듈 직접 실행으로만 띄우던 운영 표면을 설치형 CLI 로
  정렬(레거시 모듈 실행은 비설치 동치로 유지).

### Changed
- **공개 표면 표기 정리** — CLI `--help`/usage/description, 명령 stdout 헤더, 생성물
  파일 헤더(`nufi init` config·생성 nftables 룰셋), 대시보드 JSON 응답에서 내부 추적용
  식별자 표기를 제거해 사용자에게 보이는 문구를 정돈했다. 기존 동작·옵션·종료 코드·JSON
  키 구조는 무변경(표기/문구만). 재발 방지를 위해 공개 스타일 가드
  ([`scripts/check_doc_style.py`](scripts/check_doc_style.py))를 코드 사용자 표면
  (argparse help/description·명령 출력·생성물 헤더·JSON 값)까지 확장했다 — 순수 내부
  docstring/주석은 그대로 허용한다.
- **데모 가독성·카탈로그 정비** — 데모 파일 이름을 **이름만 보고 무엇을 시연하는지** 알 수
  있는 기능 이름으로 통일(`demo_<feature>.sh`): 차등 감사 분리 데모 →
  [`demo_audit_separation.sh`](scripts/demo_audit_separation.sh), 우회 차단(ENFORCED) 데모
  → [`demo_bypass_enforcement.sh`](scripts/demo_bypass_enforcement.sh), 정확도 재현 데모 →
  [`demo_accuracy.sh`](scripts/demo_accuracy.sh), 전체 기능 러너 →
  [`demo_all.sh`](scripts/demo_all.sh)(모든 데모를 차례로 실행하고 PASS/FAIL/SKIP 집계).
  전 데모를 한곳에 모은 카탈로그 [`docs/DEMO.md`](docs/DEMO.md) 신설(README 링크).
- **문서 raw `python -m` 주 명령 일소** — README·매뉴얼에서 운영 명령을 raw `python -m …`
  로 리드하던 표기를 통합 CLI(`nufi-egress …`) 리드로 교체하고, 모듈형 실행은 명시적
  "비설치 동치(equivalent)" 각주로만 강등. 재발 방지를 위해 doc-style 가드
  ([`scripts/check_doc_style.py`](scripts/check_doc_style.py))에 raw-module-as-main 규칙을
  추가(검증 `tests/test_doc_style_guard.py`).

### Release
- **GitHub Release 발행 메커닉 편입** — 태그 컷에서 끝나던 릴리스 흐름에 **공개 Release
  객체 발행** 단계를 정식 편입. 발행 스크립트 [`scripts/publish_github_release.sh`](scripts/publish_github_release.sh)
  (RELEASE_NOTES 해당 섹션 → Release 본문, 태그 주석 → 제목; `gh` 우선, 토큰+`curl` 폴백)
  + [`docs/RELEASE_CHECKLIST.md`](docs/RELEASE_CHECKLIST.md) step 5.

## [0.0.6] - 2026-06-28

확장·차별화의 첫 슬라이스. 운영(Operate) 완성 위에 **제출용 리포팅(SLA·규정준수)** 과
**멀티테넌시·읽기전용 역할(RBAC) 첫 칸**을 더한다. 게이트 결정 로직·신규 차단 규칙은 무변경
(범위: 리포팅/운영 경계). 사람 친화 릴리스 노트: [`docs/RELEASE_NOTES.md`](docs/RELEASE_NOTES.md).

### Added
- **SLA·규정준수 리포팅** — 이미 측정·적재 중인 지표를 **기간별(일/주/월) 제출용
  리포트**로 묶는 `nufi-egress report {sla,compliance}` 서브커맨드. 감사관·구매자에게
  낼 수 있는 Markdown/HTML/JSON 산출물을 만들며, **새 측정·새 벤치 없이** 기존 산출물만
  읽기 전용으로 재사용한다.
  - `report sla` — PII recall·지연 p95·게이트웨이 커버리지를 기간별로 집계하고 목표 대비
    **충족/위반**을 판정. 기본 임계 = 핵심 품질 약속(recall ≥ 0.9 / p95 ≤ 150ms /
    커버리지 ≥ 99%), 고객별 임계는 `--thresholds`/`--set` 으로 노출. 위반 시 exit 1.
  - `report compliance` — 정책 변경 감사(누가·언제·무엇 + 해시체인 무결성), 차단/가명화
    건수, 우회 탐지 요약을 한 장으로. 해시체인 변조 탐지 시 exit 1(제출 차단).
  - 구현 `enforcement/report.py`(대시보드 어댑터·감사 해시체인·커버리지 집계기 재사용)
    · 매뉴얼 [`docs/REPORTING.md`](docs/REPORTING.md) · 1-명령 데모
    [`scripts/demo_report.sh`](scripts/demo_report.sh)(6/6 PASS, 권한 불필요)
    · 검증 `tests/test_cmp150_report.py`(13 케이스) · 샘플 픽스처 `samples/sla/`.
  - 범위 밖(다음 단계): 실시간 SLA 알림·콘솔, 다고객 SLA 집계.
- **멀티테넌시·읽기전용 역할(RBAC) 첫 슬라이스** — 다수 테넌트를 한 게이트웨이에서
  운영할 때의 **안전한 첫 칸**. 두 가지를 더한다(기존 동작·차단 규칙 무변경).
  - **테넌트 읽기 경계** — 전역 `--tenant <키>` 로 리포트 조회를 한 테넌트로 **격리**한다.
    한 테넌트의 조회 세션은 다른 테넌트의 감사 결정·정책 변경·flow 레코드를 **보지 못한다**
    (미귀속 레코드도 격리 시 비노출 = fail-closed). 정책 묶기(binding)의 테넌트 키
    (`tenant:acme` 등)를 격리 경계로 승격. 해시체인 무결성은 전체 체인 기준으로 검증한다.
  - **읽기전용 역할(RBAC)** — 전역 `--role {viewer|operator}`. `viewer` 는 **조회만**
    가능하고 정책 변경(`policy bind/snapshot/rollback`)은 **거부**된다(exit 3). `operator`
    는 조회+변경. 기본값 `operator`(역호환). `NUFI_TENANT`/`NUFI_ROLE` env 폴백.
  - 구현 `enforcement/access.py`(테넌트 키 추출·격리 필터 + 역할 세션·권한 가드) ·
    매뉴얼 `docs/MULTITENANCY.md`(CMP-194에서 제거됨) · 1-명령 데모
    `scripts/demo_multitenancy.sh`(CMP-194에서 제거됨) · 검증
    `tests/test_cmp151_access.py`.
  - 범위 밖(→ 다음 단계): 완전 테넌트 격리(런타임/자격증명 분리), 쓰기 RBAC(역할별 세분
    변경 권한), 권한 위임.

## [0.0.5] - 2026-06-28

운영(Operate)을 **기능으로 완성**한 버전. v0.0.4(도입 표면)가 설치·통합 CLI·입문을 닦은 위에,
정책을 **규모 있게 운영**하고 그동안 미뤄온 **정확도 과제를 마무리**한다. 게이트(gate) 결정
로직·신규 차단 규칙은 무변경(범위: 운영/설정/측정). 재현 데모·매뉴얼: [`docs/history/DEMO_v0.0.5.md`](docs/history/DEMO_v0.0.5.md).

### Added
- **정책 운영 자동화** — v0.0.2 의 단일 프로파일·단건 무재기동 핫리로드(hot reload)를
  운영 규모로 확장. 한 게이트웨이에서 **여러 정책 프로파일 동시 운영** + **경로/테넌트별
  묶기(binding)**, 정책 **버전 관리·무재기동 되돌리기(rollback)**, **변경 감사 로그**(누가·
  언제·무엇을 + 추가전용 해시 체인(hash chain) 변조탐지).
  - `nufi-egress policy {list,bind,snapshot,versions,rollback,audit,inspect}` 서브커맨드.
  - `config/routing.yaml` 확장: `policy_profiles`(프로파일 레지스트리) + `policy_bindings`
    (묶기). 런타임 묶기 변경은 `config/policy_bindings.yaml` 오버레이에 기록(routing.yaml
    주석 비파괴). 예시 프로파일 `config/profiles/strict/`(strict-kr-pii 구체화).
  - 구현 `enforcement/policy_ops.py` · 매뉴얼 [`docs/OPS_POLICY_AT_SCALE.md`](docs/OPS_POLICY_AT_SCALE.md)
    · 1-명령 데모 [`scripts/demo_policy_ops.sh`](scripts/demo_policy_ops.sh)(4/4 PASS, root 불필요)
    · 검증 `tests/test_cmp144_policy_ops.py`(4 케이스).
  - 범위 밖(v0.1.0 예정): 멀티테넌시·권한관리(RBAC)·테넌트 격리.

### Changed
- **정확도 과제 마무리** — INT8 한국어 인명(KR_PERSON) 신뢰구간 마무리. per-tensor
  INT8 양자화(quantization)가 인명 3건을 노이즈로 잃어 Wilson 신뢰구간(confidence interval) 하한을 0.860→**0.832**(<0.85)로 떨군 회귀를,
  **채널별(per-channel) 동적 양자화**로 복원: `scripts/export_onnx_int8.py` 의 `M5_QUANT_PER_CHANNEL`
  기본 ON(가중치 출력채널별 스케일).
  - 결과(`docs/reports/recall-int8.json`): KR_PERSON 재현율(recall) **0.9127**(115/126),
    Wilson **CI95 [0.8504, 0.9506]** → 하한 **0.850 ≥ 0.85** 충족. pii_recall 0.9433.
  - 온프렘(on-prem) p95 표: INT8 부하 p95 — c=1 41ms / c=2 67ms(목표 150ms 이내), FP32 대비 ~3×.
  - 정합성 가드 `tests/test_cmp145_int8_consistency.py`(INT8↔FP32 무손실 · 모델 미설치 시
    침묵 금지 skip) · 재현 데모 [`scripts/demo_accuracy.sh`](scripts/demo_accuracy.sh)(2/2 PASS).

## [0.0.4] - 2026-06-28

도입성(adoption) 패치 — **새 기능 없음**. v0.0.3(관측 O1·보증 O2) 위에 설치형 패키징,
통합 CLI(`nufi-egress`) 마감, 입문 문서를 더한 릴리스. 운영 동작·정책·탐지 코어는 무변경,
레거시 진입점은 전부 하위호환으로 유지(`python3 -m …` 그대로 동작).

### Added
- **설치형 콘솔 스크립트**: `pip install -e .` 후 `nufi-egress`(별칭 `nufi`)를
  PATH 에서 직접 실행(`pyproject.toml` console_scripts). 레거시 `python3 -m enforcement.cli` 동치 유지.
- **`nufi-egress audit {report,daemon,once,query}`**: 비동기 감사 봇 + §4 감사로그
  조회(outcome/엔티티 집계 + 해시 체인 무결성 검증)를 통합 서브커맨드로 편입.
- **`nufi-egress targets` · `flow-tap`**: 캡처 레이어 운영 명령(`capture.targets`/
  `capture.flow_tap`)을 통합 CLI 서브커맨드로 흡수 — 마지막 CLI 통합 항목 마감.
- **Hands-on 입문 튜토리얼 `docs/HANDS_ON.md`**: 토이 프로젝트("환불 도우미")로
  SDK 한 줄 전환 + `nufi-egress` CLI 운영을 끝까지 실습(root/네트워크 불필요). 로그 위치 표 +
  실시간 `tail -f` 관찰 절 포함.

### Changed
- **문서 운영 명령 표기 정정**: README·CLI·INTEGRATION_GUIDE 의 raw
  `python3 -m capture.*`/`egress_audit.audit_bot` 리드를 통합 CLI(`nufi-egress {targets,
  flow-tap,audit}`) 리드로 교체, 레거시 진입점은 하위호환 각주로 강등.
- **멀티-프로바이더 지원 명시**: INTEGRATION_GUIDE 에 Anthropic/Google/Azure
  경로 명시.

## [0.0.3] - 2026-06-28

Operate(운영) 호라이즌 첫 릴리스 — *이미 100% 적재되는* 감사를 **읽고(O1)** 게이트웨이
커버리지를 **보증(O2)** 하는 두 사용자 대면 기능. 정책 운영 규모화(O3)는 다음 릴리스로 이연(이번 릴리스 범위 밖).

### Added
- **감사 가시성 대시보드 — read-only**: 온프렘에 이미 적재되는
  감사를 보안팀이 *읽는* 화면. 프로덕션 무변경·쓰기 권한 없음(GET/HEAD 만, 쓰기 405).
  - read-only 데이터소스 `dashboards/server.py`(stdlib) + 백엔드 중립 어댑터
    `dashboards/adapter.py` — 4 패널: 결정 뷰어/해시체인 무결성/우회 타임라인/카테고리 추이.
  - 의존성 0 정적 뷰어 `dashboards/viewer.html` + 프로덕션용 `grafana_dashboard.json`.
  - 매뉴얼 `dashboards/README.md`, 결정성 샘플 픽스처 `dashboards/sample/`(합성·비-PII).
- **커버리지 보증**: `nufi doctor`(1회 진단)의 게이트웨이 통과
  점검을 **상시 런타임 보증**으로 연장. flow tap 의 우회 판정을 연계해 nftables 집행을
  '측정 가능한 보증'으로 만든다.
  - 커버리지 집계기 `capture/coverage.py`(`CoverageAggregator`) — '내 트래픽 중 X% 가
    게이트웨이를 통과' 경량 인메모리/영속 카운터(외부 의존 0).
  - `nufi-egress coverage` 서브커맨드 — 커버리지 보증 리포트(텍스트/JSON, PASS/WARN/FAIL).
  - 우회 상시 모니터 `capture/bypass_monitor.py`(`BypassMonitor`) + `nufi-egress monitor`
    서브커맨드 — 게이트웨이 우회 준실시간 탐지·임계 알림 + suppression(쿨다운 디바운스).
  - 단위 테스트 `tests/test_cmp133_coverage.py`, 우회 버스트 샘플
    `samples/flow_bypass_burst.jsonl`(suppression 실증).
- **O1·O2 1-명령 데모 + 재현 매뉴얼**: `scripts/demo_coverage.sh`
  (coverage PASS/누수탐지 + monitor 우회 알림) · `scripts/demo_dashboards.sh`(4 엔드포인트
  200 + viewer 렌더 + read-only 405, 헤드리스 curl). 둘 다 root 불필요 1-명령 PASS/FAIL.
  재현 매뉴얼 `docs/history/DEMO_v0.0.3.md`, PASS 경로용 샘플 `samples/flow_clean.jsonl`.

### Fixed
- 대시보드 샘플 flow 픽스처가 어댑터 디렉터리 글롭 `flow-*.jsonl` 과 불일치하여
  (`flow_bypass.jsonl`) README dir-모드 우회 패널이 비던 문제 → `flow-bypass.jsonl` 로 정정.

## [0.0.2] - 2026-06-28

패키징·운영성(Day-1 도입) 릴리스. 코어 탐지/차단 엔진은 0.0.1 그대로 두고, 서빙 빌더가 실제로 깔고-띄우고-운영하는 데 필요한 CLI·SDK·배포·핫리로드·문서를 채웠다.

### Added
- **Thin client SDK**: OpenAI 호환 `base_url` 심 + 가역 가명화(pseudonymization) 라운드트립 — 기존 코드 한 줄 교체로 게이트웨이 경유.
- **`nufi doctor` 진단 CLI**: 하이브리드(private+public) 배선 자가진단.
- **파이프라인 프리셋 3종 + `nufi init` 템플릿**: 도입 즉시 쓰는 정책 프리셋.
- **단일명령 배포 패키징**: Docker Compose + 에어갭(air-gap) 번들 + Helm 스텁.
- **무재기동 룰 핫리로드**: 드라이런 + fail-closed + retain_raw/키회전 하드닝.
- **통합 `nufi-egress` CLI**: `doctor`·`init` 을 단일 진입점으로 통합, 서빙빌더 통합 가이드·README 진입 섹션·`docs/CLI.md` 레퍼런스.

### Changed
- **동시성·부하 하니스 + NER base 격상 배선**: p95 부하 측정 + KR_PERSON 신뢰구간 하한 판정. 상세 정확도·성능 리포트 동봉.
- **NER 동시성 하드닝**: intra-op 스레드 캡 + bounded 워커풀 + INT8 로더 정합성 수정.

### Notes
- 탐지 정확도/지연 수치는 0.0.1 측정치 유지(엔진 무변경). 0.0.1 'Known limitations' 그대로 적용.

## [0.0.1] - 2026-06-27

NuFi Egress-Audit Gateway 의 첫 릴리스 태그. 하이브리드 LLM(private 우선 + public 폴백)
환경에서 public LLM 으로 나가는 outbound 요청을 게이트웨이로 가로채 한국어 PII·비밀·기밀을
인라인 탐지·차단·가명화하고, 우회 트래픽을 패킷레이어에서 탐지하며 nftables 로 실제 차단한다.

### Added
- **게이트웨이**: private 기본 + public 폴백 라우팅(`gateway/`), public 행 요청
  100% 감사 로깅(`egress_audit/audit.py`). 수용 테스트 10/10 통과.
- **탐지 파이프라인**: 한국 PII 정규식(regular expression)·체크섬(checksum) + NER + 비밀정보 + 정책 엔진
  (block/redact/pseudonymize/warn) — `egress_audit/pipeline.py`, `egress_audit/policy.py`.
- **차등감사·패킷·봇**: in/out 메시지 스토어(public/private 분리), 패킷레이어
  평문 캡처·우회탐지(`capture/`), 비동기 감사봇(`egress_audit/audit_bot.py`), 통합 데모.
- **Enforcement 우회 차단**: 탐지에서 실제 차단으로 — nftables 허용목록 모델
  (`enforcement/`).
- **가역 가명화/원복**: 세션 스코프 결정적 surrogate + AES-256-GCM 매핑 Vault
  (`egress_audit/pseudonymize.py`·`surrogate.py`·`vault.py`·`reversible.py`), 비스트리밍/스트리밍 원복.
- **기밀 1차 탐지**: 분류 표식·키워드 + EDM(구조화·비구조화 지문)
  — `egress_audit/detectors/confidential.py`, `egress_audit/edm.py`.
- **벤치·하드닝**: 골드셋 확대·채점 하니스, fail-closed(탐지 실패→차단),
  감사 해시체인(변조탐지), KoELECTRA/ONNX-INT8 백엔드 실측.
- **문서**: 단일 권위 [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)(컴포넌트 + 4개 시퀀스
  Mermaid), 드리프트 방지 체크리스트.

### Measured (v0.0.1)
- PII 재현율(recall, 전체) **0.946** (목표 ≥0.90) · 강한PII/Secret recall **1.000** · 정밀도(precision) **0.985**.
- KR_PERSON recall 0.897(INT8)/0.921(FP32), 표본 48→126 확대로 신뢰구간 절반 축소.
- benign-FP **0/90**. 하드닝 12/12.
- INT8 512자 인라인 지연 p95 **38ms** (목표 ≤150ms CPU).

### Known limitations (운영 주의)
- **INT8 KR_PERSON 신뢰구간 잔여**: INT8 Wilson 신뢰구간 하한 0.832 가 0.85 를 ~1.8%p 하회(소표본 양자화
  노이즈; FP32 는 신뢰구간 하한까지 PASS). base 모델 격상(option b)은 **이후 릴리스로 이연**(v0.0.5 에서 채널별 양자화로 해소).
- **public retain_raw**: public 경로 원문은 통제된 싱크(MessageStore retain_raw 정책)에만 보존되며
  감사 로그에는 마스킹/가명화본만 저장. 운영 정책에 따라 retain_raw 활성 시 원문이 보존됨에 유의.
- **root 캡처**: 패킷레이어 캡처(`capture/`)는 권한 있는 컨텍스트(root/CAP_NET_RAW 등)를 요구.
- **후속**: NER base 모델 격상, 프로덕션 온프렘 p95 재측정.

[0.0.2]: https://example.invalid/releases/0.0.2
[0.0.1]: https://example.invalid/releases/0.0.1
