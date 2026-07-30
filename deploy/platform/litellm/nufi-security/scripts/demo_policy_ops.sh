#!/usr/bin/env bash
# =============================================================================
# NuFi 정책 운영 자동화 데모 (v0.0.5 B1 / CMP-144)
#
# 한 게이트웨이에서 여러 정책 프로파일을 동시에 운영하고, 경로/테넌트별로 다른
# 프로파일을 묶고(binding), 정책 버전을 **무재기동**으로 되돌리며(rollback),
# 누가·언제·무엇을 바꿨는지 변경 감사 로그로 남기는 것을 1-명령으로 시연·검증한다.
#
#   P1  두 프로파일 동시 운영   → 같은 입력(전화번호)에 default=통과 / strict=차단
#   P2  경로별 묶기 1건         → tenant-acme → strict 묶기 적용·영속
#   P3  버전 되돌리기(무재기동) → strict 완화(v2) 후 v1 로 rollback, 같은 가드 원자 스왑
#   P4  변경 감사 + 체인        → bind/snapshot/rollback 기록 + 해시 체인 무결성 OK
#
# 완전 격리: config 를 임시 디렉터리로 복사해 운영하므로 저장소 파일을 건드리지 않는다.
# root 불필요 · 외부 네트워크 호출 0 · gazetteer NER(결정론적).
#
# 사용: ./scripts/demo_policy_ops.sh
# 매뉴얼: docs/OPS_POLICY_AT_SCALE.md · 핫리로드 기반: docs/OPS_RULE_RELOAD.md
# =============================================================================
set -uo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
PY="${PYTHON:-python3}"

TD="$(mktemp -d -t nufi-policyops-XXXXXX)"
trap 'rm -rf "$TD"' EXIT

# --- 격리된 운영 상태 구성(저장소 무오염) ------------------------------------
cp "$ROOT/config/policy.yaml" "$TD/default_policy.yaml"
cp "$ROOT/config/profiles/strict/policy.yaml" "$TD/strict_policy.yaml"
ROUTING="$TD/routing.yaml"
cat > "$ROUTING" <<YAML
policy_default_profile: default
policy_profiles:
  default:
    policy: $TD/default_policy.yaml
    description: base(완화) 프로파일
  strict:
    policy: $TD/strict_policy.yaml
    description: strict(차단) 프로파일
policy_bindings: {}
YAML
export POLICY_BINDINGS_OVERLAY="$TD/binds.yaml"
export POLICY_VERSIONS_DIR="$TD/versions"
export POLICY_CHANGE_LOG="$TD/changes.jsonl"

pol(){ $PY -m enforcement.cli --routing "$ROUTING" policy "$@"; }
SAMPLE="연락처 010-1234-5678 로 회신 바랍니다."   # 단일 KR_PHONE 만 트리거

PASS=0 ; FAIL=0
ok()  { echo "  [PASS] $1" ; PASS=$((PASS+1)) ; }
bad() { echo "  [FAIL] $1" ; FAIL=$((FAIL+1)) ; }
hr()  { echo "------------------------------------------------------------" ; }

echo "============================================================"
echo " NuFi 정책 운영 자동화 데모 — v0.0.5 B1 (CMP-144)"
echo " 다중 프로파일·묶기·무재기동 되돌리기·변경 감사 · root 불필요 · 외부호출 0"
echo "============================================================"

# --- P1: 두 프로파일 동시 운영 ----------------------------------------------
echo ""
echo "P1 — 두 프로파일 동시 운영: 같은 전화번호 입력에 다른 결정"
pol bind tenant-acme strict >/dev/null
OUT_DEF="$(pol inspect nufi-default "$SAMPLE")" ; RC_DEF=$?
OUT_STR="$(pol inspect tenant-acme  "$SAMPLE")" ; RC_STR=$?
echo "    $OUT_DEF"
echo "    $OUT_STR"
if [ "$RC_DEF" -eq 0 ] && echo "$OUT_DEF" | grep -q "통과" \
   && [ "$RC_STR" -eq 1 ] && echo "$OUT_STR" | grep -q "차단"; then
  ok "P1 default=통과(exit 0) / strict=차단(exit 1) — 한 게이트웨이 다중 정책"
