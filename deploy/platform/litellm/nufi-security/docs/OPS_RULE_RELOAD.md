# 룰 무재기동 핫리로드 / 드라이런 / fail-closed (v0.0.2)

> **스코프:** 운영/설정·문서·테스트. 신규 차단 규칙이나 게이트웨이 결정 로직 변경은 없다.
> **충족 NFR:** NFR3 — 룰 변경에 게이트웨이 재기동 불필요.
> **구현:** `egress_audit/reload.py` · **CLI:** `scripts/reload_rules.py` ·
> **테스트:** `tests/test_cmp124_reload.py`

운영자가 게이트웨이를 **재기동하지 않고** 탐지·정책 룰을 갱신한다. 잘못된 룰은
**fail-closed** 로 거부되어 직전(검증된) 룰셋이 그대로 유지된다.

## 1. 핫리로드 대상 4개 룰 소스
| 소스 | 파일 | 내용 |
|---|---|---|
| 정규식(patterns) | `config/patterns.yaml` | 한국 PII·비밀정보 정규식 |
| 정책(policy) | `config/policy.yaml` | 엔티티→동작(block/redact/pseudonymize/warn/allow) |
| 기밀 사전(confidential) | `config/confidential.yaml` | 기밀 키워드/표식 |
| EDM 인덱스 | `config/edm/index.json` | 등록 데이터/문서 지문 |

> 무거운 NER 모델은 핫리로드 대상이 **아니다** — 룰 스왑 시 기존 NER 인스턴스를
> 재사용하므로 모델 재로드/재기동이 없다.

## 2. 동작 모델: validate → dry-run → reload
- **validate** — 후보 룰셋 빌드+검증: YAML 파싱, **정규식 컴파일**, 정책 동작이
  허용집합(`{block, redact, pseudonymize, warn, allow}`) 내인지, 표본 코퍼스 스모크
  분석이 예외 없이 끝나는지. 하나라도 실패하면 `RuleValidationError`.
- **dry-run** — 검증 후 현재 vs 후보 룰셋의 **결정 diff**(blocked/action_counts/
  finding_count 변화)를 표본에 대해 산출. **적용하지 않는다.**
- **reload** — 검증 통과 시에만 **원자적 스왑**(`generation`++). 실패 시 **fail-closed**:
  직전 룰셋 유지 + `last_error` 에 사유 기록.

## 3. 운영 절차

### 3.1 적용 전 검증(권장)
```bash
# 1) 후보 룰셋 검증 (exit 0=통과, 1=거부)
python3 scripts/reload_rules.py validate

# 2) 결정 diff 미리보기 (변경 있으면 --fail-on-change 로 exit 3)
python3 scripts/reload_rules.py --policy /path/to/candidate/policy.yaml \
        dry-run --fail-on-change
```
dry-run 출력 예(전화번호 정책을 pseudonymize→block 으로 바꾼 경우):
```json
{
  "fingerprint_before": "3248140816b9e013",
  "fingerprint_after":  "9a6d89c90e717b86",
  "totals": { "samples": 5, "changed": 1, "newly_blocked": 1, "newly_unblocked": 0 },
  "changed": [ { "index": 1, "before": {"blocked": false, ...},
                              "after":  {"blocked": true,  "action_counts": {"block": 1, ...}} } ]
}
```

### 3.2 라이브 게이트웨이에 무재기동 적용 (SIGHUP)
게이트웨이가 `ReloadableGuard.install_sighup_handler()` 를 등록하면, 운영자는
설정 파일을 수정한 뒤 시그널 한 번으로 적용한다:
```bash
# config/*.yaml / edm/index.json 수정 후
kill -HUP "$(pgrep -f egress-gateway)"
```
- 검증 통과 → 원자적 스왑, 진행 중 요청은 스왑 전/후 룰셋 중 하나로 일관되게 처리.
- 검증 실패 → **적용 안 됨**(fail-closed). 직전 룰셋으로 계속 서빙, `last_error` 로그.

### 3.3 코드 임베딩(게이트웨이 통합)
```python
from egress_audit import ReloadableGuard

guard = ReloadableGuard(on_reload=lambda r: log.info(
    "rule reload applied=%s gen=%s fp=%s err=%s",
    r.applied, r.generation, r.fingerprint, r.error))
guard.install_sighup_handler()        # kill -HUP 로 무재기동 적용
...
result = guard.inspect(text)          # 항상 현재 검증된 룰셋으로 결정
```

## 4. fail-closed 보장 (안전 불변식)
- 검증되지 않은 룰셋은 **절대 적용되지 않는다.** 깨진 정규식/알 수 없는 동작/깨진
  YAML 은 모두 거부 사유이며, 거부 시 직전 룰셋이 유지된다.
- dry-run 은 어떤 경우에도 활성 룰셋을 바꾸지 않는다(`generation` 불변).
- 이는 "더 엄격하게(차단을 더) 만드는 룰조차 검증 전엔 안 켠다"는 운영 안전장치이지,
  트래픽에 대한 차단 결정 로직 자체를 바꾸지 않는다(범위: 운영/설정).

## 5. 수용 기준 매핑
| 수용 기준 | 증거 |
|---|---|
| 재기동 없이 룰 1건 변경 적용(드라이런 diff) | `test_hot_reload_applies_single_rule_change_without_restart` |
| 잘못된 룰 fail-closed 거부 + 직전 유지 | `test_invalid_regex_fail_closed_keeps_previous`, `test_unknown_policy_action_rejected` |
| retain_raw 보존/삭제 + 키 회전 문서화 + 오설정 방지 1건 | `docs/SECURITY_RETAIN_RAW_KEYROTATION.md`, `test_misconfig_prevention_retain_raw_and_kek_rotation` |

---

## 관련 문서

| 문서 | 역할 |
|---|---|
| [`PRESETS.md`](PRESETS.md) | 핫리로드의 출발점: `nufi init <preset>` 으로 config 초기 구체화 |
| [`OPS_POLICY_AT_SCALE.md`](OPS_POLICY_AT_SCALE.md) | 단건 리로드 위에 다중 프로파일·버전관리·롤백 축 추가 |
| [`SECURITY_RETAIN_RAW_KEYROTATION.md`](SECURITY_RETAIN_RAW_KEYROTATION.md) | retain_raw 보존·TTL·삭제 + Vault 키 회전 운영 절차 |
| [`CLI.md`](CLI.md) | `nufi-egress policy` 전체 플래그·종료코드 레퍼런스 |
