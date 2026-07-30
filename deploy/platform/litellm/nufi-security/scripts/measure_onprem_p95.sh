#!/usr/bin/env bash
# CMP-147 — 온프렘 p95 재측정 1-명령 러너 (per-channel INT8 NER)
# -----------------------------------------------------------------------------
# CMP-145 ②의 분리추적(승인 6e02b6aa 리스크경로). 실제 온프렘(프로덕션 사양)
# 하드웨어가 확보되면 이 스크립트 1건을 그 박스에서 실행 → 측정표 commit 으로 종결.
#
# 핵심: 측정 결과가 dev-env 수치로 오인되지 않도록 호스트 사양(provenance)을
#       산출물에 박아 넣는다. 비프로덕션 박스에서 돌리면 [NON-PROD] 경고를 출력하고
#       산출물 파일명/표 헤더에 host_class=non-production 을 기록한다.
#
# 사용:
#   PYTHONPATH=~/.cache/m5_libs bash scripts/measure_onprem_p95.sh
#   # 대표 사양 인스턴스로 라벨 강제:  HOST_CLASS=production bash scripts/measure_onprem_p95.sh
# -----------------------------------------------------------------------------
set -euo pipefail
cd "$(dirname "$0")/.."

BACKEND="onnx-int8"
OUT_DIR="docs/reports"
NOLOAD_JSON="$OUT_DIR/CMP-147-onprem-int8-noload.json"
LOAD_JSON="$OUT_DIR/CMP-147-onprem-load.json"
PROV_JSON="$OUT_DIR/CMP-147-onprem-host.json"
TABLE_MD="$OUT_DIR/CMP-147-onprem-p95.md"
: "${PYTHONPATH:=$HOME/.cache/m5_libs}"
export PYTHONPATH

# --- 호스트 provenance 채집 (절대값 신뢰를 위한 사양 기록) -----------------------
CPU_MODEL="$(grep -m1 'model name' /proc/cpuinfo 2>/dev/null | cut -d: -f2- | sed 's/^ *//' || echo unknown)"
CPU_CORES="$(nproc 2>/dev/null || echo unknown)"
GOVERNOR="$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null || echo unknown)"
MEM_GB="$(awk '/MemTotal/ {printf "%.1f", $2/1024/1024}' /proc/meminfo 2>/dev/null || echo unknown)"
KERNEL="$(uname -srm 2>/dev/null || echo unknown)"
# 비프로덕션 휴리스틱: WSL2/노트북(-1360P 등 모바일 P-코어) 은 non-production.
HOST_CLASS="${HOST_CLASS:-}"
if [ -z "$HOST_CLASS" ]; then
  if echo "$KERNEL$CPU_MODEL" | grep -Eqi 'microsoft|WSL|1360P|-[0-9]+P\b|laptop'; then
    HOST_CLASS="non-production"
  else
    HOST_CLASS="unverified"   # 사람이 production 으로 확정 라벨링하면 HOST_CLASS=production
  fi
fi

mkdir -p "$OUT_DIR"
cat > "$PROV_JSON" <<EOF
{
  "issue": "CMP-147",
  "host_class": "$HOST_CLASS",
  "cpu_model": "$CPU_MODEL",
  "cpu_cores": "$CPU_CORES",
  "scaling_governor": "$GOVERNOR",
  "mem_total_gb": "$MEM_GB",
  "kernel": "$KERNEL",
  "backend": "$BACKEND",
  "model_stack": "PYTHONPATH=$PYTHONPATH ; INT8 ONNX ~/.cache/m5_onnx_int8/int8 (per-channel) ; Leo97/KoELECTRA-small-v3-modu-ner"
}
EOF

