#!/usr/bin/env bash
# =============================================================================
# NuFi 컴플라이언스 매핑 리포트 데모 (규제 준수 증빙 게이트웨이 첫 슬라이스)
#
# `nufi-egress report compliance --controls` 의 **점검항목 커버리지(control coverage)**
# 섹션을 1-커맨드로 시연한다. 금융보안원 안내서 점검항목 + 망분리 평가기준 대비 NuFi
# 통제 충족 상태를, 기존 감사·변경·우회 증빙에서 **자동 산출**해 제출용 리포트로 묶는다.
#
#   - direct(직접) 통제는 증빙으로 충족/미충족을 **자동판정**(차단/가명화 결정 + 무결 체인).
#   - partial(부분)/out_of_scope(범위밖)은 카탈로그의 **정적 라벨** + 보강 로드맵.
#   - 커버리지는 **정보성** — 기존 무결성 게이트(0/1) 종료코드를 바꾸지 않는다.
#
# **새 측정·새 벤치 없음** — 동봉 샘플 픽스처만 read-only 로 재사용한다.
# root 불필요 · 외부 네트워크 호출 0 (표준 라이브러리 + 동봉 픽스처).
#
#   M1  커버리지 롤업(JSON)   → 직접 23(충족 23/미충족 0) · 부분 9 · 범위밖 8
#   M2  커버리지 표(MD)       → 충족/부분충족/범위밖 3구분 행 + 자동 증빙 출처
#   M3  무결성 게이트 유지(0) → --controls 켜도 정보성 — 정상 체인은 exit 0
#   M4  무결성 게이트 유지(1) → 감사 체인 변조 시 커버리지와 무관하게 exit 1(제출 차단)
#   M5  --no-controls        → 커버리지 섹션 생략(기존 컴플라이언스 리포트로 회귀)
#   M6  한국 규제팩 소계      → 프레임워크별(fsec-ai/net-sep/pipa/cia/isms-p) 소계 + maps_to
#   M7  --framework 필터      → 규제별 행만 렌더(롤업도 필터 기준) · 종료코드 불변
#
# 사용: ./scripts/demo_compliance_mapping.sh
# 매뉴얼: docs/REPORTING.md §3 · docs/MANUAL.md §5.4
# =============================================================================
set -uo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
PY="${PYTHON:-python3}"
CLI=("$PY" -m enforcement.cli)

SDIR="$ROOT/samples/sla"
OUT="$ROOT/demo_outputs/compliance_mapping"
mkdir -p "$OUT"

PASS=0 ; FAIL=0
ok()  { echo "  [PASS] $1" ; PASS=$((PASS+1)) ; }
bad() { echo "  [FAIL] $1" ; FAIL=$((FAIL+1)) ; }
hr()  { echo "------------------------------------------------------------" ; }

echo "============================================================"
echo " NuFi 컴플라이언스 매핑 리포트 데모 — 점검항목 커버리지"
echo " 기존 증빙 재사용 · 새 측정 없음 · root 불필요 · 외부 호출 0"
echo "============================================================"

# 공통 증빙 입력(동봉 샘플): 감사 결정 + 정책 변경 + 우회 탭.
EVID=(--audit "$SDIR/audit_decisions.jsonl"
      --change-log "$SDIR/policy_changes.jsonl"
      --flow "$SDIR/flow_bypass.jsonl")

# --- M1: 커버리지 롤업(JSON) — 직접/부분/범위밖 자동 산출 -------------------- #
hr ; echo "M1  커버리지 롤업(JSON) — 직접 25(충족25/미충족0)·부분 10·범위밖 13"
COV_JSON="$OUT/compliance_controls.json"
"${CLI[@]}" report compliance "${EVID[@]}" \
  --controls --customer "Acme Corp" --format json > "$COV_JSON"
RC=$?
SUMMARY=$("$PY" -c "import json;s=json.load(open('$COV_JSON'))['control_coverage']['summary'];print(s['direct'],s['direct_met'],s['direct_unmet'],s['partial'],s['out_of_scope'])")
if [ "$RC" -eq 0 ] && [ "$SUMMARY" = "25 25 0 10 13" ] \
   && "$PY" -c "import json;ids={i['id'] for i in json.load(open('$COV_JSON'))['control_coverage']['items']};assert {'C-07','M-2.7','PIPA-23','CIA-PII','ISMS-3.3'} <= ids" 2>/dev/null ; then
  ok "롤업 자동 산출: 직접 25/25 충족 · 부분 10 · 범위밖 13 (정보성 · exit 0)"
else
  bad "롤업 산출 실패(summary='$SUMMARY', exit=$RC)"
fi

# --- M2: 커버리지 표(MD) — 충족/부분/범위밖 3구분 + 증빙 출처 -------------- #
hr ; echo "M2  커버리지 표(MD) — 충족/부분충족/범위밖 3구분 행"
COV_MD="$OUT/compliance_report.md"
"${CLI[@]}" report compliance "${EVID[@]}" \
  --controls --customer "Acme Corp" --format md > "$COV_MD"
RC=$?
if [ "$RC" -eq 0 ] && grep -q "점검항목 커버리지" "$COV_MD" \
   && grep -q "✅ 충족" "$COV_MD" && grep -q "🟡 부분충족" "$COV_MD" \
   && grep -q "⛔ 범위밖" "$COV_MD" && grep -q "action_counts" "$COV_MD" ; then
  ok "MD 표에 3구분(충족/부분/범위밖) 행 + 자동 증빙 출처 포함"
