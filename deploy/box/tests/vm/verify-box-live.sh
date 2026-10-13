#!/usr/bin/env bash
# verify-box-live.sh — end-to-end health check run ON a live box (over SSH, or
# in the box's own shell). The companion verify-ubuntu-box.sh drives a fresh
# Lima install from the Mac over TLS; this one proves an already-running box —
# any box, LAN or mesh — still works, from the inside, in the order a customer
# meets it:
#
#   1. nufi-box doctor is clean
#   2. every product answers over TLS behind the box CA
#   3. the box is on the mesh coordinator
#   4. the model answers (on the GPU if the box has one)
#   5. a document dropped in a drive is embedded and the agent cites it
#   6. a Works agent-run lands in a gVisor sandbox (only if Works is installed)
#
# Usage, from the box (or `ssh <box> 'bash ~/nufi/deploy/box/tests/vm/verify-box-live.sh'`):
#   bash deploy/box/tests/vm/verify-box-live.sh
#
# Exits non-zero if any box check fails. A model's own wrong answer is not a
# box failure: step 5 asserts a citation, never the answer's correctness.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
BOX="$(cd "$HERE/../.." && pwd)"                 # tests/vm -> deploy/box
SCN="$(cd "$BOX/../platform/scenarios" && pwd)"  # deploy/platform/scenarios
CA="$BOX/data/nufi-box-ca.crt"
HOST="$(sed -n 's/^BOX_HOST=//p' "$BOX/.env" 2>/dev/null)"; HOST="${HOST:-nufi.local}"
cd "$BOX" || { echo "no box dir at $BOX"; exit 9; }
P=0; F=0
ok(){ printf '  \033[1;32mPASS\033[0m %s\n' "$*"; P=$((P+1)); }
bad(){ printf '  \033[1;31mFAIL\033[0m %s\n' "$*"; F=$((F+1)); }
note(){ printf '       %s\n' "$*"; }
h(){ printf '\n\033[1;34m== %s ==\033[0m\n' "$*"; }

h "1. nufi-box doctor (box self-check)"
./nufi-box doctor > /tmp/e2e-doctor.txt 2>&1 || true
sed 's/^/     /' /tmp/e2e-doctor.txt
if grep -qiE 'fail|error|not (registered|reachable|running)' /tmp/e2e-doctor.txt; then bad "doctor reported problems (above)"; else ok "doctor clean"; fi

h "2. HTTP endpoints over TLS (box CA)"
ep(){ # name port path
  local c; c=$(curl -sS --max-time 20 --cacert "$CA" --connect-to "$HOST:$2:127.0.0.1:$2" \
      -o /dev/null -w '%{http_code}' "https://$HOST:$2$3" 2>/dev/null)
  case "$c" in 2??|3??) ok "$1 :$2$3 -> HTTP $c";; *) bad "$1 :$2$3 -> HTTP ${c:-no-response}";; esac; }
ep chat 3080 /health
ep console 3001 /
ep admin 3002 /
ep owner-console 3009 /
grep -qx NUFI_WORKS=1 "$BOX/.env" && ep works 3003 /api/health
ep studio 7860 /

h "3. mesh (joined the coordinator, reachable from home)"
if grep -qE '^MESH_SERVER_URL=.+' "$BOX/.env"; then
  ./nufi-box mesh status > /tmp/e2e-mesh.txt 2>&1 || true
  grep -qE '100\.64\.' /tmp/e2e-mesh.txt && ok "box has a mesh address ($(sed -n 's/^BOX_MESH_HOST=//p' "$BOX/.env"))" || bad "no mesh address (see nufi-box mesh status)"
else note "not a mesh box (no MESH_SERVER_URL) — skipping"; fi

