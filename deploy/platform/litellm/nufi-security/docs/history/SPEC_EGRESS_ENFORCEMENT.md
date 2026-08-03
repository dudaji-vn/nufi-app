# SPEC — NuFi Egress Enforcement (우회 차단) · 트랙 B

> 상위 배경: 우회 차단(Enforcement) — S4 강화
> 상태: **설계 확정 → 빌드 완료 (nftables MVP)**

---

## 0. 한 줄 요약

현 `flow tap` 은 **관찰 전용**(연결 메타데이터만, TLS 본문·인라인 drop 불가)이다.
요구사항: "탐지에서 **차단(막기)**까지 강화."
→ 실제 egress **drop** 은 P0~P2 감사 범위를 넘는 **신규 enforcement 기능**.
본 스펙은 **무엇을·어떤 모델로·어떻게 안전하게** 차단할지를 확정하고, 빌드는 별도 단계로 다룬다.

설계 결론: **모델 (a) nftables egress 허용목록 = MVP 1순위.** (c) 투명 프록시 강제 = 프로덕션 하드닝, (b) eBPF 프로세스 단위 = 향후.

---

## 1. 문제 정의 — 무엇을 막는가

NuFi Egress-Audit 의 헤드라인 가치: **하이브리드 LLM 환경에서 사용자가 정규 게이트웨이 파이프라인을 우회(오설정·사람 실수·의도적 직결)해 public LLM(`api.anthropic.com`, `api.openai.com` 등)으로 보내는 패킷**을 잡는 것.

| 단계 | 능력 | 현 상태 |
|---|---|---|
| **탐지(P1)** | flow tap 이 public 목적지行 연결을 5-튜플·SNI·PID·바이트로 캡처, `src ≠ gateway → bypass=high` 판정 | ✅ 빌드 완료 (`capture/flow_tap.py`) |
| **알림(P2)** | 비동기 봇이 bypass flow 를 high-severity alert 로 준실시간 승격 | ✅ 빌드 완료 (`egress_audit/audit_bot.py`) |
| **차단 결정(트랙 A)** | alert → `enforce: action=BLOCK … mode=SIMULATED` 결정 한 줄 + 제어점 스텁 | ✅ 데모 범위 (SIMULATED 라벨) |
| **실제 차단(트랙 B)** | 우회 패킷을 커널/네트워크 레이어에서 **실제 drop** (`mode=ENFORCED`) | ⛔ **미구현 — 본 스펙 대상** |

**차단 대상의 정의(정밀):**
- **차단해야 할 것:** 게이트웨이가 아닌 출처(host/process)에서 **public egress_class 목적지**로 나가는 직결 트래픽.
- **절대 막으면 안 되는 것:** 게이트웨이(LiteLLM/egress-gateway) 자신이 정규로 내보내는 public egress. 이것이 막히면 하이브리드 라우팅 전체가 죽는다(=서비스 중단).
- 출처 식별·목적지 집합은 이미 `config/routing.yaml` 에 단일 출처로 존재 → enforcement 가 **재사용**한다(별도 정책 사본 금지).
  - `gateway.hosts` / `gateway.process_names` (기본: `127.0.0.1·::1·localhost`, `litellm·gateway·uvicorn·egress-gateway`)
  - public 목적지 = `egress_class: public` 백엔드의 `(host, port)` 집합 (`capture/targets.py` 파생)

---

## 2. 핵심 비대칭 — 왜 차단이 탐지보다 어려운가

탐지는 **수동(passive)**: 패킷을 복제해 관찰만 하면 되고, 틀려도(거짓음성) 손해는 "놓침"뿐이다.
차단은 **능동(active)·인라인**: 잘못 막으면 **정상 서비스가 죽는다(거짓양성 = 가용성 사고)**.

따라서 enforcement 설계의 1순위 제약은 **"게이트웨이 정규 트래픽을 절대 막지 않는다"** = 화이트리스트 우선·실패 모드 명시·점진 롤아웃. 본 스펙 전체가 이 제약을 중심으로 짜였다.

