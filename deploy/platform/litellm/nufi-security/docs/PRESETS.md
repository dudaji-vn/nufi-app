# 파이프라인 프리셋 선택 가이드

`config/policy.yaml` · `routing.yaml` · `audit_profiles.yaml` 를 raw 편집하는 대신,
**의견 있는 프리셋**으로 안전한 채택을 가속한다. 프리셋은 보안 기본값을 인코딩하므로
"기본값 오설정으로 인한 조용한 누수" 위험을 줄인다.

```bash
# 사용 가능한 프리셋 보기
nufi-egress init --list

# 프리셋에서 운영 config 구체화(./config 에 기록)
nufi-egress init strict-kr-pii --out ./config

# 적용 전 결정 미리보기(파일 미생성)
nufi-egress init audit-only --dry-run
```
> CLI 를 설치하지 않은 환경의 동치 실행법은 [`CLI.md`](CLI.md)(§표기 규약)를 참고하세요.

raw YAML 직접 편집은 여전히 **파워유저 탈출구**로 유지된다 — 프리셋이 낸 config 를
그대로 손봐도 되고, 프리셋 오버레이(`config/presets/<name>.yaml`)를 고쳐 재현해도 된다.

---

## 한눈에 비교

| 프리셋 | 한 줄 요약 | 약한 PII | 강한 PII·비밀 | 요청 차단 | enforcement | 본문 보존(public) |
|---|---|---|---|---|---|---|
| **strict-kr-pii** | 최대 보호, 의심스러우면 차단 | **차단** | 차단 | 광범위 | **fail-closed** | 미보존 |
| **audit-only** | 차단 없이 전수 관찰·기록 | warn(통과) | warn(통과) | **없음** | fail-open | 보존(포렌식) |
| **pseudonymize-roundtrip** | 가역 가명화로 효용 보존 | **가명화·원복** | 차단 | 비밀/강PII만 | fail-open | 미보존(가명화본) |

> "약한 PII" = 인명·전화·이메일·사업자번호·지명. "강한 PII" = 주민/외국인/여권/면허·카드·계좌.
> "비밀" = API 키·토큰 등 SECRET.

---

## 어떤 것을 고를까

### `strict-kr-pii` — 규제·고위험 환경
- **누구를:** 금융·의료·공공 등 컴플라이언스가 강하고 "막는 게 기본"인 조직.
- **동작:** 강·약 PII 와 기밀 신호(키워드/EDM/표식)를 전부 차단. 매핑에 없는 미지
  엔티티도 기본 차단(`default_action: block`). 우회 패킷 enforcement 는 **fail-closed**
  — 집행이 실패하면 가용성보다 보호를 택해 전면 차단.
- **트레이드오프:** 오탐(benign block) 가능성이 가장 높다. 도입 전 골드셋으로 차단율 확인 권장.

### `audit-only` — 도입 초기 가시성
- **누구를:** 먼저 "무엇이 새는지" 측정하고 싶은 조직, 섀도 IT 가시화.
- **동작:** **어떤 요청도 차단하지 않는다**(`blocking_actions: []` + 모든 엔티티 `warn`).
  본문은 변형 없이 통과시키되, 탐지 finding 은 전부 감사 로그에 남긴다. 포렌식을 위해
  public 본문도 원문 보존(`retain_raw: true`).
- **트레이드오프:** 보호가 아닌 **관찰** 모드. 원문 보존을 켜므로 보존기간·접근통제를
  운영 정책으로 명시해야 한다. 운영 차단이 필요해지면 다른 두 프리셋으로 승격.

### `pseudonymize-roundtrip` — 효용 보존
- **누구를:** public LLM 답변 품질은 유지하되 PII 노출은 막고 싶은 조직.
- **동작:** 약한 PII 를 구조보존 **가역 가명토큰**으로 치환해 모델에 보내고(pre_call),
  응답에서 원래 값으로 원복(post_call, M3 `ReversibleEgress` + `MappingVault`).
  비밀·카드·주민/외국인/여권/면허는 가명화로도 내보내지 않고 **차단 유지**.
- **트레이드오프:** 가역 원복은 Vault 세션 컨텍스트에 의존. 가명화 토큰이 모델 추론
  품질에 미치는 영향은 워크로드별로 확인 권장.

---

## 동일 입력, 프리셋별 결정 diff

입력: `홍길동 고객 전화 010-1234-5678, 이메일 hong@dudaji.com, AWS 키 AKIA...EXAMPLE 포함.`

| 프리셋 | blocked | 동작 분포 | 변환 결과 |
|---|---|---|---|
| strict-kr-pii | `True` | 전부 block/redact | `<KR_PERSON_REDACTED> … <EMAIL_REDACTED>` |
| audit-only | `False` | 전부 warn(통과) | 원문 그대로(+ finding 6건 로깅) |
| pseudonymize-roundtrip | `True`* | 약 PII 가명화, **비밀 차단** | `<KR_PERSON_8b28…> …` (AWS 키 때문에 차단) |

\* 비밀이 없는 입력이면 `pseudonymize-roundtrip` 은 차단하지 않고 가명화 통과한다.
재현: `python tests/test_cmp121_presets.py` (수용 기준 자동 확인).

---

## fail-closed 보증

`nufi init` 은 다음을 **거부**하고 비0 종료하며 **어떤 파일도 쓰지 않는다**:

- 알 수 없는 프리셋 이름 (`nufi init bogus` → 거부 + 사용 가능 목록 안내)
- 허용목록 밖 `--set` 키 (안전 노브만 조정 허용; 정책 핵심은 프리셋/raw 편집 경로)
- 무효 값(예 `--set policy.enforcement.fail_mode=banana`) 또는 검증 실패 config
- 기존 config 파일 존재 시(`--force` 없으면 덮어쓰기 거부)

`--set` 허용 노브: `policy.default_action`, `policy.enforcement.fail_mode`,
`audit_profiles.profiles.public.retain_raw`, `audit_profiles.profiles.private.retain_raw`.

---

## 동작 원리

프리셋은 `config/presets/<name>.yaml` 의 **오버레이**다. `nufi init` 이
베이스 `config/*.yaml` 에 deep-merge → directive 적용 → `--set` override → 스키마 검증
순으로 완전한 config 집합(policy/routing/audit_profiles)을 만든다. 기존
`PolicyEngine`/`Applier` 가 읽는 **동일 식별자·스키마**를 유지하므로 런타임 동작 경로는
바뀌지 않는다(프리셋은 config 만 바꾼다). 엔진 구현은 `egress_audit/presets.py`.

---

## 관련 문서

| 문서 | 역할 |
|---|---|
| [`INTEGRATION_GUIDE.md`](INTEGRATION_GUIDE.md) | 통합 경로 택일 → 프리셋 고르기 → doctor 검증 순서 |
| [`OPS_RULE_RELOAD.md`](OPS_RULE_RELOAD.md) | 프리셋 적용 후 YAML 룰을 무재기동으로 갱신하는 절차 |
| [`OPS_POLICY_AT_SCALE.md`](OPS_POLICY_AT_SCALE.md) | 다중 프로파일·경로별 바인딩·버전 관리·롤백 |
| [`PII_ROUTING.md`](PII_ROUTING.md) | PII 감지 기반 로컬/클라우드 자동 분배(프리셋과 독립) |
| [`CLI.md`](CLI.md) | `nufi-egress init` 전체 플래그·종료코드 레퍼런스 |
