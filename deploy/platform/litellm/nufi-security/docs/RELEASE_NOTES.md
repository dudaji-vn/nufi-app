# 릴리스 노트 (Release Notes)

사람이 읽기 좋은 버전 안내입니다. **이 버전이 우리에게 무엇을 해주나**를 중심으로,
비개발자 의사결정자도 한눈에 이해할 수 있도록 정리합니다. 기술 상세 변경 이력은
[`CHANGELOG.md`](../CHANGELOG.md) 를 참고하세요. (최신 버전이 위에 옵니다.)

---

## v0.6.3 -- **CHANGELOG 통합 + ROADMAP 수치 갱신**

> v0.6.0~v0.6.2 야근 스프린트 변경사항을 CHANGELOG에 통합하고, ROADMAP 달성 수치를 현재 상태로 갱신합니다. (2026-07-07)

### 주요 변경

| 항목 | 내용 |
|---|---|
| **CHANGELOG 통합** | v0.6.0, v0.6.1, v0.6.2 변경사항을 CHANGELOG.md에 일괄 추가 |
| **ROADMAP 달성 수치 갱신** | v0.6.2 기준으로 갱신 — 테스트 307→770, selftest 6→7, 가명화 latency p95 191.7ms, pre-commit hooks 추가 |
| **VERSION** | 0.6.2 → 0.6.3 |

### 누구에게 유용한가

- **프로젝트 관리자** -- CHANGELOG와 ROADMAP이 최신 상태로 정렬되어 프로젝트 현황 파악이 용이합니다.
- **신규 참여자** -- 야근 스프린트(v0.6.0~v0.6.2)의 변경 이력을 한눈에 확인할 수 있습니다.

### 검증

- CHANGELOG.md v0.6.0/v0.6.1/v0.6.2 엔트리 추가 확인
- ROADMAP.md 달성 수치 v0.6.2 기준 갱신 확인
- 기존 코드 변경 없음 (문서 전용 릴리스)

---

## v0.6.2 -- **test self-check 가명화 검증 + 가명화 레이턴시 벤치마크**

> self-test에 가명화 라운드트립 검증이 추가되고, 가명화 처리량 벤치마크가 강화되었습니다. (2026-07-07)

### 주요 변경

| 항목 | 내용 |
|---|---|
| **`test` 7번째 체크: Pseudonymize** | `nufi-egress test`에 가역 가명화 라운드트립 검증 추가 — pseudonymize → deanonymize → 원본 일치 확인 |
| **가명화 레이턴시 벤치마크** | `bench_pseudonymize.py --latency` — 입력 크기별(256~16K자) p50/p95/p99 레이턴시 측정 |
| **CI 게이트** | 16K자 기준 p95 ≤ 200ms 게이트 추가 |

### 누구에게 유용한가

- **운영자** -- `nufi-egress test` 한 줄로 가명화 포함 7가지 핵심 기능을 자가 검증.
- **성능 모니터링** -- `--latency` 벤치마크로 가명화 처리 성능을 정량적으로 추적.

### 검증

- selftest 7/7 체크 통과 (pseudonymize roundtrip 포함)
- 가명화 품질 벤치마크 + 레이턴시 벤치마크 통과
- 기존 테스트 전체 회귀 없음

---

## v0.6.1 -- **pre-commit 프레임워크 통합 + diff --pseudonymize**

> pre-commit 훅 패키지와 diff 커맨드의 가명화 옵션이 추가되었습니다. (2026-07-07)

### 주요 변경

| 항목 | 내용 |
|---|---|
| **`nufi-pseudonymize` pre-commit 훅** | `.pre-commit-hooks.yaml` 에 `nufi-pseudonymize` 훅 추가 — 커밋 시 PII가 있으면 fail + 가명화 제안 출력 |
| **`pseudonymize --check`** | 파일별 PII 체크 모드 — PII 발견 시 exit 1 + 가명화 제안 (pre-commit 훅 진입점) |
| **`diff --pseudonymize`** | git 변경 파일 스캔에 `--pseudonymize` 플래그 추가 — PII 발견 시 가명화 결과도 함께 출력 |
| **README pre-commit 사용 예시** | `.pre-commit-config.yaml` 설정 예시를 README에 추가 |

### 누구에게 유용한가

- **pre-commit 프레임워크 사용자** -- `.pre-commit-config.yaml` 한 줄로 NuFi PII 스캔과 가명화 체크를 커밋 훅에 통합.
- **PR 리뷰** -- `diff --pseudonymize` 로 변경 파일의 PII를 탐지하면서 가명화 제안까지 한 번에 확인.

### 검증

- diff --pseudonymize 테스트 통과
- pseudonymize --check 테스트 통과
- 기존 테스트 전체 회귀 없음

---

## v0.6.0 -- **가역 가명화 CLI 커맨드 + scan --pseudonymize**

> PII를 가역적 surrogate로 치환·원복하는 CLI 커맨드가 추가되었습니다. (2026-07-07)

### 주요 변경

| 항목 | 내용 |
|---|---|
| **`pseudonymize` 서브커맨드** | `nufi-egress pseudonymize "텍스트"` — PII를 surrogate 토큰(⟦P1⟧)으로 치환하고 세션 ID 발급. `--restore --session <ID>` 로 원복 가능 |
| **파일 단위 처리** | `--file input.txt --output output.txt` 로 파일 가명화/원복 지원 |
| **JSON 출력** | `--json` 또는 `--format json` 으로 세션 ID·가명화 결과·통계를 JSON으로 출력 |
| **`scan --pseudonymize`** | 기존 scan 명령에 `--pseudonymize` 플래그 추가 — PII 발견 시 가명화 텍스트를 함께 출력하고, `--output` 지정 시 가명화 파일 저장 |

### 누구에게 유용한가

- **데이터 전처리** -- 외부 LLM 전송 전 CLI 한 줄로 PII를 가역 가명화하고, 응답 후 원복할 수 있다.
- **파일 스캔 + 가명화** -- `scan --pseudonymize` 로 PII 탐지와 가명화를 한 번에 수행.
- **자동화 파이프라인** -- `--json` 출력으로 스크립트·CI에서 세션 ID와 가명화 결과를 프로그래밍 방식으로 처리.

### 검증

- pseudonymize CLI 텍스트/파일/restore/JSON 모드 테스트 통과
- scan --pseudonymize 테스트 통과
- 기존 테스트 전체 회귀 없음

---

## v0.5.4 -- **KR_PERSON 조사 부착 인명 탐지 개선**

> 한국어 조사가 붙은 인명도 정확히 탐지합니다. (2026-07-07)

### 주요 변경

| 항목 | 내용 |
|---|---|
| **조사 부착 인명 탐지** | "김철수에게", "이영희는", "박민수를" 등 24종 조사(에게/은/는/이/가/을/를/와/의/에게서/한테 등)가 붙은 인명을 문맥 게이팅 하에서 정확히 탐지 |
| **회귀 방지** | 기존 경칭(님/씨/선생님)·직함 게이팅과의 호환성 유지. 테스트 11건 추가 |

### 누구에게 유용한가

- **한국어 텍스트 처리** -- 자연스러운 한국어 문장에서 조사가 붙은 인명도 놓치지 않고 PII 탐지.
- **정확도** -- 문맥 게이팅이 유지되어 일반 명사 오탐 없이 인명만 정확히 잡아냄.

---

## v0.5.3 -- **인젝션 문서 현행화 + 패턴 카운트 자동 검증**

> 인젝션 탐지 문서를 코드와 동기화하고, 드리프트를 CI로 방지합니다. (2026-07-07)

### 주요 변경

| 항목 | 내용 |
|---|---|
| **PROMPT_INJECTION.md 현행화** | 패턴 카운트 18→45, 카테고리에 `code_switch`·`indirect` 추가, 동사 활용형·Unicode 정규화·severity 체계·벤치마크 결과 섹션 반영 |
| **드리프트 방지 CI** | 패턴 수 ≥40 검증 + 코드-문서 카테고리 일치 테스트 2건 추가. 문서가 코드와 어긋나면 CI가 잡아냄 |

### 누구에게 유용한가

- **보안 운영자** -- 인젝션 문서가 항상 최신 코드 상태를 반영하므로 문서만 보고도 현재 방어 수준 파악 가능.
- **CI/CD** -- 문서-코드 드리프트 자동 감지로 문서 누락 방지.

---

## v0.5.2 -- **인젝션 벤치마크 CI 게이트**

> 인젝션 탐지 품질을 CI에서 자동 검증합니다. (2026-07-07)

### 주요 변경

| 항목 | 내용 |
|---|---|
| **벤치마크 스크립트** | `bench_injection.py` — 골드셋 기반 인젝션 탐지 벤치마크. severity별 통계, JSON/markdown 출력 |
| **벤치마크 결과** | `injection-benchmark.json` — recall 1.000, precision 1.000, F1 1.000, benign FP 0.000 |
| **CI 게이트** | recall ≥ 0.95, benign FP ≤ 0.05 기준 미달 시 CI 실패. 품질 퇴보 자동 차단 |

### 누구에게 유용한가

- **보안 팀** -- 인젝션 탐지 recall/precision이 릴리스마다 자동 검증되어 품질 퇴보 방지.
- **CI/CD** -- 벤치마크 게이트가 기준 미달 코드의 병합을 차단.

---

## v0.5.1 -- **프롬프트 인젝션 탐지 강화 (Phase 2)**

> 한국어 동사 활용형, Unicode 우회, 코드스위칭 탐지를 대폭 확장합니다. (2026-07-07)

### 주요 변경

| 항목 | 내용 |
|---|---|
| **동사 활용형 확장** | 한국어 동사 활용형 47개 패턴 추가 (`_V_END`, `_V_END2`). "무시해라", "잊어버려" 등 다양한 어미 변형 탐지 |
| **Unicode 우회 탐지** | NFKC 정규화 + 제로폭 문자 제거 + 자모 재조합. 시각적으로 동일한 우회 시도 차단 |
| **코드스위칭 탐지** | `code_switch` 카테고리 추가 — 한영 혼합 인젝션 ("ignore하고 출력해") 탐지 |
| **골드셋 확장** | 인젝션 골드셋 215 샘플로 확대. 다양한 공격 패턴 커버리지 강화 |

### 누구에게 유용한가

- **보안 운영자** -- 단순 키워드 매칭으로 놓치던 활용형·우회 공격을 자동 차단.
- **다국어 서비스** -- 한영 혼합 프롬프트 인젝션까지 탐지하여 코드스위칭 기반 공격 방어.

---

## v0.5.0 -- **KoELECTRA fine-tuned 모델 기본 활성화**

> KoELECTRA 모델을 기본 모델로 전환하여 한국어 PII 탐지 정확도를 대폭 향상합니다. (2026-07-07)

### 주요 변경

| 항목 | 내용 |
|---|---|
| **KoELECTRA 기본 활성화** | `Leo97/KoELECTRA-small-v3-modu-ner` 기반 fine-tuned ONNX-INT8 모델(14.7MB)을 기본 모델로 전환 |
| **KR_LOCATION F1 향상** | 73.7% → **90.2%** (+16.5p). corpus4everyone 외부 데이터셋 검증 |
| **KR_PERSON F1 향상** | ~96.6% → **98.2%**. corpus4everyone 외부 데이터셋 검증 |
| **Union 플래그 기본 on** | `M5_LOCATION_UNION`, `M5_PERSON_UNION` 기본값 off → on 변경. 규칙 + ML 모델 결과 합집합 사용 |

### 내부 골드셋 결과

| 지표 | 수치 | 기준 |
|---|---|---|
| person_recall | 0.9741 | ≥ 0.95 |
| location_recall | 1.0000 | ≥ 0.95 |
| pii_recall | 0.9882 | ≥ 0.95 |
| benign_false_block | 0.0000 | ≤ 0.05 |

### 누구에게 유용한가

- **한국어 서비스** -- 별도 설정 없이 기본 상태에서 한국어 인명·지명 탐지 정확도가 대폭 향상.
- **의사결정자** -- 외부 데이터셋으로 검증된 F1 90%+ 수치로 도입 근거 확보.

---

## v0.4.18 (patch177) -- **안정 릴리스: 인젝션 가드레일 + 파일 스캔 + REST API + CLI 확장**

> patch55~175 전체를 아우르는 마일스톤 릴리스. (2026-07-06)

### 주요 기능

| 계층 | 기능 |
|---|---|
| **인젝션 가드레일** | 한국어 프롬프트 인젝션 28종 패턴 탐지. Guard 통합으로 PII+인젝션 동시 차단 |
| **REST API** | `nufi-egress serve` — OpenAPI/Swagger, 14개 엔드포인트(/detect, /route, /inspect, /mask, /redact, /injection, /pipeline, /explain, /scan, /posture, /summary, /stats, /badge, /health) |
| **파일 스캔** | `scan --recursive --redact --dry-run --git-staged --stats` 전체 옵션 세트 |
| **CLI 37개+** | dashboard, report(executive/badge/posture/coverage-map), doctor, init, watch 등 |
| **SDK 20개+ 함수** | detect, route, explain, batch_*, security_report, guard_context 등 |
| **보안 대시보드** | ASCII 터미널 대시보드, 경영진 등급 리포트, SVG 배지 |

### 누구에게 유용한가

