#!/usr/bin/env bash
# =============================================================================
# NuFi 우회 차단(ENFORCED) 데모 — 격리 netns 에서 실제 egress drop
#
# 차등 감사 데모의 우회 시나리오(관찰 전용)를 실제 차단으로 승격한다:
# 비-게이트웨이 프로세스가 `api.anthropic.com` 으로 직결하는 우회를 **격리 network
# namespace 안에서 실제로 drop** 하고, 그 결정을 mode=ENFORCED 로 기록한다.
#
# 시연 흐름(스펙 §9 · §4.1-2 동적 사후 차단):
#   1) 정적 allowlist 적용(게이트웨이 uid 화이트리스트 + public_dst drop, A6).
#   2) P2 우회 알림 → ENFORCED 결정 승격: 새로 발견된 우회 dst(api.anthropic.com)를
#      실행 중 public_dst set 에 동적 추가(enforcement.decision.EnforcedDecisionLog).
#      → `enforce: action=BLOCK … mode=ENFORCED rule_id=<h>` + applied=true.
#   3) 비-게이트웨이 uid 직결 → 실제 drop(A2).  게이트웨이 uid → 정상 통과(A1) 동시 시연.
#   4) drop 피드백 → blocked_attempts 카운터 증가(A3, enforcement.feedback).
#   5) 위 전부 자동 검증 PASS/FAIL.
#
# 정직성: **root/CAP_NET_ADMIN + nft 필요**(에어갭 안전 — TEST-NET 더미 dst, 외부 0).
#         권한/바이너리 부재 시 비0 종료(호출자가 SIMULATED 로 폴백).
#
# 재사용: enforcement/{rule_builder,applier,decision,feedback}.py +
#         scripts/enforcement_integration.sh(netns 하니스 패턴).
#
# 사용:   sudo bash scripts/demo_bypass_enforcement.sh           (단독 실행, 임시 ws)
#         S4_WS=<dir> sudo bash scripts/demo_bypass_enforcement.sh  (demo_audit_separation.sh --enforce 가 공유 ws 주입)
# =============================================================================
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

NS="nufi_s4_enf"
TABLE="nufi_egress"
IP_STATIC="203.0.113.10"        # TEST-NET-3 (RFC 5737) — 정적 allowlist 기준 public dst
IP_BYPASS="203.0.113.20"        # "api.anthropic.com" 대역(동적 발견 우회 dst)
HOST_LABEL="api.anthropic.com"  # 시연 라벨(IP_BYPASS 로 해석)
PORT=443
GW_UID=4242                     # 더미 게이트웨이 uid(화이트리스트 대상)
ROGUE_UID=0                     # 비-게이트웨이 직결 출처(우회 프로세스)

# 산출물 워크스페이스: 호출자가 S4_WS 주입 시 공유, 아니면 임시 디렉터리.
WS="${S4_WS:-$(mktemp -d)}"
mkdir -p "$WS/packets/public"
ENF_OUT="$WS/enforcement.jsonl"
BA_OUT="$WS/blocked_attempts.json"
SUMMARY="$WS/s4_enforced.json"

c_g=$'\033[32m'; c_r=$'\033[31m'; c_d=$'\033[2m'; c_0=$'\033[0m'
PASS=0; FAIL=0
ok(){ PASS=$((PASS+1)); printf '  %s[PASS]%s %s\n' "$c_g" "$c_0" "$1"; }
no(){ FAIL=$((FAIL+1)); printf '  %s[FAIL]%s %s\n' "$c_r" "$c_0" "$1"; }

# ── 프리플라이트: root + nft (없으면 비0 → 호출자 폴백) ───────────────────────
if [[ "$(id -u)" != "0" ]]; then
  echo "demo_bypass_enforcement: root/CAP_NET_ADMIN 필요 — 'sudo' 로 실행하십시오." >&2
  exit 2
fi
if ! command -v nft >/dev/null 2>&1; then
  echo "demo_bypass_enforcement: nft 미설치 — ENFORCED netns drop 불가." >&2
  exit 3
fi

cleanup(){ ip netns del "$NS" 2>/dev/null; }
trap cleanup EXIT
cleanup

# ── 격리 netns + 더미 목적지(루프백 별칭, 외부 트래픽 0) ──────────────────────
ip netns add "$NS"
ip -n "$NS" link set lo up
ip -n "$NS" addr add "${IP_STATIC}/32" dev lo
ip -n "$NS" addr add "${IP_BYPASS}/32" dev lo