또한 **TLS 본문은 못 본다** (탐지와 동일 한계). 따라서 차단 판단은 **L3/L4 = 출처(src host/pid) + 목적지(dst host/port)** 로만 한다. "내용 기반 차단"(예: 이 요청에 PII 있으니 막아라)은 **본 스펙 범위 밖**이며, 그건 게이트웨이 인라인 정책(M3 가명화)이 담당한다 → §7 경계 참조.

---

## 3. 모델 비교 · 확정

세 모델을 **차단 정확도 · 우회 저항 · 운영 비용 · 온프렘 적합성 · 실패 안전성** 으로 비교한다.

### (a) nftables/iptables egress 허용목록 — **MVP 1순위 ✅**

호스트 방화벽 레이어에서 public 목적지(`dst host/port`)로 나가는 OUTPUT 트래픽을, **게이트웨이 출처(uid/cgroup)만 허용하고 나머지는 drop**.

```
# 의사규칙 (설계 표현 — 구현 아님)
table inet nufi_egress {
  set public_dst { type ipv4_addr . inet_service; elements = { <routing.yaml public (ip,port)> } }
  chain output {
    type filter hook output priority 0;
    # 1) 게이트웨이 프로세스(uid/cgroup)는 public 목적지 허용 (화이트리스트 우선)
    meta skuid <gateway_uid>           ip daddr . th dport @public_dst  accept
    socket cgroupv2 level 1 "<gw_cg>"  ip daddr . th dport @public_dst  accept
    # 2) 그 외 출처가 public 목적지로 = 우회 → drop + 로그
    ip daddr . th dport @public_dst    log prefix "nufi-egress-block " drop
  }
}
```

| 항목 | 평가 |
|---|---|
| 차단 정확도 | L3/L4 정확. 게이트웨이=uid/cgroup, 우회=그 외 → flow tap 의 bypass 판정과 **동일 기준** |
| 우회 저항 | 중. 같은 호스트 내 root 사용자는 규칙 우회 가능(루트 위협은 §6 범위 밖) |
| 운영 비용 | **낮음**. 리눅스 표준, 추가 데몬 없음. 규칙은 routing.yaml 에서 생성 |
| 온프렘 적합성 | **높음**. 에어갭/온프렘 리눅스 호스트에 그대로 적용 |
| 실패 안전성 | 규칙 로드 실패 시 fail-open/closed 토글(§5). 게이트웨이 화이트리스트가 1순위 규칙 |
| 결정 | **MVP 1순위.** public 직결 drop·게이트웨이만 허용을 가장 적은 비용으로 달성 |

**선정 이유(value/effort 렌즈):** 가장 높은 가치(실제 drop)를 가장 낮은 노력(표준 방화벽, 신규 데몬 0)으로 — flow tap 이 이미 쓰는 routing.yaml 출처/목적지 모델을 그대로 재사용하므로 정책 중복도 없다.

### (c) 투명 아웃바운드 프록시 강제 — 프로덕션 하드닝(2순위)

게이트웨이 외 모든 egress(:443)를 투명 프록시로 강제 redirect. 프록시는 SNI 화이트리스트(게이트웨이 목적지만)로 비-게이트웨이 직결을 거절. 선택적으로 SNI 기반 정책·감사 일원화.

| 항목 | 평가 |
|---|---|
| 차단 정확도 | 높음(SNI 단). 비-허용 SNI 전부 차단 가능 |
| 우회 저항 | 높음. egress 단일 통로화(choke point) → DNS-over-HTTPS·IP 직결까지 통제 가능 |
| 운영 비용 | **높음**. 프록시 컴포넌트 운영·HA·인증서·CA 신뢰 체인 |
| 온프렘 적합성 | 중. 경계 네트워크 제어가 가능한 고객사에 적합 |
| 실패 안전성 | 프록시가 SPOF → HA 필요. 프록시 다운 시 fail-closed 가 곧 전체 egress 중단 |
| 결정 | **2순위(프로덕션 하드닝).** "egress 단일 통로" 가 필요한 성숙 배치에서 (a) 위에 추가 |

