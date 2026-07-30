# 정책 운영 자동화 — 다중 프로파일·묶기·버전/되돌리기·변경 감사 (v0.0.5)

> **스코프:** 운영/설정·문서·테스트. 신규 차단 규칙이나 게이트웨이 결정 로직 변경은 없다.
> **구현:** `enforcement/policy_ops.py` · **CLI:** `nufi-egress policy …` ·
> **데모:** [`scripts/demo_policy_ops.sh`](../scripts/demo_policy_ops.sh) ·
> **테스트:** `tests/test_cmp144_policy_ops.py`

[`OPS_RULE_RELOAD.md`](OPS_RULE_RELOAD.md)가 **단일 프로파일·단건** 무재기동
반영을 제공했다면, 본 기능은 그것을 **운영 규모**로 끌어올린다 — 한 게이트웨이에서
**여러 정책 프로파일을 동시 운영**하고, **경로/테넌트별로 다른 프로파일을 묶고**,
정책을 **버전 관리·되돌리기(rollback)** 하며, **누가·언제·무엇을 바꿨는지** 감사한다.

## 1. 개념

| 개념 | 무엇 | 어디에 |
|---|---|---|
| **프로파일(profile)** | 이름이 붙은 룰셋. 보통 `policy`(엔티티→동작)만 다르게 두고 나머지(patterns/confidential/edm)는 base config 를 공유 | `config/routing.yaml` 의 `policy_profiles` |
| **묶기(binding)** | 경로/테넌트 키 → 프로파일. 묶이지 않은 키는 기본 프로파일 | 선언: `policy_bindings` · 런타임: `config/policy_bindings.yaml`(오버레이) |
| **버전(version)** | 프로파일 정책 내용의 **불변 스냅샷**(v1, v2, …) + 활성 포인터 | `logs/policy_versions/<profile>/` |
| **변경 감사** | register/bind/snapshot/rollback 의 추가전용 **해시 체인** 로그 | `logs/policy_changes.jsonl` |

> **무재기동 불변식:** 되돌리기는 프로파일 가드를 **원자적으로 스왑**
> (`generation`++)할 뿐 프로세스를 재기동하지 않는다. 깨진 후보는 **fail-closed** 로
> 거부되어 직전(검증된) 룰셋·정책 파일이 그대로 유지된다. 무거운 NER 모델은 재로드하지
> 않는다.

## 2. routing.yaml 확장

```yaml
policy_default_profile: default     # 묶이지 않은 경로의 기본 프로파일
policy_profiles:
  # default 는 선언 생략 가능 — base config(config/policy.yaml)를 그대로 쓴다.
  strict:
    description: 한국어 PII·비밀·기밀을 최대 차단(strict-kr-pii 프리셋 구체화).
    policy: config/profiles/strict/policy.yaml   # policy 만 override, 나머지는 base 공유
policy_bindings: {}                 # 선언 기본 묶기(런타임 변경은 오버레이가 덮어씀)
```

- 프로파일 정책 파일은 [`PRESETS.md`](PRESETS.md) 의 `nufi init <preset> --out <dir>` 로
  손쉽게 구체화한다. 예: `nufi init strict-kr-pii --out config/profiles/strict`.
- 미선언 키(`patterns`/`confidential`/`edm`)는 base `config/*` 에서 자동 보충된다.

## 3. 운영 명령 (`nufi-egress policy …`)

| 명령 | 무엇 |
|---|---|
| `policy list` | 프로파일·묶기·활성 버전 요약 |
| `policy bind <route> <profile>` | 경로/테넌트 → 프로파일 묶기(런타임 오버레이에 영속) |
| `policy snapshot <profile> [--note N]` | 현재 정책을 새 불변 버전으로 적재(active 갱신) |
| `policy versions <profile>` | 버전 이력(작성자·시각·지문·메모·활성) |
| `policy rollback <profile> [--to N]` | 이전(또는 지정) 버전으로 **무재기동** 되돌리기 |
| `policy audit [--verify-chain]` | 변경 감사 로그(누가·언제·무엇을) + 해시 체인 검증 |
| `policy inspect <route> <text>` | 경로가 어느 프로파일로 묶이고 어떻게 결정되는지 확인 |

- 변경 주체(actor)는 `--actor`, 없으면 `$NUFI_ACTOR`, 그것도 없으면 현재 사용자.
- 상태 경로는 환경변수로 격리 가능: `POLICY_BINDINGS_OVERLAY`,
  `POLICY_VERSIONS_DIR`, `POLICY_CHANGE_LOG`.

## 4. 운영 절차 — 다중 프로파일 + 무재기동 되돌리기

```bash
# 1) 두 프로파일을 동시 운영 — 같은 입력이 경로별로 다르게 결정된다.
nufi-egress policy bind tenant-acme strict
nufi-egress policy inspect nufi-default "연락처 010-1234-5678"   # default → 통과(가명화)
nufi-egress policy inspect tenant-acme  "연락처 010-1234-5678"   # strict  → 차단(block)

# 2) 변경 전 현재 정책을 버전으로 박제(롤백 지점 확보)
nufi-egress policy snapshot strict --note "전화 차단 기준선"

#    …정책 수정(config/profiles/strict/policy.yaml) 후 새 버전 적재…
nufi-egress policy snapshot strict --note "전화 완화"

# 3) 문제 발견 → 직전 버전으로 무재기동 되돌리기(프로세스 재기동 없음)
nufi-egress policy rollback strict          # generation N→N+1, 라이브 즉시 반영
nufi-egress policy versions strict          # 활성 버전 확인

# 4) 누가·언제·무엇을 바꿨는지 + 변조 여부 검증
nufi-egress policy audit --verify-chain     # 체인 BROKEN 이면 exit 1(변조탐지)
```

> **라이브 게이트웨이 적용:** 위 절차는 운영 상태(버전·묶기·감사)를 파일로 관리한다.
> 실행 중 게이트웨이의 **무재기동 룰 적용** 메커니즘 자체는 [`OPS_RULE_RELOAD.md`](OPS_RULE_RELOAD.md)
> (`SIGHUP`/`ReloadableGuard`)와 동일하다 — 본 기능은 그 위에 프로파일·버전 축을 더한 것.

## 5. fail-closed 되돌리기

되돌리기 대상 버전의 정책이 깨져 있으면(알 수 없는 동작·정규식 오류 등) 후보 검증에서
거부되고, **라이브 정책 파일과 active 포인터가 원복**되며 가드는 직전 룰셋을 유지한다
(`generation` 불변). 거부는 `reload-reject` 로 변경 감사에 남는다. 운영 가용성보다 잘못된
정책의 라이브 반영을 막는 것을 우선한다.

## 6. 범위 밖 (Won't → v0.1.0)

멀티테넌시·권한관리(RBAC)·테넌트 격리는 본 MVP 범위 밖이다. 묶기는 라우팅 키 단위의
정책 선택일 뿐 테넌트 간 데이터/권한 격리를 제공하지 않는다.

---

## 관련 문서

| 문서 | 역할 |
|---|---|
| [`OPS_RULE_RELOAD.md`](OPS_RULE_RELOAD.md) | 단건 룰 무재기동 리로드 (본 기능의 기반 메커니즘) |
| [`PRESETS.md`](PRESETS.md) | 프로파일 정책 파일 구체화: `nufi init <preset> --out <dir>` |
| [`CLI.md`](CLI.md) | `nufi-egress policy list/bind/snapshot/rollback/audit/inspect` 전체 레퍼런스 |
| [`REPORTING.md`](REPORTING.md) | 정책 변경 감사 로그를 컴플라이언스 리포트로 연결 |
