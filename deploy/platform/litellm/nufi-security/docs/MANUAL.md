# 📘 NuFi Egress-Audit Gateway — 운영자 매뉴얼 (Operator Manual)

> **이 문서는 처음부터 끝까지 한 번에 정주행(read-through)하는 단일 매뉴얼입니다.**
> 설치 → 5분 퀵스타트 → 핵심 개념 → CLI → 운영 → 보안 운영을 한 흐름으로 안내하고,
> 각 주제의 **상세·권위(authoritative) 문서로 링크**합니다. 같은 내용을 여기서 다시 풀어
> 쓰지 않습니다 — 깊이 들어갈 때는 링크된 심화편을 보세요.
>
> 아키텍처의 단일 권위(single source of truth)는 [`ARCHITECTURE.md`](ARCHITECTURE.md),
> 공개 문서 작성 규칙은 [`DOC_STYLE.md`](DOC_STYLE.md) 입니다.

**NuFi Egress-Audit Gateway** 는 외부 LLM(클라우드 대규모 언어모델, Large Language Model
— Claude·OpenAI 등)을 쓰면서도 한국어 개인정보(Personally Identifiable Information)·기밀이
회사 밖으로 새지 않게 막아 주는 게이트웨이(gateway)입니다. 앱이 외부로 보내는 모든
아웃바운드 요청(outbound request)을 하나의 관문으로 모아, 암호화되어 나가기 직전(TLS 적용 전)에
개인정보·비밀을 **탐지(detection) → 차단(block) / 가명화(pseudonymization)** 하고, 외부로
나간 요청 100% 를 변조 탐지(tamper-evident) 가능한 감사 로그(audit log)로 봉인합니다.

---

## 목차 (Table of Contents)