### (b) eBPF 프로세스 단위 — 향후(3순위)

`cgroup/connect4`·`cgroup/skb` eBPF 프로그램으로 **프로세스(=PID/cgroup) 단위** egress 정책. flow tap 의 PID 단위 탐지와 가장 가까운 입도.

| 항목 | 평가 |
|---|---|
| 차단 정확도 | **최고**. 프로세스 입도, 컨테이너/네임스페이스 인지 |
| 우회 저항 | 높음. 커널 레벨, 프로세스 위장에 강함 |
| 운영 비용 | 높음. 커널 버전 의존(BTF/CO-RE), eBPF 빌드·검증 체인, 디버깅 난이도 |
| 온프렘 적합성 | 중~낮. 고객 커널 다양성이 리스크 |
| 결정 | **3순위(향후).** 컨테이너 밀집·프로세스 입도가 요구될 때. MVP 과잉 |

### 확정 로드맵

```
MVP        →  (a) nftables egress 허용목록      ← 본 스펙의 빌드 인계 대상
하드닝     →  (c) 투명 프록시 (a 위에 choke point 추가)
향후       →  (b) eBPF 프로세스 단위 (컨테이너 밀집 시)
```

---

## 4. enforcement 제어점 — P1 탐지·P2 알림과의 연결

기존 감사 파이프라인은 **탐지→알림** 까지였다. enforcement 는 그 뒤에 **결정→적용** 두 단계를 잇는다. **핵심: 정책(무엇이 우회인가)은 P1/P2 와 동일 출처(routing.yaml)를 재사용** — enforcement 는 새 판정 로직을 만들지 않고, 이미 내려진 bypass 판정을 *집행*만 한다.

```
[P1 flow tap]   public 목적지 연결 캡처 + bypass 판정(src≠gateway)
      │  flow record (severity=high, bypass=true)
      ▼
[P2 audit bot]  bypass flow → high-severity alert (준실시간)
      │  alert
      ▼
[enforcement decision]   action=BLOCK 결정 (dst/src/이유)
      │           ├─ mode=SIMULATED → 로그만 (트랙 A · 데모)
      │           └─ mode=ENFORCED  → 규칙 적용 (트랙 B · 본 스펙)
      ▼
[enforcement applier]    routing.yaml → nftables 규칙 생성/리로드
      │  (게이트웨이 화이트리스트 + public_dst drop set)
      ▼
[커널 OUTPUT hook]       비-게이트웨이 → public 목적지 = drop + 로그
                         drop 로그 → P1/P2 로 재유입(피드백 루프, §4.3)
```

### 4.1 두 가지 적용 패러다임 — 사전(preventive) vs 사후(reactive)

enforcement 적용에는 두 모드가 있고 **둘 다 같은 routing.yaml 출처**를 쓴다:

1. **정적·사전 차단 (권장 기본):** 시작 시 routing.yaml 의 public 목적지 + 게이트웨이 화이트리스트로 nftables 규칙을 **선적용**. 우회 트래픽은 *처음부터* drop 된다 → P2 alert 를 기다리지 않음. 가장 견고(탐지 누락에도 막힘).
2. **동적·사후 차단 (보강):** 정적 규칙에 안 잡힌 신종 우회(예: routing.yaml 에 아직 없는 신규 public 호스트)를 P2 alert 가 잡으면, applier 가 해당 dst 를 set 에 **추가**. = 탐지 피드백으로 정책 자가확장.

> 설계 결정: **정적 사전 차단을 1차 방어**로, 동적 사후 차단을 **2차 보강**으로 둔다. 사후 단독은 "첫 패킷은 이미 나간 뒤" 문제(준실시간이라도 누수)가 있으므로 단독 채택 금지.

### 4.2 결정 페이로드 (트랙 A SIMULATED 와 동일 스키마 — 승격만)

트랙 A 가 이미 출력하는 결정 한 줄을 트랙 B 가 그대로 승계하고 `mode` 만 바꾼다. **스키마를 새로 만들지 않는다.**