echo "================================================================"
echo " CMP-147 온프렘 p95 측정 — host_class=$HOST_CLASS"
echo "   CPU : $CPU_MODEL ($CPU_CORES cores, gov=$GOVERNOR, ${MEM_GB}GB)"
echo "   stack: PYTHONPATH=$PYTHONPATH"
echo "================================================================"
if [ "$HOST_CLASS" = "non-production" ]; then
  echo "[NON-PROD] 이 박스는 비프로덕션 — 산출 절대값은 dev-env 인터림(참고치)일 뿐"
  echo "[NON-PROD] 운영 용량 산정 근거 아님. 프로덕션 사양에서 재실행 필요(CMP-147 블로커)."
fi

# --- ① 무부하 버킷 (≤128 / 512(NFR2) / 2048) -----------------------------------
echo; echo "[1/2] 무부하 버킷 측정 → $NOLOAD_JSON"
python3 scripts/bench_m5.py --backend "$BACKEND" --split test --json-out "$NOLOAD_JSON" \
  | tail -n 3 || { echo "[FAIL] bench_m5 — 모델 스택(PYTHONPATH=~/.cache/m5_libs) 확인"; exit 1; }

# --- ② 동시성·지속부하 (NFR2 512자) -------------------------------------------
echo; echo "[2/2] 동시성·지속부하 측정 → $LOAD_JSON"
python3 scripts/bench_load.py --backend "$BACKEND" --concurrency 1,2,4,8 \
  --requests 200 --chars 512 --sustain-seconds 10 --sustain-concurrency 4 \
  --json-out "$LOAD_JSON" | tail -n 3 || { echo "[FAIL] bench_load"; exit 1; }

# --- 측정표(markdown) 생성 — host provenance 헤더 포함 --------------------------
python3 - "$PROV_JSON" "$NOLOAD_JSON" "$LOAD_JSON" "$TABLE_MD" <<'PY'
import json, sys
prov, noload, load, out = (json.load(open(p, encoding="utf-8")) if i < 3 else p
                           for i, p in enumerate(sys.argv[1:5]))
b = noload.get("latency", {}).get("buckets", {})
def row(k, label):
    d = b.get(k, {})
    return f"| {label} | {d.get('p50','—')} | **{d.get('p95','—')}** | {d.get('p99','—')} | {d.get('req_per_s','—')} |"
lines = [
    "# CMP-147 — 온프렘 p95 측정표 (per-channel INT8 NER)",
    "",
    f"- **host_class:** `{prov['host_class']}`  ·  **CPU:** {prov['cpu_model']} "
    f"({prov['cpu_cores']} cores, governor={prov['scaling_governor']}, {prov['mem_total_gb']}GB)",
    f"- **kernel:** {prov['kernel']}",
    f"- **backend:** {prov['backend']}  ·  **stack:** {prov['model_stack']}",
    "",
]
if prov["host_class"] != "production":
    lines += [
        f"> ⚠️ **host_class={prov['host_class']} — 이 표는 프로덕션 측정이 아니다.** "
        "운영 용량 산정 근거로 인용 금지. 프로덕션 사양에서 `HOST_CLASS=production` 으로 재실행 필요.",
        "",
    ]
lines += [
    "## 무부하 버킷 p95",
    "",
    "| 입력 | p50 | **p95** | p99 | req/s |",
    "|---|---|---|---|---|",
    row("<=128", "≤128자"),
    row("512", "**512자(NFR2)**"),
    row("2048", "2048자"),
    "",
    "## 동시성·지속부하 (512자)",
    "",
    "```json",
    json.dumps(load.get("levels", load), ensure_ascii=False, indent=2)[:2000],
    "```",
    "",
]
open(out, "w", encoding="utf-8").write("\n".join(lines) + "\n")
print(f"[written] {out}")
PY

echo; echo "================================================================"
echo " 산출: $NOLOAD_JSON · $LOAD_JSON · $PROV_JSON · $TABLE_MD"
if [ "$HOST_CLASS" = "production" ]; then
  echo " host_class=production → 측정표 commit 으로 CMP-147 종결 가능."
else
  echo " host_class=$HOST_CLASS → 인터림(참고치). CMP-147 은 프로덕션 사양 재실행까지 blocked."
fi
echo "================================================================"