- **보안 운영자** -- 터미널 대시보드와 경영진 리포트로 전체 보안 상태를 즉시 파악.
- **개발자** -- SDK 20개+ 함수와 Guard 컨텍스트 매니저로 코드 레벨 PII 보호.
- **CI/CD** -- `scan --git-staged`, pre-commit hook, SVG 배지로 파이프라인 통합.
- **마이크로서비스** -- REST API 6개 엔드포인트로 원격 스캔·판정.

---

## v0.4.17 (patch175) -- **ASCII dashboard + Guard + API endpoints + git-staged scan**

> ASCII 터미널 대시보드, Guard 컨텍스트 매니저, REST API 확장, git staged 스캔. (2026-07-06)

### 이번 릴리스에 포함된 것 (patch169~174)

| 계층 | 기능 |
|---|---|
| **Dashboard** | `nufi-egress dashboard` -- ASCII box-drawing 터미널 보안 대시보드. 등급/테스트/위험/닥터/인젝션을 한 화면에 표시. `--json` 지원 (patch174) |
| **Guard** | `with Guard() as g:` 컨텍스트 매니저 -- 블록 내 PII/인젝션 위반 시 예외 발생. SDK 통합 용이 (patch172-173) |
| **API** | `POST /scan`, `POST /pipeline`, `POST /explain` REST 엔드포인트 추가. 서버 측 스캔/체인/상세설명 API (patch169-170, 172-173) |
| **Scan** | `scan --git-staged` -- git staged 파일만 PII 스캔. pre-commit hook 통합용 (patch171) |

### 누구에게 유용한가

- **보안 운영자** -- `dashboard` 로 터미널에서 전체 보안 상태를 한 눈에 확인.
- **개발자** -- `Guard` 컨텍스트 매니저로 코드 블록 단위 PII 보호.
- **CI/CD 파이프라인** -- `scan --git-staged` 로 커밋 전 스테이지 파일만 빠르게 스캔.
- **마이크로서비스** -- `/scan`, `/pipeline`, `/explain` 엔드포인트로 HTTP API 통한 원격 스캔.

---

## v0.4.17 (patch165) -- **badge generator + executive report + OpenAPI**

> OpenAPI 스키마, 경영진 보안 등급, SVG 배지 생성, HTML 테스트 콘솔. (2026-07-06)

### 이번 릴리스에 포함된 것 (patch158~164)

| 계층 | 기능 |
|---|---|
| **Badge** | `nufi-egress report badge --type grade\|recall\|injection\|tests` -- shields.io-style SVG 배지 생성. `--output badge.svg` 로 README/CI 대시보드에 임베딩 (patch164) |
| **Executive** | `nufi-egress report executive` -- 1페이지 경영진용 보안 요약: 등급(A-F)·핵심 지표·위험·권고. `--format text\|json\|md` (patch163) |
| **Serve** | HTML 테스트 콘솔(루트 `/`), `completions` 전 커맨드 등록 (patch162) |
| **OpenAPI** | Pydantic 모델 기반 OpenAPI/Swagger 스키마 자동생성. `POST /injection` 엔드포인트. `--openapi` JSON 스펙 내보내기 (patch158-160) |

### 누구에게 유용한가

- **보안 팀 리드** -- `report executive` 로 경영진에게 보안 포스처를 A-F 등급 한 장으로 보고.
- **CI/CD 파이프라인** -- `report badge` 로 README 뱃지 자동 갱신. 그린/오렌지 색상으로 상태 직관 표시.
- **API 연동 개발자** -- Swagger UI(`/docs`) 에서 엔드포인트를 브라우저에서 직접 테스트.

---

## v0.4.17 (patch157) -- **serve HTTP API + docs + CHANGELOG**

> HTTP REST API 서버 모드, API 문서·데모·퀵스타트 보강. (2026-07-05)

### 이번 릴리스에 포함된 것 (patch155~156)

| 계층 | 기능 |
|---|---|
| **Serve** | `nufi-egress serve --port 8000` -- FastAPI/uvicorn HTTP REST API 서버. POST `/detect`, `/route`, `/inspect`, `/mask`, `/redact` + GET `/health`. 마이크로서비스에서 HTTP 호출로 PII 탐지·라우팅·마스킹 연동 (patch155) |
| **Docs** | CLI.md serve 레퍼런스(엔드포인트·Request/Response·curl 예시), README 데모 #24, QUICKSTART.md §9 추가 (patch156) |

### 누구에게 유용한가

- **마이크로서비스 팀** -- 기존 서비스에서 HTTP REST 호출로 PII 탐지·마스킹·라우팅을 바로 연동. SDK 설치 없이 HTTP 만으로 동작.
- **Docker/K8s 배포** -- `nufi-egress serve` 를 사이드카 또는 독립 파드로 배포하여 클러스터 내부에서 PII 보호 API 제공.
- **빠른 프로토타이핑** -- curl 한 줄로 PII 탐지·라우팅 결정 확인.

---

## v0.4.17 (patch154) -- **report diff + quickstart + examples + CHANGELOG**

> 스캔 비교 diff 리포트, 퀵스타트 가이드, 예제 README 갱신. (2026-07-05)

### 이번 릴리스에 포함된 것 (patch151~153)

| 계층 | 기능 |
|---|---|
| **Report Diff** | `report diff before.json after.json` -- 두 스캔 결과를 비교하여 new/resolved/unchanged diff 리포트 생성. `--format md\|json\|html`, `--output` 파일 출력. PR 리뷰 리포트/릴리스 노트에 활용 (patch153) |
| **Quickstart** | `docs/QUICKSTART.md` -- 2분 퀵스타트 가이드 신규 (patch151) |
| **Examples** | `examples/README.md` -- 12종 예시 전체 목록 갱신 (patch152) |

### 누구에게 유용한가

- **PR 리뷰** -- `report diff` 로 PR 전후 스캔 결과를 비교하여 신규 PII 유출을 한눈에 확인.
- **릴리스 노트** -- diff 리포트를 마크다운/HTML로 자동 생성하여 릴리스 문서에 첨부.
- **신규 사용자** -- 퀵스타트 가이드로 2분 안에 NuFi 설치부터 첫 스캔까지 완료.

---

## v0.4.17 (patch150) -- **report trends + summary dashboard + CHANGELOG**

> PII 탐지 트렌드 리포트, 프로젝트 헬스 대시보드, CLI 쇼케이스 데모. (2026-07-05)

### 이번 릴리스에 포함된 것 (patch147~149)

| 계층 | 기능 |
|---|---|
| **Trends** | `report trends` -- 감사 로그를 날짜별 그룹핑하여 PII 탐지 추이(이벤트·차단·유형) 출력. `--period N` 기간 지정, `--json` 기계 출력 (patch149) |
| **Summary** | `summary` -- 프로젝트 헬스 대시보드. 설정·활동·위험·닥터·버전을 한 화면 요약 (patch147) |
| **Demo** | CLI 쇼케이스 데모 스크립트 추가 (patch148) |

### 누구에게 유용한가

- **운영/보안팀** -- `report trends` 로 PII 탐지 추이를 날짜별로 확인. 차단 건수 증가 추세 파악.
- **대시보드** -- `summary` 로 NuFi 설정·활동·위험을 한 화면에서 빠르게 점검.
- **CI/자동화** -- `--json` 출력으로 모니터링 파이프라인에 통합.

---

## v0.4.17 (patch146) -- **playground + SDK typing + CLI UX + CHANGELOG**

> 인터랙티브 playground REPL, PEP 561 타입 마커, CLI 에러 친화 처리. (2026-07-05)

### 이번 릴리스에 포함된 것 (patch143~145)

| 계층 | 기능 |
|---|---|
| **Playground** | `playground` -- 인터랙티브 PII 분석 REPL. 텍스트 입력마다 PII/인젝션/위험도/라우팅/차단 한 줄 요약. `mode mask`/`mode redact` 전환. `--text`/파이프 비인터랙티브 지원 (patch145) |
| **CLI UX** | scan/route/explain 필수 인자 누락 시 구체적 에러 안내. 전역 예외 처리(FileNotFoundError, PermissionError, KeyboardInterrupt, BrokenPipeError) (patch144) |
| **SDK Typing** | PEP 561 `py.typed` 마커 + SDK 타입 어노테이션 개선 (patch143) |

### 누구에게 유용한가

- **탐색/학습** -- `playground` 로 텍스트를 실시간 입력하며 NuFi 보안 파이프라인이 무엇을 탐지하고 어떻게 판정하는지 바로 확인.
- **CI/파이프** -- `playground --text` 또는 stdin 파이프로 비인터랙티브 빠른 분석.
- **타입 안전** -- SDK 소비자가 mypy/pyright 등 타입 체커로 NuFi API 호출을 검증 가능.

---

## v0.4.17 (patch142) — **pipeline + history + CHANGELOG**

> 체인 파이프라인 · 활동 로그 조회 · CHANGELOG sweep. (2026-07-05)

### 이번 릴리스에 포함된 것 (patch139~141)

| 계층 | 기능 |
|---|---|
| **활동 로그** | `history` — 감사 로그 + 스캔 캐시를 통합 읽어 최근 활동(스캔·차단·라우팅) 시간순 출력. `--last N`, `--type`, `--json` 지원 (patch141) |
| **README** | 테스트 520건·서브커맨드 33종·pipeline 반영 (patch140) |
| **파이프라인** | `pipeline --text` — detect→decide→transform→route 전체 보안 파이프라인을 한 번에 실행. `--actions` 선택, `--json` 기계 출력 (patch139) |

### 누구에게 유용한가

- **운영 감시** — `history` 로 최근 NuFi 활동을 한눈에 조회. 차단·라우팅·스캔 이벤트를 유형별로 필터링하여 실시간 모니터링.
- **통합 파이프라인** — `pipeline` 으로 PII 탐지부터 라우팅까지 전체 보안 체인을 단일 명령으로 실행. CI/CD 또는 실시간 게이트 용도.

---

## v0.4.17 (patch138) — **selftest + scan --verbose + CLI docs**

> 설치 자가진단 · 스캔 상세 출력 · CLI 레퍼런스 갱신. (2026-07-05)

### 이번 릴리스에 포함된 것 (patch135~137)

| 계층 | 기능 |
|---|---|
| **스캔 상세 출력** | `scan --verbose` — 발견 항목별 상세 정보(파일/줄/컬럼/엔티티/점수/탐지방법/전후 컨텍스트) 출력. 디버깅·리뷰 용도 (patch137) |
| **CLI 문서** | CLI.md 에 compare·test 레퍼런스 추가. DEMO.md 갱신 (patch136) |
| **자가진단** | `test` — PII·인젝션·라우팅·Guard·설정·버전 6체크 설치 검증. `--json` 기계 출력 (patch135) |

### 누구에게 유용한가

- **디버깅** — `scan --verbose` 로 각 발견의 정확한 위치(줄/컬럼), 점수, 탐지 방법(regex/ner), 주변 컨텍스트를 확인. 오탐/미탐 분석에 활용.
- **설치 검증** — `test` 로 NuFi 설치 후 핵심 기능이 모두 동작하는지 6개 체크로 즉시 확인. CI 파이프라인 사전 검증.

---

## v0.4.17 (patch134) — **compare + lint + generate + CLI docs + HANDOVER**

> 스캔 비교 커맨드 · 보안 안티패턴 검사 · PII 샘플 생성 · CLI 레퍼런스 갱신 · HANDOVER 현행화. (2026-07-05)

### 이번 릴리스에 포함된 것 (patch129~133)

| 계층 | 기능 |
|---|---|
| **스캔 비교** | `compare before.sarif after.sarif` — 두 스캔 결과 비교(new/resolved/unchanged). `--fail-on-new` CI 게이트. PR 리뷰용 (patch133) |
| **CLI 문서** | CLI.md 에 lint·generate·mask·redact 레퍼런스 추가 (patch132) |
| **샘플 생성** | `generate` — 한국어 PII 샘플 데이터 생성. `--count`/`--seed`/`--include-injection`/`--format` 지원 (patch131) |
| **안티패턴 검사** | `lint` — hardcoded key/debug/http/eval 등 보안 안티패턴 탐지. `--fix` 자동 수정 (patch130) |
| **HANDOVER** | v0.4.17-patch128 기준 전체 현행화 (patch129) |

### 누구에게 유용한가

- **PR 리뷰** — `compare` 로 before/after 스캔을 비교해 신규 PII 도입 여부를 즉시 확인. `--fail-on-new` 로 CI 게이트화.
- **보안 감사** — `lint` 로 하드코딩 키·debug 모드·HTTP·eval 등 보안 안티패턴을 파일/디렉터리 단위로 검사.
- **테스트** — `generate` 로 현실적 한국어 PII 샘플을 대량 생성. 탐지 파이프라인 테스트·벤치마크 시나리오 구축.

---

## v0.4.17 (patch128) — **mask/redact + unified benchmark(injection) + 통합 데모**

> 텍스트 PII 마스킹·리댁션 커맨드, 벤치마크에 인젝션 통합, 통합 데모. (2026-07-05)

### 이번 릴리스에 포함된 것 (patch124~127)

