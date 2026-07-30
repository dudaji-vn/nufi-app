# 조사·전략 문서 (`docs/research/`)

> 이 폴더는 **참조용 조사·전략 산출물**을 보관합니다. 현행 제품 방향·우선순위의 권위는
> [`../ROADMAP.md`](../ROADMAP.md) 이고, 통합 문서 색인의 권위는 [`../README.md`](../README.md) 입니다.
> 여기에 있는 문서들은 "왜 이 방향을 선택했나"의 배경 근거로 읽습니다.

---

## 문서 목록

| 파일 | 내용 | 상태 |
|---|---|---|
| [`FSEC_AI_GUIDE_2026.md`](FSEC_AI_GUIDE_2026.md) | 금융분야 AI 보안 안내서(2026.6) NuFi 관련 점검항목 분석 — 컴플라이언스 매핑의 입력 원천 | 📄 참조 |
| [`NUFI_SECURITY_PLANE_CHARTER.md`](NUFI_SECURITY_PLANE_CHARTER.md) | NuFi 보안·증빙 평면 차터 — 통합 플랫폼 내 소유 범위·통합 계약·가드레일 | 📄 참조 |
| [`SOLUTION_FOCUS_OPTIONS.md`](SOLUTION_FOCUS_OPTIONS.md) | 솔루션 집중 방향 옵션 분석 — 2축 집중(규제 증빙 + 한국어 PII DLP) 보드 결정(2026-06-29) 배경 | 📄 참조 |
| [`HYBRID_LLM_PRIVACY_ACCURACY.md`](HYBRID_LLM_PRIVACY_ACCURACY.md) | 하이브리드 LLM 파이프라인 — 가명화 환경에서 응답 품질 유지 방안 조사 | 📄 참조 |

---

## 배경 — 왜 이 문서들이 있나

- **FSEC_AI_GUIDE_2026.md** — 금융보안원 안내서 72쪽을 NuFi 통제 커버리지 관점에서 분석한 내부 참고 자료입니다.
  `enforcement/compliance_catalog.yaml` 의 `fsec-ai` 프레임워크 매핑 항목의 원천입니다.

- **NUFI_SECURITY_PLANE_CHARTER.md** — NuFi 가 통합 AI 플랫폼 안에서 **무엇을 소유**하고 **무엇을 소유하지 않는지**를
  정의한 차터 초안입니다. 4 기둥(PII/DLP 엔진·이그레스 정책·해시체인 감사·컴플라이언스 매핑)의 경계를 확정합니다.

- **SOLUTION_FOCUS_OPTIONS.md** — 제품 방향 선택지 5개를 분석하고, 보드가 "규제 준수 증빙 게이트웨이 + 한국어 PII DLP"
  2축에 집중하기로 결정한 근거입니다. ROADMAP.md 의 P1(규제 증빙)·P2(SDK) 우선순위의 배경입니다.

- **HYBRID_LLM_PRIVACY_ACCURACY.md** — 외부 LLM에 가명화된 데이터를 보낼 때 응답 품질 저하를 해소하는 방안을
  조사한 자료입니다. 가역적 가명화, PRIV-QA, 민감도 기반 라우팅 등 5가지 접근 방식과 관련 논문·오픈소스를 정리합니다.

---

## 관련 living 문서

| 문서 | 역할 |
|---|---|
| [`../ROADMAP.md`](../ROADMAP.md) | 현행 방향·우선순위 (research/ 결정을 반영한 living 문서) |
| [`../REPORTING.md`](../REPORTING.md) | 컴플라이언스 매핑 리포트 API·출력 방법 |
| [`../ARCHITECTURE.md`](../ARCHITECTURE.md) | 보안·증빙 평면 구현 아키텍처 |