else
  bad "P1 기대=default 통과·strict 차단, 실제 def_rc=$RC_DEF str_rc=$RC_STR"
fi

# --- P2: 경로별 묶기 1건 ----------------------------------------------------
echo ""
echo "P2 — 경로별 묶기: tenant-acme → strict 적용·영속"
OUT="$(pol list)"
echo "$OUT" | sed 's/^/    /'
if echo "$OUT" | grep -q "tenant-acme" && echo "$OUT" | grep -q "tenant-acme .*strict"; then
  ok "P2 묶기 1건(tenant-acme → strict) 반영 — list 에 노출"
else
  bad "P2 묶기 미반영"
fi

# --- P3: 버전 되돌리기(무재기동) --------------------------------------------
echo ""
echo "P3 — 버전 되돌리기(무재기동): strict v1(차단)→v2(완화) 후 v1 로 rollback"
pol snapshot strict --note "v1 차단(전화 block)" >/dev/null      # v1
# strict 정책 완화: 전화 block→warn 후 v2 적재
$PY - "$TD/strict_policy.yaml" <<'PYEOF'
import sys, yaml
p=sys.argv[1]; c=yaml.safe_load(open(p))
c["entities"]["KR_PHONE"]={"action":"warn","severity":"low"}
open(p,"w").write(yaml.safe_dump(c, allow_unicode=True, sort_keys=False))
PYEOF
pol snapshot strict --note "v2 완화(전화 warn)" >/dev/null        # v2 (active)
BEFORE="$(pol inspect tenant-acme "$SAMPLE")"                     # v2 → 통과
OUT_RB="$(pol rollback strict)" ; RC_RB=$?                        # v2 → v1 무재기동
echo "    완화(v2) 상태: $BEFORE"
echo "    $OUT_RB"
AFTER="$(pol inspect tenant-acme "$SAMPLE")" ; RC_AF=$?           # v1 → 차단
echo "    되돌림(v1) 상태: $AFTER"
if [ "$RC_RB" -eq 0 ] && echo "$OUT_RB" | grep -q "무재기동" \
   && echo "$OUT_RB" | grep -q "generation 0→1" \
   && echo "$BEFORE" | grep -q "통과" && echo "$AFTER" | grep -q "차단"; then
  ok "P3 v2→v1 무재기동 되돌리기(generation 0→1) — 완화→차단 라이브 반영"
else
  bad "P3 무재기동 되돌리기 미충족 (rollback_rc=$RC_RB)"
fi

# --- P4: 변경 감사 + 해시 체인 ----------------------------------------------
echo ""
echo "P4 — 변경 감사: 누가·언제·무엇을 + 추가전용 해시 체인 무결성"
OUT="$(pol audit --verify-chain)" ; RC=$?
echo "$OUT" | sed 's/^/    /'
if [ "$RC" -eq 0 ] && echo "$OUT" | grep -q "bind" && echo "$OUT" | grep -q "snapshot" \
   && echo "$OUT" | grep -q "rollback" && echo "$OUT" | grep -q "해시 체인: OK"; then
  ok "P4 bind/snapshot/rollback 기록 + 해시 체인 OK(변조탐지)"
else
  bad "P4 변경 감사/체인 미충족 (exit=$RC)"
fi

hr
echo "요약: $((PASS+FAIL))개 시나리오 중 ${PASS} PASS, ${FAIL} FAIL"
if [ "$FAIL" -eq 0 ]; then
  echo "✅ 정책 운영 자동화 데모 PASS — 다중 프로파일·묶기·무재기동 되돌리기·변경 감사 전부 동작"
  exit 0
else
  echo "❌ 정책 운영 자동화 데모 FAIL — 위 [FAIL] 항목 확인"
  exit 1
fi
