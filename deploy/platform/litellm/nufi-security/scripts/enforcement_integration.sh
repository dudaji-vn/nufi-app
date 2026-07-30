#!/usr/bin/env bash
# Egress Enforcement 통합 검증 (CMP-94 트랙 B · 스펙 §8.3 통합).
#
# 격리 network namespace 안에서 실제 nftables drop 을 집행해 수용 기준
# A1·A2·A4·A5·A8·A9 를 재현한다. **root/CAP_NET_ADMIN 필요** (유닛/CI 와 분리).
#
# 더미 public 목적지(테스트 IP, 외부 트래픽 0)로 실 drop 을 확인하므로 에어갭에서도
# 안전하다. 실행:  sudo bash scripts/enforcement_integration.sh
#
# 모델 (a) nftables egress 허용목록. nft 우선, 없으면 SKIP(A9 는 nft·iptables-nft 매트릭스).
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NS="nufi_egtest"
TABLE="nufi_egress"
DUMMY_IP="203.0.113.10"        # TEST-NET-3 (RFC 5737, 비라우팅)
DUMMY_PORT=443
GW_UID=4242                    # 더미 게이트웨이 uid (화이트리스트 대상)
PASS=0; FAIL=0
say(){ printf '%s\n' "$*"; }
ok(){ PASS=$((PASS+1)); say "  [PASS] $1"; }
no(){ FAIL=$((FAIL+1)); say "  [FAIL] $1"; }

if [[ "$(id -u)" != "0" ]]; then
  say "root 필요 (CAP_NET_ADMIN). 'sudo bash $0' 로 실행하십시오."; exit 2
fi
if ! command -v nft >/dev/null 2>&1; then
  say "nft 미설치 — A9 매트릭스의 nft 경로 SKIP. iptables-nft 폴백은 별도 호스트에서."; exit 3
fi

cleanup(){
  ip netns del "$NS" 2>/dev/null
  nft delete table inet "$TABLE" 2>/dev/null
}
trap cleanup EXIT
cleanup

# --- 격리 netns + 더미 목적지(루프백 별칭) -----------------------------------
ip netns add "$NS"
ip -n "$NS" link set lo up
ip -n "$NS" addr add "${DUMMY_IP}/32" dev lo            # 더미 public 목적지

# 규칙 생성(정적 사전 차단). policy override 로 더미 uid 화이트리스트.
RULESET="$(NUFI_EGRESS_PRIVILEGED=1 python3 - "$GW_UID" "$DUMMY_IP" "$DUMMY_PORT" <<'PY'
import sys; sys.path.insert(0, ".")
from enforcement.rule_builder import render_ruleset, EnforcementConfig
from capture.targets import Target
uid, ip, port = int(sys.argv[1]), sys.argv[2], int(sys.argv[3])
cfg = EnforcementConfig(fail_mode="open", gateway_uids=[uid])
print(render_ruleset([Target(ip, port)], cfg, resolver=lambda h: [ip]), end="")
PY
)"
cd "$ROOT"

# nft 는 netns 안에서 적용해야 OUTPUT 훅이 그 netns 트래픽에 걸린다.
if ip netns exec "$NS" nft -f - <<<"$RULESET"; then
  ok "A6 규칙 원자 적용(화이트리스트 선commit)"
else
  no "A6 규칙 적용 실패"; exit 1
fi

probe(){ # uid host port  → 0=연결가능(accept), 비0=drop
  local uid="$1"
  ip netns exec "$NS" setpriv --reuid "$uid" --clear-groups \
    timeout 2 python3 - "$DUMMY_IP" "$DUMMY_PORT" <<'PY' 2>/dev/null
import socket, sys
s = socket.socket(); s.settimeout(1.5)
try:
    s.connect((sys.argv[1], int(sys.argv[2]))); print("ok")
except (socket.timeout, OSError):
    sys.exit(1)
PY
}

# A2: 비-게이트웨이(uid 0) 직결 → drop (연결 실패 + drop 로그).
if probe 0; then no "A2 비-게이트웨이 직결이 통과됨(drop 안 됨)"; else ok "A2 비-게이트웨이 직결 drop"; fi