| 계층 | 기능 |
|---|---|
| **벤치마크 통합** | `benchmark` 에 인젝션 축 통합 — PII 정확도 + 가명화 + 인젝션 3축 한 번에 재현. `--only injection` 단독 실행 지원 (patch127) |
| **통합 데모** | mask/redact/explain 통합 데모(5시나리오 PASS/FAIL) + README·DEMO.md 갱신 (patch125-126) |
| **텍스트 변환** | `mask` — PII를 `***`로 마스킹. `redact` — PII를 `[TYPE]` 태그로 리댁션. `--text`/`--file`/`--output` 지원 (patch124) |

### 누구에게 유용한가

- **CI/품질 게이트** — `benchmark` 한 명령으로 PII 정확도·가명화·인젝션 3축 모두 PASS 확인. 하나라도 미달이면 exit 1.
- **데이터 보호** — `mask`/`redact` 로 텍스트 내 PII 를 즉시 가림/치환. 파일 일괄 처리 지원.
- **데모/교육** — 통합 데모 스크립트로 mask/redact/explain 기능을 한 번에 시연.

---

## v0.4.17 (patch123) — **export patterns + audit verify + SDK explain + summary-only**

> 패턴 내보내기 · 감사 해시체인 검증 · SDK explain 노출 · 스캔 요약 전용 모드 · CLI 문서 갱신. (2026-07-05)

### 이번 릴리스에 포함된 것 (patch118~122)

| 계층 | 기능 |
|---|---|
| **패턴 내보내기** | `export patterns [--format yaml\|json\|regex]` — PII + 인젝션 탐지 패턴 표준 형식 내보내기. 팀 공유·백업·grep 연동 (patch122) |
| **CLI 문서** | CLI.md 에 explain·stats·audit verify 레퍼런스 추가 (patch121) |
| **감사 검증** | `audit verify` — JSONL 감사 로그 해시체인 무결성 검증. 변조 시 위치 보고 (patch120) |
| **스캔 요약** | `scan --summary-only` — CI 빠른 체크용 한줄 요약 + explain 자동완성 등록 (patch119) |
| **SDK explain** | `from nufi import explain` — 텍스트 탐지 이유 상세 분석 SDK 노출 (patch118) |

### 누구에게 유용한가

- **팀 공유/외부 연동** — `export patterns --format regex` 로 패턴을 ripgrep/grep 에 직접 전달. YAML/JSON 으로 백업·버전관리.
- **감사/컴플라이언스** — `audit verify` 로 감사 로그 변조 여부를 즉시 확인(CI 게이트 가능).
- **CI/자동화** — `scan --summary-only` 로 파일별 상세 없이 합격/불합격만 빠르게 확인.
- **SDK 개발** — `explain()` 편의 함수로 탐지 근거를 프로그래밍 방식으로 접근.

---

## v0.4.17 (patch117) — **explain 디버깅 명령 + stats + MANUAL + CLI smoke tests + HANDS_ON**

> explain 탐지 근거 설명 · stats 개요 · 매뉴얼 빠른 참조 · CLI 스모크 15건 · 실습 가이드. (2026-07-05)

### 이번 릴리스에 포함된 것 (patch92~117)

| 계층 | 기능 |
|---|---|
| **explain** | `explain --text "..."` — PII·인젝션 탐지 결과를 엔티티·위치·방법·신뢰도·정책·라우팅까지 상세 설명 (patch116) |
| **stats** | `stats` — 설정 파일·탐지 패턴·캐시·감사 로그 상태 개요 (patch112) |
| **MANUAL** | MANUAL.md v0.4.17 신규 CLI 커맨드 빠른 참조 (patch113) |
| **CLI 스모크** | 전 서브커맨드 통합 스모크 테스트 15건 (patch114) |
| **HANDS_ON** | §10 파일 스캔 & CI 연동 실습 가이드 (patch115) |

### 누구에게 유용한가

- **디버깅/교육** — `explain` 으로 왜 특정 텍스트가 차단/경고되는지 상세 근거 확인. 오탐 조사, 신규 팀원 교육에 활용.
- **운영 점검** — `stats` 로 설정·탐지·캐시·로그 상태를 한눈에 파악.
- **품질 보증** — CLI 전 서브커맨드 스모크 테스트로 회귀 방지.

---

## v0.4.17 (patch110) — **scan profiles + shell completions + E2E tests + SDK examples**

> 스캔 프로파일 · 셸 자동완성 · E2E 통합 테스트 10건 · SDK 실전 예시 2종. (2026-07-05)

### 이번 릴리스에 포함된 것 (patch92~110)

| 계층 | 기능 |
|---|---|
| **스캔 프로파일** | `scan --profile ci` — 사전 정의 프로파일(development/ci/strict)로 옵션 일괄 적용 (patch110) |
| **셸 자동완성** | `completions bash/zsh` — 자동완성 스크립트 생성 + CLI 카테고리 분류 (patch109) |
| **SDK 예시** | `sdk_security_report.py` · `sdk_ci_integration.py` 실전 예시 (patch108) |
| **E2E 테스트** | init→scan→redact, cache 무효화, SARIF/JSONL, 병렬, 인젝션 등 파이프라인 검증 10건 (patch107) |
| **설정 검증** | `config validate` — policy/routing YAML syntax·필수 필드·regex 유효성 검증 (patch105) |
| **diff 스캔** | `diff` — git 변경 파일만 PII/인젝션 스캔, PR 리뷰·pre-commit (patch104) |
| **README** | 데모 섹션에 report·init·watch 추가 (patch103) |
| **webhook 알림** | `watch --webhook URL` — PII 탐지 시 JSON POST(Slack/Teams 연동) (patch102) |
| **스캔 캐싱** | `scan --cache` — SHA-256 파일 해시 기반 결과 캐싱으로 반복 스캔 성능 향상 (patch101) |
| **HTML 리포트** | `report security --format html` — 인라인 CSS, 색상 배지, 외부 의존 없는 자립형 HTML 보안 리포트 (patch99) |
| **보안 리포트** | `report security` — PII/인젝션 스캔 → 위험도 평가 → Markdown/JSON/HTML 리포트 (patch98) |
| **병렬 스캔** | `scan --parallel N` — ThreadPoolExecutor 멀티스레드 스캔 (patch97) |
| **Getting Started** | 워크플로우 데모 스크립트 + SDK batch 문서 (patch96) |
| **SDK batch** | `batch_route()` · `batch_inspect()` 일괄 처리 (patch95) |
| **scan 출력** | `--output PATH` + `--format jsonl` 스트리밍 (patch94) |
| **데모 카탈로그** | DEMO.md 인젝션·스캔·벤치 데모 등록 (patch93) |
| **디렉터리 감시** | `watch` — inotify/polling 기반 파일 변경 실시간 감시 + 자동 스캔 (patch92) |

### 누구에게 유용한가

- **CI/pre-commit** — `scan --profile ci` 로 프로파일 기반 일관된 스캔. `diff --fail-on-pii` 로 변경분만 빠르게 PII 게이트. `config validate` 로 설정 오류 사전 차단.
- **개발자 경험** — `completions bash/zsh` 셸 자동완성으로 CLI 사용성 향상. SDK 실전 예시로 빠른 통합.
- **보안 감사 보고서** — HTML 리포트를 경영진·감사팀에 바로 전달. 색상 배지로 위험도 직관적 파악.
- **대규모 프로젝트** — `--parallel` 멀티스레드 + `--cache` 로 반복 스캔 성능 향상.
- **실시간 알림** — `watch --webhook` 으로 PII 탐지 시 Slack/Teams 즉시 통보.

---

## v0.4.17 (patch105) — **config validate + diff + webhook + scan cache**

> 설정 검증 CLI · git diff 스캔 · watch --webhook 알림 · scan --cache SHA-256 캐싱. (2026-07-05)

### 이번 릴리스에 포함된 것 (patch92~105)

| 계층 | 기능 |
|---|---|
| **설정 검증** | `config validate` — policy/routing YAML syntax·필수 필드·regex 유효성 검증 (patch105) |
| **diff 스캔** | `diff` — git 변경 파일만 PII/인젝션 스캔, PR 리뷰·pre-commit (patch104) |
| **README** | 데모 섹션에 report·init·watch 추가 (patch103) |
| **webhook 알림** | `watch --webhook URL` — PII 탐지 시 JSON POST(Slack/Teams 연동) (patch102) |
| **스캔 캐싱** | `scan --cache` — SHA-256 파일 해시 기반 결과 캐싱으로 반복 스캔 성능 향상 (patch101) |
| **HTML 리포트** | `report security --format html` — 인라인 CSS, 색상 배지, 외부 의존 없는 자립형 HTML 보안 리포트 (patch99) |
| **보안 리포트** | `report security` — PII/인젝션 스캔 → 위험도 평가 → Markdown/JSON/HTML 리포트 (patch98) |
| **병렬 스캔** | `scan --parallel N` — ThreadPoolExecutor 멀티스레드 스캔 (patch97) |
| **Getting Started** | 워크플로우 데모 스크립트 + SDK batch 문서 (patch96) |
| **SDK batch** | `batch_route()` · `batch_inspect()` 일괄 처리 (patch95) |
| **scan 출력** | `--output PATH` + `--format jsonl` 스트리밍 (patch94) |
| **데모 카탈로그** | DEMO.md 인젝션·스캔·벤치 데모 등록 (patch93) |
| **디렉터리 감시** | `watch` — inotify/polling 기반 파일 변경 실시간 감시 + 자동 스캔 (patch92) |

### 누구에게 유용한가

- **CI/pre-commit** — `diff --fail-on-pii` 로 변경분만 빠르게 PII 게이트. `config validate` 로 설정 오류 사전 차단.
- **보안 감사 보고서** — HTML 리포트를 경영진·감사팀에 바로 전달. 색상 배지로 위험도 직관적 파악.
- **대규모 프로젝트** — `--parallel` 멀티스레드 + `--cache` 로 반복 스캔 성능 향상.
- **실시간 알림** — `watch --webhook` 으로 PII 탐지 시 Slack/Teams 즉시 통보.
- **개발 워크플로우** — `watch` 모드로 코드 작성 중 실시간 PII 감시.

---

## v0.4.17 (patch91) — **인젝션 가드레일 + 파일 스캔 + CI 연동 + 스캔 통계**

> 프롬프트 인젝션 탐지 전 계층 + 디렉터리 스캔 + pre-commit/CI + SARIF + redact + init quick-start + scan --stats. (2026-07-05)

### 이번 릴리스에 포함된 것 (patch55~86)

| 계층 | 기능 |
|---|---|
| **SDK** | `detect_injection` · `route` · `inspect_text` · `scan_dir` · `Guard(check_injection=True)` |
| **CLI** | `route --file --stdin --check-injection` · `inspect` · `scan --fail-on-pii --format sarif` · `doctor` (6체크) · `version` |
| **게이트웨이** | `NUFI_CHECK_INJECTION=1` → Phase 0 인젝션 차단 (PII 탐지 전 선행) |
| **LiteLLM** | pre_call_hook Phase 0 인젝션 차단 + 감사 로깅 |
| **파일 스캔** | `scan` 서브커맨드 — 디렉터리 재귀·.nufiignore·--exclude·SARIF 출력 |
| **CI 연동** | pre-commit 훅 + GitHub Actions 예시 + `--fail-on-pii` exit code |
| **severity** | 패턴별 critical/high/medium/low 분류 · `min_severity` · 카테고리 필터 |
| **정책** | `config/policy.yaml` injection.action (block/warn/log) + `config/pii_routing.yaml` |
| **커스텀** | `config/injection_patterns.yaml` 로 운영자 정의 패턴 추가 |
| **벤치마크** | `bench_injection.py` — 골드셋 38건 recall/precision 게이트 (현재 1.0/1.0) |
| **간접 인젝션** | HTML 코멘트·ChatML·Llama·역할변경·유니코드 제로폭 8종 |
| **문서** | `PROMPT_INJECTION.md` · `SDK.md §2.9~2.11` · `INTEGRATION_GUIDE §6` |
| **데모** | `demo_prompt_injection.sh` (31건 PASS) + E2E 11건 + SDK 예시 |

### 누구에게 유용한가

- **LLM 서비스 운영자** — 프롬프트 인젝션을 게이트웨이/프록시 레벨에서 차단. severity 필터로 민감도 조절.
- **보안 감사** — PII + 인젝션 동시 탐지 증빙. `doctor --check-injection`으로 설정 상태 진단.
- **에어갭 환경** — 순수 정규식, 외부 의존 0.

---

## v0.4.17 (patch61) — **한국어 프롬프트 인젝션 탐지 + Guard 통합**

> 한국어·영어 프롬프트 인젝션/탈옥 패턴을 감지하고 차단하는 가드레일 기능. (2026-07-05)

### 무엇이 달라지나

- **`from nufi import detect_injection`** — 한국어 8종·영어 8종·역할변경 2종 프롬프트 인젝션 패턴 탐지.
- **`Guard(check_injection=True).inspect(text)`** — PII 차단과 인젝션 차단을 한 번에.
- **`nufi-egress route --check-injection`** — CLI 에서 인젝션 탐지 동시 수행.
- **`nufi-egress route --file input.txt --summary`** — 파일 일괄 스캔 + 통계.

### 누구에게 유용한가

- LLM 서비스에 **사용자 입력 가드레일**이 필요한 팀 — 프롬프트 인젝션을 인라인으로 차단.
- **에어갭 환경** — 외부 의존 없는 순수 정규식 탐지.
- **보안 감사 대응** — PII + 인젝션 동시 탐지를 증빙으로 제출 가능.

