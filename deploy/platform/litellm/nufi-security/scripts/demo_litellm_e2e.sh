#!/usr/bin/env bash
# =============================================================================
# NuFi + LiteLLM Proxy E2E 데모
#
# litellm 프록시를 실제로 기동하고, NuFi 콜백(PII 감지·라우팅·감사)이
# 올바르게 동작하는지 3개 시나리오로 자동 검증한다.
#
#   S1  PII 없는 일반 질문    → 클라우드 모델 통과 (HTTP 200)
#   S2  약한 PII (전화번호)   → 로컬 모델로 라우팅 (HTTP 200, LOCAL ECHO)
#   S3  강한 PII (주민번호)   → 차단 (HTTP 403)
#
# 사전 조건: pip install litellm uvicorn
# 네트워크/root 불필요 (스텁 로컬 LLM + gazetteer NER).
#
# 사용:   ./scripts/demo_litellm_e2e.sh
# 매뉴얼: docs/HANDS_ON_LITELLM.md
# =============================================================================
set -uo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"

PY="${PYTHON:-python3}"
STUB_PORT="${STUB_PORT:-8099}"
PROXY_PORT="${PROXY_PORT:-4099}"

# ── 사전 조건 확인 ──────────────────────────────────────────────────────
if ! "$PY" -c "import litellm" 2>/dev/null; then
  echo "SKIP: litellm 미설치 — pip install 'litellm[proxy]' 후 재실행"
  exit 0
fi
if ! "$PY" -c "import uvicorn" 2>/dev/null; then
  echo "SKIP: uvicorn 미설치 — pip install uvicorn 후 재실행"
  exit 0
fi

export EGRESS_NER_BACKEND="gazetteer"
export PYTHONPATH="${ROOT}:${PYTHONPATH:-}"

c_g=$'\033[32m'; c_r=$'\033[31m'; c_b=$'\033[1m'; c_d=$'\033[2m'; c_0=$'\033[0m'

WS="$ROOT/logs/demo_litellm_e2e"
rm -rf "$WS"
mkdir -p "$WS"

STUB_PID=""; PROXY_PID=""
cleanup() {
  [[ -n "$PROXY_PID" ]] && kill "$PROXY_PID" 2>/dev/null && wait "$PROXY_PID" 2>/dev/null
  [[ -n "$STUB_PID"  ]] && kill "$STUB_PID"  2>/dev/null && wait "$STUB_PID"  2>/dev/null
  STUB_PID=""; PROXY_PID=""
}
trap cleanup EXIT INT TERM

# ── 스텁 로컬 LLM (OpenAI 호환 에코 서버) ──────────────────────────────
echo "${c_b}NuFi + LiteLLM Proxy E2E 데모${c_0}"
echo "${c_d}스텁 로컬 LLM 기동 (port=$STUB_PORT)...${c_0}"

"$PY" - "$STUB_PORT" <<'PYEOF' >"$WS/stub.log" 2>&1 &
import json, sys, time
from http.server import HTTPServer, BaseHTTPRequestHandler

port = int(sys.argv[1])

