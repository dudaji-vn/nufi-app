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

echo "==> 1/5 Liveness"
curl -fsS "${PROXY_URL}/health/liveliness"
echo

echo "==> 2/5 Model list"
curl -fsS "${AUTH[@]}" "${PROXY_URL}/v1/models" >/dev/null
echo "ok"

echo "==> 3/5 Chat completion"
curl -fsS "${AUTH[@]}" "${JSON[@]}" \
  -X POST "${PROXY_URL}/v1/chat/completions" \
  -d "{\"model\":\"${MODEL}\",\"messages\":[{\"role\":\"user\",\"content\":\"ping\"}],\"max_tokens\":10}" \
  >/dev/null
echo "ok"

echo "==> 4/5 Streaming"
curl -fsSN "${AUTH[@]}" "${JSON[@]}" \
  -X POST "${PROXY_URL}/v1/chat/completions" \
  -d "{\"model\":\"${MODEL}\",\"messages\":[{\"role\":\"user\",\"content\":\"ping\"}],\"max_tokens\":10,\"stream\":true}" \
  >/dev/null
echo "ok"

echo "==> 5/5 Error handling (unknown model should 4xx)"
status=$(curl -s -o /dev/null -w '%{http_code}' "${AUTH[@]}" "${JSON[@]}" \
  -X POST "${PROXY_URL}/v1/chat/completions" \
  -d '{"model":"does-not-exist","messages":[{"role":"user","content":"ping"}]}')
if [ "${status}" -lt 400 ] || [ "${status}" -ge 500 ]; then
  echo "error: expected a 4xx for unknown model, got ${status}" >&2
  exit 1
fi
echo "ok (got ${status})"

echo
echo "all checks passed"
