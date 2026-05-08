#!/usr/bin/env bash
# Smoke test for the LiteLLM Proxy.
# Covers W1 Task 1.1 acceptance: liveness, models, chat, streaming, error.
set -euo pipefail

PROXY_URL="${PROXY_URL:-http://localhost:4000}"
MODEL="${MODEL:-llama-3-gpu}"

# Source .env if LITELLM_MASTER_KEY isn't already in the environment.
if [ -z "${LITELLM_MASTER_KEY:-}" ] && [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . .env
  set +a
fi

if [ -z "${LITELLM_MASTER_KEY:-}" ]; then
  echo "error: LITELLM_MASTER_KEY is not set (export it or put it in .env)" >&2
  exit 1
fi

AUTH=(-H "Authorization: Bearer ${LITELLM_MASTER_KEY}")
JSON=(-H "Content-Type: application/json")

echo "==> 1/7 Liveness"
curl -fsS "${PROXY_URL}/health/liveliness"
echo

echo "==> 2/7 Model list"
curl -fsS "${AUTH[@]}" "${PROXY_URL}/v1/models" >/dev/null
echo "ok"

echo "==> 3/7 Chat completion"
curl -fsS "${AUTH[@]}" "${JSON[@]}" \
  -X POST "${PROXY_URL}/v1/chat/completions" \
  -d "{\"model\":\"${MODEL}\",\"messages\":[{\"role\":\"user\",\"content\":\"ping\"}],\"max_tokens\":10}" \
  >/dev/null
echo "ok"

echo "==> 4/7 Streaming"
curl -fsSN "${AUTH[@]}" "${JSON[@]}" \
  -X POST "${PROXY_URL}/v1/chat/completions" \
  -d "{\"model\":\"${MODEL}\",\"messages\":[{\"role\":\"user\",\"content\":\"ping\"}],\"max_tokens\":10,\"stream\":true}" \
  >/dev/null
echo "ok"

echo "==> 5/7 Error handling (unknown model should 4xx)"
status=$(curl -s -o /dev/null -w '%{http_code}' "${AUTH[@]}" "${JSON[@]}" \
  -X POST "${PROXY_URL}/v1/chat/completions" \
  -d '{"model":"does-not-exist","messages":[{"role":"user","content":"ping"}]}')
if [ "${status}" -lt 400 ] || [ "${status}" -ge 500 ]; then
  echo "error: expected a 4xx for unknown model, got ${status}" >&2
  exit 1
fi
echo "ok (got ${status})"

echo "==> 6/7 Langfuse trace exists for the chat request"
LANGFUSE_PUBLIC_HOST="${LANGFUSE_PUBLIC_HOST:-http://localhost:3000}"
if [ -z "${LANGFUSE_PUBLIC_KEY:-}" ] || [ -z "${LANGFUSE_SECRET_KEY:-}" ]; then
  echo "skipped (LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY not set)"
else
  # `python3` on macOS/Linux, `python` on Windows Git Bash — pick whichever exists.
  PY=$(command -v python3 || command -v python || true)
  if [ -z "${PY}" ]; then
    echo "error: neither python3 nor python found in PATH" >&2
    exit 1
  fi
  # LiteLLM ships traces async, and on a fresh `bootstrap` the langfuse-worker
  # may still be warming its ClickhouseWriter when the chat request lands —
  # poll for up to 30s instead of a one-shot query after a fixed sleep.
  count=0
  for _ in $(seq 1 15); do
    count=$(curl -fsS -u "${LANGFUSE_PUBLIC_KEY}:${LANGFUSE_SECRET_KEY}" \
      "${LANGFUSE_PUBLIC_HOST}/api/public/traces?limit=1" |
      "${PY}" -c 'import sys,json; d=json.load(sys.stdin); print(len(d.get("data",[])))')
    [ "${count}" -ge 1 ] && break
    sleep 2
  done
  if [ "${count}" -lt 1 ]; then
    echo "error: no traces visible in Langfuse after 30s — check langfuse-worker logs" >&2
    exit 1
  fi
  echo "ok (${count} trace(s) visible)"
fi

echo "==> 7/7 Prometheus has scraped the LiteLLM request counter"
PROMETHEUS_URL="${PROMETHEUS_URL:-http://localhost:9090}"
# Wait one full scrape interval (15s) plus a small buffer so the chat
# request from step 3 lands in a scrape window before we query.
sleep 18
PY=$(command -v python3 || command -v python || true)
if [ -z "${PY}" ]; then
  echo "error: neither python3 nor python found in PATH" >&2
  exit 1
fi
count=$(curl -fsSG "${PROMETHEUS_URL}/api/v1/query" \
  --data-urlencode 'query=sum(litellm_proxy_total_requests_metric_total)' |
  "${PY}" -c 'import sys,json
d=json.load(sys.stdin)
r=d.get("data",{}).get("result",[])
print(int(float(r[0]["value"][1])) if r else 0)')
if [ "${count}" -lt 1 ]; then
  echo "error: prometheus has no litellm_proxy_total_requests_metric_total data — check the scrape config and litellm /metrics" >&2
  exit 1
fi
echo "ok (cumulative request count = ${count})"

echo
echo "all checks passed"