```
enforce: action=BLOCK dst=api.anthropic.com:443 src=<host/pid> reason=gateway_bypass
         policy_src=routing.yaml mode={SIMULATED|ENFORCED} rule_id=<nft handle> ts=<iso>
```
- `mode=SIMULATED`: 트랙 A(데모) — 로그만, 규칙 미적용.
- `mode=ENFORCED`: 트랙 B(본 스펙) — applier 가 규칙 적용, `rule_id` 에 실제 nft 핸들 기록.

### 4.3 피드백 루프 (drop → 감사 재유입)

커널 drop 로그(`nufi-egress-block ` prefix)는 다시 P1/P2 로 흘려 **"막힌 시도"도 감사 증적**으로 남긴다. = "탐지했는데 못 막음"(현재)에서 "막고+막은 사실을 기록"(목표)으로. 대시보드/리포트에 `blocked_attempts` 카운터 추가(빌드 명세 §8 후속).

---

## 5. 실패 모드 · 권한 · 예외

### 5.1 실패 모드 (fail-open vs fail-closed) — **운영자 토글, 기본 = open**

| 모드 | 의미 | 위험 | 권장 |
|---|---|---|---|
| **fail-open** | enforcement 로드/적용 실패 시 **차단 규칙 미적용**(=관찰만으로 폴백) | 우회 잠시 통과(탐지는 살아있음) | **기본값.** 가용성 우선·점진 도입 |
| **fail-closed** | 실패 시 **public egress 전면 차단** | 게이트웨이 정규 트래픽까지 중단 가능 | 규제·고민감 고객 명시 선택 시 |

> 설계 결정: **기본 fail-open.** 이유 — enforcement 는 신규·인라인이라 초기 신뢰가 낮고, 오차단=서비스 사고. 탐지(P1/P2)는 enforcement 와 독립적으로 항상 동작하므로 fail-open 이어도 "보이지 않는" 구간은 없다. fail-closed 는 `config/policy.yaml` 의 `enforcement.fail_mode: closed` 로 옵트인.

**부분 실패 처리:** 규칙 셋 중 일부만 로드되면 **전부 롤백**(원자적 적용). 화이트리스트 규칙이 안 들어간 채 drop 규칙만 들어가는 "게이트웨이 자살" 순서를 금지 — **화이트리스트 규칙을 항상 먼저 commit**.

### 5.2 권한

- nftables OUTPUT 훅 조작 = **`CAP_NET_ADMIN`** (또는 root) 필요. applier 만 이 권한을 갖고, 게이트웨이/봇 본체는 비특권 유지(최소권한).
- 온프렘 배치: applier 를 별도 systemd 유닛(또는 사이드카)으로 분리, `AmbientCapabilities=CAP_NET_ADMIN` 만 부여. cgroupv2 매칭 사용 시 게이트웨이 프로세스의 cgroup 경로를 유닛에서 고정.
- 컨테이너 배치: applier 컨테이너에 `--cap-add=NET_ADMIN`, host netns 공유 시 영향 범위를 문서화(§6 리스크).

### 5.3 예외 (게이트웨이 화이트리스트) — **1순위 규칙·반드시 선적용**

- 화이트리스트 = `routing.yaml` 의 `gateway.hosts` + `gateway.process_names`(→ uid/cgroup 으로 해석).
- 운영 예외(임시 허용 IP·점검용 호스트)는 `policy.yaml` 의 `enforcement.allow_extra[]` 로 명시, **변경 사유 기록** 후 추가(감사 가능).
- 화이트리스트 변경은 routing.yaml/policy.yaml 단일 출처에서만 — 규칙 파일 직접 수정 금지(드리프트 방지).

---

## 6. 리스크 (likelihood · impact · 완화)