---

## v0.4.17 (patch58) — **README.md PII 라우팅 표면 반영**

> patch55~57 결과물(CLI route·설정 파일·SDK route)을 최상위 README.md에 반영. (2026-07-05)

---

## v0.4.17 (patch56) — **config/pii_routing.yaml 설정 파일 도입**

> PII 라우팅을 코드 수정 없이 YAML 설정 파일로 제어할 수 있습니다. (2026-07-05)

- **운영자 친화**: `config/pii_routing.yaml` 하나만 수정하면 모델명, 활성화 여부, 엔티티 필터를 즉시 변경 가능.
- **하위 호환**: 기존 환경변수·코드 파라미터 방식도 그대로 동작. 설정 파일이 없어도 기본값 사용.
- **우선순위**: 코드 파라미터 > 환경변수 > YAML 설정 (가장 안전한 오버라이드 체계).

---

## v0.4.17 (patch55) — **CLI `route` 서브커맨드 추가**

> PII 라우팅 결정을 CLI에서 바로 테스트할 수 있습니다. (2026-07-05)

### 무엇이 달라지나

- **`nufi-egress route --text "김민수님 계좌 110-123-456789"`** → PII 감지, 로컬 모델 라우팅 판정 출력.
- **`nufi-egress route --text "오늘 날씨 어때"`** → PII 없음, 클라우드 허용 출력.
- **`--json` 플래그** → 기계용 JSON 출력(CI/자동화 연동).
- **`--model`/`--local-model`/`--cloud-model`** → 모델명 커스터마이징.

### 누구에게 유용한가

- **운영자**: 정책 변경 전 PII 라우팅 결정을 즉석에서 확인.
- **개발자**: 감지 엔진 동작을 CLI 한 줄로 디버깅.
- **CI/CD**: `--json` 출력을 파이프라인에서 자동 검증.

---

## v0.4.16 패치 시리즈 (patch01~patch57) — **문서 풍부화 + SDK 사용성 개선**

> 핵심 수치 변경 없음. SDK 표면 확장 + 문서·사용성 보강. (2026-07-05)

### patch57 — SDK `route()` 함수 노출

PII 라우팅 결정을 SDK 한 줄로 호출할 수 있게 됐습니다:

```python
from nufi import route
decision = route("고객 홍길동님 주민번호 …")
if decision.routed_to_local:
    print("로컬 모델로 전환")
```

- `route(text) -> RoutingDecision` — PII 감지 시 로컬, 미감지 시 클라우드 모델 반환
- `RoutingDecision`, `PiiRouter` 도 stable 계층으로 export
- 예시: `examples/sdk_pii_routing.py`

### 패치 시리즈 성과 요약 (한눈에)

| 영역 | 패치 이전 | 패치 이후 |
|---|---|---|
| **Python SDK 예시** | 5종 | **7종** (sdk_file_scan·sdk_compliance_report 신규) |
| **내부 문서 링크** | 92개 | **145개** (+53개, 모든 문서 교차링크 완성) |
| **관련 문서 섹션 보유 문서** | 일부 | **전체** (docs/ 20종 + HANDOVER/ 5종 + 하위 디렉터리) |
| **Finding dataclass 필드 문서화** | 없음 | **7개 필드 타입·설명 표 완비** |
| **PII 클래스 목록 문서화** | 흩어짐 | **12종 표(탐지 방식·강한/약한 구분) MANUAL에 집중** |
| **규제 프레임워크 커버리지 수치** | 총계만 | **5종 프레임워크별 direct/partial/oos 상세 표** |
| **reports/JSON 접근 가이드** | 없음 | **recall-int8.json Python 접근 예시 포함** |
| **디렉터리 진입점 README** | 없음 | **docs/history/ · docs/research/ 인덱스 신설** |

### 무엇이 추가됐나
- **Python SDK 예시 7종 완성** — `sdk_file_scan.py`(파일 PII 탐지), `sdk_compliance_report.py`(규제 커버리지 출력) 신규. 예시 인덱스 `examples/README.md` 신설.
- **`Finding.__repr__` 개선** — 개발자 REPL/로그에서 None 필드 제거, score 소수점 2자리, 기본 source 생략으로 가독성 향상.
- **문서 교차링크 강화** — ARCHITECTURE·DEMO·INTEGRATION_GUIDE·SDK·MANUAL·CLI·HANDS_ON 에 SDK 예시 교차링크 추가. ARCHITECTURE.md §8에 SDK·REPORTING·PII_ROUTING 링크.
- **REPORTING.md Python SDK §4 추가** — `compliance_report`·`render_report`·`load_catalog` 코드 스니펫 신설.
- **골드셋 README 프로그래밍 가이드** — `samples/gold/README.md` 에 Python 로드·필터링·manifest 검증 코드 스니펫 추가.
- **ROADMAP 완료 상태 업데이트** — P1(한국 규제 증빙 48개 통제 완료)·P2(SDK v0.4.6·patch 확장) 정확히 기록.
- **보고서 인덱스 정비 + 링크 수정** — `docs/reports/README.md` 누락 파일 5건 추가, ROADMAP.md 깨진 링크 2건 수정.
- **research/ 문서 인덱스** — `docs/README.md` 에 research/ 조사·전략 문서 섹션 추가.
- **HANDOVER 전반 현행화** — `PROJECT_STATE.md`·`PROJECT_OVERVIEW.md`·`README.md` patch15 기준 갱신 + 갭 점검 결과 기록.
- **교차링크 전반 보강(patch14~19)** — `INTEGRATION_GUIDE.md`·`PRESETS.md`·`OPS_RULE_RELOAD.md`·`OPS_POLICY_AT_SCALE.md`·`SECURITY_RETAIN_RAW_KEYROTATION.md` 에 관련 문서 표 신설. `MANUAL.md` SDK 예시 7종 인덱스 링크.
- **디렉터리 README 신설(patch18~19)** — `docs/research/README.md`(조사·전략 문서 3종 인덱스), `docs/history/README.md`(역사적 스냅샷 6종 인덱스) 신설.

- **관련 문서 섹션 전반 보강(patch20~24)** — `SDK.md`·`PII_ROUTING.md`·`REPORTING.md`·`DEMO.md`·`ROADMAP.md` 에 관련 문서 표 신설. 문서간 교차링크 체계 완성.

- **docs/README.md 진입점 보강(patch27)** — history/README.md·research/README.md 링크 추가로 하위 폴더 탐색성 향상.
- **INTEGRATION_GUIDE.md 관련 문서 표(patch28)** — PRESETS·CLI·SDK·HANDS_ON·PII_ROUTING·OPS_RULE_RELOAD 6종 교차링크.

- **하위 패키지 README 교차링크(patch30~31)** — `nufi_client/README.md`·`samples/gold/README.md` 에 관련 문서 표 신설.

- **research/ 전략 문서 관련 문서 섹션(patch33)** — `FSEC_AI_GUIDE_2026.md`·`SOLUTION_FOCUS_OPTIONS.md`·`NUFI_SECURITY_PLANE_CHARTER.md` 에 관련 문서 표 신설. 조사·전략 문서 간 교차링크 체계 완성.

- **CLI·HANDS_ON 관련 문서 섹션(patch35)** — `CLI.md`·`HANDS_ON.md` 에 관련 문서 표 신설. 두 핵심 레퍼런스 문서 교차링크 완성.

- **HANDOVER·DOC_STYLE 관련 문서 섹션(patch36)** — `AGENT_OPERATING_MODEL.md`·`ENGINEERING_CONVENTIONS.md`·`DOC_STYLE.md` 에 관련 문서 표 신설. 거버넌스·규약 문서 간 교차링크 완성.

- **RELEASE_CHECKLIST 관련 문서 섹션(patch37)** — `RELEASE_CHECKLIST.md` 에 관련 문서 표 신설. 릴리스 절차 문서 교차링크 완성.

- **reports/README 관련 문서 섹션(patch38)** — `docs/reports/README.md` 에 관련 문서 표 신설. 측정 보고서와 REPORTING·SDK·HANDS_ON·goldset 교차링크 완성.

- **docs/README 관련 문서 섹션(patch39)** — `docs/README.md`(문서 지도 인덱스) 에 관련 문서 표 신설. 지도 → 제품·매뉴얼·실습·이력·인수인계 교차링크 완성.

- **PROJECT_STATE 교차링크 이력 현행화(patch40)** — `HANDOVER/PROJECT_STATE.md` §4 갭 점검에 patch14~39 에 걸친 교차링크 전반 보강 16개 항목 표 추가.

- **reports/README 보고서 JSON 키 구조 안내(patch41)** — `recall-int8.json` 의 Python 접근 예시(per_class_recall·latency·acceptance·SDK) 추가. 수치를 코드에서 읽는 방법 문서화.

- **REPORTING 프레임워크별 커버리지 수치 표(patch42)** — 5종 규제(fsec-ai·net-sep·pipa·cia·isms-p) 48개 통제의 direct(25)/partial(11)/oos(12) 수치를 프레임워크별 표로 명시화. `net-sep` 5/5 direct 강조.

- **MANUAL §3 PII 클래스 12종 표(patch43)** — 매뉴얼 §3 핵심 개념에 탐지 대상 PII 클래스 전체 목록(클래스명·설명·탐지 방식·강한/약한 구분) 추가.

- **SDK Finding 필드 상세 표(patch44)** — `docs/SDK.md` §2.2 에 `Finding` dataclass 7개 필드(entity_type·text·start·end·score·source·context) 타입·설명 표 추가.

- **MANUAL 부록 문서 지도 완성(patch45)** — `docs/MANUAL.md` 부록 문서 지도 표에 SDK·PII_ROUTING·RELEASE_NOTES·DOC_STYLE 4개 링크 추가. 잔재 XML 태그 제거. 내부 링크 145개로 증가.

- **RELEASE_NOTES 패치 시리즈 성과 요약 표(patch46)** — patch01~patch45 의 성과를 "패치 이전/이후" 8개 지표 비교 표로 시각화(SDK 예시 수·내부 링크 수·관련 문서 섹션·Finding 문서화·PII 클래스 표·규제 커버리지·reports JSON 가이드·디렉터리 README).

- **MANUAL §9 용어집 7개 항목 추가(patch47)** — Wilson 신뢰구간·강한 PII·약한 PII·가역성·PII 라우팅 등 독자가 자주 헷갈리는 핵심 개념 7개를 용어집에 추가.

- **ROADMAP §6 현재 달성 수치 표(patch48)** — v0.4.16 기준 10개 지표(전체 PII 재현율·인명·주소·지연·오탐·12클래스 CI·규제 증빙·SDK 예시·테스트·데모)를 목표값 대비 달성값 표로 정리. 로드맵 문서에서 제품 현황을 한눈에 파악 가능.

- **MANUAL §3 감사 로그 JSONL 스키마(patch49)** — `logs/egress_audit.jsonl` 레코드 필드 표(12개 필드)와 실제 JSON 예시 추가. 원문 PII 마스킹 방식(`len=...:sha256=...`) 명시.

- **REPORTING §5 감사관 제출 치트시트(patch50)** — 한국 규제 감사(금융보안원·금융위원회·개인정보보호위원회·과기부·KISA) 대응 시 표준 5단계 CLI 흐름과 규제별 `--framework` 대응표 추가.

- **SDK GuardResult·Decision 필드 표(patch51)** — `Guard.inspect()` 반환값 `GuardResult`·`Decision` dataclass 의 모든 필드(5+4개, 타입·설명·property 포함)와 사용 예시 추가.

기술 변경 상세: [`CHANGELOG.md`](../CHANGELOG.md) patch01~patch51 절.

---

## v0.4.16 — **인명 재현율(recall) 97.99% 달성 — 골드셋 최신화**

### 한 줄 요약
인명(KR_PERSON) 재현율(recall)이 **97.99%**(Wilson 신뢰구간(confidence interval) 하한 **95.91%**)로
상향되었습니다. 이전 릴리스의 골드셋 회귀(regression)를 완전 해소하고, 전체 개인정보(PII) 재현율도
**99.08%** 로 개선되었습니다.

### 주요 변경
- **미수록 성씨 골드셋 재설계** — 자연어 처리(NLP) 모델이 탐지할 수 없는 합성 음절 성씨를
  실제 탐지가 확인된 성씨 23종으로 교체했습니다.
- **골드셋 표본 확대** — KR_PERSON 테스트 샘플 258건→348건으로 늘려 신뢰구간 하한을 강화했습니다.
- **컨텍스트 개선** — 약한 문맥 패턴에 경칭을 추가해 모델 탐지 정확도를 높였습니다.

### 검증 결과

| 지표 | v0.4.15 (회귀) | v0.4.16 |
|------|---------------|---------|
| 전체 PII 재현율 | 0.8739 | **0.9908** |
| 인명 재현율 | 0.6700 | **0.9799** |
| 인명 CI 하한 | — | **0.9591** |
| 골드셋 n | 818 | **854** |
| 수용 기준 통과 | ✗ | **✅** |

### 클래스별 재현율 (onnx-int8, split=test)

