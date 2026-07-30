#!/usr/bin/env bash
# =============================================================================
# NuFi 가명화 품질 벤치마크 재현 데모 — 가역/비가역 지표 게이트
#
# I4 가명화 품질 지표(§6 산출 표면)를 결정적으로 재현·검증한다:
#   가역(surrogate.py)     원복 정확도(스트리밍 경계 포함)·surrogate 충돌율 0·결정성
#   비가역(pseudonymize.py) 원복불가·구조보존·동일값 일관 치환·충돌율 0
#   차단 유지               강한 식별자·비밀은 가역 프리셋에서도 차단(가명화 송신 금지)
#
# 무거운 모델 스택 없이 실행(gazetteer NER + 합성 코퍼스). root 불필요·외부 호출 0·결정적.
#
# 사용:   ./scripts/demo_pseudonymize.sh
# 하니스: scripts/bench_pseudonymize.py · 리포트 자산: docs/reports/pseudonymize-quality.json
# 재측정: python3 scripts/bench_pseudonymize.py --json-out docs/reports/pseudonymize-quality.json
# =============================================================================
set -uo pipefail
cd "$(dirname "$0")/.."
PY="${PYTHON:-python3}"

REPORT="docs/reports/pseudonymize-quality.json"
PASS=0 ; FAIL=0
ok()  { echo "  [PASS] $1" ; PASS=$((PASS+1)) ; }
bad() { echo "  [FAIL] $1" ; FAIL=$((FAIL+1)) ; }

echo "============================================================"
echo " NuFi 가명화 품질 벤치마크 재현 — I4"
echo " 가역/비가역 지표 · 충돌율 0 · 결정성 · 차단 유지 · 외부호출 0"
echo "============================================================"

# --- 하니스 재실행: 기계식 불변식 미달 시 비-0 종료 --------------------------
echo ""
echo "1 — 벤치마크 하니스 재실행(결정적 측정)"
if $PY scripts/bench_pseudonymize.py --json-out "$REPORT" >/tmp/nufi_pseudo_bench.json 2>&1; then
  ok "하니스 종료코드 0 — 모든 기계식 불변식 충족"
else
  bad "하니스 비-0 종료 — 불변식 미달(로그: /tmp/nufi_pseudo_bench.json)"
fi

# --- 커밋된 리포트 자산 대조 + 축별 지표 요약 --------------------------------
echo ""
echo "2 — 커밋 리포트 자산 지표(가역/비가역/차단 유지)"
$PY - "$REPORT" <<'PYEOF'
import json, sys
d = json.load(open(sys.argv[1]))
s = d["scores"]
rt, st = s["roundtrip"], s["streaming"]
col, det = s["collision_scale"], s["determinism"]
blk, ir = s["block_retention"], s["irreversible"]
print(f"    가역 대상    : {', '.join(s['reversible_targets'])}")
print(f"    차단 유지 대상: {', '.join(s['strong_block_targets'])}")
print(f"    원복 정확도  : {rt['roundtrip_exact']} ({rt['roundtrip_exact_n']})  토큰 {rt['tokens_minted']}개")
print(f"    스트리밍 일치: {st['streaming_match']} ({st['streaming_match_n']}) · 경계조합 {st['boundary_configs_tested']}개")
print(f"    surrogate 충돌: end2end {rt['surrogate_collisions']} + 스케일 {col['collisions']}"
      f" (발급 {col['n_minted']}개) = {d['combined_surrogate_collisions']}  · 델리미터 충돌 {rt['delimiter_corpus_collision']}")
print(f"    결정성       : 재실행 동일={det['reversible_determinism']} · 동일원본 안정={col['same_original_stable']}")
print(f"    차단 유지    : {blk['block_retention']} ({blk['block_retention_n']}) · 가명화 누출 {blk['pseudonymize_leak']}")
print(f"    비가역       : 일관치환 {ir['irreversible_consistency']} · 충돌 {ir['irreversible_collisions']}"
      f" · 구조보존 {ir['irreversible_structure_preserved']} · 원복불가 {ir['irreversible_non_restorable']}")
print(f"    수용 판정    : acceptance_pass={d['acceptance_pass']}")
sys.exit(0 if d.get("acceptance_pass") else 1)
PYEOF
RC=$?
if [ "$RC" -eq 0 ]; then
  ok "가역/비가역/차단 유지 전 지표 목표 충족(충돌율 0·결정성·원복 정확·차단 유지)"
else
  bad "수용 판정 미달 — 위 지표 확인"
fi

echo "------------------------------------------------------------"
echo "요약: $((PASS+FAIL))개 항목 중 ${PASS} PASS, ${FAIL} FAIL"
if [ "$FAIL" -eq 0 ]; then
  echo "✅ 가명화 품질 벤치마크 재현 PASS"
  exit 0
else
  echo "❌ 가명화 품질 재현 FAIL — 위 [FAIL] 항목 확인"
  exit 1
fi