h "4. GPU/model inference"
ANS=$(docker exec nufi-box-rag_api-1 python -c '
import os,urllib.request,json
u=os.environ["OLLAMA_BASE_URL"].rstrip("/")+"/api/generate"
d=json.dumps({"model":os.environ.get("E2E_MODEL","qwen2.5:7b"),"prompt":"Reply with one word: PONG","stream":False}).encode()
r=urllib.request.urlopen(urllib.request.Request(u,d,{"content-type":"application/json"}),timeout=120)
print(json.load(r)["response"].strip())
' 2>/dev/null)
[ -n "$ANS" ] && ok "model answered: \"$ANS\"" || bad "no model response"
VRAM=$(nvidia-smi --query-compute-apps=process_name,used_memory --format=csv,noheader 2>/dev/null | grep -i llama | head -1)
[ -n "$VRAM" ] && ok "GPU in use: $VRAM" || note "no GPU in use (CPU box, or model unloaded — not a failure)"

h "5. RAG end-to-end (document in a drive -> agent answers with citation)"
python3 - "$SCN" > /tmp/e2e-doc.sh <<'PY'
import base64,json,sys,pathlib
depts=json.load(open(pathlib.Path(sys.argv[1])/"departments.json"))["departments"]
doc=next(d for d in depts if d["id"]=="legal")["documents"][0]
print("DOC_NAME_B64="+base64.b64encode(doc["name"].encode()).decode())
print("DOC_TEXT_B64="+base64.b64encode(doc["text"].encode()).decode())
PY
source /tmp/e2e-doc.sh
DOC_NAME=$(printf %s "$DOC_NAME_B64" | base64 -d)
printf %s "$DOC_TEXT_B64" | base64 -d > "$BOX/data/drives/legal/$DOC_NAME"
if [ -s "$BOX/data/drives/legal/$DOC_NAME" ]; then ok "dropped '$DOC_NAME' into drives/legal"; else bad "could not write to drives/legal (drive uid? nufi-box doctor)"; fi
note "waiting for nufi-ingest to embed it (up to 5 min)..."
EMB=""
for _ in $(seq 1 60); do
  EMB=$(docker compose logs --no-log-prefix nufi-ingest 2>&1 | grep -a 'embedded=True' | grep -aF "legal/$DOC_NAME" | tail -1)
  [ -n "$EMB" ] && break; sleep 5
done
# A soft note, not a failure: on a box that already holds this document, or
# whose nufi-ingest was recently recreated (an update resets its log), no fresh
# "embedded=True" line appears even though the embedding is in the store. The
# agent-citation check below is the authoritative RAG proof, so gate on that.
[ -n "$EMB" ] && ok "nufi-ingest embedded it" || note "no fresh embedded=True in the ingest log (already embedded, or its log was reset by a recent recreate) — the citation check below is the real RAG proof"
EMAIL=$(sed -n 's/^ADMIN_EMAIL=//p' "$BOX/.env"); PASS=$(sed -n 's/^ADMIN_PASSWORD=//p' "$BOX/.env")
rm -rf /tmp/e2e-ev /tmp/e2e-dr; mkdir -p /tmp/e2e-ev /tmp/e2e-dr
( cd "$SCN" && python3 run_box.py --base "https://$HOST:3080" --email "$EMAIL" --password "$PASS" \
    --drives /tmp/e2e-dr --only legal --timeout 300 \
    --cacert "$CA" --connect-to "$HOST:3080:127.0.0.1:3080" --out /tmp/e2e-ev ) > /tmp/e2e-agent.log 2>&1 || true
if [ -f /tmp/e2e-ev/box.md ]; then
  CITED=$(grep "sources:" /tmp/e2e-ev/box.md 2>/dev/null | grep -v "sources: none$")
  [ -n "$CITED" ] && ok "agent answered WITH a citation" || bad "agent cited nothing (every sources: none)"
  note "answers (the model's own, verbatim):"; grep -E '→ (PASS|FAIL)' /tmp/e2e-ev/box.md | sed 's/^/       /'
else
  bad "run_box.py produced no evidence"; tail -8 /tmp/e2e-agent.log | sed 's/^/       /'
fi

h "6. Works — agent runs land in a gVisor sandbox"
if grep -qx NUFI_WORKS=1 "$BOX/.env"; then
  IMG=$(sed -n 's/^WORKS_SANDBOX_IMAGE=//p' "$BOX/.env")
  if [ -n "$IMG" ]; then
    KERNEL=$(docker run --rm --runtime=runsc --init --read-only --cap-drop ALL --network works-sandbox "$IMG" uname -r 2>/dev/null)
    case "$KERNEL" in *gvisor*) ok "sandbox kernel: $KERNEL (gVisor in effect; host $(uname -r))";; *) bad "sandbox kernel: ${KERNEL:-none} (runsc NOT in effect)";; esac
  else bad "no WORKS_SANDBOX_IMAGE in .env"; fi
else note "Works not installed (NUFI_WORKS!=1) — skipping"; fi

printf '\n\033[1m=== E2E SUMMARY: %d passed, %d failed ===\033[0m\n' "$P" "$F"
[ "$F" -eq 0 ] && echo "The box is working well." || echo "Some checks failed — see above."
echo "$F" > /tmp/e2e.fails
exit "$F"