else
  bad "MD 표 누락(exit=$RC) — $COV_MD 확인"
fi

# --- M3: 무결성 게이트 유지(0) — 커버리지는 정보성 ------------------------- #
hr ; echo "M3  무결성 게이트 유지 — 정상 체인 + --controls → exit 0"
"${CLI[@]}" report compliance "${EVID[@]}" --controls --format json > /dev/null
RC=$?
if [ "$RC" -eq 0 ] ; then
  ok "커버리지(--controls)는 종료코드 비반영 — 정상 체인 exit 0 유지"
else
  bad "정상 체인인데 exit=$RC (0 기대) — 커버리지가 게이트를 오염시킴"
fi

# --- M4: 무결성 게이트 유지(1) — 변조 시 커버리지와 무관하게 차단 --------- #
hr ; echo "M4  무결성 게이트 유지 — 감사 체인 변조 + --controls → exit 1"
TAMP="$OUT/_tampered_audit.jsonl"
"$PY" - "$SDIR/audit_decisions.jsonl" "$TAMP" <<'PYEOF'
import json, sys
src, dst = sys.argv[1], sys.argv[2]
recs = [json.loads(l) for l in open(src, encoding="utf-8") if l.strip()]
recs[2]["outcome"] = "allowed"   # 한 행 변조(해시 미수정) → 체인 깨짐
with open(dst, "w", encoding="utf-8") as f:
    for r in recs:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
PYEOF
"${CLI[@]}" report compliance --audit "$TAMP" \
  --change-log "$SDIR/policy_changes.jsonl" --controls --format json > /dev/null
RC=$?
rm -f "$TAMP"
if [ "$RC" -eq 1 ] ; then
  ok "변조 감사 체인 → 커버리지 켜져 있어도 exit 1(제출 차단) 유지"
else
  bad "변조인데 exit=$RC (1 기대) — 커버리지가 무결성 게이트를 가림"
fi

# --- M5: --no-controls — 커버리지 섹션 생략 ------------------------------- #
hr ; echo "M5  --no-controls — 커버리지 섹션 생략(기존 리포트로 회귀)"
NOCOV_MD="$OUT/compliance_report_nocontrols.md"
"${CLI[@]}" report compliance "${EVID[@]}" --no-controls --format md > "$NOCOV_MD"
RC=$?
if [ "$RC" -eq 0 ] && ! grep -q "점검항목 커버리지" "$NOCOV_MD" ; then
  ok "--no-controls 는 커버리지 섹션을 빼고 기존 컴플라이언스 리포트만 산출"
else
  bad "--no-controls 인데 커버리지 섹션이 남음(exit=$RC) — $NOCOV_MD 확인"
fi

# --- M6: 한국 규제팩 프레임워크별 소계 + maps_to 교차참조 ------------------ #
hr ; echo "M6  한국 규제팩 소계 — 프레임워크별(pipa/cia/isms-p) + maps_to"
if "$PY" -c "
import json
bf=json.load(open('$COV_JSON'))['control_coverage']['summary']['by_framework']
assert bf['pipa']['direct']==6 and bf['pipa']['partial']==2 and bf['pipa']['out_of_scope']==2, bf['pipa']
assert bf['cia']['direct']==5 and bf['cia']['partial']==1 and bf['cia']['out_of_scope']==2, bf['cia']
assert bf['isms-p']['direct']==5 and bf['isms-p']['partial']==2 and bf['isms-p']['out_of_scope']==4, bf['isms-p']
items={i['id']:i for i in json.load(open('$COV_JSON'))['control_coverage']['items']}
assert items['PIPA-23']['maps_to']=='C-07'
assert items['CIA-XBORDER']['maps_to']=='C-26'
assert items['ISMS-2.9.4']['maps_to']=='M-1.2'
" 2>/dev/null ; then
  ok "프레임워크별 소계(pipa 6/cia 5/isms-p 5 direct) + maps_to 교차참조 산출"
else
  bad "프레임워크 소계/maps_to 산출 실패 — $COV_JSON 확인"
fi

# --- M7: --framework 정보성 필터 — 규제별 행만 + 종료코드 불변 ------------- #
hr ; echo "M7  --framework 필터 — pipa 만 렌더(롤업 필터 기준) · exit 0 불변"
FILT_JSON="$OUT/compliance_pipa.json"
"${CLI[@]}" report compliance "${EVID[@]}" \
  --controls --framework pipa --format json > "$FILT_JSON"
RC=$?
if [ "$RC" -eq 0 ] && "$PY" -c "
import json
cc=json.load(open('$FILT_JSON'))['control_coverage']
assert cc['frameworks_filter']==['pipa'], cc['frameworks_filter']
assert {i['framework'] for i in cc['items']}=={'pipa'}
assert cc['summary']['direct']==6 and set(cc['summary']['by_framework'])=={'pipa'}
" 2>/dev/null ; then
  ok "--framework pipa: pipa 8행만 렌더 · 롤업 직접 6 · 종료코드 0 유지(정보성)"
else
  bad "--framework 필터 실패(exit=$RC) — $FILT_JSON 확인"
fi

hr
echo "결과: PASS=$PASS  FAIL=$FAIL   (산출물: $OUT/)"
[ "$FAIL" -eq 0 ] && echo "✅ DEMO PASS" || echo "❌ DEMO FAIL"
exit "$FAIL"