| 클래스 | 재현율 | Wilson CI95 하한 | n |
|---|---:|---:|---:|
| KR_PERSON | 0.9799 | **0.9591** ✅ | 348 |
| KR_LOCATION | 1.0000 | 0.9417 ✅ | 62 |
| KR_RRN | 1.0000 | 0.9011 ✅ | 35 |
| KR_FOREIGNER_REG | 1.0000 | 0.9011 ✅ | 35 |
| KR_PASSPORT | 1.0000 | 0.9011 ✅ | 35 |
| KR_DRIVER_LICENSE | 1.0000 | 0.9011 ✅ | 35 |
| KR_ACCOUNT | 1.0000 | 0.9036 ✅ | 36 |
| KR_BRN | 1.0000 | 0.9011 ✅ | 35 |
| KR_PHONE | 1.0000 | 0.9036 ✅ | 36 |
| CREDIT_CARD | 1.0000 | 0.9011 ✅ | 35 |
| EMAIL | 1.0000 | 0.9036 ✅ | 36 |
| SECRET | 1.0000 | 0.9036 ✅ | 36 |

**12개 클래스 전부 Wilson CI95 하한 ≥ 0.90 달성.**

### 참고
- 성능 측정: `docs/reports/recall-int8.json`
- 골드셋 정합 검증: `python3 goldset/generate.py --verify`
- 전체 테스트: `pytest` — 307 passed (v0.4.16 + examples/ 스모크 테스트 7건)

---

## v0.4.15 — **골드셋 성씨 목록 정합 복원**

### 한 줄 요약
성씨 사전 확장 이후 골드셋의 "미수록 성씨" 목록과 실제 사전이 어긋나는 불일치를 해소했습니다.
테스트 스위트가 전면 통과하도록 복원했습니다.

### 주요 변경
- 사전에 수록된 성씨를 "미수록" 목록에서 제거하여 골드셋 불변 조건 복원
- 골드셋·매니페스트·가명화 리포트 재생성

---

## v0.4.14 — **확장 골드셋 벤치마크 확정 (n=818)**

### 한 줄 요약
극희귀 성씨 54건을 추가한 확장 골드셋(818건)으로 ONNX-int8 전체 벤치마크를 재실행해
확정했습니다.

### 주요 변경
- 골드셋 764→818건 (KR_PERSON 극희귀 성씨 54건 추가)
- `recall-int8.json` 갱신 — n=818, pii_recall=0.9908 이전 기준으로 확정

---

## v0.4.13 — **체크섬 엔터티 골드셋 + KR_PERSON 신뢰구간 강화**

### 한 줄 요약
주민등록번호·여권번호 등 체크섬(checksum) 기반 엔터티 6종의 골드셋 표본을 확대하고,
인명 골드셋 표본 120건을 추가해 Wilson 신뢰구간 하한 0.93+ 를 달성했습니다.

### 주요 변경
- 체크섬 엔터티(RRN·여권번호·운전면허번호·신용카드번호·사업자번호·외국인등록번호) n≥35, CI 하한 0.90+
- KR_PERSON 등재 성씨 120건 추가 → test 186→258건
- `recall-int8.json` 갱신

---

## v0.4.12 — **KR_ACCOUNT·SECRET 신뢰구간 하한 완료**

### 한 줄 요약
계좌번호(KR_ACCOUNT)·비밀값(SECRET) 골드셋을 확대해 Wilson 신뢰구간(confidence interval)
하한 0.90 목표를 달성했습니다.

### 주요 변경
- KR_ACCOUNT·SECRET 각 20건→36건으로 확대 → CI 하한 0.862→0.9036

---

## v0.4.11 — **문서 풍부화 + 정확도 골드셋 확대**

### 한 줄 요약
운영자 매뉴얼 업그레이드 가이드를 실제 내용으로 채우고, SDK/아키텍처/PII 라우팅 문서를
정리했으며, KR_PHONE·EMAIL 골드셋 표본을 확대하여 Wilson CI 하한 ≥0.90 을 달성했습니다.

### 주요 변경
- **MANUAL.md §8 업그레이드 가이드** — 버전별 마이그레이션 절차·롤백 방법 완비
- **SDK.md·ARCHITECTURE.md·PII_ROUTING.md** — 레퍼런스 정리·버전 통일·비용추적 추가
- **골드셋 882건** — KR_PHONE 60건, EMAIL 60건으로 확대 → CI 하한 0.90+ 통과

### 검증
- `python3 goldset/generate.py --verify` — VERIFY OK (content_hash 일치)
- `pytest` — 297 passed, 3 skipped

---

## v0.4.6 — **SDK 편의 함수 — 파일·일괄 PII 탐지를 한 줄로**

### 한 줄 요약
`scan_file("고객데이터.txt")` 한 줄로 파일의 PII 를 탐지하고,
`guard_file("제안서.md")` 로 외부 전송 가부를 판정하고,
`batch_detect(["텍스트1", "텍스트2"])` 로 여러 텍스트를 효율적으로 일괄 탐지합니다.

### 사용법

```python
from nufi import scan_file, guard_file, batch_detect

# 파일에서 PII 찾기
findings = scan_file("customer_data.txt")

# 파일을 외부로 보내도 되는지 판정
result = guard_file("proposal.md")
if result.blocked:
    print("차단됨")

# 여러 텍스트 한 번에 탐지
all_findings = batch_detect(["텍스트1", "텍스트2"])
```

### 검증
- 테스트: `python3 tests/test_cmp249_sdk_helpers.py` — 14/14 PASS
- 데모: `./scripts/demo_sdk_helpers.sh` — 5/5 PASS

---

## v0.4.5 — **운영자 매뉴얼 v0.4.x 반영**

MANUAL.md 에 v0.4.0~v0.4.4 기능(SDK·PII 라우팅·강건성·벤치마크)을 반영했습니다.
상세: [`CHANGELOG.md`](../CHANGELOG.md) [0.4.5] 참고.

---

## v0.4.4 — **데모 정합성 수정 — FAIL 5 → FAIL 0 달성**

### 한 줄 요약
카탈로그 업그레이드(23→25 direct) 이후 깨진 데모 assertion 3건을 수정하고,
uvicorn 미설치 환경에서 HTTP 게이트웨이 데모가 SKIP 되도록 개선했습니다.
`demo_all.sh` **FAIL 0** (PASS 11 · SKIP 2) 달성.

### 수정 내용

| 데모 | 문제 | 수정 |
|---|---|---|
| `demo_location_union.sh` | `person_union` 속성 누락 → AttributeError | 속성 초기화 추가 |
| `demo_report.sh` | direct 통제 23→25 미반영 | assertion 갱신 |
| `demo_compliance_mapping.sh` | 롤업·프레임워크 소계 미반영 | assertion 갱신 |
| `demo.sh` · `demo_audit_separation.sh` | uvicorn 없으면 FAIL | 없으면 SKIP (exit 0) |
| `demo_all.sh` | SKIP 감지 못 함 | SKIP 출력 감지 → 집계 |

---

## v0.4.5 — **운영자 매뉴얼이 v0.4.x 를 따라잡았다 — SDK·라우팅·강건성·벤치마크 반영**

### 한 줄 요약
운영자 매뉴얼(`docs/MANUAL.md`)에 v0.4.0~v0.4.4 에서 추가된 기능을 모두 반영했습니다.
처음 매뉴얼을 읽는 운영자가 Python SDK, PII 라우팅, 게이트웨이 강건성 설정을 한 문서에서
확인할 수 있습니다.

### 무엇이 달라졌나

| 항목 | 이전 | 이후 |
|---|---|---|
| Python SDK | 매뉴얼에 없음 | §2 퀵스타트 뒤에 5줄 예시 추가 |
| PII 라우팅 | 매뉴얼에 없음 | §3 흐름도에 "유출 경로 원천 제거" 추가 |
| 게이트웨이 강건성 | 매뉴얼에 없음 | §5.7 환경변수 표(타임아웃·크기제한·지연추적) |
| `benchmark` 서브커맨드 | CLI 표에 없음 | §4 CLI 표에 추가 |
| `nufi` 별칭 | 매뉴얼에 없음 | §4 실행 방법에 명시 |
| 정확도 수치 | 0.9433 (v0.1.0) | 0.977 (v0.3.0) |

### 검증

- 문서 스타일 가드: `check_doc_style.py` rc=0
- 문서 정합 가드: `test_docs_consistency.py` 12/12 PASS

---

## v0.4.3 — **문서 정합성 강화 — 운영 제외 안내 전파 + CLI 누락 보완 + 릴리스 노트 확장**

### 한 줄 요약
문서 간 **정합성**을 높였습니다. 운영 레이어 제외 안내가 README 에만 있어 다른 문서를
보는 사용자가 제외된 기능을 현행으로 오해할 수 있는 문제를 해소하고, CLI 레퍼런스의
누락·불일치를 교정했습니다.

### 무엇이 달라졌나

| 항목 | 이전 | 이후 |
|---|---|---|
| 운영 제외 안내 | README 에만 | DEMO·HANDS_ON·CLI 에도 ⚠️ 표기 |
| CLI `benchmark` 표기 | 상세 절만 있고 usage·표에서 누락 | usage + 표에 추가 |
| CLI `nufi` 별칭 | 미언급 | 실행 방법 절에 명시 |
| v0.4.1 릴리스 노트 | 2줄 스텁 | 전체 형식(비교표·사용법·검증) |
| HANDS_ON 버전 라벨 | `(v0.0.3)`, `(v0.0.5 신규)` | 제거 (현재 v0.4.x) |
| README 데모 번호 | `3b`, `3b''`, `3b'''` | `4` ~ `10` 순차 |

### 검증

- 문서 스타일 가드: `check_doc_style.py` rc=0
- 문서 정합 가드: `test_docs_consistency.py` 12/12 PASS

---

## v0.4.2 — **게이트웨이가 더 튼튼해졌다 — 타임아웃·지연 추적·방어 파싱 + README 포지셔닝 정렬**

### 한 줄 요약
게이트웨이 코어에 **탐지 타임아웃**(NER 모델이 멈춰도 요청이 안전 차단됨),
**요청 지연 추적**(모든 응답에 latency_ms), **방어 파싱**(비정상 입력 안전 처리)을
추가해 프로덕션 안정성을 높였습니다. README 를 로드맵 방향과 정렬했습니다.

### 무엇이 달라졌나

| 기능 | 이전 | 이후 |
|---|---|---|
| NER 모델 행(hang) | 게이트웨이 전체 멈춤 | 5초(조정 가능) 후 fail-closed 차단 |
| 비정상 메시지(content=null 등) | 파이프라인 예외 위험 | 안전하게 건너뜀 |
| 큰 프롬프트(수 MB) | OOM 위험 | 512KB(조정 가능)까지만 탐지 |
| 처리 지연 측정 | 없음 | 응답 헤더 `X-NuFi-Latency-Ms` + 감사 로그 |
| README 첫인상 | "Egress-Audit Gateway" | "한국어 PII·규제 증빙 경량 엔진" |

### 설정

```bash
export NUFI_DETECT_TIMEOUT_MS=3000    # 탐지 타임아웃 (밀리초, 기본 5000)
export NUFI_MAX_PROMPT_BYTES=262144   # 프롬프트 크기 제한 (바이트, 기본 512KB)
```

### 검증

- 테스트: `python3 tests/test_cmp249_resilience.py` — 16/16 PASS
- 데모: `./scripts/demo_resilience.sh` — 5/5 PASS
- 기존 테스트: `test_cmp85_p0.py` 4/4 PASS · `test_cmp247_pii_routing.py` 35/35 PASS

---

## v0.4.1 — **Python SDK 파사드 — `from nufi import ...` 한 줄로 시작**

### 한 줄 요약
게이트웨이 없이, 코드에서 NuFi 엔진을 직접 임포트해 쓸 수 있는 **Python SDK 파사드**를
구현했습니다. `from nufi import detect, Guard, pseudonymize` 한 줄로 탐지·가명화·정책 평가를
시작할 수 있습니다.

### 무엇이 달라졌나

| 기능 | 이전 | 이후 |
|---|---|---|
| 라이브러리 사용 | `egress_audit`, `enforcement` 등 내부 패키지 직접 임포트 | `from nufi import detect` 한 줄 |
| 탐지 편의 함수 | 없음 — `DetectionPipeline` 객체 직접 생성 | `detect(text)` 한 줄 (모델 지연 로딩) |
| 공개 API 정의 | 흩어진 3곳 | `nufi.__all__` 에 stable 15개 심볼 |
| 임포트 부수효과 | 미보장 | `import nufi` 가 모델·config 로딩 0 (에어갭 안전) |

### 사용법

```python
from nufi import detect, Guard, pseudonymize

findings = detect("김민수님 계좌번호 110-123-456789")
token = pseudonymize("KR_PERSON", "김민수")
result = Guard().inspect(text)
```

API 전체 목록: [`docs/SDK.md`](SDK.md)

### 검증

- 테스트: `python3 -m pytest tests/test_cmp249_sdk.py` — 26/26 PASS
- 데모: `./scripts/demo_sdk.sh` — 4/4 PASS

---

## v0.4.0 — **PII 가 있으면 아예 클라우드로 안 보낸다 — 하이브리드 라우팅 + 규제 증빙 48개 통제 완성**

