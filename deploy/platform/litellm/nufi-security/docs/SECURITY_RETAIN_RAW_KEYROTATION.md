# retain_raw 보존정책 & Vault 키 회전 가이드 (v0.0.2)

> **스코프:** 운영/설정·문서·테스트. 신규 egress 차단 규칙이나 게이트웨이 결정 로직 변경은 없다.
> **오설정 방지 테스트:** `tests/test_cmp124_reload.py::test_misconfig_prevention_retain_raw_and_kek_rotation`

이 문서는 보안검토에서 우선적으로 확인되는 항목 두 가지 — (1) egress 원문(raw) 보존(retain_raw)과
(2) 매핑 Vault의 AES-256-GCM 키 회전 — 의 보존/TTL/삭제 정책과 절차를 명문화한다.

---

## 1. retain_raw — 원문 본문 보존 정책

### 1.1 무엇을 저장하는가
분리 메시지 스토어(`config/audit_profiles.yaml` → `profiles`)와 게이트웨이 출구
content dump(`capture/content_dump.py`)는 `egress_class`(private/public)별로 본문을
다음 둘 중 하나로 저장한다.

| retain_raw | 저장 본문 | 의미 |
|---|---|---|
| `false` (기본, public) | **정책 통과본**(가명화/마스킹) | 원문 PII/기밀 평문이 디스크에 남지 않음 |
| `true` (기본, private) | **원문(raw)** | 경계 내 감사·내부자 오남용 추적용 |

`content_dump.dump(..., body_retained=...)`의 기본값은 **`"sanitized"`** 다 —
즉 retain_raw 를 명시적으로 켜지 않으면 원문은 보존되지 않는다(오설정 방지의 기본값).

### 1.2 보안 불변식 (오설정 = 사고)
- **경계 밖(public) 기본은 `retain_raw: false`.** public 을 `true` 로 켜면 egress
  **원문 평문**(PII·기밀 포함)이 `logs/messages/public/`·`logs/packets/public/` 에
  평문 jsonl 로 남는다. 이는 데이터 잔류(at-rest) 위험을 만든다.
- public `retain_raw: true` 전환은 **반드시** 아래를 선행한다:
  1. 디스크 접근 제어(파일 권한 `600`, 디렉터리 `700`, 전용 운영 계정).
  2. 보존기간(§1.3) 합의 + 자동 삭제 작업 등록.
  3. 운영 책임자 검토 후 적용. 코드 변경이 아니라 **운영 설정 변경**으로 다룬다.

### 1.3 보존기간(TTL) & 삭제 절차
보존 파일은 일자 회전(`YYYY-MM-DD.jsonl`)된다 — 따라서 TTL = "N일 이전 파일 삭제".
현재 자동 GC 데몬은 없으므로(스코프 외) **운영 cron** 으로 강제한다. 권장 기본값:

| 데이터 | 경로 | 기본 보존 | 삭제 |
|---|---|---|---|
| private 메시지 | `logs/messages/private/*.jsonl` | 90일 | cron 일삭제 |
| public 통과본 | `logs/messages/public/*.jsonl` | 30일 | cron 일삭제 |
| public content dump | `logs/packets/public/dump-*.jsonl` | 14일 | cron 일삭제 |
| 감사 finding/alert | `logs/audit_findings.jsonl`, `logs/alerts.jsonl` | 180일 | 회전 후 보관 |

권장 cron(예: public dump 14일 초과 삭제):
```bash
# 매일 03:10, 14일 지난 public dump/통과본 삭제 (보존기간 = 운영 합의값으로 교체)
10 3 * * *  find /opt/nufi/logs/packets/public -name 'dump-*.jsonl' -mtime +14 -delete
15 3 * * *  find /opt/nufi/logs/messages/public -name '*.jsonl'      -mtime +30 -delete
```
> public `retain_raw: true` 인 환경은 위 보존기간을 **짧게**(예: 7일) 잡고 접근 로그를
> 별도 보관한다. 삭제는 되돌릴 수 없으므로(평문 원문) cron 경로를 절대경로로 고정한다.

### 1.4 검증
`config/audit_profiles.yaml` 의 기본값(private=true / public=false)과
`ContentDumpWriter.dump` 의 `body_retained="sanitized"` 기본값은 오설정 방지 테스트로
회귀 고정된다(§상단 링크). public 기본이 `true` 로 바뀌면 검토 대상 — 의도된 변경이면
이 문서의 보존기간/접근통제 항목을 동시 갱신할 것.

---

