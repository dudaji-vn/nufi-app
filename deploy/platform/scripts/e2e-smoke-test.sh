#!/usr/bin/env bash
# End-to-end smoke test for W2 Task 2.2.
#
# Runs scripts/e2e/e2e_smoke_test.py inside the compose network (so it can
# reach librechat:3080 and langfuse-web:3000 by service name). Sources .env so
# E2E_USER_PASSWORD / LANGFUSE_*_KEY land in the container.
#
# Usage:
#     ./scripts/e2e-smoke-test.sh             # run the test
#     ./scripts/e2e-smoke-test.sh --rebuild   # rebuild the e2e image first
set -euo pipefail
cd "$(dirname "$0")/.."

REBUILD=0
for arg in "$@"; do
  case "$arg" in
    --rebuild) REBUILD=1 ;;
    -h | --help)
      sed -n '2,12p' "$0"
      exit 0
      ;;
    *)
      echo "unknown argument: $arg (try --help)" >&2
      exit 1
      ;;
  esac
done

if [ ! -f .env ]; then
  echo "error: .env missing — run ./scripts/bootstrap.sh first" >&2
  exit 1
fi

# Load .env so the e2e service inherits secrets (compose's env_file: would
# also work, but sourcing here lets us fail fast with a clear message if a
# required var is missing).
set -a
# shellcheck disable=SC1091
. ./.env
set +a

: "${E2E_USER_PASSWORD:?E2E_USER_PASSWORD is unset (see .env.example)}"
: "${LANGFUSE_PUBLIC_KEY:?LANGFUSE_PUBLIC_KEY is unset}"
: "${LANGFUSE_SECRET_KEY:?LANGFUSE_SECRET_KEY is unset}"

if [ "$REBUILD" -eq 1 ]; then
  docker compose --profile e2e build e2e-test
fi

# `--rm` cleans the container up; profile keeps the service out of `up -d`.
docker compose --profile e2e run --rm e2e-test
