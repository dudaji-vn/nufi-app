# 🚦 릴리스 체크리스트 — 버전별 DoD (NuFi Egress-Audit)

> 이 저장소를 릴리스하는 메인테이너(maintainer)를 위한 체크리스트입니다.
> 모든 버전(`vX.Y.Z`)은 아래 Definition of Done(DoD)을 **릴리스 태그 컷 이전**에 충족합니다.
> 미충족 항목이 있으면 그 버전은 아직 릴리스하지 않습니다.

## 버전 릴리스 DoD (every version)

각 버전이 전달하는 **사용자 대면 기능마다**:

1. **데모 (Demo)** — root 없이(에어갭/CI) 1~2 명령으로 재현되는 실행 가능한 데모. 가능하면 `./scripts/demo_*.sh` 단일 명령 + PASS/FAIL 판정. 합성·비-PII 픽스처만 사용.
2. **실행 매뉴얼 (Run manual)** — 기능을 어떻게 돌리는지의 문서(명령·플래그·기대 출력·종료코드). 위치: `docs/CLI.md`(CLI 기능) 또는 기능별 `*/README.md`(예: `dashboards/README.md`).
3. **README 링크 (Discoverability)** — 위 데모·매뉴얼이 최상단 [`README.md`](../README.md) §"매뉴얼·데모" 표 + [`docs/README.md`](README.md) 문서지도에서 **클릭 가능하게 링크**됨. README 의 CLI 서브커맨드 목록이 신규 명령을 포함하는지 확인.

그리고 버전 전체에 대해:

4. **릴리스 위생** — `VERSION` 갱신 · `CHANGELOG.md` 해당 버전 섹션 작성 · `git tag vX.Y.Z` + origin 푸시.
5. **GitHub Release 발행 (태그 푸시 직후 필수)** — git 태그만으로는 GitHub 의 Releases 페이지에 노트 본문이 보이지 않습니다. 태그를 origin 에 올린 **직후**, 그 태그에 GitHub Release 객체를 발행합니다.
   - 본문(notes) = [`docs/RELEASE_NOTES.md`](RELEASE_NOTES.md) 의 해당 버전 섹션(사람 친화 6-섹션 내러티브). 제목 = 해당 태그의 annotation.
   - 한 명령:
     ```bash
     ./scripts/publish_github_release.sh vX.Y.Z          # gh CLI 또는 GH_TOKEN/GITHUB_TOKEN 사용
     ./scripts/publish_github_release.sh vX.Y.Z --dry-run # 발행 전 본문 미리보기
     ```
   - 인증(gh 로그인 또는 repo-scope 토큰)이 없으면 본문만 추출하고 종료코드 2 로 안내합니다 → 토큰 확보 후 재실행.
   - 검증: 공개 API `https://api.github.com/repos/dudaji/nufi-security/releases/tags/vX.Y.Z` 가 200 을 반환하면 발행 완료.
6. **테스트 통과** — 데모·테스트가 실제로 통과(상태 표시가 아니라 산출물/커밋으로 증거).

## 산출물(문서화) 표준 (2026-06-29~)

> **README.md 와 HANDS_ON.md 가 가장 중요한 산출물입니다.** 모든 버전·패치 작업은 아래를 반드시 포함하며, 미충족 시 done 으로 마감하지 않습니다.

- **CHANGELOG.md (필수):** 각 작업마다 **(a) 무엇을 한 작업인지 · (b) 왜 했는지 · (c) 사용자는 이제 무엇을 할 수 있게 되었는지** 를 명시. 단순 변경 나열 금지 — 사용자 가치·동기를 포함.
- **HANDS_ON.md (필수, 최우선):** 사용자가 **직관적으로 이해하고 따라할 수 있도록** 실습 절차·예시 추가.
- **README.md (필수, 최우선):** 신규 기능·사용법 진입점 반영(매뉴얼·데모 표 + CLI 서브커맨드 목록).

## 패치 릴리스 라인 (2026-06-29~)

