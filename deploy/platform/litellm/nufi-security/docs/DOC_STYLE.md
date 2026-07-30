# 공개 문서 작성 규칙 (Public Documentation Style Rule)

> 적용 범위: 이 저장소(`dudaji/nufi-security`)의 **공개되는 모든 문서** — `README.md`,
> `CHANGELOG.md`, `docs/**`, 각 폴더의 `README.md`.
> 출처: board 지시 (2026-06-28). 이 규칙은 공개 저장소에 머지되는 모든 문서에 우선 적용된다.

이 저장소는 **외부 사용자(개발자·도입 검토자)** 가 읽는 공개 저장소다. 문서는 그 독자를 향해
쓴다. 사내 회의록·이사회 보고처럼 쓰지 않는다.

## 1. 독자는 사용자다 — 이사회·내부 보고처럼 쓰지 않는다 (가장 중요)

공개 문서에 **다음을 쓰지 않는다.**

- 사내 이슈 번호 (`CMP-123` 등) — 독자에게 의미 없는 내부 식별자
- 사내 역할/조직 호칭 (`CEO`·`CPO`·`CMO`·`Engineer`·`보드`·`이사회`)
- 내부 의사결정·승인 절차 (`보드 승인`·`board approved`·`상시 승인`·`검수`·`게이트 판정`)
- 내부 진척 보고 어투 (`보드 리뷰 핵심 증거`·`내부 진척·마일스톤`·`Internal status & board review`)
- 영업/세일즈 자산·타겟 고객·아웃리치 계획 → **공개 저장소에 두지 않는다** (`docs/gtm/` 는 `.gitignore`)

대신 **무엇을·왜·어떻게 쓰는지**를 사용자 관점에서 설명한다. 변경 이력이 필요하면
버전(`v0.0.5`)으로 말하고, 사내 이슈 번호로 말하지 않는다.

| ❌ 이사회처럼 | ✅ 사용자처럼 |
|---|---|
| `M5 벤치·하드닝 (CMP-99/100) — 보드 리뷰 핵심 증거` | `벤치마크: 한국어 PII 재현율(recall) 0.9433` |
| `보드 approved` / `상시 승인 CMP-96` | (삭제 — 사용자에게 불필요) |
| `Internal status & board review: docs/STATUS.md` | (삭제) |
| `전체 문서 지도(설계·명세·데모·영업)` | `전체 문서 목록` |

## 2. 전문 용어는 한글 + 괄호 안에 영어를 함께

전문 용어(technical term)는 처음 나올 때 **한글 뒤 괄호에 영어 원어**를 적어 검색·대조가
쉽게 한다. 예: 게이트웨이(gateway), 폴백(fallback), 가명화(pseudonymization),
재현율(recall), 정밀도(precision), 해시체인(hash chain), 정규식(regular expression),
체크섬(checksum), 에어갭(air-gap), 온프렘(on-prem).

## 3. 사용자 친화적으로 — 충분히 설명한다

- 약어·줄임말은 풀어 쓴다. PII → 개인정보(Personally Identifiable Information).
- "왜 필요한가 → 무엇을 하는가 → 어떻게 쓰나" 순서로, 배경 지식이 없는 독자도 따라오게.
- 표(table)에서 한 열(column)에 긴 명령어를 통째로 넣지 않는다. 긴 명령은 코드 블록
  (code block)으로 따로 빼서 표의 열 폭이 한쪽으로 쏠리지 않게 한다.
- 친절한 설명을 위해 길어지는 것은 괜찮다. 다만 내부 사정이 아니라 사용자가 할 일을 설명한다.

## 4. 적용 체크 (PR/머지 전)

```bash
# 공개 문서에 내부 식별자/호칭이 남아 있는지 점검 (0 이어야 한다)
git grep -nE '이사회|보드 승인|board approved|board review|Internal status|상시 승인|검수|영업|CMP-[0-9]|\b(CPO|CMO|CEO)\b|Engineer' -- '*.md'
```

남는 것이 있으면 §1 표대로 사용자 관점 표현으로 바꾸거나 삭제한다.

## 5. 적용 범위 예외 — 내부 인수인계 문서 (`HANDOVER/`)

이 규칙은 **외부 사용자용 공개 제품 문서**(`README.md`·`CHANGELOG.md`·`docs/**`)에 적용된다.
저장소 최상단 `HANDOVER/` 폴더는 예외다. 이 폴더는 저장소를 **이어받아 작업할 팀 구성원과
그들의 AI 에이전트**를 독자로 하는 내부 운영 문서로, 거버넌스·역할·에이전트 동작 규약을
설명하려면 역할 호칭 등 위 금지어를 인용할 수밖에 없다(이 `DOC_STYLE.md` 자신이 금지어를
예시로 인용하느라 예외인 것과 같은 이유). 스타일 가드(`scripts/check_doc_style.py`)는
`HANDOVER/` 트리를 검사에서 제외한다. 공개 제품 문서에는 규칙이 그대로 강제된다.

---

## 관련 문서

| 문서 | 역할 |
|---|---|
| [`../HANDOVER/ENGINEERING_CONVENTIONS.md`](../HANDOVER/ENGINEERING_CONVENTIONS.md) | 커밋·릴리스·테스트 규약 — 사전 커밋 점검 스크립트 목록 포함 |
| [`../HANDOVER/AGENT_OPERATING_MODEL.md`](../HANDOVER/AGENT_OPERATING_MODEL.md) | 에이전트 거버넌스 — 이 스타일 규칙이 적용되는 배경 |
| [`README.md`](README.md) | 문서 지도 — 각 문서의 역할과 읽기 순서 |