- [§0 개요 & 독자 — 이 매뉴얼을 누가 어떻게 읽나](#0-개요--독자)
- [§1 설치 & 사전요건 — 온프렘·에어갭·비설치](#1-설치--사전요건)
- [§2 5분 퀵스타트](#2-5분-퀵스타트)
- [§3 핵심 개념 — 무엇이 어떻게 흐르나](#3-핵심-개념)
- [§4 CLI 레퍼런스 — `nufi-egress`](#4-cli-레퍼런스)
- [§5 운영 — 정책·리로드·리포팅·가시성](#5-운영)
- [§6 보안 운영 — 원문 보존·키 회전](#6-보안-운영)
- [§7 트러블슈팅 & FAQ — 자주 막히는 지점](#7-트러블슈팅--faq)
- [§8 업그레이드 & 마이그레이션](#8-업그레이드--마이그레이션)
- [§9 용어집 (Glossary)](#9-용어집)
- [부록 — 전체 문서 지도](#부록--전체-문서-지도)

---

## §0 개요 & 독자

### 누구를 위한 문서인가

이 매뉴얼은 **NuFi 게이트웨이를 직접 띄우고 운영하는 사람**(플랫폼·보안·인프라 담당, 그리고
사내 LLM 서비스를 만드는 개발자)을 독자로 합니다. 아래 순서로 따라오면 한 번에 운영자가
됩니다.

| 당신이 이렇다면 | 어디부터 보나 |
|---|---|
| 우선 깔아서 띄워 보고 싶다 | [§1 설치](#1-설치--사전요건) → [§2 퀵스타트](#2-5분-퀵스타트) |
| 손으로 따라하며 감을 잡고 싶다 | [`HANDS_ON.md`](HANDS_ON.md) (토이 프로젝트 1개, 20~30분, 관리자 권한 불필요) |
| 내 LLM 서비스 앞단에 붙이려 한다 | [§3 핵심 개념](#3-핵심-개념) → [`INTEGRATION_GUIDE.md`](INTEGRATION_GUIDE.md) |
| 이미 돌아가는 걸 운영·튜닝한다 | [§5 운영](#5-운영) · [§6 보안 운영](#6-보안-운영) |
| 명령어 전체를 찾는다 | [§4 CLI 레퍼런스](#4-cli-레퍼런스) → [`CLI.md`](CLI.md) |

### 이 매뉴얼의 약속 — 단일 출처, 중복 없음

같은 내용을 여러 문서에 복사해 두면 한쪽만 고쳐져 어긋납니다. 그래서 NuFi 문서는 **주제마다
권위 문서를 하나만** 둡니다. 이 매뉴얼은 그 권위 문서들을 **하나의 읽기 흐름으로 엮는 척추
(spine)** 이며, 깊은 내용은 직접 옮겨 쓰지 않고 링크합니다.

- 아키텍처(컴포넌트·시퀀스)의 단일 권위 → [`ARCHITECTURE.md`](ARCHITECTURE.md)
- 모든 명령어의 권위 → [`CLI.md`](CLI.md)
- 입문 실습의 권위 → [`HANDS_ON.md`](HANDS_ON.md)
- 운영 주제별 권위 → [§5 운영](#5-운영)의 각 링크

---

## §1 설치 & 사전요건

설치 경로는 세 가지입니다. **(A) 소스 직접 실행**(개발·검증), **(B) 온프렘 컨테이너**(Docker
Compose), **(C) 에어갭(air-gap, 인터넷 단절) 오프라인 번들**. 코어(core)는 외부 네트워크
의존이 0 이라 세 경로 모두 폐쇄망에서 동작합니다.

### 1.1 사전 요건

| 경로 | 필요한 것 |
|---|---|
| A. 소스 실행 | Python 3, `pip` — 코어 의존: PyYAML·fastapi·uvicorn·httpx |
| B. 온프렘 컨테이너 | Docker Engine ≥ 24, Docker Compose v2 |
| C. 에어갭 번들 | (빌드 호스트) Docker · (대상 호스트) Docker, 외부 연결 불필요 |

무거운 NER(Named Entity Recognition, 개체명 인식) 백엔드(transformers/ONNX)는 **선택**입니다.
설치되어 있지 않아도 코어는 사전 기반(gazetteer)으로 외부 호출 0 으로 동작합니다(정확도는
NER 백엔드가 담당 — [§3 핵심 개념](#3-핵심-개념) 참조).

### 1.2 경로 A — 소스 직접 실행 (개발·검증)

가장 빠른 길입니다. 자세한 실행·예제는 루트 [`../README.md`](../README.md) 의 *빠른 시작* 절을
보세요. 요약:

```bash
cd security
python3 -m pip install -r requirements.txt    # 코어 의존: PyYAML·fastapi·uvicorn·httpx

# 게이트웨이 띄우기 (OpenAI 호환 /v1/chat/completions)
PORT=4000 ./scripts/run_gateway.sh
```

`nufi-egress` 통합 CLI 를 설치형으로 쓰려면(권장) 패키지를 설치합니다. **설치하지 않은
환경에서의 동치 실행법**(모듈 폴백)은 [`CLI.md`](CLI.md) 의 *실행 방법* 절에 한 곳으로 정리돼
있습니다.

### 1.3 경로 B — 온프렘 컨테이너 (Docker Compose)

게이트웨이 + 탐지코어 + 감사봇을 **단일 명령**으로 기동합니다. 전체 구성 매핑·헬스체크·무거운
백엔드 오버레이는 [`../deploy/README.md`](../deploy/README.md) 가 권위입니다. 요약:

```bash
docker compose -f deploy/docker-compose.yml up -d --build   # 빌드 + 기동
docker compose -f deploy/docker-compose.yml ps              # 두 서비스 healthy
curl -fsS http://localhost:4000/health                      # {"status":"ok",...}
```

게이트웨이와 감사봇은 **공유 볼륨**으로만 통신하고, 탐지코어는 `internal: true` 네트워크에
격리되어 외부 egress 가 0 입니다(에어갭 우선 설계).

### 1.4 경로 C — 에어갭(오프라인) 번들

레지스트리·PyPI 접근 없이 `docker save`/`load` 기반 단일 tar.gz 번들로 설치합니다. 번들
생성 → 물리 전송 → 로드 → 기동 → 헬스체크의 **단계별 절차**는
[`../deploy/airgap/INSTALL.md`](../deploy/airgap/INSTALL.md) 가 권위입니다. 요약:

```bash
# (연결된 빌드 호스트) 단일 tar.gz 번들 생성
bash deploy/airgap/build-bundle.sh            # 무거운 백엔드 포함은 --heavy

# (에어갭 대상 호스트) 로드 + 무결성 검증 + 단일명령 기동
bash load-bundle.sh
docker compose -f deploy/docker-compose.yml up -d
```

`up` 은 인터넷을 전혀 사용하지 않습니다(이미지 로컬 로드 완료, 의존성 이미지 내장).

---

## §2 5분 퀵스타트

설치를 마쳤다면, 게이트웨이가 실제로 막고 기록하는 것을 직접 확인합니다. 더 깊은 실습
(토이 프로젝트를 SDK 한 줄 전환부터 운영까지)은 [`HANDS_ON.md`](HANDS_ON.md) 가 권위입니다.

```bash
# 1) 평범한 요청 — 사내 LLM 으로 라우팅, 외부로 안 나감
curl -s localhost:4000/v1/chat/completions \
  -d '{"model":"nufi-default","messages":[{"role":"user","content":"안녕"}]}'

# 2) 개인정보가 섞인 요청 + 외부 폴백 → 차단(403)
#    EGRESS_PRIVATE_DOWN=1 은 "사내 LLM 다운 → 외부 폴백" 상황을 강제 재현하는 데모 스위치
EGRESS_PRIVATE_DOWN=1 ./scripts/run_gateway.sh &
curl -s localhost:4000/v1/chat/completions \
  -d '{"model":"nufi-default","messages":[{"role":"user","content":"김민수님 주민번호 900101-1234568"}]}'
# => 403 {"error":{"type":"egress_blocked","entities":["KR_RRN"], ...}}
```

차단된 시도·외부로 나간 요청은 모두 `logs/egress_audit.jsonl` 에 기록됩니다.

배선이 제대로 됐는지 한 번에 보려면 자가진단을, 기능별 1-명령 PASS/FAIL 데모를 돌려 보려면
데모 러너를 씁니다.

```bash
nufi-egress doctor          # 5개 항목 배선 자가진단
./scripts/demo_all.sh       # 전체 기능 데모를 차례로 실행하고 집계 PASS/FAIL — 카탈로그: docs/DEMO.md
```

> 데모 전체 목록(이름·목적·시나리오 수·실행법)은 [`DEMO.md`](DEMO.md) 카탈로그를 보세요.

### 라이브러리로 쓰기 (Python SDK)

게이트웨이 없이, 코드에서 NuFi 엔진을 직접 임포트해 쓸 수 있습니다.

```python
from nufi import detect, Guard, pseudonymize

# 탐지
findings = detect("김민수님 계좌번호 110-123-456789")

# 가명화
token = pseudonymize("KR_PERSON", "김민수")

# 탐지+정책 한 번에
result = Guard().inspect("김민수님 계좌번호 110-123-456789")
```

`import nufi` 는 모델·config 를 로딩하지 않습니다(지연 로딩 — 에어갭 안전). 실행 가능한
완전 예시(12종): [`examples/README.md`](../examples/README.md) · 주요 3종: [`library_detect.py`](../examples/library_detect.py)·[`sdk_file_scan.py`](../examples/sdk_file_scan.py)·[`sdk_compliance_report.py`](../examples/sdk_compliance_report.py). API 전체
목록·안정성 계층은 [`SDK.md`](SDK.md), 실습은 [`HANDS_ON.md`](HANDS_ON.md) §7b 참고.

---

## §3 핵심 개념

내부 구조의 단일 권위는 [`ARCHITECTURE.md`](ARCHITECTURE.md)(컴포넌트/컨테이너 다이어그램 +
시퀀스 4종)입니다. 운영에 필요한 만큼만 여기서 정리합니다.

### 한눈에 — 무엇이 어떻게 흐르나

```
앱 ──> [게이트웨이] ──(라우팅)──> 사내 LLM(private, 온프렘) ──> 외부로 안 나감
                  │
                  └─(사내 LLM 불가 시 폴백, fallback)─> 외부 LLM 직전
                        │
                        ├─ 탐지(detect) → 차단(block) / 가명화(pseudonymize) / 경고(warn)
                        └─ 외부로 나간 요청 100% 감사 로그(변조탐지 해시체인)
```

- **사내 LLM 우선** — 사내(private)에서 처리 가능하면 데이터가 아예 외부로 나가지 않습니다.
- **외부 LLM 은 폴백** — 사내에서 못 할 때만 외부로 나가며, 이때는 **항상** 게이트웨이를
  통과합니다(OpenAI 호환 `/v1/chat/completions` — 기존 코드를 거의 그대로 사용).
- **PII 기반 하이브리드 라우팅** (v0.4.0+) — PII 감지가 기존 감사보다 **앞서** 실행되어,
  PII 포함 요청은 **로컬 모델로 강제 전환**합니다. 클라우드로 나가는 경로 자체가
  사라지므로 "차단"이 아니라 **"유출 경로 원천 제거"**입니다. 설정·데모는
  [`PII_ROUTING.md`](PII_ROUTING.md) 참고.

### 운영자가 알아야 할 다섯 가지

| 개념 | 무엇 | 깊이 보기 |
|---|---|---|
| 탐지 코어 | 한국어 개인정보 정규식(regular expression)+체크섬(checksum), 한국어 인명 NER, 비밀(키 패턴+섀넌 엔트로피, Shannon entropy) | [`ARCHITECTURE.md`](ARCHITECTURE.md) |
| [가역 가명화](#9-용어집) | 개인정보를 결정적 대체값(surrogate)으로 가리고 응답에서 원복(AES-256-GCM Vault) | [`ARCHITECTURE.md`](ARCHITECTURE.md) |
| 100% 감사 + [해시체인](#9-용어집) | 외부 전송 전부 JSONL 기록, 해시체인(hash chain)으로 변조 탐지, fail-closed(기록 실패 시 차단) | [`REPORTING.md`](REPORTING.md) |
| 패킷 레이어 [우회](#9-용어집) 차단 | 게이트웨이를 거치지 않는 직접 트래픽을 패킷 수준에서 잡아 방화벽 허용목록(nftables allowlist)으로 차단 | [`ARCHITECTURE.md`](ARCHITECTURE.md) |
| 정책 프리셋 | 차단/마스킹/가명화/경고 동작을 YAML 로 운영자가 조정 | [`PRESETS.md`](PRESETS.md) |

> 위 용어(egress·가역 가명화·해시체인·우회·[커버리지](#9-용어집)·EDM)의 짧은
> 정의는 [§9 용어집](#9-용어집)에 모아 두었습니다.

### 탐지 대상 PII 클래스 (12종)

| 클래스 | 설명 | 탐지 방식 |
|---|---|---|
| **KR_RRN** | 주민등록번호 | 정규식 + 체크섬 |
| **KR_FOREIGNER_REG** | 외국인등록번호 | 정규식 + 체크섬 |
| **KR_BRN** | 사업자등록번호 | 정규식 + 체크섬 |
| **KR_PASSPORT** | 여권번호 | 정규식 |
| **KR_DRIVER_LICENSE** | 운전면허번호 | 정규식 |
| **KR_ACCOUNT** | 계좌번호 | 정규식 |
| **CREDIT_CARD** | 신용카드번호 | 정규식 + Luhn 체크섬 |
| **KR_PHONE** | 국내 전화번호 | 정규식 |
| **EMAIL** | 이메일 주소 | 정규식 |
| **KR_PERSON** | 한국어 인명 | NER (onnx-int8 / gazetteer) |
| **KR_LOCATION** | 한국어 지명 | NER (onnx-int8 / gazetteer) |
| **SECRET** | API 키·토큰·비밀 | 패턴 + 섀넌 엔트로피(Shannon entropy) |

> "강한 PII" = KR_RRN·KR_FOREIGNER_REG·KR_PASSPORT·KR_DRIVER_LICENSE·KR_ACCOUNT·CREDIT_CARD (어떤 프리셋에서도 외부 전송 차단).
> "약한 PII" = KR_PHONE·EMAIL·KR_PERSON·KR_LOCATION·KR_BRN (프리셋에 따라 가명화·경고·차단).

탐지 정확도(한국어 개인정보 재현율 0.9908, KR_PERSON 0.9799 등) 실측값과 한계는 루트
[`../README.md`](../README.md) 의 *성능·정확도* 절을 보세요.

### 감사 로그 레코드 스키마 (`logs/egress_audit.jsonl`)

외부 전송 100%가 적재되는 감사 로그의 JSONL 레코드 구조입니다.

| 필드 | 타입 | 설명 |
|---|---|---|
| `id` | `str` | UUID — 레코드 고유 식별자 |
| `ts` | `str` | ISO 8601 타임스탬프 (`2026-07-04T12:34:56+0900`) |
| `epoch_ms` | `int` | 유닉스 에포크 밀리초 — 정렬·범위 조회용 |
| `model` | `str` | 요청 모델 명 (예: `claude-3-5-sonnet-20241022`) |
| `provider` | `str` | egress 프로바이더 (예: `anthropic`, `openai`) |
| `is_public` | `bool` | 외부(public) 경로 전송 여부 |
| `outcome` | `str` | `forwarded` / `blocked` / `transformed` |
| `decision` | `dict` | 정책 결정 요약 — `{blocked, action_counts, finding_count}` |
| `findings` | `list` | Finding 목록 (원문 PII 는 `len=...:sha256=...` 단축해시로 마스킹) |
| `request_body` | `dict` | 요청 본문 (마스킹/가명화 처리본) |
| `chain` | `dict` | 해시체인 정보 — `{seq, prev_hash, hash}` (hash_chain=True 시) |
| `extra` | `dict?` | 추가 메타데이터 (게이트웨이 경로별 선택적) |

```json
{
  "id": "a1b2c3d4-...",
  "ts": "2026-07-04T12:34:56+0900",
  "epoch_ms": 1751598896000,
  "model": "claude-3-5-sonnet-20241022",
  "provider": "anthropic",
  "is_public": true,
  "outcome": "blocked",
  "decision": {
    "blocked": true,
    "action_counts": {"block": 1, "pseudonymize": 1},
    "finding_count": 2
  },
  "findings": [
    {"entity_type": "KR_RRN", "text": "len=14:sha256=a3f2..."},
    {"entity_type": "KR_PERSON", "text": "len=3:sha256=b7c1..."}
  ],
  "chain": {"seq": 42, "prev_hash": "3a9f...", "hash": "8d2c..."}
}
```

> 원문 PII 평문은 `findings[].text` 에 넣지 않습니다. `len=<길이>:sha256=<해시>` 단축해시만 보관합니다(`_mask_finding()`). 해시체인 무결성 검증은 `nufi-egress audit query --verify-chain` 으로 수행합니다.

---

## §4 CLI 레퍼런스

운영의 단일 진입점(entry point)은 통합 CLI **`nufi-egress <서브커맨드>`** 입니다. 전체
서브커맨드·옵션·예시·**설치하지 않은 환경에서의 실행법**은 [`CLI.md`](CLI.md) 가 권위입니다.
자주 쓰는 것만 추립니다.

| 서브커맨드 | 무엇을 하나 |
|---|---|
| `doctor` | 배선 5개 항목 자가진단 |
| `init` | 프리셋에서 운영 config 구체화 |
| `render` / `apply` / `disable` / `status` | 정책 미리보기·적용·해제·현황 |
| `coverage` | "내 트래픽 중 몇 %가 게이트웨이를 통과했나" |
| `monitor` | 우회를 실시간 알림으로 |
| `audit` | 감사 로그 집계·조회 |
| `targets` / `flow-tap` | 캡처 대상 생성·우회 탐지 |
| `policy` | 다중 프로파일·묶기·무재기동 되돌리기·변경 감사 |
| `report compliance` | 규정준수·컴플라이언스 매핑 리포트(증빙, 제출용) |
| `benchmark` | 정확도+가명화 벤치마크 재현(커밋 증거 대조 + 라이브 하니스) |

```bash
nufi-egress --help              # 전체 서브커맨드
nufi --help                     # nufi-egress 와 동일(별칭)
nufi-egress coverage --simulate samples/flow_replay.jsonl
```

> 각 서브커맨드의 인자·종료코드·출력 예시는 [`CLI.md`](CLI.md) 에서 해당 절을 보세요.

### v0.4.18 신규 CLI 커맨드 빠른 참조

v0.4.18 에서 추가·확장된 CLI 커맨드를 아래 표로 정리합니다. 각 커맨드의 전체 옵션·예시는
[`CLI.md`](CLI.md) 가 권위입니다.

| 커맨드 | 설명 | 카테고리 |
|---|---|---|
| `scan <target>` | 파일/디렉터리 PII + 인젝션 스캔 (CI/pre-commit) | 탐지 |
| `scan --baseline <file>` | 베이스라인 대비 신규 탐지만 보고 | 탐지 |
| `scan --count-only` | 탐지 건수만 출력 (CI gate용) | 탐지 |
| `scan --min-score <n>` | 최소 점수 이상 항목만 필터링 | 탐지 |
| `scan --only-types <t,...>` | 특정 PII 유형만 스캔 | 탐지 |
| `scan --format csv` | CSV 형식 출력 | 탐지 |
| `route --text <text>` | PII 라우팅 결정 테스트 (로컬/클라우드 판정) | 탐지 |
| `inspect --text <text>` | 통합 보안 분석 (PII + 인젝션 + 라우팅 + 위험도) | 탐지 |
| `diff [--base REF]` | git 변경 파일만 PII/인젝션 스캔 | 탐지 |
| `lint --fix-report` | 린트 결과를 수정 리포트로 출력 | 탐지 |
| `watch <directory>` | 디렉터리 PII 실시간 감시 (폴링) | 운영 |
| `init [preset]` | 프로젝트 초기화 또는 프리셋 구체화 | 운영 |
| `config validate` | 설정 파일 유효성 검증 (syntax/필수필드/regex) | 운영 |
| `config show` | 현재 활성 설정 출력 | 운영 |
| `version` | 버전 및 백엔드 정보 출력 | 운영 |
| `completions {bash\|zsh}` | 셸 자동완성 스크립트 출력 | 운영 |
| `stats` | NuFi 설정·탐지 역량 요약 통계 | 운영 |

---

## §5 운영

돌아가는 게이트웨이를 **운영·튜닝**하는 작업입니다. 주제마다 권위 문서가 따로 있습니다.


### 5.1 여러 정책을 한 게이트웨이에서 (정책 at scale)

다중 정책 프로파일(profile)·경로별 묶기(binding)·버전/무재기동 되돌리기(rollback)·변경
감사를 운영합니다. 권위: [`OPS_POLICY_AT_SCALE.md`](OPS_POLICY_AT_SCALE.md). 1-명령 데모:
[`../scripts/demo_policy_ops.sh`](../scripts/demo_policy_ops.sh).

### 5.2 룰 무재기동 핫리로드 / 드라이런

게이트웨이를 재기동하지 않고 룰셋을 검증(validate) → 드라이런(dry-run) → 적용(reload)
합니다. fail-closed 안전 불변식을 보장합니다. 권위: [`OPS_RULE_RELOAD.md`](OPS_RULE_RELOAD.md).

### 5.3 규정준수·컴플라이언스 매핑 리포팅 (증빙)

감사관·구매자 제출용 **규정준수 리포트**(정책 변경 감사 + 차단/가명화 + 우회 증빙)를 냅니다.
이것이 NuFi 의 **한국 규제 증빙** 축입니다(코어 유지 대상).

**컴플라이언스 매핑 — 점검항목 커버리지(control coverage).** 규정준수 리포트에
`--controls` 를 더하면, **금융분야 AI 보안 안내서·망분리 평가기준 + 개인정보보호법·
신용정보법·ISMS-P** 대비 NuFi 통제의 충족 상태를 위 리포트의 **기존 증빙에서 자동
산출**한 매핑 표가 규제별로 붙습니다. 감사관·구매자가 "어느 점검항목을 무엇으로
충족하나"를 한 장으로 보는 **규제 준수 증빙 게이트웨이**입니다. 동일 NuFi 증빙이 여러
규제를 동시에 충족(`maps_to` 교차참조)함을 규제별 행으로 투명하게 보입니다.

```bash
# 점검항목 커버리지 포함 컴플라이언스 리포트(제출용 MD)
nufi-egress report compliance --audit audit.jsonl --change-log changes.jsonl \
  --flow flow.jsonl --controls --customer "Acme Corp" --format md
```

- **출력 해석** — 롤업 배지(직접 N(충족/미충족) · 부분 N · 범위밖 N) 아래에 항목별 행이
  옵니다. 충족 구분은 세 가지입니다:
  - **직접(direct)** — 차단/가명화 결정·무결 체인 같은 **리포트 증빙으로 충족/미충족을
    자동판정**(✅/❌). 증빙 출처(`action_counts`·`decisions.total`·`chain.ok` 등)가 행에 표기됩니다.
  - **부분(partial)** — 일부만 충족하는 통제. 정적 라벨 + 보강 로드맵(🟡)을 보여줍니다.
  - **범위밖(out_of_scope)** — 파트너·이연 영역(⛔). 솔직하게 범위 밖으로 표기합니다.
- **규제별 소계·필터** — 출력은 규제(프레임워크)별 소계와 매핑 표로 묶입니다. `--framework ID`
  (반복 허용; `pipa`/`cia`/`isms-p`/`fsec-ai`/`net-sep`)로 특정 규제 행만 추려 제출할 수 있고,
  롤업도 필터 기준으로 산출됩니다(정보성 — 종료코드 불변).
- **증거 출처** — 별도 입력이 아니라 **같은 리포트의 감사 결정·정책 변경·우회 증빙**에서
  결정론적으로 평가합니다(새 측정 없음). 통제 카탈로그는 동봉 기본값을 쓰며 `--catalog` 로
  교체할 수 있고, `--no-controls` 로 섹션을 끌 수 있습니다.
- **종료코드** — 커버리지는 **정보성**입니다. 기존 무결성 게이트의 종료코드(정상 0 ·
  변조 1)를 **바꾸지 않습니다**.

권위: [`REPORTING.md`](REPORTING.md) §2. 1-명령 데모:
[`../scripts/demo_compliance_mapping.sh`](../scripts/demo_compliance_mapping.sh).

### 5.4 감사 가시성 — 커버리지

- **커버리지 점검** — "내 트래픽 중 몇 %가 게이트웨이를 통과했나" + 우회 알림. 권위:
  [`CLI.md#coverage`](CLI.md#coverage). 1-명령 데모:
  [`../scripts/demo_coverage.sh`](../scripts/demo_coverage.sh).

### 5.5 정책 프리셋 고르기

도입 단계·위험 수준에 맞춰 `strict-kr-pii`·`audit-only`·`pseudonymize-roundtrip` 중 하나를
고릅니다. 동일 입력에 대한 프리셋별 결정 diff 와 fail-closed 보증은
[`PRESETS.md`](PRESETS.md) 가 권위입니다.

### 5.6 게이트웨이 강건성 설정 (v0.4.2+)

프로덕션 환경에서 게이트웨이를 안전하게 운영하기 위한 세 가지 환경변수입니다.

| 환경변수 | 무엇 | 기본값 |
|---|---|---|
| `NUFI_DETECT_TIMEOUT_MS` | NER 탐지 타임아웃 (밀리초). 초과 시 fail-closed 차단 | `5000` (5초) |
| `NUFI_MAX_PROMPT_BYTES` | 탐지 대상 프롬프트 최대 크기 (바이트). 초과 시 잘라서 탐지 | `524288` (512KB) |
| `X-NuFi-Latency-Ms` | 응답 헤더로 반환되는 처리 지연 (밀리초). 감사 로그에도 기록 | (자동) |

```bash
# 예: 타임아웃을 3초로 줄이고 프롬프트 크기를 256KB로 제한
export NUFI_DETECT_TIMEOUT_MS=3000
export NUFI_MAX_PROMPT_BYTES=262144
```

- **fail-closed**: 탐지 타임아웃 시 요청을 **차단**(통과 아님)합니다. 안전쪽 실패.
- **방어 파싱**: `content=None`, 비-dict 메시지 등 비정상 입력을 안전하게 건너뜁니다.

1-명령 데모: [`../scripts/demo_resilience.sh`](../scripts/demo_resilience.sh) (5/5 PASS).

### 5.7 환경변수 레퍼런스

게이트웨이·탐지·감사·집행에 쓰이는 **전체 환경변수** 통합 테이블입니다.

#### 게이트웨이 / 탐지

| 변수명 | 기본값 | 소스 모듈 | 설명 | 보안 영향 |
|---|---|---|---|---|
| `EGRESS_PRIVATE_DOWN` | `0` | `gateway/core.py` | 사내 LLM 불가 시뮬레이션. `1`=외부 폴백 강제 (데모용) | 프로덕션에서 `1` 사용 금지 — 전체 트래픽이 외부로 나감 |
| `EGRESS_NER_BACKEND` | `auto` | `gateway/core.py` | NER 백엔드 선택: `gazetteer`(사전 기반)·`transformers`(모델)·`auto` | `gazetteer`는 에어갭 안전, `auto`는 모델 다운로드 시도 가능 |
| `NUFI_DETECT_TIMEOUT_MS` | `5000` | `gateway/core.py` | NER 탐지 타임아웃 (밀리초). 초과 시 fail-closed 차단 | 짧으면 안전(차단) 쪽, 길면 지연 증가 |
| `NUFI_MAX_PROMPT_BYTES` | `524288` | `gateway/core.py` | 탐지 대상 프롬프트 최대 크기 (바이트). 초과분은 잘라서 탐지 | 너무 크면 탐지 지연 증가 |
| `NUFI_LOCAL_MODEL` | `nufi-local` | `gateway/litellm_hook.py` | PII 라우팅 시 PII 포함 요청을 보낼 로컬 모델명 | — |
| `NUFI_CLOUD_MODEL` | `nufi-cloud` | `gateway/litellm_hook.py` | PII 없는 클린 요청을 보낼 클라우드 모델명 | — |
| `NUFI_FAIL_CLOSED` | `1` | `gateway/litellm_hook.py` | PII 감지 오류 시 로컬 폴백. `0`=비활성(클라우드 허용) | `0`으로 끄면 감지 실패 시 PII가 외부로 유출될 수 있음 |

#### 감사 / 로깅

| 변수명 | 기본값 | 소스 모듈 | 설명 | 보안 영향 |
|---|---|---|---|---|
| `EGRESS_AUDIT_LOG` | `logs/egress_audit.jsonl` | `egress_audit/audit.py` | 감사 로그 파일 경로 | 접근 제어 필수 — 외부 전송 전문 포함 가능 |
| `EGRESS_AUDIT_HASH_CHAIN` | `0` | `egress_audit/audit.py` | 해시체인 활성화. `1`=변조탐지 해시체인 기록 | 프로덕션에서 `1` 권장 — 변조 탐지 기반 |
| `EGRESS_AUDIT_PROFILES` | `config/audit_profiles.yaml` | `egress_audit/audit_bot.py` | 감사 프로파일 YAML 경로 (봇·메시지 스토어 공용) | — |
| `EGRESS_MESSAGE_STORE_DIR` | `logs/messages` | `egress_audit/message_store.py` | 메시지 스토어 디렉터리 (private/public 분리 저장) | 원문 보존 시 접근 제어·디스크 암호화 필수 |
| `EGRESS_ENFORCEMENT_LOG` | `logs/enforcement.jsonl` | `egress_audit/enforcement.py` | 집행(차단/허용) 로그 경로 | — |
| `EGRESS_FLOW_DIR` | `logs/flows` | `enforcement/report.py` | 플로우 로그 디렉터리 (`coverage`/`report` 입력) | — |
| `EGRESS_PACKET_DIR` | `logs/packets` | `capture/flow_tap.py`, `capture/content_dump.py` | 패킷 캡처·콘텐츠 덤프 저장 디렉터리 | 원문 패킷 포함 — 접근 제어 필수 |

#### 암호화 / 키

| 변수명 | 기본값 | 소스 모듈 | 설명 | 보안 영향 |
|---|---|---|---|---|
| `EGRESS_VAULT_KEK` | *(없음, 필수)* | `egress_audit/vault.py` | Vault AES-256-GCM KEK (32바이트, hex64 또는 base64) | 🔴 **필수** — 미설정 시 가명화 원복 불가. 디스크 미저장, keyring/비밀관리자 주입 |
| `EGRESS_PSEUDO_KEY` | `nufi-egress-poc-key` | `egress_audit/pseudonymize.py` | 가명화 결정적 대체값 생성 키 | 🔴 **프로덕션에서 반드시 변경** — 기본값은 PoC용 |
| `EGRESS_EDM_SALT` | `nufi-edm-poc-salt` | `egress_audit/edm.py` | EDM 해시 salt | 🔴 **프로덕션에서 반드시 변경** — 기본값은 PoC용 |

#### 집행 / 운영

| 변수명 | 기본값 | 소스 모듈 | 설명 | 보안 영향 |
|---|---|---|---|---|
| `NUFI_EGRESS_PRIVILEGED` | *(없음)* | `enforcement/applier.py` | nftables 권한 모드. `1`=활성 | `1` 시 nftables 규칙 직접 적용 — root 권한 필요 |
| `NUFI_ACTOR` | *(현재 사용자)* | `enforcement/cli.py` | 정책 변경 주체 이름 (감사 로그에 기록) | — |
| `NUFI_NER_PROC_START` | `spawn` | `egress_audit/detectors/_proc_pool.py` | NER 프로세스 풀 시작 방식 (`spawn`/`forkserver`) | `fork`는 GIL 이슈 — `spawn` 또는 `forkserver` 권장 |
| `NUFI_NER_INFER_WORKERS` | `cores // K` | `egress_audit/detectors/_infer_pool.py` | NER 동시 추론 허용 수 W | — |
| `NUFI_NER_INTRA_OP_THREADS` | `1` | `egress_audit/detectors/_infer_pool.py` | NER 세션당 intra-op 스레드 캡 K | — |

#### 배포

| 변수명 | 기본값 | 소스 모듈 | 설명 | 보안 영향 |
|---|---|---|---|---|
| `NUFI_TAG` | `0.0.2-dev` | `deploy/docker-compose.yml` | Docker 이미지 태그 | — |

---

## §6 보안 운영

게이트웨이를 안전하게 **운영**하는 보안 절차입니다.

### 6.1 외부 원문 보존(retain_raw) 정책

본문 보존 기본값은 **사내(private) = 원문 보존**, **외부(public) = 가명화된 통과본만 보존**
입니다. 외부 경로를 원문 보존으로 켜면 회사 밖으로 나간 요청 원문(개인정보 포함 가능)이
디스크에 남습니다. 켤 경우 접근 제어(권한 0700·디스크 암호화), 보존기간(TTL, 권고 ≤ 30일)·
파기 절차를 반드시 정의하세요. 보안 불변식·검증 절차는
[`SECURITY_RETAIN_RAW_KEYROTATION.md`](SECURITY_RETAIN_RAW_KEYROTATION.md) 가 권위입니다.

### 6.2 Vault AES-256-GCM 키 회전

가명화 매핑 저장소(Vault)의 키 암호화 키(KEK, Key Encryption Key) 주입(필수)과 회전(rotation)
절차입니다. KEK 는 keyring/비밀관리자에 보관하고 주입하며, 오설정 방지 검증을 거칩니다.
권위: [`SECURITY_RETAIN_RAW_KEYROTATION.md`](SECURITY_RETAIN_RAW_KEYROTATION.md) §2.

> ⚠️ 보안 하드닝(hardening) 점검은 12/12 통과(기록 실패 시 차단·감사 해시체인·원문 미저장
> 등) 상태입니다 — 실측 근거는 루트 [`../README.md`](../README.md) *성능·정확도* 절 참조.

---

## §7 트러블슈팅 & FAQ

첫 운영자가 자주 막히는 지점을 **증상 → 원인 → 해결** 순으로 모았습니다. 각 항목은 위의
권위 문서로 연결됩니다 — 같은 내용을 여기서 다시 풀어 쓰지 않습니다.

### 7.1 `nufi-egress: command not found` — 설치가 안 됐다

콘솔 스크립트(console script)가 설치되지 않은 상태입니다. 패키지를 설치하면 됩니다.

```bash
pip install -e .            # security/ 에서
nufi-egress doctor          # 배선 5개 항목 자가진단으로 확인
```

설치하지 않고 쓰는 환경(에어갭 등)에서의 **동치 실행법**(모듈 폴백)은 [`CLI.md`](CLI.md) 의
*실행 방법* 절에 한 곳으로 정리돼 있습니다.

### 7.2 룰을 바꿨는데 반영이 안 된다 — 리로드

룰 핫리로드는 게이트웨이를 **재기동하지 않고** 원자 스왑(atomic swap)으로 적용합니다. 룰이
유효하지 않으면 **이전 룰셋이 그대로 유지**되고 적용이 거부됩니다 — 롤백된 것이 아니라
**적용 자체가 거부**된 것입니다. 리로드 출력의 `action` 값으로 구분하세요.

- `action=reload` — 새 룰셋 적용됨.
- `action=reload-reject` — 새 룰셋이 검증에 실패해 **거부**(이전 룰셋 유지). 룰 파일의
  문법·필드를 고치고 다시 시도하세요.

검증→드라이런→적용 절차와 fail-closed 안전 불변식은 [`OPS_RULE_RELOAD.md`](OPS_RULE_RELOAD.md)
가 권위입니다.

### 7.3 우회(bypass)가 잡히는데 어디로 새는지 모르겠다

`coverage`/`report` 출력의 `bypass` 가 0 보다 크면, 게이트웨이를 거치지 않고 나간 송신이
있다는 뜻입니다. 5-튜플(출발/목적 IP·포트·프로토콜) 표본으로 어디서 새는지 좁힙니다.

```bash
nufi-egress coverage --simulate samples/flow_replay.jsonl   # bypass 건수 + bypass_samples
nufi-egress monitor                                         # 우회를 실시간 알림으로
```

`via_gateway`/`bypass` 분류는 flow-tap 이 적재합니다. 패킷 레이어에서 우회 자체를 원천 차단
하려면 nftables 허용목록(§3 *패킷 레이어 우회 차단*)을 적용하세요. 권위:
[`CLI.md#coverage`](CLI.md#coverage).

### 7.4 커버리지가 0이거나 비어 있다

`coverage` 입력이 비었거나 디렉터리 글롭(glob)이 어긋난 경우입니다.

- 단일 파일 모드 — `--simulate <파일>` 경로가 맞는지, 그 파일에 flow 레코드가 있는지 확인.
- 디렉터리 모드 — `flow-*.jsonl` 패턴에 맞는 파일명인지 확인(예: `flow-2026-06-28.jsonl`).
  패턴과 다른 이름은 **조용히 건너뜁니다**.

### 7.5 해시체인 무결성 실패 — 종료코드 1

`report` 가 감사 로그의 해시체인에서 변조·유실을 탐지하면 `integrity_ok=false` 와 함께
"❌ 무결성 위반(변조 의심)" 및 끊긴 지점(`broken_seq`)을 출력하고 **종료코드 1**로 끝납니다.
감사 로그가 손실 없이 보관되는지, 권한·보존 절차가 지켜지는지 확인하세요. 무결성 모델과
원문 보존·키 회전 보안 절차는 [`SECURITY_RETAIN_RAW_KEYROTATION.md`](SECURITY_RETAIN_RAW_KEYROTATION.md)
가 권위입니다.

> 종료코드 요약: **0** 정상 · **1** 무결성/리포트 게이트 실패.
> 각 서브커맨드의 종료코드 표는 [`CLI.md`](CLI.md) 가 권위입니다.

---

## §8 업그레이드 & 마이그레이션

이 절은 NuFi 게이트웨이의 **버전 업그레이드 절차**, **config 키 변경 이력**, **에어갭 번들
재생성**, **v0.3.x → v0.4.x 마이그레이션** 을 안내합니다.

### 8.1 업그레이드 원칙

- **무엇이 바뀌었나** — 버전별 변경 이력은 [`../CHANGELOG.md`](../CHANGELOG.md), 사람 친화
  릴리스 노트는 [`RELEASE_NOTES.md`](RELEASE_NOTES.md) 가 권위입니다. 업그레이드 전 해당
  버전 절을 먼저 읽으세요.
- **무중단 룰 변경** — 정책·룰 변경은 재기동 없이 핫리로드로 적용됩니다([§7.2](#7-트러블슈팅--faq)).
- **롤백** — 정책 수준 되돌리기는 [`OPS_POLICY_AT_SCALE.md`](OPS_POLICY_AT_SCALE.md) 의
  버전/무재기동 되돌리기를 사용합니다.

### 8.2 Config 키 변경 이력

아래 표는 버전별로 추가·변경·제거된 설정 키를 정리합니다. 업그레이드 시 기존 config 파일이
새 키를 포함하는지 확인하세요.

| 버전 | 파일 | 키 | 변경 | 설명 |
|---|---|---|---|---|
| v0.4.0 | `config/routing.yaml` | `pii_routing` (섹션) | **신규** | PII 감지 시 로컬 모델 강제 라우팅. `enabled`, `local_backend`, `entity_types` 하위 키 |
| v0.4.0 | `config/routing.yaml` | `pii_routing.enabled` | **신규** | PII 라우팅 활성화 (`true`/`false`, 기본 `true`) |
| v0.4.0 | `config/routing.yaml` | `pii_routing.local_backend` | **신규** | PII 포함 요청을 보낼 로컬 백엔드 이름 (기본 `private-llm`) |
| v0.4.0 | `config/routing.yaml` | `pii_routing.entity_types` | **신규** | 라우팅 대상 엔티티 타입 리스트 (빈 리스트 = 모든 PII) |
| v0.4.0 | `config/routing.yaml` | `policy_profiles` | **신규** | 다중 정책 프로파일 정의 |
| v0.4.0 | `config/routing.yaml` | `policy_default_profile` | **신규** | 묶이지 않은 경로의 기본 프로파일 |
| v0.4.0 | `config/routing.yaml` | `policy_bindings` | **신규** | 경로→프로파일 선언적 묶기 |
| v0.4.2 | 환경변수 | `NUFI_DETECT_TIMEOUT_MS` | **신규** | 탐지 타임아웃 밀리초 (기본 5000, 초과 시 fail-closed 차단) |
| v0.4.2 | 환경변수 | `NUFI_MAX_PROMPT_BYTES` | **신규** | 프롬프트 최대 크기 바이트 (기본 524288) |
| v0.4.10 | CLI | `--tenant`, `--role`, `--all-tenants` | **제거** | RBAC/멀티테넌시 제거에 따라 삭제 |
| v0.4.10 | CLI | `report sla` | **제거** | SLA 리포팅 서브커맨드 삭제 |

> 기존 config 파일에 없는 신규 키는 **기본값으로 동작**합니다. 명시적으로 설정하지 않아도
> 게이트웨이는 정상 기동됩니다.

### 8.3 인플레이스 게이트웨이 업그레이드 절차

소스 직접 실행(경로 A)·컨테이너(경로 B) 환경에서의 인플레이스(in-place) 업그레이드 절차입니다.

#### 경로 A — 소스 직접 실행

```bash
# 1. 현재 버전 확인
cat VERSION

# 2. 소스 갱신
git pull origin main          # 또는 릴리스 태그 checkout

# 3. 의존성 갱신
pip install -r requirements.txt

# 4. 배선 자가진단
nufi-egress doctor

# 5. 정책 핫리로드 (재기동 불필요)
nufi-egress policy apply      # 변경된 정책이 있을 경우
```

> 게이트웨이 프로세스 재기동이 필요한 경우(코어 코드 변경 시)는 `systemctl restart nufi-gateway`
> 또는 프로세스를 다시 시작합니다. **정책·룰 변경만** 이면 핫리로드로 충분합니다.

#### 경로 B — Docker Compose

```bash
# 1. 이미지 재빌드 + 롤링 재기동
docker compose -f deploy/docker-compose.yml up -d --build

# 2. 헬스체크
curl -fsS http://localhost:4000/health

# 3. 배선 확인
docker compose -f deploy/docker-compose.yml exec gateway nufi-egress doctor
```

### 8.4 에어갭 번들 재생성 안내

폐쇄망(에어갭) 환경은 **새 번들을 생성 → 물리 전송 → 로드**하는 흐름으로 업그레이드합니다.
전체 절차의 권위는 [`../deploy/airgap/INSTALL.md`](../deploy/airgap/INSTALL.md) 입니다.

```bash
# (연결된 빌드 호스트) — 새 버전의 번들 재생성
git pull origin main                         # 새 버전 소스 확보
bash deploy/airgap/build-bundle.sh           # 경량 번들
bash deploy/airgap/build-bundle.sh --heavy   # 무거운 NER 백엔드 포함 시

# 산출물: dist/nufi-egress-audit-<tag>[-heavy]-airgap.tar.gz
# USB/단방향 전송으로 에어갭 호스트에 전달

# (에어갭 호스트) — 기존 컨테이너 정지 + 새 번들 로드 + 기동
docker compose -f deploy/docker-compose.yml down
tar -xzf nufi-egress-audit-<new-tag>-airgap.tar.gz -C nufi
cd nufi && bash load-bundle.sh               # docker load + sha256 무결성 검증
docker compose -f deploy/docker-compose.yml up -d
curl -fsS http://localhost:4000/health       # 헬스체크
```

> `load-bundle.sh` 는 `MANIFEST.txt` 의 sha256 해시를 대조해 전송 중 변조를 검출합니다.
> 검증 실패 시 스크립트가 중단되며 번들 재전송이 필요합니다.

### 8.5 v0.3.x → v0.4.x 마이그레이션 노트

v0.4.0 은 **두 가지 주요 변경**을 도입합니다: PII 기반 하이브리드 라우팅 추가와 운영 레이어
(RBAC/멀티테넌시·SLA 리포팅) 제거.

#### 추가된 것 — PII 라우팅

`config/routing.yaml` 에 `pii_routing` 섹션이 추가됩니다. 기본값(`enabled: true`)으로 PII 가
포함된 요청은 자동으로 로컬 모델로 전환됩니다. 기존 동작(egress 감사만)을 유지하려면:

```yaml
# config/routing.yaml 에 추가
pii_routing:
  enabled: false
```

#### 제거된 것 — RBAC/멀티테넌시 + SLA 리포팅

v0.3.x 에서 사용하던 아래 기능이 **완전히 제거**되었습니다:

| 제거 항목 | 영향 | 대응 |
|---|---|---|
| `--tenant` / `--role` / `--all-tenants` CLI 플래그 | CLI 호출에서 해당 플래그 사용 시 에러 | 스크립트·자동화에서 해당 플래그 제거 |
| `report sla` 서브커맨드 | SLA 리포트 생성 불가 | 외부 모니터링 도구로 대체하거나 제거 |
| `enforcement/access.py` (접근 제어 모듈) | 테넌트별 접근 분리 없음 | 단일 테넌트 운영 (네트워크/인프라 수준 분리 권장) |
| `docs/MULTITENANCY.md` | 문서 삭제 | 해당 없음 |
| 종료코드 3 (AccessDenied) | 더 이상 발생하지 않음 | 종료코드 3 을 처리하던 스크립트에서 분기 제거 |

#### 마이그레이션 체크리스트

```text
□ config/routing.yaml 에 pii_routing 섹션 존재 확인 (없으면 기본값 적용됨)
□ 자동화 스크립트에서 --tenant / --role / --all-tenants 플래그 제거
□ report sla 호출부 제거 또는 대체
□ 종료코드 3 분기 제거
□ nufi-egress doctor 로 배선 확인
□ (에어갭) 새 번들 생성 + 전송 + 로드
```

> 코어 기능(PII 탐지·가명화·감사 로그·정책 집행·컴플라이언스 매핑)은 **변경 없이 호환**됩니다.
> config 파일 형식(`version: 1`)도 유지됩니다.

---

## §9 용어집

이 매뉴얼에서 자주 나오는 용어의 짧은 정의입니다. 깊은 내용은 각 권위 문서를 보세요.

| 용어 | 뜻 |
|---|---|
| **egress(송신)** | 워크로드가 조직 경계 밖으로 내보내는 트래픽. NuFi 가 탐지·가명화·집행하는 대상 경로. |
| **가역 가명화(reversible pseudonymization)** | 원문 개인정보를 결정적 대체값(surrogate)으로 가리되 키(Vault, AES-256-GCM)로 원복 가능. 응답 원복·감사·EDM 목적. |
| **해시체인(hash chain)** | 감사 레코드를 직전 레코드의 해시에 연결해, 중간이 변조·유실되면 체인이 끊기는 변조탐지(tamper-evident) 구조. `report` 무결성 게이트의 기반. |
| **우회(bypass)** | 게이트웨이를 경유하지 않고 나가는 송신. `coverage`/`monitor` 가 측정·표본화하고, 패킷 레이어(nftables 허용목록)에서 원천 차단. |
| **커버리지(coverage)** | 전체 송신 중 게이트웨이를 경유한(`via_gateway`) 비율. nftables 집행을 "몇 %를 실제로 통과시켰나"라는 측정 가능한 보증으로 만든다. |
| **EDM(Exact Data Match, 정확 일치)** | 고객 데이터셋 사전을 기반으로 한 정확 일치 탐지 — 정규식·NER 로 잡기 어려운 고객 고유 식별자를 직접 매칭. |
| **NER(개체명 인식)** | Named Entity Recognition. 한국어 인명 등 문맥상 개체를 인식하는 탐지 백엔드(선택, 미설치 시 사전 기반으로 동작). |
| **fail-closed** | 실패 시 **안전 쪽으로** 닫힘 — 감사 기록에 실패하면 외부 전송을 차단. 가용성보다 유출 방지를 우선. |
| **Wilson 신뢰구간(Wilson CI)** | 이항 비율에 대한 통계적 하한 추정. 단순 점추정(재현율 = X/N)이 아닌, 표본 크기를 반영한 실제 성능의 하한 보증. NuFi 는 Wilson CI95 하한 ≥ 0.90 을 릴리스 수용 기준으로 사용. |
| **강한 PII(strong PII)** | 주민등록번호·외국인등록번호·여권·운전면허·신용카드·계좌번호 — 체크섬이 있거나 구조적으로 고유한 강한 식별자. 기본 정책: **차단(block)**. |
| **약한 PII(weak PII)** | 인명(KR_PERSON)·전화(KR_PHONE)·이메일·사업자등록번호·지명(KR_LOCATION) — 문맥 없이는 유일 식별이 어려운 식별자. 기본 정책: **가명화(pseudonymize)** 또는 경고(warn). |
| **가역성(reversibility)** | 가명화된 surrogate 토큰을 Vault 에 보관된 세션 DEK 로 원복할 수 있는 특성. 응답에서 LLM 이 surrogate 를 그대로 사용하면 deanonymize 로 원문을 복원. |
| **PII 라우팅(PII routing)** | PII 감지 결과를 기반으로 LLM 요청 경로를 결정하는 레이어. PII 포함 → 로컬 모델 강제, PII 없음 → 클라우드 허용. egress 감사보다 앞단에서 실행. |

---

## 부록 — 전체 문서 지도

이 매뉴얼은 **정주행 척추**입니다. 주제별 권위 문서와 역사적 스냅샷을 한눈에 보려면 문서
지도 [`README.md`](README.md) 를 보세요. 버전별 변경 이력은 [`../CHANGELOG.md`](../CHANGELOG.md),
사람 친화 릴리스 노트는 [`RELEASE_NOTES.md`](RELEASE_NOTES.md) 입니다.

| 주제 | 권위 문서 |
|---|---|
| 제품 개요 + 빠른 시작 | [`../README.md`](../README.md) |
| 아키텍처(단일 권위) | [`ARCHITECTURE.md`](ARCHITECTURE.md) |
| 입문 실습 | [`HANDS_ON.md`](HANDS_ON.md) |
| 서빙 앞단 통합 | [`INTEGRATION_GUIDE.md`](INTEGRATION_GUIDE.md) |
| CLI 전체 레퍼런스 | [`CLI.md`](CLI.md) |
| 데모 카탈로그 | [`DEMO.md`](DEMO.md) |
| 정책 운영 자동화 | [`OPS_POLICY_AT_SCALE.md`](OPS_POLICY_AT_SCALE.md) |
| 룰 핫리로드 | [`OPS_RULE_RELOAD.md`](OPS_RULE_RELOAD.md) |
| 규정준수·컴플라이언스 매핑(증빙) | [`REPORTING.md`](REPORTING.md) |
| 정책 프리셋 | [`PRESETS.md`](PRESETS.md) |
| 원문 보존·키 회전 | [`SECURITY_RETAIN_RAW_KEYROTATION.md`](SECURITY_RETAIN_RAW_KEYROTATION.md) |
| SDK | [`SDK.md`](SDK.md) |
| PII 기반 라우팅 | [`PII_ROUTING.md`](PII_ROUTING.md) |
| 릴리스 노트 | [`RELEASE_NOTES.md`](RELEASE_NOTES.md) |
| 공개 문서 스타일 | [`DOC_STYLE.md`](DOC_STYLE.md) |

*최종 갱신: 2026-07-04 · v0.4.16-patch45*