| # | 리스크 | L | I | 완화 |
|---|---|---|---|---|
| R1 | 게이트웨이 정규 egress 오차단 = 서비스 중단 | 중 | **높음** | 화이트리스트 선적용·원자적 롤백·기본 fail-open·SIMULATED→ENFORCED 단계 롤아웃 |
| R2 | 같은 호스트 root 사용자가 nft 규칙 우회 | 중 | 중 | (a)의 알려진 한계로 명시. 루트 위협은 (c)/(b)·호스트 하드닝 영역 → 범위 밖 |
| R3 | IP 직결(SNI 우회)·DoH 로 호스트 변경 | 중 | 중 | (a)는 routing.yaml IP/host 집합 기반. 동적 set 보강(§4.1) + (c) 프록시로 SNI 통로화(하드닝) |
| R4 | routing.yaml public 호스트 누락 → 신규 목적지 미차단 | 중 | 중 | P2 동적 사후 차단(§4.1)으로 set 자가확장 + 누락 alert |
| R5 | 커널/배포판 다양성으로 nft 규칙 비호환 | 낮 | 중 | nft(레거시 iptables-nft 폴백) 호환 매트릭스를 빌드 수용 기준에 포함(§8) |
| R6 | fail-closed 오설정 → 점검 중 전체 egress 마비 | 낮 | 높 | 기본 open·옵트인만 closed·closed 선택 시 헬스체크/킬스위치 의무화 |

---

## 7. 범위 경계 (무엇을 안 하는가)

- **내용 기반 차단 아님.** "이 요청에 PII 가 있으니 막아라"는 게이트웨이 인라인 정책(M3 가역 가명화, `docs/design/gateway/m3-reversible-pseudonymization-spec.md`) 담당. 본 enforcement 는 **출처·목적지(L3/L4) 기반**으로 "정규 게이트웨이를 안 거친 직결"만 막는다.
- **TLS 복호화 아님.** 본문 안 봄(탐지와 동일).
- **이그레스 DLP 전수 검사 아님.** 그건 게이트웨이 통과 트래픽 대상(M2~M4). enforcement 는 "게이트웨이를 *통과하게 강제*"하는 게이트키퍼.
- 즉 **enforcement = 우회 경로를 닫아 모든 egress 가 게이트웨이를 통과하도록 강제** → 그 다음 내용 정책은 기존 게이트웨이가 처리. 두 레이어는 보완 관계.

---

## 8. 빌드 작업 명세 (구현 완료)

> 본 스펙은 빌드 완료된 상태다.

### 8.1 빌드 대상 (MVP = 모델 (a))

1. **`enforcement/rule_builder`** — routing.yaml/policy.yaml → nftables 규칙 셋 생성(게이트웨이 화이트리스트 우선 + public_dst drop set). 정책 사본 금지, 기존 `capture/targets.py` 의 목적지 파생 재사용.
2. **`enforcement/applier`** — 규칙 원자적 commit/rollback, fail_mode(open|closed) 처리, `CAP_NET_ADMIN` 분리 유닛. 시작 시 정적 사전 적용 + (옵션) P2 alert 구독 동적 보강.
3. **결정 로그 승격** — 트랙 A SIMULATED 결정 라인의 `mode=ENFORCED` 경로 + `rule_id`(nft 핸들) 기록.
4. **drop 피드백** — 커널 drop 로그 → P1/P2 재유입, `blocked_attempts` 카운터.
5. **킬스위치** — `nufi-egress disable` 즉시 전 규칙 제거(롤백) CLI.

### 8.2 바이너리/산출물 수용 기준 (binary acceptance criteria)

