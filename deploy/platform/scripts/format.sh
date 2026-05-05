#!/usr/bin/env bash
# Auto-format YAML and shell scripts to match the rules in .yamllint.yml /
# CI shellcheck. Run before committing if your IDE's format-on-save drifts.
set -uo pipefail

cd "$(dirname "$0")/.." || exit 1

fail=0
missing=0

ensure() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "==> $1: not installed (skipped)"
    missing=1
    return 1
  fi
  return 0
}

if ensure yamlfmt; then
  echo "==> yamlfmt"
  if yamlfmt -conf .yamlfmt .; then
    echo "ok"
  else
    fail=1
  fi
fi

if ensure shfmt; then
  echo "==> shfmt (2-space, indent switch cases)"
  # -i 2: 2-space indent · -ci: indent switch cases · -bn: binary ops at line start
  shell_scripts=$(find scripts -maxdepth 2 -name '*.sh' 2>/dev/null)
  if [ -n "${shell_scripts}" ]; then
    # shellcheck disable=SC2086
    if shfmt -i 2 -ci -w ${shell_scripts}; then
      echo "ok"
    else
      fail=1
    fi
  else
    echo "no shell scripts found"
  fi
fi

if [ -d console ] && ensure bun; then
  if [ -d console/node_modules ]; then
    echo "==> biome (console — applies safe lint fixes + formats)"
    if (cd console && bun run lint:fix); then
      echo "ok"
    else
      fail=1
    fi
  else
    echo "==> biome (console): skipped (run 'cd console && bun install' first)"
    missing=1
  fi
fi

echo
if [ "${fail}" -ne 0 ]; then
  echo "format: errors during formatting"
  exit 1
fi
if [ "${missing}" -ne 0 ]; then
  echo "format: done (some formatters missing — install with: brew install yamlfmt shfmt)"
  exit 0
fi
echo "format: done"
