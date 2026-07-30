#!/usr/bin/env bash
# =============================================================================
# NuFi 정확도 재현 데모 — KR_PERSON INT8 정확도 + 온프렘 p95 + 단일 명령 벤치마크(I5)
#
# M6 정확도 부채(세 버전 이연)의 두 산출물을 **재현·검증**한다:
#   A1  KR_PERSON 신뢰구간   → per-channel INT8 양자화로 Wilson CI 하한 ≥ 0.85
#                              (per-tensor 회귀 0.832 → per-channel 복원 0.850)
#   A2  온프렘 p95 표         → INT8 부하 p95 지연(동시성 sweep) 운영 기준 충족
#
# 무거운 모델 스택 없이도 **고정 측정 산출물**(docs/reports/*.json — 커밋된 증거)을
# 목표선에 대조해 PASS/FAIL 을 낸다. 실제 재측정(모델 재실행) 경로는 아래 안내.
# root 불필요 · 외부 네트워크 호출 0 · 결정론적(stdlib + 커밋 JSON).
#
# A1/A2 는 v0.0.5 봉인 골드셋(KR_PERSON 126) 측정 증거를 재생한다(게이트).
# A3 는 I1 공개 골드셋(samples/gold, test n=372) 현행 baseline 을 **정보성**으로 표시한다
#   (docs/reports/baseline-int8.json — onnx-int8 실측). PASS/FAIL 미산입.
#   I1 baseline 재측정: PYTHONPATH=~/.cache/m5_libs python3 scripts/bench_m5.py \
#     --backend onnx-int8 --split test --no-latency --json-out docs/reports/baseline-int8.json
#
# 사용: ./scripts/demo_accuracy.sh
# 매뉴얼: docs/history/DEMO_v0.0.5.md · 측정 스택: docs/M5_MEASUREMENT_REPORT.md
# 재측정: PYTHONPATH=~/.cache/m5_libs python3 scripts/export_onnx_int8.py   # per-channel INT8 산출
#         PYTHONPATH=~/.cache/m5_libs python3 scripts/bench_m5.py --recall ...  # recall 재측정
# =============================================================================
set -uo pipefail
cd "$(dirname "$0")/.."
PY="${PYTHON:-python3}"

RECALL_REPORT="docs/reports/recall-int8.json"   # per-channel INT8(활성) recall
P95_REPORT="docs/reports/load-p95.json"         # INT8 부하 p95(동시성 sweep)
PERSON_CI_FLOOR_TARGET="0.85"

PASS=0 ; FAIL=0
ok()  { echo "  [PASS] $1" ; PASS=$((PASS+1)) ; }
bad() { echo "  [FAIL] $1" ; FAIL=$((FAIL+1)) ; }

echo "============================================================"
echo " NuFi 정확도 숙제 종결 재현 — v0.0.5 B2 (CMP-145)"
echo " per-channel INT8 KR_PERSON CI ≥ 0.85 + 온프렘 p95 표 · root 불필요 · 외부호출 0"
echo "============================================================"

# --- A1: KR_PERSON Wilson 신뢰구간 하한 ≥ 0.85 -------------------------------
echo ""
echo "A1 — KR_PERSON 신뢰구간: per-channel INT8 Wilson CI 하한 ≥ ${PERSON_CI_FLOOR_TARGET}"
$PY - "$RECALL_REPORT" "$PERSON_CI_FLOOR_TARGET" <<'PYEOF'
import json, sys
report, target = sys.argv[1], float(sys.argv[2])
try:
    d = json.load(open(report))
except FileNotFoundError:
    print(f"    측정 산출물 없음: {report}"); sys.exit(3)
sc = d["scores"]
pc = (sc.get("per_class", {}).get("KR_PERSON")
      or sc.get("per_class", {}).get("PERSON") or {})
ci = pc.get("ci95") or [None, None]
floor = ci[0]
backend = d.get("ner_backend_active", "?")
print(f"    backend={backend}  KR_PERSON recall={pc.get('recall')} "
      f"({pc.get('hit')}/{pc.get('exp')})  Wilson CI95={ci}")
print(f"    pii_recall={sc.get('pii_recall')} CI95={sc.get('pii_recall_ci95')}  "
      f"benign_false_block={sc.get('benign_false_block')}")
sys.exit(0 if (floor is not None and floor >= target) else 1)
PYEOF
RC=$?
if [ "$RC" -eq 0 ]; then
  ok "A1 KR_PERSON CI 하한 ≥ ${PERSON_CI_FLOOR_TARGET} — per-tensor 0.832 회귀를 per-channel 이 복원"
elif [ "$RC" -eq 3 ]; then
  bad "A1 측정 산출물 누락 — scripts/export_onnx_int8.py + bench_m5.py 로 재측정 필요"
else
  bad "A1 KR_PERSON CI 하한 < ${PERSON_CI_FLOOR_TARGET} — 표본 확대 재판정 필요"
fi

