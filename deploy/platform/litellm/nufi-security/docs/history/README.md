# 설계 배경·마일스톤 명세 (`docs/history/`)

> 이 폴더는 **역사적 스냅샷**을 보관합니다. 처음에는 읽지 않아도 됩니다.
> 현행 흐름은 [`../ARCHITECTURE.md`](../ARCHITECTURE.md) · [`../MANUAL.md`](../MANUAL.md) 가 권위이며,
> history/ 는 "왜·당시 결정"의 근거 보관용입니다.

---

## 문서 목록

| 파일 | 내용 | 상태 |
|---|---|---|
| [`SPEC.md`](SPEC.md) | 기반 게이트웨이 + 개인정보·비밀 탐지 설계 명세 | 🕮 역사적 (현행 흐름은 ARCHITECTURE.md) |
| [`SPEC_EGRESS_ENFORCEMENT.md`](SPEC_EGRESS_ENFORCEMENT.md) | nftables 우회 차단·패킷레이어 설계 명세 | 🕮 역사적 → 빌드됨 |
| [`SPEC_M4.md`](SPEC_M4.md) | 기밀 1차 탐지(키워드·표식·EDM) 설계 명세 | 🕮 역사적 → 구현됨 |
| [`IMPL_M4.md`](IMPL_M4.md) | 기밀 1차 탐지 구현 상세·결정 사유 | 🕮 역사적 → 구현됨 |
| [`DEMO_v0.0.5.md`](DEMO_v0.0.5.md) | v0.0.5 1-명령 데모 재현 매뉴얼 | 🕮 역사적 — 버전별 스냅샷 |
| [`DEMO_v0.0.3.md`](DEMO_v0.0.3.md) | v0.0.3 1-명령 데모 재현 매뉴얼 | 🕮 역사적 — 버전별 스냅샷 |

---

## 언제 읽나

- **SPEC.md / SPEC_EGRESS_ENFORCEMENT.md / SPEC_M4.md** — 현재 구현이 "왜 이 구조인가"를 추적할 때.
  설계 당시의 NFR(비기능 요건)·트레이드오프가 문서화되어 있습니다.
- **IMPL_M4.md** — 기밀 탐지(EDM·키워드·표식) 구현 선택지와 결정 근거가 필요할 때.
- **DEMO_v0.0.x.md** — 초기 버전 데모 재현이 필요하거나, 현재 데모와의 변화 추적이 필요할 때.
  현행 데모는 [`../DEMO.md`](../DEMO.md) · [`../../scripts/demo_all.sh`](../../scripts/demo_all.sh) 가 권위입니다.

---

## 관련 living 문서

| 문서 | 역할 |
|---|---|
| [`../ARCHITECTURE.md`](../ARCHITECTURE.md) | 현행 아키텍처 단일 권위 (컴포넌트·시퀀스 4종) |
| [`../DEMO.md`](../DEMO.md) | 현행 데모 카탈로그 (11종 + examples/ 12종) |
| [`../MANUAL.md`](../MANUAL.md) | 한 번에 정주행하는 현행 운영자 매뉴얼 |