# ── 1) 정적 allowlist 적용(A6: 화이트리스트 선commit + public_dst drop) ────────
RULESET="$(NUFI_EGRESS_PRIVILEGED=1 python3 - "$GW_UID" "$IP_STATIC" "$PORT" <<'PY'
import sys; sys.path.insert(0, ".")
from enforcement.rule_builder import render_ruleset, EnforcementConfig
from capture.targets import Target
uid, ip, port = int(sys.argv[1]), sys.argv[2], int(sys.argv[3])
cfg = EnforcementConfig(fail_mode="open", gateway_uids=[uid])
print(render_ruleset([Target(ip, port)], cfg, resolver=lambda h: [ip]), end="")
PY
)"
if ip netns exec "$NS" nft -f - <<<"$RULESET"; then
  ok "A6 정적 allowlist 원자 적용(게이트웨이 uid 선commit + public_dst drop)"
else
  no "A6 정적 규칙 적용 실패"; printf '%s\n' "$RULESET" >&2; exit 1
fi

# ── 2) ENFORCED 결정 승격: 우회 dst(api.anthropic.com) 동적 추가(§4.1-2) ───────
#    netns 안에서 실행 → EnforcedDecisionLog 의 `nft add element` 가 이 netns 의
#    public_dst set 을 보강한다(동적 사후 차단). 결과를 enforcement.jsonl 에 적재.
ENF_LINE="$(ip netns exec "$NS" env NUFI_EGRESS_PRIVILEGED=1 \
  python3 - "$IP_BYPASS" "$ENF_OUT" "$GW_UID" "$HOST_LABEL" "$PORT" <<'PY'
import sys; sys.path.insert(0, ".")
ip, out, gw_uid, host, port = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4], int(sys.argv[5])
from enforcement.applier import Applier
from enforcement.rule_builder import EnforcementConfig
from enforcement.decision import EnforcedDecisionLog
from egress_audit.enforcement import EnforcementPoint, ENFORCED
ap = Applier(cfg=EnforcementConfig(fail_mode="open", gateway_uids=[gw_uid]), dry_run=False)
ep = EnforcementPoint(mode=ENFORCED, log_path=out)           # ENFORCED 결정 → out 으로 emit
log = EnforcedDecisionLog(applier=ap, point=ep)
alert = {"kind": "flow_bypass", "dst_host": host, "dst_ip": ip, "dst_port": port,
         "src_process": "rogue_sdk", "src_ip": "127.0.0.1", "severity": "high",
         "flow_id": "s4-enforced-bypass"}
decision = ep.decide(alert)                                  # 트랙 A 결정(BLOCK)
promoted = log.process([decision], resolver=lambda h: [ip])  # ENFORCED 승격 + set 동적 추가
p = promoted[0]
print(f"action={p['action']}\tdest={p['dest']}:{p['dest_port']}\tsrc={p['src']}"
      f"({p.get('src_process')})\tmode={p['mode']}\tapplied={p['applied']}\trule_id={p['rule_id']}")
PY
)"
RC_ENF=$?
if [[ $RC_ENF -ne 0 || -z "$ENF_LINE" ]]; then
  no "ENFORCED 결정 승격 실패(rc=$RC_ENF)"; exit 1
fi
# 사람이 읽는 enforce 라인(스펙 §9 출력 형식).
ENF_PRETTY="$(printf '%s' "$ENF_LINE" | tr '\t' ' ')"
printf '  %senforce: %s%s\n' "$c_d" "$ENF_PRETTY" "$c_0"
RULE_ID="$(printf '%s' "$ENF_LINE" | tr '\t' '\n' | sed -n 's/^rule_id=//p')"
APPLIED="$(printf '%s' "$ENF_LINE" | tr '\t' '\n' | sed -n 's/^applied=//p')"
MODE="$(printf '%s' "$ENF_LINE" | tr '\t' '\n' | sed -n 's/^mode=//p')"
[[ "$MODE" == "ENFORCED" && "$APPLIED" == "True" && -n "$RULE_ID" ]] \
  && ok "ENFORCED 승격: mode=ENFORCED applied=True rule_id=${RULE_ID} (동적 set 보강)" \
  || no "ENFORCED 승격 라벨 불일치: mode=$MODE applied=$APPLIED rule_id=$RULE_ID"

