#!/usr/bin/env bash
# Run all linters used by CI (.github/workflows/ci.yml).
# Exits non-zero if any check fails; runs the rest regardless.
set -uo pipefail

cd "$(dirname "$0")/.." || exit 1

fail=0
missing=0

run() {
  local name=$1
  shift
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "==> ${name}: skipped (${1} not installed)"
    missing=1
    return
  fi
  echo "==> ${name}"
  if "$@"; then
    echo "ok"
  else
    fail=1
  fi
}

run "yamllint" yamllint -c .yamllint.yml .

dockerfiles=$(find . -name Dockerfile -not -path './.git/*' -not -path './librechat/source/*')
if [ -n "${dockerfiles}" ]; then
  # shellcheck disable=SC2086
  run "hadolint" hadolint ${dockerfiles}
else
  echo "==> hadolint: no Dockerfiles found"
fi

shell_scripts=$(find scripts -maxdepth 2 -name '*.sh' 2>/dev/null)
if [ -n "${shell_scripts}" ]; then
  # shellcheck disable=SC2086
  run "shellcheck" shellcheck ${shell_scripts}
else
  echo "==> shellcheck: no shell scripts found"
fi

if [ -s docker-compose.yml ]; then
  run "docker compose config" docker compose config --quiet
fi

if [ -d console ]; then
  if command -v bun >/dev/null 2>&1; then
    if [ -d console/node_modules ]; then
      echo "==> biome (console)"
      if (cd console && bun run lint); then
        echo "ok"
      else
        fail=1
      fi
    else
      echo "==> biome (console): skipped (run 'cd console && bun install' first)"
      missing=1
    fi
  else
    echo "==> biome (console): skipped (bun not installed)"
    missing=1
  fi
fi

echo
if [ "${fail}" -ne 0 ]; then
  echo "lint: failures detected"
  exit 1
fi
if [ "${missing}" -ne 0 ]; then
  echo "lint: passed, but some linters were skipped (install with: brew install yamllint shellcheck hadolint)"
  exit 0
fi
echo "lint: all checks passed"
