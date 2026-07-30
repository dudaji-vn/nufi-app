#!/usr/bin/env bash
# =============================================================================
# NuFi 규정준수 리포팅 데모 (CMP-150)
#
# 이미 측정·적재된 산출물(정책 변경 감사 · 감사 결정 · flow tap)을
# `nufi-egress report compliance` 로 **제출용 리포트**(MD/HTML/JSON)로
# 묶고, 해시체인 무결성 게이트가 동작하는지 헤드리스로 자동검증한다.
#
# **새 측정·새 벤치 없음** — 동봉 샘플 픽스처만 read-only 로 재사용한다.
# root 불필요 · 외부 네트워크 호출 0 (표준 라이브러리 + 동봉 픽스처).
#
#   C1  report compliance (MD) → 정책 변경 감사 + 차단/가명화 + 우회 요약
#   C2  무결성 게이트            → 감사 로그 변조 시 compliance exit 1
#   C3  점검항목 커버리지         → 안내서·망분리 통제 충족 자동 산출(정보성)
#
# 사용: ./scripts/demo_report.sh
# 매뉴얼: docs/REPORTING.md · docs/HANDS_ON.md
# =============================================================================
set -uo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
PY="${PYTHON:-python3}"
CLI=("$PY" -m enforcement.cli)

SDIR="$ROOT/samples/sla"
OUT="$ROOT/demo_outputs/report"
mkdir -p "$OUT"

PASS=0 ; FAIL=0
ok()  { echo "  [PASS] $1" ; PASS=$((PASS+1)) ; }
bad() { echo "  [FAIL] $1" ; FAIL=$((FAIL+1)) ; }
hr()  { echo "------------------------------------------------------------" ; }

echo "============================================================"
echo " NuFi 규정준수 리포팅 데모 (CMP-150)"
echo " 기존 측정 재사용 · 새 측정 없음 · root 불필요 · 외부 호출 0"
echo "============================================================"

# --- C1: 규정준수 리포트 — 변경 감사 + 차단/가명화 + 우회 ------------------- #
hr ; echo "C1  report compliance (MD) — 변경 감사 + 차단/가명화 + 우회"
COMP_MD="$OUT/compliance_report.md"
"${CLI[@]}" report compliance --audit "$SDIR/audit_decisions.jsonl" \
  --change-log "$SDIR/policy_changes.jsonl" --flow "$SDIR/flow_bypass.jsonl" \
  --customer "Acme Corp" --format md > "$COMP_MD"
RC=$?
"${CLI[@]}" report compliance --audit "$SDIR/audit_decisions.jsonl" \
  --change-log "$SDIR/policy_changes.jsonl" --flow "$SDIR/flow_bypass.jsonl" \
  --customer "Acme Corp" --format html > "$OUT/compliance_report.html"
if [ "$RC" -eq 0 ] && grep -q "정책 변경 감사" "$COMP_MD" \
   && grep -q "차단·가명화" "$COMP_MD" && grep -q "우회 탐지 요약" "$COMP_MD" \
   && grep -q "무결성 정상" "$COMP_MD" ; then
  ok "변경 감사·차단/가명화·우회 요약 + 체인 무결성 OK (exit 0)"
else
  bad "compliance MD 누락 또는 exit=$RC"
fi

# --- C2: 무결성 게이트 — 감사 로그 변조 시 exit 1 -------------------------- #
hr ; echo "C2  무결성 게이트 — 감사 로그 변조 탐지"
TAMP="$OUT/_tampered_audit.jsonl"
"$PY" - "$SDIR/audit_decisions.jsonl" "$TAMP" <<'PY'
import json, sys
src, dst = sys.argv[1], sys.argv[2]
recs = [json.loads(l) for l in open(src, encoding="utf-8") if l.strip()]
recs[2]["outcome"] = "allowed"   # 한 행 변조(해시 미수정) → 체인 깨짐
with open(dst, "w", encoding="utf-8") as f:
    for r in recs:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
PY
"${CLI[@]}" report compliance --audit "$TAMP" \
  --change-log "$SDIR/policy_changes.jsonl" --format json > /dev/null
RC=$?
rm -f "$TAMP"
if [ "$RC" -eq 1 ] ; then
  ok "변조된 감사 체인 탐지 → exit 1 (제출 차단)"
else
  bad "변조인데 exit=$RC (1 기대)"
fi

# --- C3: 점검항목 커버리지 — 한국 규제팩 통제 충족 자동 산출 ------------------- #
hr ; echo "C3  점검항목 커버리지 — 한국 규제팩 통제 충족 자동 산출"
COV_JSON="$OUT/compliance_controls.json"
"${CLI[@]}" report compliance --audit "$SDIR/audit_decisions.jsonl" \
  --change-log "$SDIR/policy_changes.jsonl" --flow "$SDIR/flow_bypass.jsonl" \
  --controls --customer "Acme Corp" --format json > "$COV_JSON"
RC=$?
# 동봉 증빙: direct 전부 충족(차단/가명화 결정 + 무결 체인). 카탈로그 v1.2+ → 25 direct.
DIRECT_MET=$("$PY" -c "import json;d=json.load(open('$COV_JSON'));s=d['control_coverage']['summary'];print(s['direct'],s['direct_met'])")
if [ "$RC" -eq 0 ] && [ "$DIRECT_MET" = "25 25" ] \
   && "$PY" -c "import json;d=json.load(open('$COV_JSON'));ids={i['id'] for i in d['control_coverage']['items']};assert {'C-07','M-2.7','PIPA-23','CIA-PII','ISMS-3.3'} <= ids" ; then
  ok "direct 25/25 충족 + partial/out_of_scope 라벨 산출 (정보성 · exit 0)"
else
  bad "커버리지 산출 실패(direct_met='$DIRECT_MET', exit=$RC)"
fi

hr
echo "결과: PASS=$PASS  FAIL=$FAIL   (산출물: $OUT/)"
[ "$FAIL" -eq 0 ] && echo "✅ DEMO PASS" || echo "❌ DEMO FAIL"
exit "$FAIL"