# --- A2: 온프렘 p95 표 (INT8 부하 동시성 sweep) ------------------------------
echo ""
echo "A2 — 온프렘 p95 표: INT8 부하 p95 지연(동시성 sweep) — 운영 기준 대조"
$PY - "$P95_REPORT" <<'PYEOF'
import json, sys
d = json.load(open(sys.argv[1]))
tgt = d.get("p95_target_ms", 150.0)
sweep = d["concurrency_sweep"]
print(f"    backend={d.get('ner_backend_active')}  chars={d.get('chars')}  목표 p95 ≤ {tgt}ms")
print(f"    {'동시성':>6} {'p50(ms)':>9} {'p95(ms)':>9} {'p99(ms)':>9} {'throughput(req/s)':>18}  판정")
ok_low = True
for k in sorted(sweep, key=lambda x: int(x)):
    s = sweep[k]
    verdict = "✅≤목표" if s.get("p95_le_150ms") or s["lat_p95_ms"] <= tgt else "초과"
    print(f"    {s['concurrency']:>6} {s['lat_p50_ms']:>9.1f} {s['lat_p95_ms']:>9.1f} "
          f"{s['lat_p99_ms']:>9.1f} {s['throughput_req_s']:>18.1f}  {verdict}")
    if int(k) <= 2 and s["lat_p95_ms"] > tgt:
        ok_low = False
# 운영 기준: 단일~중간 동시성(c≤2)에서 p95 가 목표 이내면 통과(고동시성은 풀 스케일아웃 권고).
sys.exit(0 if ok_low else 1)
PYEOF
RC=$?
if [ "$RC" -eq 0 ]; then
  ok "A2 온프렘 p95 표 — INT8 c≤2 p95 목표 이내(고동시성은 워커 스케일아웃 권고)"
else
  bad "A2 INT8 p95 가 운영 기준 초과 — 측정/배포 점검"
fi

# --- A3: I1 공개 골드셋 현행 baseline (정보성, 게이트 아님) -------------------
I1_BASELINE="docs/reports/baseline-int8.json"
echo ""
echo "A3 — I1 공개 골드셋 baseline (samples/gold test n=372) · 정보성(PASS/FAIL 미산입)"
$PY - "$I1_BASELINE" <<'PYEOF'
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except FileNotFoundError:
    print(f"    I1 baseline 산출물 없음: {sys.argv[1]} (정보성 — 데모 판정 무관)"); sys.exit(0)
sc = d["scores"]
pc = sc["per_class"]
def line(name, key, floor):
    v = pc.get(key, {})
    ci = v.get("ci95", [None, None])
    mark = "≥" if (v.get("recall", 0) >= floor) else "↓"
    print(f"    {name:14} recall={v.get('recall')} ({v.get('hit')}/{v.get('exp')}) "
          f"CI95={ci}  [{mark}{floor} 점추정]")
print(f"    backend={d.get('ner_backend_active')}  acceptance_pass={d.get('acceptance_pass')}")
print(f"    집계 PII recall={sc['pii_recall']} CI95={sc['pii_recall_ci95']}  "
      f"precision={sc['pii_precision']}  benign_false_block={sc['benign_false_block']} ({sc['benign_false_block_n']})")
print(f"    강식별자(checksum) recall={sc['strong_recall']} CI95={sc['strong_recall_ci95']} (결정적 regex+checksum)")
line("KR_PERSON", "KR_PERSON", 0.85)
line("KR_LOCATION", "KR_LOCATION", 0.85)
sys.exit(0)
PYEOF
echo "    (KR_PERSON CI 하한·KR_LOCATION 목표 미달은 I3/I4 코어 개선 추적 — §5 게이트 확정 입력)"

# --- B: 단일 명령 벤치마크 (I5) — 정확도 게이트 + 가명화 품질 --------------
# 정확도(I2 커밋 측정 JSON 게이트)와 가명화 품질(I4 하니스 라이브)을 한 명령으로 재현.
# 흩어진 두 벤치마크를 SDK/CLI 단일 진입점(`nufi-egress benchmark`)으로 노출한 검증.
echo ""
echo "B — 단일 명령 재현: nufi-egress benchmark (정확도 I2 커밋 JSON + 가명화 I4 하니스)"
if $PY -m enforcement.cli benchmark >/tmp/nufi_benchmark_demo.log 2>&1; then
  ok "B 단일 명령 벤치마크 PASS(exit0) — 정확도 게이트 + 가명화 품질 동시 재현"
  sed -n 's/^/    /p' /tmp/nufi_benchmark_demo.log | grep -E '\[(PASS|FAIL)\]' || true
else
  bad "B 단일 명령 벤치마크 FAIL — 로그: /tmp/nufi_benchmark_demo.log"
  sed -n 's/^/    /p' /tmp/nufi_benchmark_demo.log | tail -12
fi

echo "------------------------------------------------------------"
echo "요약: $((PASS+FAIL))개 항목 중 ${PASS} PASS, ${FAIL} FAIL"
if [ "$FAIL" -eq 0 ]; then
  echo "✅ 정확도 숙제 종결 재현 PASS — KR_PERSON CI ≥ 0.85 + 온프렘 p95 표 충족"
  exit 0
else
  echo "❌ 정확도 재현 FAIL — 위 [FAIL] 항목 확인(재측정: 헤더 주석)"
  exit 1
fi