| # | 기준 | 검증 |
|---|---|---|
| A1 | 게이트웨이(uid/cgroup) 출처의 public egress 는 **항상 통과** | 게이트웨이로 public 호출 → 성공(드롭 0) |
| A2 | 비-게이트웨이 출처의 public 직결은 **drop** | 별도 프로세스로 `api.anthropic.com:443` 직결 → 연결 실패 + drop 로그 1건 |
| A3 | drop 시도가 **감사 증적**으로 남음 | `blocked_attempts` 증가 + P1/P2 에 record |
| A4 | fail-open: applier 강제 종료 후 게이트웨이/우회 모두 통과(관찰만) | 유닛 kill 후 트래픽 통과 확인 |
| A5 | fail-closed(옵트인): applier 실패 시 public egress 전면 차단 | policy fail_mode=closed 설정 후 동일 시나리오 |
| A6 | 규칙 원자성: 부분 실패 시 전체 롤백, 화이트리스트 선commit | rule_builder 에 의도적 오류 주입 → 게이트웨이 egress 무중단 |
| A7 | 정책 단일 출처: routing.yaml 변경만으로 규칙 갱신, 수동 nft 편집 불요 | public 백엔드 추가 → 리로드 후 set 반영 |
| A8 | 킬스위치: disable 후 nft 규칙 0, 트래픽 전면 통과 | `nufi-egress disable` → `nft list` 비어있음 |
| A9 | 호환: nft 및 iptables-nft 폴백 환경에서 동작 | 호환 매트릭스 환경 2종 PASS |

### 8.3 검증 절차 (재현 가능·root 필요 표기)

- **유닛/CI(root 불요):** rule_builder 가 생성한 규칙 셋의 **골든 텍스트 비교**(routing.yaml 픽스처 → 기대 nft 규칙). SIMULATED 결정 로그 스키마 일치.
- **통합(root/CAP_NET_ADMIN 필요·격리 netns):** A1~A9 를 네트워크 네임스페이스/테스트 호스트에서 실집행. 더미 public 목적지(테스트 IP)로 실제 drop 확인.
- **데모 승격:** §9.

---

## 9. S4 데모 ENFORCED 통합 (트랙 A → 트랙 B 승격)

트랙 A S4 데모는 이미 **탐지 → high-sev alert → `action=BLOCK mode=SIMULATED` 결정 + 차단 제어점 스텁**을 보인다("빌드된 것만 시연" 원칙).

트랙 B 빌드 완료 후 후속 통합:

1. **동일 시나리오·라벨만 전환:** S4 스크립트에 `--enforce` 플래그 추가. 없으면 기존 `mode=SIMULATED`(root 불요·CI 안전), 있으면 `mode=ENFORCED` — applier 가 격리 netns 에서 실제 drop.
2. **시연 흐름(ENFORCED):** 비-게이트웨이 프로세스가 `api.anthropic.com` 직결 시도 → **연결 실패(실제 drop)** + `enforce: action=BLOCK … mode=ENFORCED rule_id=<h>` + `blocked_attempts` 증가 + 게이트웨이 정규 호출은 **정상 통과**(A1 동시 시연).
3. **정직성 원칙 유지:** ENFORCED 데모는 root/격리 환경에서만. 기본 데모 경로는 SIMULATED 유지(에어갭/CI 재현성). 두 모드를 한 화면에서 대비해 "탐지(현재)→실제 차단(신규)"의 가치를 명확히.

---

## 10. 진행 순서 (확정)

```
① 트랙 A 데모 완결          ← 탐지 + SIMULATED 차단결정
② 본 스펙 확정              ← 설계
③ 빌드 (done)              ← 구현
④ ENFORCED 모드 S4 데모 통합 (§9)
```

- **본 문서 = 설계.** 구현(빌드)은 완료된 상태다.
- **차별점:** NuFi Egress-Audit 의 가치(한국어 PII 갭 + 파이프라인 우회 통제) → enforcement 는 "탐지만 vs 실제 차단"의 차이를 만든다.

---

## 부록 A — 설계 렌즈 적용 요약

- **value/effort:** (a) nftables = 최고 가치/최저 노력 → MVP. 정책은 routing.yaml 재사용으로 중복 0.
- **risk visibility:** R1(오차단)을 최상위로, 화이트리스트 선적용·fail-open·단계 롤아웃으로 완화.
- **MoSCoW:** Must=(a) 정적 사전 차단·화이트리스트·킬스위치·fail-open. Should=동적 사후 보강·drop 피드백. Could=(c) 프록시. Want=(b) eBPF.
- **milestone hygiene:** §8.2 A1~A9 = 빌드 done 의 이진 기준.
- **delivery cadence:** SIMULATED(트랙 A) 선출시 → ENFORCED(트랙 B) 후속 = 증분 전달.