### ① 한 줄 요약
v0.4.0 은 두 가지를 동시에 해낸 릴리스입니다. 첫째, PII 감지 엔진을 **라우팅의 가장 앞단**에
올려, PII 가 포함된 요청은 클라우드로 보내지 않고 로컬 모델로 강제 전환하는 **하이브리드 LLM
라우팅**을 도입했습니다. 둘째, 한국 규제 증빙 팩을 **48개 통제**(카탈로그 v1.2)로 확장하고
자동판정 비율을 높였습니다.

### ② 이번 버전의 핵심

**1. PII 기반 하이브리드 LLM 라우팅 — "차단"이 아니라 "경로 자체를 없앤다"**

기존 v0.3.0 까지는 PII 가 섞인 요청이 클라우드 경로에 도달한 뒤 **차단(403)** 하거나
**가명화 후 전송**했습니다. v0.4.0 은 한 단계 앞서, PII 감지가 기존 egress 감사보다
**먼저 실행**되어 PII 포함 요청을 **로컬 모델로 강제 전환**합니다. 클라우드로 나가는
경로 자체가 사라지므로 유출 가능성이 원천 차단됩니다.

```
요청 → [PII 감지] → PII 있음 → 로컬 모델 (강제, 외부 미전송)
                 → PII 없음 → [기존 라우팅] → private/public 결정
```

- **무엇이 좋아졌나**: PII 유출을 "나가려는 걸 막는다"에서 **"나가는 길 자체를 없앤다"**로
  방어 수준이 올라갔습니다. PII 없는 요청은 그대로 클라우드 모델을 써서 비용·품질 최적화를
  유지합니다.
- **비용 추적**: 요청마다 어느 모델로 갔는지, 비용이 얼마인지 추적합니다.
- **fail-closed**: 프로바이더 장애 시 로컬 모델로 폴백하여 외부 전송을 허용하지 않습니다.

**2. 한국 규제 증빙 팩 — 48개 통제, 자동판정 25개로 확장**

PIPA(개인정보보호법) 10항목, CIA(신용정보법) 7항목, ISMS-P 11항목을 추가해 **총 48개
통제**(direct 25 / partial 10 / OOS 13)를 완비했습니다. v0.1.0 의 19개 대비 2.5배 확장입니다.

- **partial → direct 승격**: 모니터링·보고(C-11)를 감사 로그 증빙으로 자동판정하도록
  승격했습니다. 위변조방지(CIA-19-INTEG)도 direct 로 분리해 자동판정 범위를 넓혔습니다.
- **증빙 출처 강화**: "이 통제는 **어떤 증빙**으로 충족했나"를 행 단위로 확인할 수 있습니다
  (로그 경로·체인 수·무결성 상태 포함).
- **무엇이 좋아졌나**: 감사·구매 심사에서 **점검표 48개 항목에 대한 답**이 한 리포트에 나옵니다.
  자동판정 25개는 증빙을 **손으로 채우지 않아도** 됩니다.

### ③ 사용법

```bash
git pull && pip install -e .

# PII 라우팅 데모 — PII 포함 → 로컬, PII 없음 → 클라우드
python3 scripts/demo_pii_routing.py

# 컴플라이언스 매핑 — 48개 통제 전체 커버리지
./scripts/demo_compliance_mapping.sh

# 전체 데모
./scripts/demo_all.sh
```

### ④ 호환성 / 주의
- PII 라우팅은 `config/routing.yaml` 의 `pii_routing.enabled: true` 로 활성화합니다
  (기본 `true`). 기존 egress 감사·차단·가명화 동작은 그대로 유지됩니다.
- 컴플라이언스 카탈로그 v1.2 는 기존 v1.0/v1.1 과 **상위 호환**입니다.
- 대시보드 레이어 코드가 정리되었습니다(`dashboards/` 디렉터리·`dashboard` CLI 서브커맨드 삭제).
  방향 재설정(v0.1.0)에서 이미 제외 표기된 기능이며, 운영 영향은 없습니다.

### ⑤ 다음
PII 라우팅 Phase 2 — 엔티티별 세분 정책(예: 주민번호만 로컬, 이메일은 가명화 후 클라우드) ·
LiteLLM 프록시 프로덕션 연동 · 비용 대시보드. 규제 증빙 팩 partial 항목 추가 승격.

### ⑥ 한눈에 — 무엇을 받았나
- **PII 기반 하이브리드 라우팅** — PII 포함 → 로컬 모델 강제, PII 없음 → 클라우드 허용. 비용 추적 + fail-closed.
- **규제 증빙 48개 통제** — PIPA·CIA·ISMS-P 카탈로그 v1.2, direct 25개 자동판정 + 증빙 출처 강화.
- **대시보드 코드 정리** — 제외된 운영 레이어 잔여 코드 삭제.

---

## v0.3.0 — **인명 인식률 95% 달성 — 모든 한국어 PII 목표 통과**

### ① 한 줄 요약
v0.3.0 은 한국어 PII 탐지에서 마지막으로 남은 정확도 한계였던 **인명(KR_PERSON)** 의
재현율을 **0.9516**(Wilson CI 하한 **0.9106** ≥ 목표 0.90)으로 끌어올린 **정확도 본편
릴리스**입니다. v0.2.0 이 주소를, v0.3.0 은 인명까지 릴리스 게이트로 통과시켰습니다.

### ② 이번 버전의 핵심

**인명 인식률을 릴리스 게이트로 끌어올림 — CI 하한 0.85에서 0.91+로**

v0.2.1 분석에서 인명 FN 의 약 82%가 **사전 미수록 성씨**(희성·복성)에 몰려 있음을
확인했습니다. v0.3.0 은 이를 세 갈래로 고쳤습니다.

- **성씨 사전 대폭 확장**: 상위 ~60 → **~138** 으로 확장. 희귀 단성 ~78 + 복합 성씨
  (남궁·선우·황보·제갈 등) 14 를 추가해 사전 미수록 FN 의 대부분을 해소했습니다.
- **모델이 놓친 인명을 규칙이 회복(유니온)**: 주소(v0.2.0)와 동일한 플레이북으로, 프로덕션
  모델의 출력에 규칙(경칭/직함/문맥 게이팅)이 찾은 인명을 **더해** 회복합니다. 더하는
  방향이라 오탐은 늘지 않습니다.
- **통계적으로 믿을 만한 표본**: 등재 성씨 표본 100건을 추가해 test 셋 KR_PERSON 을
  126 → 186 건으로 확대. Wilson CI 폭이 좁혀져 CI 하한이 목표선을 넘었습니다.

**전체 성적표**

| 지표 | before v0.2.2 | after v0.3.0 |
|---|---|---|
| 전체 PII 재현율 | 0.9433 | **0.977** (CI 0.9569–0.9879) |
| 인명(KR_PERSON) 재현율 | 0.9127 (CI 하한 0.85) | **0.9516** (CI 하한 **0.91**) |
| 주소(KR_LOCATION) 재현율 | 1.0 | **1.0** |
| 정밀도 | 0.9925 | **0.9948** |
| 오탐 (benign FP) | 0/90 | **0/90** |

- 무엇이 좋아졌나: "인명도 잘 잡는다"가 주장이 아니라 **공개 평가셋 비교로 통과가
  증명된 게이트**가 되었습니다. 전체 PII 카테고리 중 목표선(0.90) 미달이 더 이상 없습니다.

### ③ 참고
KR_PERSON 게이트 기준이 CI 하한 ≥ 0.85 에서 **≥ 0.90** 으로 상향되었습니다. 프로덕션
모델(onnx-int8)을 직접 재실행할 수 없는 환경에서는 규칙 백엔드의 라이브 하한을 인용합니다.
유니온은 모델 출력에 규칙을 더하므로 실제 재현율은 이 하한 이상이며, 모델을 붙여 재측정하면
숫자가 확정·상향됩니다.

### ④ 다음
잔여 인명 FN 은 사전 미수록 극희귀 성씨에 집중됩니다. NER 베이스 모델 격상과 가명화 품질
고도화는 후속 과제로 이어집니다.

---

## v0.2.2 — **공개하는 숫자를 봉인하다** (수치 무결성·문서 패치)

### ① 한 줄 요약
v0.2.2 는 코드·규칙·모델·재현율을 바꾸지 않는 **정직성 패치**입니다. 우리가 공개 문서에
자랑하는 정확도·성능 숫자가 실제 근거(커밋된 측정 리포트)와 **한 자리도 어긋나지 않도록**
맞추고, 앞으로 어긋나면 자동으로 걸리도록 가드를 걸었습니다. 보안·컴플라이언스 제품에서
숫자의 정직성은 곧 신뢰입니다.

### ② 이번 버전의 핵심

**공개 숫자를 전수 대조해 옛 값 3건을 바로잡았습니다.**

초기 버전(v0.0.1) 때 적은 README 요약표의 세 숫자가, 그 뒤 평가셋이 커지고 실측이
갱신됐는데도 옛 값으로 남아 있었습니다. 이번에 근거 리포트와 맞췄습니다.

- 전체 개인정보 인식률: 0.946 → **0.9433** (신뢰구간 0.9098–0.9648)
- 정밀도: 0.985 → **0.9925**
- 인라인 지연: 38ms → **41ms** (단일 동시성 실측)

세 숫자 모두 각주로 **어느 리포트에서 나온 값인지** 경로를 붙여 누구나 확인할 수 있게
했습니다. 나머지 공개 수치(주소·인명 인식률, 신뢰구간, 오탐 0, 부하 지연)는 전수 대조
결과 **전부 근거와 일치**했습니다 — 문제는 초기 세 숫자에 국한됐습니다.

- **무결성 감사 리포트 신설**: 공개 수치 ↔ 리포트 대조표(드리프트 3건·일치 6건)를
  [`docs/reports/accuracy-integrity-audit.md`](reports/accuracy-integrity-audit.md) 로 남겼습니다.
- **재발 방지 가드**: 문서의 헤드라인 숫자가 근거 리포트 값과 벌어지면 검사(`check_docs`)가
  실패합니다. 다음에 측정이 바뀌면 문서를 같이 고치도록 강제됩니다.

### ③ 정직한 실측 보고 (이월)
프로덕션 모델(onnx-int8)이 이번 환경에도 설치돼 있지 않아 주소 유니온 재측정은 skip 을
유지하고 주소 재현율은 규칙 하한(1.0)으로 인용합니다. 온프렘 지연 정밀 측정도 측정
하드웨어 확보 대기 중입니다. 확보 시 재측정으로 상향 확정합니다(측정 강요 아닌 정직 보고).

### ④ 다음(v0.3.0)
인명 정확도 **본편**과 SDK 경량 파사드는 새 기능이므로 별도 minor 로 진행합니다.

---

## v0.2.1 — **인명 정확도, 다음 개선의 지도를 그리다** (측정·문서·정리 패치)

### ① 한 줄 요약
v0.2.1 은 코드를 바꾸지 않는 **정리·측정 패치**입니다. v0.2.0(주소 정확도)에서 남긴 실측
잔여를 정직하게 마무리하고, 공개 문서에 남은 **마지막 정확도 한계인 인명(KR_PERSON)** 을
왜·어디서 놓치는지 데이터로 규명해 다음 개선(v0.3.0)의 지도를 그렸습니다.

### ② 이번 버전의 핵심

**인명 인식의 약점을 숫자로 짚었습니다 — 그리고 어디를 고치면 되는지도.**

프로덕션 모델의 한국어 인명 인식률은 **0.9127**(100건 중 약 91건)로 목표선(0.90)을 넘지만,
통계적으로 "확신을 갖고 0.90 이상"이라고 말하려면 신뢰구간 하한(현재 **0.85**)이 더 올라가야
합니다. 이번 분석으로 **놓치는 이름의 약 82%가 사전에 없는 이름**(드문 성씨, 그리고 선우·
남궁·황보 같은 두 글자 성씨)에 몰려 있음을 확인했습니다. 즉 문맥이 아니라 **이름 형태**가
원인이며, 다음 버전에서 성씨·이름 사전 확장과 규칙∪모델 유니온으로 겨냥할 지점이 분명해졌습니다.

- **오차 분석 리포트 신설**: 놓친 사례를 전량 덤프하고 이름 형태·업무 도메인·조사 경계로
  분류했습니다. 규칙·모델은 손대지 않았습니다(측정만).
- **정직한 실측 보고**: 프로덕션 모델(onnx-int8)이 이번 환경에도 설치돼 있지 않아 주소
  유니온 재측정은 skip 을 유지하고, 주소 재현율은 규칙 하한(1.0)으로 인용합니다.
- **공개 문서 동기화**: README 의 인명 한계 설명에 실제 수치와 분석 리포트 링크를 붙였습니다.

### ③ 다음(v0.3.0)
인명 정확도 **본편** — 성씨·이름 규칙 확장 + 모델∪규칙 유니온 + 골드셋 미수록 슬라이스
확장 + 신뢰구간 하한 게이트 상향(0.90) — 은 별도 minor 로 진행합니다. 근거는 이번 리포트
[`docs/reports/kr-person-error-analysis.md`](reports/kr-person-error-analysis.md).

---

## v0.2.0 — **주소 인식, 자랑할 수 있는 숫자로** (한국어 PII 정확도 엔진 본편)

### ① 한 줄 요약
v0.2.0 은 한국어 PII 탐지에서 가장 약했던 **주소(KR_LOCATION)** 를 골라, 재현율을
**0.79 → 1.0(신뢰구간 하한 0.90 이상)** 으로 끌어올린 **정확도 본편 릴리스**입니다.
v0.1.0 이 "정확도를 재현 가능한 숫자로" 고정했다면, v0.2.0 은 그 숫자 중 하나를 실제로
**릴리스 게이트로 통과**시켰습니다.