## 2. Vault AES-256-GCM 키 회전 가이드

매핑 Vault(`egress_audit/vault.py`)는 가역 가명화의 surrogate↔원본 매핑을 **봉투암호화**로
보관한다: 세션 DEK 로 원본 암호화 → **KEK** 로 DEK 봉인. at-rest 평문 키는 0.

### 2.1 KEK 주입(필수, 운영)
KEK 은 환경변수 `EGRESS_VAULT_KEK` 로 주입한다. 형식은 **정확히 32바이트(AES-256)**:
- `hex64` (64 hex 문자), 또는 `base64`(디코드 시 32B).
- 미주입(PoC) 시 부팅마다 휘발성 랜덤 KEK 생성 → 재시작 시 기존 매핑 복호 불가(**안전한 실패**).
- 잘못된 길이(16B/AES-128 등)·디코드 실패는 **부팅 시 거부**(`ValueError`) — 평문/약키 폴백 금지.

```bash
# 32바이트 KEK 생성(hex64). keyring/HashiCorp Vault 등 비밀관리자에 보관 후 주입.
export EGRESS_VAULT_KEK="$(openssl rand -hex 32)"
```

### 2.2 회전 절차(권장)
Vault 는 외부 호출 0(NFR1) — 로컬 키소스만 사용한다. 회전은 운영 절차로 수행한다.

**원칙:** 매핑 TTL 이 짧으므로(기본 30분, hard cap 24h) **드레이닝 회전**이 가장 안전하다.

1. **새 KEK 발급:** `NEW_KEK=$(openssl rand -hex 32)` — 비밀관리자에 신규 버전으로 저장.
2. **드레이닝:** 신규 세션이 새 KEK 를 쓰도록 배포하되, 기존 in-flight 세션의 TTL(≤24h)이
   만료될 때까지 유지. 매핑은 응답 경로(가명 원복)에서만 단명으로 쓰이므로 짧게 소진된다.
3. **컷오버:** `EGRESS_VAULT_KEK=$NEW_KEK` 로 게이트웨이 롤링 재기동. 재기동 시점에 미만료
   매핑은 복호 불가가 되지만(안전한 실패), 드레이닝을 거쳤으면 영향 세션은 0 에 수렴한다.
4. **무중단 회전이 필요하면** 봉투암호화의 KEK 계층을 다중 키로 확장한다(아래 §2.3).

### 2.3 무중단 회전 설계 노트(향후 — 스코프 외, 구현 미포함)
in-memory PoC 는 단일 KEK 만 보유한다(`MappingVault._kek`). 무중단 회전은 다음으로 확장:
- **다중 KEK 언랩:** `_unwrap` 이 `{kid: kek}` 맵을 순회하며 현재/직전 KEK 로 시도, `_wrap` 은
  항상 최신 KEK 로 재봉인. wrapped_dek 앞에 `kid` 프리픽스를 둔다.
- **백그라운드 재봉인:** 회전 시 활성 세션의 `wrapped_dek` 을 새 KEK 로 lazy 재봉인.
이 확장은 키관리 동작 변경이므로 별도 작업으로 다룬다. 이 문서의 범위는 절차 문서화까지다.

### 2.4 오설정 방지 검증
`load_kek` 의 32바이트 강제(16B/8B 거부)는 키 회전 오설정 테스트로 고정된다(§상단 링크).
KEK 길이/형식이 틀리면 **부팅이 실패**해야 하며, 평문 폴백은 보안상 금지다.

---

## 3. 운영 체크리스트 (요약)
- [ ] public `retain_raw` 는 `false` 인가? `true` 라면 접근통제+보존기간+운영 책임자 검토가 끝났는가?
- [ ] 보존기간 cron 이 등록되어 있는가? 경로는 절대경로인가?
- [ ] `EGRESS_VAULT_KEK` 가 32바이트로 주입되어 있는가(휘발성 PoC 아님)?
- [ ] 키 회전 시 드레이닝(§2.2) 순서를 따랐는가?

---

## 관련 문서

| 문서 | 역할 |
|---|---|
| [`OPS_RULE_RELOAD.md`](OPS_RULE_RELOAD.md) | 핫리로드 운영 절차 (retain_raw 오설정 방지 포함) |
| [`PRESETS.md`](PRESETS.md) | `audit_profiles.profiles.public.retain_raw` 프리셋 노브 설명 |
| [`REPORTING.md`](REPORTING.md) | 감사 로그·보존 데이터를 컴플라이언스 리포트와 연결하는 방법 |