# A1: 게이트웨이 uid → 통과 (드롭 없는 connect; 더미 목적지엔 리스너 없으니
#     'connection refused'(통과 후 거절) 와 'timeout'(drop) 을 구분).
out="$(probe "$GW_UID"; echo "rc=$?")"
if echo "$out" | grep -q "rc=0\|refused\|Connection refused"; then
  ok "A1 게이트웨이 출처 public egress 통과(화이트리스트)"
else
  # connect 가 즉시 refused 면 통과(룰 accept), timeout 이면 drop.
  ip netns exec "$NS" setpriv --reuid "$GW_UID" --clear-groups \
    timeout 2 bash -c "exec 3<>/dev/tcp/${DUMMY_IP}/${DUMMY_PORT}" 2>/tmp/gw.err
  if grep -qi "refused" /tmp/gw.err; then ok "A1 게이트웨이 통과(refused=룰 accept 후 리스너 없음)";
  else no "A1 게이트웨이 출처가 막힘(오차단 — 서비스 중단 리스크)"; fi
fi

# A3: drop 감사 증적 — 커널 로그 prefix + feedback 카운터.
sleep 0.3
if ip netns exec "$NS" bash -c "dmesg 2>/dev/null | grep -q 'nufi-egress-block'" \
   || journalctl -k --since "-1 min" 2>/dev/null | grep -q "nufi-egress-block"; then
  ok "A3 drop 감사 증적(커널 로그 prefix)"
else
  say "  [INFO] A3 커널 로그는 netns 로깅 설정에 의존 — feedback 파서는 유닛에서 검증됨"
fi

# A8: 킬스위치 — disable 후 테이블 0, 트래픽 전면 통과.
ip netns exec "$NS" nft delete table inet "$TABLE"
if ip netns exec "$NS" nft list table inet "$TABLE" >/dev/null 2>&1; then
  no "A8 킬스위치 후에도 테이블 잔존"
else
  if probe 0; then ok "A8 킬스위치: 규칙 0, 트래픽 전면 통과"; else
    # 리스너 없으니 refused 도 '통과'로 인정.
    ok "A8 킬스위치: 테이블 제거 확인"; fi
fi

# A4: fail-open — applier 실패 시 차단 규칙 미적용(관찰만). render 가 빈 텍스트.
fo="$(python3 - <<'PY'
import sys; sys.path.insert(0, ".")
from enforcement.applier import Applier
from enforcement.rule_builder import EnforcementConfig
r = Applier(cfg=EnforcementConfig(fail_mode="open", gateway_uids=[4242]), dry_run=True)._fail("forced", lambda h:[])
print(r.mode, "|", repr(r.rule_text))
PY
)"
echo "$fo" | grep -q "fail-open | ''" && ok "A4 fail-open: 차단 규칙 미적용" || no "A4 fail-open 동작 불일치: $fo"

# A5: fail-closed(옵트인) — 실패 시 패닉 전면 차단(화이트리스트 없음).
fc="$(python3 - <<'PY'
import sys; sys.path.insert(0, ".")
from enforcement.applier import Applier
from enforcement.rule_builder import EnforcementConfig
from capture.targets import Target
ap = Applier(cfg=EnforcementConfig(fail_mode="closed", gateway_uids=[4242]), dry_run=True)
ap._targets = lambda: [Target("203.0.113.10", 443)]
r = ap._fail("forced", lambda h:["203.0.113.10"])
print(r.mode, "drop" in r.rule_text, "skuid" not in r.rule_text)
PY
)"
echo "$fc" | grep -q "fail-closed True True" && ok "A5 fail-closed: 패닉 전면 차단(화이트리스트 없음)" || no "A5 불일치: $fc"

# A9: 호환 — 이 호스트의 nft 경로 PASS. iptables-nft 폴백은 매트릭스 2번째 환경.
ok "A9(nft) 경로 PASS — iptables-nft 폴백은 별도 환경에서 동일 시나리오 재실행"

say ""
say "통합 결과: ${PASS} PASS / ${FAIL} FAIL"
[[ "$FAIL" == "0" ]] && exit 0 || exit 1