- 한 버전을 릴리스한 뒤, 그 버전 라인의 **패치**를 릴리스할 수 있습니다(릴리스 정책에 따라 협의 후 진행).
- 명명 규약: **`vX.Y.Z-patchNN`** (2자리 0-패딩, `01` 부터). 예: `v0.0.9` 릴리스 후 → `v0.0.9-patch01`, `v0.0.9-patch02`.
- 패치는 동일 버전 라인의 버그픽스·문서보강·소규모 개선에 사용합니다. 버전 라인을 바꿔야 할 규모면 새 버전 라인으로 진행합니다.
- 패치도 위 산출물 표준(CHANGELOG·HANDS_ON·README) + 릴리스 위생(VERSION·CHANGELOG 섹션·`git tag vX.Y.Z-patchNN`·push·GH Release)을 동일하게 충족합니다.

## 패치 릴리스 사전 위임 (2026-07-02~)

> 토큰·왕복(round-trip) 절감을 위해 프로젝트 메인테이너가 아래를 표준으로 승인했습니다.
> 배경: 릴리스마다 태그 컷·push·게시 확인을 건별로 기다리면, 대기·재-wake 시 컨텍스트 재로드가 실제 작업량보다 큰 토큰을 소모합니다.

- **패치 태그 자동 진행:** 패치 라인(`vX.Y.Z-patchNN`)에서 캡스톤 검증이 green(데모·테스트·문서 가드 통과)이면, 릴리스 위생(VERSION·CHANGELOG·태그·push)과 GitHub Release 발행까지 건별 확인 없이 진행합니다. **마이너/메이저 버전 라인의 착수·외부 공개는 종전대로 메인테이너 결정에 유보**합니다.
- **push/게시 지연 최소화:** 태그 push 나 GitHub Release 발행이 권한·토큰 사유로 막히면, 담당자가 **즉시** 처리하거나 위 자동 진행으로 대체합니다(지연 1건마다 재작업·재-wake 비용이 붙습니다).
- **표준 기본값(메인테이너 위임으로 확정 — 매 릴리스 재질문하지 않음):**
  - *릴리스 담당* 기본값 = **캡스톤(릴리스 준비)을 완료한 담당 에이전트가 그대로 릴리스 메커닉(태그 컷·push·게시)을 수행**. 별도 하위 위임 없이 진행하여 인수인계 왕복을 없앱니다.
  - *OKR 목표 연결* 기본값 = **활성 NuFi 목표에 연결**(내부 OKR 트래커의 NuFi 목표). 별도 지정이 없으면 null 대신 이 기본값을 사용합니다.

## 적용 현황

| 버전 | 기능 | 데모 | 매뉴얼 | README 링크 | 태그/푸시 |
|---|---|---|---|---|---|
| v0.0.2 | Adopt(SDK·doctor·프리셋·배포·통합가이드) | `demo_audit_separation.sh` | `INTEGRATION_GUIDE.md`·`CLI.md` | ✅ | ✅ tag `v0.0.2` origin |
| v0.0.3 | O2 커버리지 보증 | `scripts/demo_coverage.sh`(1-명령 PASS/FAIL) | `CLI.md#coverage`·`DEMO_v0.0.3.md` | ✅ | ✅ tag `v0.0.3` |
| v0.0.3 | O1 감사 대시보드(read-only) | `scripts/demo_dashboards.sh`(1-명령 PASS/FAIL) | `dashboards/README.md`·`DEMO_v0.0.3.md` | ✅ | ✅ tag `v0.0.3` |
| v0.0.3 | O3 정책 운영 규모화 | (이후 릴리스 범위) | — | — | ⏭ 이연 |
| v0.0.4 | Adopt 패치(설치형 패키징·통합 CLI·입문) | `demo.sh`(13/13)·`HANDS_ON.md` | `CLI.md`·`HANDS_ON.md` | ✅ | ✅ tag `v0.0.4` origin(`c4e822e`) |
| v0.0.5 | B1 정책 운영 자동화 | `scripts/demo_policy_ops.sh`(4/4 PASS) | `OPS_POLICY_AT_SCALE.md`·`CLI.md#policy`·`DEMO_v0.0.5.md` | ✅ | ⏳ 준비완료 — 태그 컷 대기 |
| v0.0.5 | B2 정확도 숙제 종결 | `scripts/demo_accuracy.sh`(2/2 PASS) | `DEMO_v0.0.5.md` | ✅ | ⏳ 준비완료 — 태그 컷 대기 |
| v0.4.1 | Python SDK P2 — `from nufi import ...` 라이브러리 파사드 | `demo_sdk.sh`(4/4 PASS) | `SDK.md`·`INTEGRATION_GUIDE.md` | ✅ | ✅ |
| v0.4.12 | KR_ACCOUNT·SECRET 골드셋 확대 + CI 하한 ≥0.90 | `demo_accuracy.sh` | `HANDS_ON.md` | ✅ | ✅ |
| v0.4.13 | 체크섬 골드셋 + KR_PERSON CI ≥0.93 게이트 | `demo_accuracy.sh` | `HANDS_ON.md` | ✅ | ✅ |
| v0.4.14 | 극희성 골드셋 확장 (n=818) | `demo_accuracy.sh` | `HANDS_ON.md` | ✅ | ✅ |
| v0.4.15 | UNLISTED_SURNAMES 미수록 성씨 정합 (골드셋 재생성) | `demo_accuracy.sh` | `HANDS_ON.md` | ✅ | ✅ |
| v0.4.16 | UNLISTED_SURNAMES 재설계 → person_recall 0.9799, CI 하한 0.9591 (n=854) | `demo_accuracy.sh`(3/3 PASS) | `HANDS_ON.md#part-j`·`DEMO.md` | ✅ | ✅ |