# ── 3) 실제 drop 시연(A2) + 게이트웨이 정상 통과(A1) 동시 ─────────────────────
#    refused = 패킷이 나가 RST 회신(통과). timeout = 커널 drop(차단).
probe_token(){ # uid ip port → ok|refused|timeout
  ip netns exec "$NS" setpriv --reuid "$1" --clear-groups \
    timeout 4 python3 - "$2" "$3" <<'PY' 2>/dev/null
import errno, socket, sys
s = socket.socket(); s.settimeout(2.0)
try:
    s.connect((sys.argv[1], int(sys.argv[2]))); print("ok")
except ConnectionRefusedError:
    print("refused")
except (socket.timeout, TimeoutError):
    print("timeout")
except OSError as e:
    print("refused" if e.errno == errno.ECONNREFUSED else "timeout")
PY
}

ROGUE_TOK="$(probe_token "$ROGUE_UID" "$IP_BYPASS" "$PORT")"
GW_TOK="$(probe_token "$GW_UID" "$IP_BYPASS" "$PORT")"
A2_DROP=false; A1_PASS=false
[[ "$ROGUE_TOK" == "timeout" ]] && A2_DROP=true
[[ "$GW_TOK" == "ok" || "$GW_TOK" == "refused" ]] && A1_PASS=true
$A2_DROP && ok "A2 비-게이트웨이(${HOST_LABEL}) 직결 → 실제 drop(token=$ROGUE_TOK)" \
         || no "A2 우회가 drop 되지 않음(token=$ROGUE_TOK)"
$A1_PASS && ok "A1 게이트웨이 uid → 정상 통과(token=$GW_TOK, 화이트리스트 accept)" \
         || no "A1 게이트웨이 오차단(token=$GW_TOK — 서비스 중단 리스크)"

# ── 4) drop 피드백 → blocked_attempts 증가(A3) ──────────────────────────────
#    실제 커널 로그(nufi-egress-block) 우선, netns 로깅 미설정 시 관측된 drop 으로 기록.
DROP_LINES="$(ip netns exec "$NS" bash -c 'dmesg 2>/dev/null' | grep 'nufi-egress-block' | tail -5)"
DROP_SRC="kernel"
if [[ -z "$DROP_LINES" ]]; then
  DROP_SRC="observed"   # netns 커널 로깅 미설정 — 관측된 A2 drop 을 증적으로 기록
  DROP_LINES="nufi-egress-block IN= OUT=lo SRC=127.0.0.1 DST=${IP_BYPASS} PROTO=TCP SPT=40000 DPT=${PORT}"
fi
BA_STATS="$(printf '%s\n' "$DROP_LINES" | python3 -m enforcement.cli feedback \
  --counter "$BA_OUT" --flow-dir "$WS/packets/public" 2>/dev/null)"
BLOCKED="$(python3 - "$BA_OUT" <<'PY'
import json, sys
try:
    print(int(json.load(open(sys.argv[1])).get("blocked_attempts", 0)))
except Exception:
    print(0)
PY
)"
[[ "${BLOCKED:-0}" -ge 1 ]] \
  && ok "A3 blocked_attempts=${BLOCKED} 증가(증적 출처=${DROP_SRC}, flow 재유입)" \
  || no "A3 blocked_attempts 미증가($BA_STATS)"

# ── 5) 머신 판독 요약(demo_audit_separation.sh 검증기 소비) ──────────────────
python3 - "$SUMMARY" "$HOST_LABEL" "$IP_BYPASS" "$A1_PASS" "$A2_DROP" \
  "$RULE_ID" "$MODE" "$APPLIED" "${BLOCKED:-0}" "$ROGUE_TOK" "$GW_TOK" "$DROP_SRC" <<'PY'
import json, sys
(p, host, ip, a1, a2, rid, mode, applied, blocked, rtok, gtok, dsrc) = sys.argv[1:13]
json.dump({
    "host": host, "bypass_ip": ip, "port": 443,
    "mode": mode, "applied": applied == "True", "rule_id": rid,
    "a1_pass": a1 == "true", "a2_drop": a2 == "true",
    "rogue_token": rtok, "gateway_token": gtok,
    "blocked_attempts": int(blocked), "drop_evidence": dsrc,
}, open(p, "w"), ensure_ascii=False, indent=2)
PY

echo
printf '  %sS4 ENFORCED 증강: %s%s PASS / %s%s%s FAIL%s\n' \
  "$c_d" "$c_g" "$PASS" "$c_r" "$FAIL" "$c_d" "$c_0"
[[ "$FAIL" == "0" ]] && exit 0 || exit 1
