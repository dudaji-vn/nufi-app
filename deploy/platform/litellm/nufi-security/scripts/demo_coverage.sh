#!/usr/bin/env bash
# =============================================================================
# NuFi 커버리지 보증 데모 (v0.0.3 O2 / CMP-133)  [CMP-138]
#
# '내 트래픽 중 X% 가 게이트웨이를 통과'(coverage) + 게이트웨이 우회 상시
# 모니터링/임계 알림(monitor)을 1-명령으로 시연·자동검증하고 PASS/FAIL 을 출력.
#
#   C1  커버리지 PASS    → 전부 게이트웨이 경유(우회 0) → 100% PASS(exit 0)
#   C2  커버리지 누수탐지 → 우회 2건 섞인 트래픽 → 50% < 90% → FAIL 로 누수 플래그
#   C3  우회 알림        → 우회 버스트 → 임계 초과 알림 2건 발화 + 반복분 suppression
#
# 각 시나리오는 명령의 출력·종료코드가 '기대대로' 인지 검증한다(데모 PASS = 기능이
# 설계대로 동작). C2 의 coverage exit 1·C3 의 monitor exit 1 은 누수/우회를 정확히
# 플래그한 것 = 기능이 동작한 것이므로 데모상 PASS 다.
#
# --simulate(기본): root 없이(에어갭/CI) flow 리플레이로 집계. 외부 네트워크 호출 0.
#                   라이브 캡처(--live)는 root/CAP_NET_RAW 필요 — 데모 범위 밖.
# 사용: ./scripts/demo_coverage.sh
# 매뉴얼: docs/history/DEMO_v0.0.3.md · docs/CLI.md#coverage / #monitor
# =============================================================================
set -uo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
PY="${PYTHON:-python3}"

CLEAN="$ROOT/samples/flow_clean.jsonl"          # 전부 게이트웨이 경유(우회 0)
REPLAY="$ROOT/samples/flow_replay.jsonl"        # 우회 2건 섞임(누수 탐지용)
BURST="$ROOT/samples/flow_bypass_burst.jsonl"   # 우회 버스트(알림+suppression)

PASS=0 ; FAIL=0
ok()   { echo "  [PASS] $1" ; PASS=$((PASS+1)) ; }
bad()  { echo "  [FAIL] $1" ; FAIL=$((FAIL+1)) ; }
hr()   { echo "------------------------------------------------------------" ; }

echo "============================================================"
echo " NuFi 커버리지 보증 데모 — v0.0.3 O2 (CMP-133) [CMP-138]"
echo " root 불필요 · 외부 호출 0 · --simulate(flow 리플레이)"
echo "============================================================"

# --- C1: 커버리지 PASS (전부 게이트웨이 경유) ---------------------------------
echo ""
echo "C1 — 커버리지 PASS: 전부 게이트웨이 경유 → 100% (우회 0)"
OUT="$($PY -m enforcement.cli coverage --simulate "$CLEAN" --no-json)" ; RC=$?
echo "$OUT" | sed 's/^/    /'
if [ "$RC" -eq 0 ] && echo "$OUT" | grep -q "100.0%" && echo "$OUT" | grep -q "PASS"; then
  ok "C1 coverage 100% PASS (exit 0) — 보증 충족"
else
  bad "C1 기대=100% PASS exit 0, 실제 exit=$RC"
fi

# --- C2: 커버리지 누수 탐지 (우회 섞인 트래픽) -------------------------------
echo ""
echo "C2 — 커버리지 누수 탐지: 우회 2건 섞인 트래픽 → 50% < 90% → FAIL"
OUT="$($PY -m enforcement.cli coverage --simulate "$REPLAY" --no-json)" ; RC=$?
echo "$OUT" | sed 's/^/    /'
if [ "$RC" -eq 1 ] && echo "$OUT" | grep -q "50.0%" && echo "$OUT" | grep -q "FAIL"; then
  ok "C2 coverage 50% FAIL (exit 1) — 우회 누수를 정확히 플래그"
else
  bad "C2 기대=50% FAIL exit 1, 실제 exit=$RC"
fi

# --- C3: 우회 상시 모니터링/알림 (suppression) -------------------------------
echo ""
echo "C3 — 우회 알림: 우회 버스트 → 임계 초과 알림 발화 + 반복분 suppression"
OUT="$($PY -m enforcement.cli monitor --simulate "$BURST" --threshold 1)" ; RC=$?
echo "$OUT" | sed 's/^/    /'
if [ "$RC" -eq 1 ] && echo "$OUT" | grep -q "알림 2" && echo "$OUT" | grep -q "억제(suppressed) 4"; then
  ok "C3 monitor 알림 2건 발화 + 억제 4건 — 임계/디바운스 동작"
else
  bad "C3 기대=알림 2 + 억제 4 (exit 1), 실제 exit=$RC"
fi

hr
echo "요약: $((PASS+FAIL))개 시나리오 중 ${PASS} PASS, ${FAIL} FAIL"
if [ "$FAIL" -eq 0 ]; then
  echo "✅ 커버리지 데모 PASS — coverage/monitor 가 전부 설계대로 동작"
  exit 0
else
  echo "❌ 커버리지 데모 FAIL — 위 [FAIL] 항목 확인"
  exit 1
fi