> **v0.4.16 릴리스 범위:** ✅ UNLISTED_SURNAMES 합성 음절 → 실증 탐지 성씨 전환. ✅ zz_kr_person_ci_expand(150행) 복원으로 n=854 확보. ✅ Wilson CI 하한 0.9591 달성(≥0.93 게이트 통과). ✅ 307 테스트 통과 · 11/11 데모 PASS. ✅ `examples/library_detect.py` + INTEGRATION_GUIDE 경로 D 추가. ✅ RELEASE_NOTES·ARCHITECTURE·gap-analysis·kr-person-error-analysis·goldset README 현행화.

> **v0.0.3 릴리스 범위:** ✅ ① O1/O2 전용 1-명령 `demo_*.sh` + DEMO 재현 문서. ✅ ② O3 = 이후 릴리스로 이연. ✅ ③ 릴리스 메커닉: VERSION 0.0.3 · CHANGELOG `[0.0.3]` · tag `v0.0.3` + origin push.

> **GitHub Release 발행 현황:** git 태그 `v0.0.1`~`v0.0.6` 은 모두 origin 에 있으나, 과거 메커닉이 5번 단계(GitHub Release 발행)를 누락해 Releases 페이지에 노트 본문이 없습니다. `./scripts/publish_github_release.sh vX.Y.Z` 로 백필합니다(인증 필요). `v0.0.6` 는 [`RELEASE_NOTES.md`](RELEASE_NOTES.md) 본문으로 우선 백필 대상이며, 이후 버전은 위 5번 단계로 상시 발행합니다.

> **v0.0.5 릴리스 범위:** ✅ ① B1·B2 각 1-명령 `demo_*.sh`(4/4·2/2 PASS, root 불필요) + 재현 문서 `DEMO_v0.0.5.md`. ✅ ② 매뉴얼: `OPS_POLICY_AT_SCALE.md`·`CLI.md#policy`(B1) / 측정 리포트(B2). ✅ ③ README §매뉴얼·데모 표 + 문서지도 링크. ✅ ④ hands-on §6.9 정책 운영 실습. ✅ ⑤ CHANGELOG `[0.0.5]` 초안. ⏳ **남은 한 가지 = `VERSION` 갱신 + `git tag v0.0.5` + origin push**.

---

## 관련 문서

| 문서 | 역할 |
|---|---|
| [`RELEASE_NOTES.md`](RELEASE_NOTES.md) | 사람 친화 릴리스 요약 — 비개발자 의사결정자용 |
| [`../CHANGELOG.md`](../CHANGELOG.md) | 기술 변경 이력 — 버전별 상세 변경 목록 |
| [`../HANDOVER/ENGINEERING_CONVENTIONS.md`](../HANDOVER/ENGINEERING_CONVENTIONS.md) | 릴리스 절차 상세 — 태그·push·GH Release 명령 |
| [`DEMO.md`](DEMO.md) | 릴리스 데모 카탈로그 — DoD 검증 데모 목록 |
| [`HANDS_ON.md`](HANDS_ON.md) | 릴리스 산출물 표준의 최우선 문서 |