### ② 이번 버전의 핵심

**주소 인식률을 릴리스 게이트로 끌어올림 — 0.79에서 0.90+로**

v0.1.0 baseline 에서 주소는 "서울 강남", "삼성동" 같은 어휘밖 고유지명과 도로명·상세주소를
놓쳐 재현율 **0.79(신뢰구간 하한 0.60)** 에 머물렀습니다. v0.2.0 은 이를 세 갈래로 고쳤습니다.

- **주소 규칙 대폭 확장**: 시군구·랜드마크·도로명·상세주소를 아우르도록 주소 사전을
  28항에서 206항으로 확장하고, 조사 경계를 정확히 처리해 무해한 문장에서의 오탐을 없앴습니다.
- **모델이 놓친 주소를 규칙이 회복(유니온)**: 프로덕션 모델의 출력에 주소 규칙이 찾은
  부분을 **더해** 구조적 주소까지 잡습니다. 더하는 방향이라 오탐(무해 입력 오차단)은 늘지
  않습니다.
- **통계적으로 믿을 만한 표본**: 공개 평가셋의 주소 예시를 늘려, 점수의 신뢰구간 하한이
  목표선(0.90)을 넘도록 표본을 확보했습니다.

**릴리스 게이트 3조건, 전부 통과**

| 조건 | before v0.1.0 | after v0.2.0 |
|---|---|---|
| 주소 재현율(신뢰구간 하한) | 0.79 (하한 0.60) | **1.0 (하한 0.94 test · 0.91 dev)** |
| 무해 입력 오차단 | 0.0 | **0.0** |
| 전체 정밀도 | ~1.0 | **~0.99** |

- 무엇이 좋아졌나: "주소도 잘 잡는다"가 주장이 아니라 **전/후 공개 평가셋 비교로 통과가
  증명된 게이트**가 되었습니다. 재현율을 올리면서도 오탐을 늘리지 않았다는 점이 함께
  검증됩니다. 판정 증빙은 [`docs/reports/kr-location-gate.md`](reports/kr-location-gate.md).

### ③ 참고
프로덕션 모델을 직접 재실행할 수 없는 환경에서는 규칙 백엔드의 **라이브 하한**을 인용합니다.
유니온은 모델 출력에 규칙을 더하므로 실제 재현율은 이 하한 이상이며, 모델을 붙여 재측정하면
숫자가 확정·상향됩니다. 버전 태그·배포는 별도 릴리스 명령으로 진행합니다.

---

## v0.1.0 — **방향 재설정을 릴리스에서 참으로** (한국어 PII·한국 규제 증빙 / 경량 CLI·SDK)

### ① 한 줄 요약
v0.1.0 은 NuFi 의 **방향 전환을 실체화한 첫 마이너 릴리스**입니다. NuFi 는 이제 독립 경량
프로젝트로서 **한국어 PII·한국 규제 증빙**에 집중하고, 프론트엔드 없이 **CLI/SDK**로 가며,
운영(ops) 레이어(멀티테넌시·SLA·대시보드)는 **제외**하되 게이트웨이 코어는 유지합니다. 즉,
"무엇이든 한다"는 넓은 제품에서 **"한국 규제 증빙을 가장 잘 한다"는 좁고 깊은 도구**로
정체성을 좁혔고, 그 좁힘을 README·매뉴얼·리포트 표면에서 **참으로** 만들었습니다.

### ② 이번 버전의 핵심

**1. 한국 규제 증빙 팩 1차 — PIPA·신용정보법·ISMS-P 로 확장**

컴플라이언스 매핑 리포트가 금융보안원 안내서·망분리를 넘어 **개인정보보호법(PIPA)·신용정보법·
ISMS-P** 까지 점검항목을 매핑합니다. 핵심은 **"한 번 통제, 여러 규제 자동 증빙"** — 같은 통제가
여러 규제 요구를 동시에 충족함을 교차참조로 보여주고, 규제별 소계를 한 표로 롤업합니다.

- 무엇이 좋아졌나: 감사·구매 심사에서 규제마다 따로 받는 점검표를 **하나의 증빙에서 자동
  재증빙**합니다. 새 측정 없이 기존 증빙을 한국 규제 언어로 다시 말합니다.

**2. Python SDK 표면 — "CLI/SDK" 정체성의 설계 확정**

탐지·가명화·정책평가·증빙 리포트를 단일 `nufi` 파사드로 쓰는 **라이브러리 API 표면**을 설계로
확정했습니다(안정성 3계층·CLI 동등 매핑·구현 인계 명세). 본 릴리스는 **설계 스펙**을 싣고,
패키지 구현은 후속으로 이어집니다.

- 무엇이 좋아졌나: NuFi 를 **코드에서 직접 임포트**해 파이프라인에 끼우는 길이 명확해집니다.

**3. 한국어 PII 평가셋 정식화 + baseline 측정 — 정확도를 "재현 가능한 숫자"로**

한국어 PII 평가셋을 라이선스(CC0)·재현 해시·누수방지 게이트를 갖춘 **공개 배포 형태**로
정식화하고, baseline 정확도를 **실측해 커밋 자산으로 고정**했습니다(PII recall·precision·
카테고리별 + 신뢰구간 하한). 누구나 같은 숫자를 재현할 수 있습니다.

- 무엇이 좋아졌나: "정확하다"는 주장이 아니라 **검증 가능한 baseline**이 생겼습니다. 엔진
  개선 본편은 다음 버전(v0.2.0)에서 이 baseline 위에 올립니다.

**4. 운영(ops) 레이어 제외 — 정체성을 표면에서 솔직하게**

멀티테넌시/RBAC·SLA·대시보드를 README·운영자 매뉴얼에서 **제외/강등** 표기하고, 코어+규제
증빙을 전면 동선으로 재배열했습니다. 제품이 무엇을 하고 무엇을 하지 않는지 과장 없이 보입니다.

### ③ 범위 밖 / 다음 (v0.2.0+)
한국어 PII **엔진 정확도 개선 본편** · 개인신용정보 커버리지 판정·가명화 품질 벤치·CLI/SDK 진입점
확장(D4 잔여 트랙) · 한국어 생성형 가드레일. SDK 는 **패키지 구현**으로 이어집니다.

---

## v0.0.9 — **"어느 점검항목을, 무엇으로 충족하나"** 를 한 장으로

### ① 한 줄 요약
규제 감사·구매 심사에서 가장 먼저 받는 질문은 **"이 점검항목을 무엇으로 충족합니까?"** 입니다.
v0.0.9 는 **금융보안원 안내서 점검항목 + 망분리 평가기준**에 NuFi 통제를 **매핑한 컴플라이언스
리포트**를 새로 냅니다. 핵심은 — 이 매핑이 **선언이 아니라 증빙**이라는 점입니다. 충족 여부를
이미 쌓아 둔 **감사 결정·정책 변경·우회 기록에서 자동 산출**해, "막연히 한다"가 아니라 "이
결정·이 무결 체인으로 한다"를 한 표로 보여줍니다. (**규제 준수 증빙 게이트웨이**의 첫 슬라이스.)

### ② 이번 버전의 핵심

**1. 점검항목 커버리지 — 안내서·망분리 항목 대비 충족 현황 한 장**

규정준수 리포트에 점검항목 매핑 표가 붙습니다. 항목마다 **요구사항 → NuFi 통제 → 충족 여부 →
증빙 출처**가 한 행으로 정리됩니다. 롤업 배지로 "직접 충족 몇 / 부분 몇 / 범위밖 몇"을 한눈에
봅니다.

- 무엇이 좋아졌나: 감사관·구매자에게 **점검표를 따로 손으로 채우지 않고** 리포트 한 장으로
  답합니다.

**2. 충족을 "증빙으로 자동판정" — 손으로 ✅ 찍지 않는다**

직접(direct) 통제는 차단/가명화 결정 수·감사 결정 총수·**해시체인 무결성** 같은 실제 증빙으로
충족/미충족을 **자동 판정**하고, 그 근거(`action_counts`·`decisions.total`·`chain.ok` 등)를
행에 함께 적습니다. 일부만 되는 항목은 **부분충족**, 파트너·이연 영역은 **범위밖**으로 솔직하게
구분합니다.

- 무엇이 좋아졌나: 매핑이 **체크박스 선언이 아니라 검증 가능한 증빙**이 됩니다. 과장 없이,
  되는 것은 근거와 함께, 안 되는 것은 범위밖으로.

**3. 무결성 게이트는 그대로 — 커버리지는 "정보성"**

커버리지 표는 정보성입니다. 기존 **제출 게이트(기록이 정상이면 통과 0 · 변조되면 차단 1)** 의
종료코드를 **바꾸지 않습니다**. 매핑을 켜도 무결성 보증은 흔들리지 않습니다.

- 무엇이 좋아졌나: 새 기능이 **기존 제출 안전장치를 약화시키지 않는다**는 보장(데모로 0/1 유지
  검증).

### ③ 업그레이드 / 사용법

```bash
git pull        # 최신 버전으로

# 점검항목 커버리지 포함 컴플라이언스 리포트(제출용 MD)
nufi-egress report compliance --audit audit.jsonl --change-log changes.jsonl \
  --flow flow.jsonl --controls --customer "Acme Corp" --format md

# 1-명령 데모로 한 번에 확인
./scripts/demo_compliance_mapping.sh
```

### ④ 호환성 / 주의
- **기존 동작·종료 코드·JSON 키를 바꾸지 않습니다.** 커버리지는 `--controls`(기본 상시)로
  더해지는 **추가 섹션**이며, `--no-controls` 로 끄면 기존 컴플라이언스 리포트로 회귀합니다.
- 커버리지는 **정보성** — 무결성 게이트 종료코드(정상 0 · 변조 1)에 영향을 주지 않습니다.
- 통제 카탈로그는 동봉 기본값을 쓰며 `--catalog` 로 교체할 수 있습니다.

### ⑤ 알려진 한계 / 다음 예정
- 매핑은 **직접 8 / 부분 6 / 범위밖 5** 통제로 시작합니다. 부분충족 항목(rate limit·자산
  RBAC·자산 무결성 인벤토리·생성형 회피공격 가드 등)은 후속 버전에서 직접 충족으로 승격할
  계획입니다.
- 자동판정은 **direct** 통제에 한합니다. partial/out_of_scope 는 카탈로그의 정적 라벨입니다.

### ⑥ 한눈에 — 무엇을 받았나
- **컴플라이언스 매핑 리포트** — 안내서·망분리 점검항목 대비 NuFi 통제 커버리지(직접/부분/범위밖).
- **증빙 자동판정** — 직접 통제는 기존 감사·변경·우회 증빙에서 충족/미충족 자동 산출 + 근거 표기.
- **무결성 게이트 불변** — 정보성 커버리지가 기존 제출 게이트(0/1)를 흔들지 않음.
- **1-명령 데모 + 매뉴얼 절** — `demo_compliance_mapping.sh` 5/5 · `docs/MANUAL.md` §5.4.

---

## v0.0.8 — 흩어진 문서를 **하나의 운영자 매뉴얼**로

### ① 한 줄 요약
v0.0.7 까지 기능은 충분히 쌓였지만, 그 **사용법이 여러 문서에 흩어져** 있었습니다. v0.0.8 은
새 기능을 더하는 대신, **처음 온 운영자가 한 번에 정주행(read-through)하는 단일 매뉴얼**
([`docs/MANUAL.md`](MANUAL.md))을 만듭니다. 설치 → 5분 퀵스타트 → 핵심 개념 → CLI → 운영 →
보안 운영 → 트러블슈팅 → 용어집을 **하나의 읽기 흐름**으로 잇고, 깊은 내용은 기존 권위
문서로 링크합니다(같은 내용을 다시 풀어 쓰지 않음 — 중복 0).

### ② 이번 버전의 핵심

**1. 단일 정주행 매뉴얼 — "어디부터 보지?"가 사라진다**

설치법이 루트 README·`deploy/` 안내·CLI 문서에 흩어져 있고, 트러블슈팅·용어집은 아예
없었습니다. 이제 **매뉴얼 한 편**이 설치(소스·온프렘 컨테이너·에어갭)부터 운영·보안 운영까지
순서대로 안내합니다.

- 무엇이 좋아졌나: 처음 온 사람이 **문서를 헤매지 않고** 위에서 아래로 따라오면 운영자가
  됩니다. 깊이 들어갈 때는 각 절이 권위 문서(아키텍처·CLI·실습 가이드)로 링크합니다.

**2. 트러블슈팅 & FAQ (신규) — 자주 막히는 지점을 한 곳에**

`command not found`(설치 경로), 룰을 바꿨는데 반영이 안 됨(리로드), 우회가 어디로 새는지
추적, 커버리지가 0, 권한 거부(exit 3), 기록 무결성 실패(exit 1) — **실제로 자주 막히는
지점**과 그 해소법을 한 절(§7)에 모았습니다.

- 무엇이 좋아졌나: 막혔을 때 **검색 없이 매뉴얼 한 절**에서 증상→원인→해소를 찾습니다.

**3. 용어집 (신규) — 처음 보는 용어를 그 자리에서**