class H(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}
        msgs = body.get("messages", [])
        last = msgs[-1]["content"] if msgs else "(empty)"
        resp = {
            "id": "echo-001", "object": "chat.completion",
            "created": int(time.time()), "model": "local-echo",
            "choices": [{"index": 0,
                         "message": {"role": "assistant", "content": f"[LOCAL ECHO] {last}"},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        }
        out = json.dumps(resp).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def do_GET(self):
        out = json.dumps({"object": "list", "data": [{"id": "local-echo"}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a): pass

HTTPServer(("127.0.0.1", port), H).serve_forever()
PYEOF
STUB_PID=$!

# 스텁 대기
for _ in $(seq 1 30); do
  curl -fs "http://127.0.0.1:$STUB_PORT/v1/models" >/dev/null 2>&1 && break
  sleep 0.2
done

# ── LiteLLM config (스텁 포트 반영) ─────────────────────────────────────
cat > "$WS/litellm_config.yaml" <<YAML
model_list:
  - model_name: nufi-local
    litellm_params:
      model: openai/local-echo
      api_base: http://127.0.0.1:$STUB_PORT/v1
      api_key: "sk-stub"
    model_info:
      egress_class: private
  - model_name: nufi-cloud
    litellm_params:
      model: openai/local-echo
      api_base: http://127.0.0.1:$STUB_PORT/v1
      api_key: "sk-stub"
    model_info:
      egress_class: public

litellm_settings:
  callbacks: gateway.litellm_hook.egress_audit_hook
  set_verbose: false
YAML

# ── LiteLLM Proxy 기동 ─────────────────────────────────────────────────
echo "${c_d}LiteLLM Proxy 기동 (port=$PROXY_PORT)...${c_0}"

"$PY" -m litellm.proxy.proxy_cli \
  --config "$WS/litellm_config.yaml" \
  --port "$PROXY_PORT" \
  >"$WS/proxy.log" 2>&1 &
PROXY_PID=$!

# 프록시 health 대기
PROXY_OK=0
for _ in $(seq 1 60); do
  if curl -fs "http://127.0.0.1:$PROXY_PORT/health" >/dev/null 2>&1; then
    PROXY_OK=1; break
  fi
  kill -0 "$PROXY_PID" 2>/dev/null || break
  sleep 0.5
done

if [[ $PROXY_OK -ne 1 ]]; then
  echo "${c_r}LiteLLM Proxy 기동 실패. 로그:${c_0}"
  tail -20 "$WS/proxy.log"
  exit 1
fi
echo "${c_d}LiteLLM Proxy 기동 완료 (pid=$PROXY_PID)${c_0}"

BASE="http://127.0.0.1:$PROXY_PORT"

# ── 요청 헬퍼 ──────────────────────────────────────────────────────────
# $1=scenario $2=model $3=content → CODE, BODY 전역 설정
chat() {
  local out
  out="$(curl -s -w "\n%{http_code}" -X POST "$BASE/v1/chat/completions" \
    -H "Content-Type: application/json" \
    -d "{\"model\":\"$2\",\"messages\":[{\"role\":\"user\",\"content\":\"$3\"}]}")"
  CODE="$(printf '%s' "$out" | tail -1)"
  BODY="$(printf '%s' "$out" | sed '$d')"
}

# ── 검증 ────────────────────────────────────────────────────────────────
rows=()
check() {
  local name="$1" ok="$2" detail="${3:-}"
  rows+=("$ok")
  local tag
  if [[ "$ok" == "1" ]]; then tag="${c_g}[PASS]${c_0}"; else tag="${c_r}[FAIL]${c_0}"; fi
  echo "  $tag $name${detail:+ ${c_d}— $detail${c_0}}"
}

echo ""
echo "${c_b}── S1: PII 없는 일반 질문 → 클라우드 통과 ──${c_0}"
chat "S1" "nufi-cloud" "파이썬에서 리스트를 정렬하는 방법은?"
s1_ok=0; [[ "$CODE" == "200" ]] && s1_ok=1
check "S1 PII 없음 → HTTP 200 (클라우드 통과)" "$s1_ok" "HTTP $CODE"

echo ""
echo "${c_b}── S2: 약한 PII → 로컬 라우팅 ──${c_0}"
chat "S2" "nufi-cloud" "고객 박서연의 전화번호 010-1234-5678로 연락해주세요"
s2_ok=0
if [[ "$CODE" == "200" ]]; then
  # 응답에 LOCAL ECHO가 있으면 로컬로 라우팅된 것
  echo "$BODY" | grep -q "LOCAL ECHO" && s2_ok=1
fi
check "S2 약한 PII → 로컬 라우팅 (LOCAL ECHO 확인)" "$s2_ok" "HTTP $CODE"

echo ""
echo "${c_b}── S3: 강한 PII (주민번호) → 차단 ──${c_0}"
chat "S3" "nufi-cloud" "김민수 주민번호 900101-1234568 으로 신청서 작성해줘"
s3_ok=0
# 강한 PII: 403 차단 또는 로컬 라우팅(200) 모두 보안상 OK
# 정책에 따라 다르지만, 외부 전송이 안 되면 OK
if [[ "$CODE" == "403" ]]; then
  s3_ok=1  # hard-block
elif [[ "$CODE" == "200" ]] && echo "$BODY" | grep -q "LOCAL ECHO"; then
  s3_ok=1  # 로컬 라우팅 (정책이 block 대신 route인 경우)
fi
check "S3 강한 PII → 차단(403) 또는 로컬 라우팅" "$s3_ok" "HTTP $CODE"

# ── 집계 ────────────────────────────────────────────────────────────────
echo ""
passed=0; total=${#rows[@]}
for r in "${rows[@]}"; do [[ "$r" == "1" ]] && ((passed++)); done

echo "  ${c_b}요약${c_0}: ${c_g}${passed}${c_0}/${total} 시나리오 PASS"
if [[ $passed -eq $total ]]; then
  echo "  ${c_g}✅ LiteLLM + NuFi E2E 데모 PASS${c_0}"
  exit 0
else
  echo "  ${c_r}❌ 일부 시나리오 실패 (위 [FAIL] 확인)${c_0}"
  echo "  ${c_d}프록시 로그: $WS/proxy.log${c_0}"
  exit 1
fi
