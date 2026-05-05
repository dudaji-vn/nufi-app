#!/usr/bin/env bash
# console-smoke-test.sh — drive the W3 console end-to-end against a
# running stack. Auto-loads .env, sanity-checks the console is reachable,
# then runs the Bun TypeScript test in console/scripts/smoke.ts.
#
# Usage:
#   ./scripts/console-smoke-test.sh
#   CONSOLE_URL=https://console.staging ./scripts/console-smoke-test.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# Load .env so E2E_USER_EMAIL / E2E_USER_PASSWORD are visible to bun.
if [[ -f .env ]]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
fi

CONSOLE_URL="${CONSOLE_URL:-http://localhost:3001}"
LIBRECHAT_URL="${LIBRECHAT_URL:-http://localhost:3080}"
LITELLM_URL="${LITELLM_URL:-http://localhost:4000}"

# Required env
: "${E2E_USER_EMAIL:?E2E_USER_EMAIL not set in .env}"
: "${E2E_USER_PASSWORD:?E2E_USER_PASSWORD not set in .env}"

# Sanity-check the three services are reachable. Fail fast with a helpful
# message instead of letting the test fail with confusing errors.
check() {
    local name="$1" url="$2"
    if ! curl -fsS --max-time 3 "$url" >/dev/null 2>&1; then
        echo "✗ $name not reachable at $url" >&2
        echo "  (run \`docker compose up -d\` first)" >&2
        return 1
    fi
}

check "Console" "$CONSOLE_URL/_health" || exit 2
check "LibreChat" "$LIBRECHAT_URL/api/health" || exit 2
check "LiteLLM" "$LITELLM_URL/health/liveliness" || exit 2

# Hand off to the Bun test runner.
export CONSOLE_URL LIBRECHAT_URL LITELLM_URL
cd console
exec bun run scripts/smoke.ts