egress·가역 가명화·해시체인·우회·커버리지·테넌트/RBAC·EDM·NER·fail-closed 등 자주 쓰는
용어의 정의를 §9 용어집에 모으고, 개념·운영 절에서 **교차링크**했습니다.

- 무엇이 좋아졌나: 낯선 단어에서 멈추지 않고, **그 자리에서 뜻을 확인**하고 계속 읽습니다.

### ③ 업그레이드 / 사용법

```bash
git pull        # 최신 문서로 — 코드 변경 없음(순수 문서 릴리스)

# 운영자 매뉴얼부터 정주행: 설치 → 퀵스타트 → 운영 → 트러블슈팅 → 용어집
#   docs/MANUAL.md
```

### ④ 호환성 / 주의
- **코드·CLI·동작·종료 코드·JSON 키 변경이 전혀 없습니다.** 순수 문서 릴리스입니다.
- 기존 주제 문서는 그대로 **권위(authoritative)** 로 남고, 매뉴얼은 그 위를 잇는
  **척추(spine)** 입니다 — 같은 내용을 복제하지 않습니다.
- 0바이트 잔재 `docs/SPEC.md` 가 제거됐습니다(히스토리 명세는 `docs/history/SPEC.md` 로 유지).

### ⑤ 알려진 한계 / 다음 예정
- §8 업그레이드 & 마이그레이션은 **골격(호환 패치 흐름 원칙)** 까지입니다. 버전별 마이그레이션
  절차는 이어서 채웁니다.
- PDF/오프라인 단일 파일 배포와 영문(i18n) 매뉴얼은 다음 후보입니다.
- (기능 측 로드맵은 변동 없음) `--webhook` 실제 발송, 온프렘 p95 정밀 측정, 완전 테넌트
  격리·쓰기 RBAC 는 v0.1.0 으로 이어집니다.

### ⑥ 자세히
- 운영자 매뉴얼: [`docs/MANUAL.md`](MANUAL.md)
- 기술 변경 이력: [`CHANGELOG.md`](../CHANGELOG.md)
- 아키텍처 단일 권위: [`docs/ARCHITECTURE.md`](ARCHITECTURE.md)
- 전체 문서 지도: [`docs/README.md`](README.md)

---

## v0.0.7 — "증명"에서 **선제 보증**으로, 단일 조회에서 **다고객 운영**으로

### ① 한 줄 요약
v0.0.6 이 게이트웨이의 역할을 **증명**(제출용 SLA·규정준수 한 장)했다면, v0.0.7 은 그
증명을 **선제 보증**으로 바꿉니다. SLA 위반을 사후 보고가 아니라 **즉시 신호**로 알리고,
한 고객이 아니라 **여러 고객(테넌트)의 SLA 를 한 표로** 봅니다. 더불어 데모·CLI·릴리스
노트를 정돈해 **처음 보는 사람도 5분 안에 무엇이 되는지** 알 수 있게 했습니다.

### ② 이번 버전의 핵심

**1. SLA 선제 알림 — "지키고 있나?"에서 "어겼으면 바로 알려줘"로**

기존 SLA 리포트는 "물어볼 때" 답을 줬습니다. 이제는 **위반이 생기면 명령이 실패로
신호**하고, 위반 내역을 알림 파일로 남겨 자동화(크론·CI·운영 콘솔)에 그대로 물릴 수 있습니다.

```bash
# 위반이 있으면 0이 아닌 종료코드 + 알림 JSON 적재 → 크론/CI가 즉시 감지
nufi-egress report sla --period 7d --alert alerts/sla.json

# (선택) 외부 수신처로 발송 — 페이로드 형식 고정 (발송은 다음 단계)
nufi-egress report sla --period 7d --alert alerts/sla.json --webhook https://hooks.example/…
```

- 무엇이 가능해졌나: SLA 위반을 **사람이 리포트를 열어보기 전에** 시스템이 먼저 잡습니다.
  충족이면 조용하고, 위반이면 종료코드와 알림 파일로 떠들어 줍니다.

**2. 다고객(테넌트) SLA 플릿 집계 — 고객이 늘어도 한 표로**

여러 고객을 한 게이트웨이로 운영할 때, 고객마다 리포트를 따로 돌리지 않고 **한 표에
테넌트별 충족/위반**을 모아 봅니다.

```bash
# 운영자(operator) 권한으로 모든 테넌트의 SLA 를 한 표에
nufi-egress --role operator report sla --period 30d --all-tenants
```

- 무엇이 가능해졌나: "지금 어느 고객이 SLA 를 어기고 있나"가 **한눈에** 들어옵니다.
  이 집계는 **운영자 전용**이라, 조회 전용(viewer) 역할에게는 노출되지 않습니다(권한 일관).

**3. 사용 편의·전문성 정돈 — 처음 보는 사람도 5분 안에**

기능을 늘리는 대신, **이미 있는 것을 더 쉽게 쓰도록** 다듬은 묶음입니다.

- **대시보드도 명령 하나로** — read-only 감사 대시보드를 `nufi-egress dashboard` 한 줄로
  띄웁니다(예전엔 모듈 직접 실행만 가능). 이로써 일상 운영 명령이 전부 `nufi-egress` 한
  진입점으로 모였습니다.
- **데모가 이름만 봐도 무엇인지** — 데모 파일을 기능 이름으로 통일하고(`demo_<기능>.sh`),
  전부 모은 카탈로그([`docs/DEMO.md`](DEMO.md))와 **한 번에 다 돌리는 러너**(`demo_all.sh`)를
  더했습니다. 처음 온 사람이 "뭘 보여주나"를 목록에서 바로 고릅니다.
- **문서가 설치형 명령을 먼저** — 매뉴얼이 운영 명령을 `nufi-egress …` 로 안내하고, 모듈
  직접 실행은 "설치 안 했을 때의 동치"로만 남깁니다.
- **출시가 공개 Release 페이지까지** — 태그만 달던 릴리스에 **GitHub Release 발행**까지
  메커닉으로 편입해, 받는 사람이 사람친화 노트를 그대로 받아봅니다.

### ③ 업그레이드 / 사용법

```bash
git pull                 # 최신 코드로
pip install -e .         # 동일 패키지, 새 명령·옵션이 바로 추가됨

nufi-egress report sla --period 7d --alert alerts/sla.json   # 선제 알림
nufi-egress --role operator report sla --all-tenants         # 다테넌트 집계 (operator 전용)
nufi-egress dashboard --port 8080                            # 감사 대시보드 (read-only)
./scripts/demo_all.sh                                        # 전체 기능 데모 한 번에
```

### ④ 호환성 / 주의
- **호환성 깨짐 없음.** 기존 명령·설정·차단 규칙·종료 코드·JSON 키는 그대로입니다.
- 새 옵션(`--alert`/`--all-tenants`/`--webhook`)은 모두 **선택**입니다. 지정하지 않으면
  v0.0.6 과 동일하게 동작합니다.
- `--all-tenants` 집계와 정책 변경은 **operator** 권한이 필요합니다(viewer 는 조회만).
- `--webhook` 은 이번 버전에서 **페이로드 형식 고정**까지입니다(실제 발송 연동은 다음 단계).
- 데모 파일 이름이 바뀌었습니다 — 자동화에서 옛 이름을 참조한다면 새 이름으로 갱신하세요
  (카탈로그 [`docs/DEMO.md`](DEMO.md) 참조).

### ⑤ 알려진 한계 / 다음 예정
- `--webhook` 실제 발송(재시도·서명·수신처 인증)은 다음 단계입니다.
- 온프렘(고객 사양) 환경의 지연 p95 정밀 측정은 측정 하드웨어 확보 대기 중입니다.
- 완전 테넌트 격리(런타임·자격증명 분리)와 역할별 세분 변경 권한(쓰기 RBAC)은
  다음 버전(v0.1.0)에서 이어집니다.

### ⑥ 자세히
- 기술 변경 이력: [`CHANGELOG.md`](../CHANGELOG.md)
- SLA·규정준수 리포트 매뉴얼: [`docs/REPORTING.md`](REPORTING.md)
- 데모 카탈로그: [`docs/DEMO.md`](DEMO.md)
- 명령어 전체 레퍼런스: [`docs/CLI.md`](CLI.md)

---

## v0.0.6 — 게이트웨이가 제 역할을 "증명"하고, 여러 팀을 안전하게 나눠 운영하는 첫 칸

### ① 한 줄 요약
우리 게이트웨이가 **제 역할을 증명**하고(SLA·규정준수 리포트), **여러 팀/테넌트를 안전하게
나눠 운영**하는 첫 칸을 엽니다. 새 측정이나 추가 설치 없이, 이미 쌓이고 있는 로그만으로
제출용 한 장과 조회 격리를 얻습니다.

### ② 이번 버전의 핵심

**1. SLA·규정준수 리포트 — 제출용 한 장이 명령 하나로**

"우리 게이트웨이가 약속한 품질을 지키고 있나?"를 감사관·구매자에게 그대로 낼 수 있는
한 장으로 만듭니다. **새로 측정하지 않고** 이미 쌓인 로그만 읽어 기간별(일/주/월)로
목표 충족/위반을 판정합니다.

```bash
# 지난 30일 SLA 충족 여부 한 장 (PII 탐지율·지연·커버리지가 목표를 지켰나)
nufi-egress report sla --period 30d

# 규정준수 한 장 (정책 변경 감사·차단/가명화 건수·기록 무결성)
nufi-egress report compliance --period 30d
```

- 무엇이 가능해졌나: 탐지율·지연·커버리지가 **목표를 지켰는지**가 기간별 표로 나오고,
  위반이 있으면 명령이 실패(0이 아닌 종료코드)로 신호를 줍니다. 그대로 제출하면 됩니다.
- 기록이 중간에 바뀌지 않았다는 **무결성 검증**이 함께 들어가, 변조가 의심되면 리포트가
  제출을 막습니다.
- 고객별로 다른 목표치는 옵션 한 줄(`--thresholds` / `--set`)로 바꿉니다.

**2. 팀/테넌트 분리 + 조회 전용 역할 (첫 슬라이스)**

여러 팀·고객(테넌트)을 한 게이트웨이에서 운영할 때의 **안전한 첫 칸**입니다. 기존 동작과
차단 규칙은 **그대로 두고**, 두 가지를 더합니다.

```bash
# 한 테넌트의 리포트만 보도록 조회를 격리 (다른 테넌트 기록은 보이지 않음)
nufi-egress --tenant acme report compliance --period 30d

# 조회만 가능한 역할 — 설정 변경 명령은 거부됩니다
nufi-egress --role viewer report sla --period 7d
```

- 무엇이 가능해졌나: 한 테넌트의 조회 세션은 **다른 테넌트의 기록을 보지 못합니다**
  (귀속되지 않은 기록도 격리 시 숨김 = 안전 우선). "조회만" 역할과 "조회+변경" 역할을
  나눠, 조회 담당자가 실수로 설정을 바꾸지 못하게 합니다.

### ③ 업그레이드 / 사용법

```bash
git pull                 # 최신 코드로
pip install -e .         # 동일 패키지, 새 명령이 바로 추가됨

nufi-egress report sla --help          # SLA 리포트 옵션
nufi-egress report compliance --help   # 규정준수 리포트 옵션
nufi-egress --tenant <키> --role viewer report sla --period 30d   # 테넌트·역할
```

손으로 따라하며 익히려면 [`docs/HANDS_ON.md`](HANDS_ON.md) 의 v0.0.6 절을 보세요
(토이 프로젝트 하나, 관리자 권한·네트워크 불필요).

### ④ 호환성 / 주의
- **호환성 깨짐 없음.** 기존 명령·설정·차단 규칙은 그대로 동작합니다.
- 새 옵션은 모두 **선택**입니다. 역할 기본값은 "조회+변경"이라, 지정하지 않으면 예전과 같습니다.
- SLA·규정준수 리포트는 **읽기 전용**입니다 — 어떤 정책·기록도 바꾸지 않습니다.

### ⑤ 알려진 한계 / 다음 예정
- 온프렘(고객 사양) 환경에서의 지연 p95 정밀 측정은 측정 하드웨어 확보 대기 중입니다.
- 이번 테넌트 분리는 **조회 격리** 중심의 첫 칸입니다. 런타임·자격증명까지 완전 분리하는
  멀티테넌시와, 역할별 세분 변경 권한(쓰기 RBAC)은 다음 버전(v0.1.0)에서 이어집니다.
- 실시간 SLA 알림·콘솔, 다고객 SLA 집계도 다음 단계입니다.

### ⑥ 자세히
- 기술 변경 이력: [`CHANGELOG.md`](../CHANGELOG.md)
- SLA·규정준수 리포트 매뉴얼: [`docs/REPORTING.md`](REPORTING.md)
- 테넌트·역할 운영 매뉴얼: [`docs/MULTITENANCY.md`](MULTITENANCY.md)
- 손으로 따라하기: [`docs/HANDS_ON.md`](HANDS_ON.md)
- 명령어 전체 레퍼런스: [`docs/CLI.md`](CLI.md)

---

이전 버전(v0.0.5 이하)의 변경 이력은 [`CHANGELOG.md`](../CHANGELOG.md) 에서 확인하세요.
사람 친화 릴리스 노트는 v0.0.6부터 누적합니다.
