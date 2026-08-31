#!/usr/bin/env bash
#
# Runs the MeshBox adapter suites.
#
# They need their own runner for two reasons. `pyproject.toml` sets
# `testpaths = ["tests"]`, so a bare `pytest` never collects `adapters/` at all
# -- the three adapters were linted but never once tested in CI, on the seam the
# entire appliance integration rides. And each adapter directory holds a
# same-named `test_adapter.py`, which pytest refuses to import together without
# packages. Running each as a script in its own directory solves both, and is
# how the files are written (each has a main() and exits 0 on pass).
set -uo pipefail

cd "$(dirname "$0")/.." || exit 1
PY="${PYTHON:-python3}"
fail=0

for suite in adapters/*/test_*.py; do
  [ -e "$suite" ] || continue
  dir=$(dirname "$suite")
  name=$(basename "$suite")
  printf '==> %s\n' "$suite"
  if ( cd "$dir" && "$PY" "$name" >/tmp/adapter-suite.$$ 2>&1 ); then
    tail -1 /tmp/adapter-suite.$$
  else
    cat /tmp/adapter-suite.$$
    printf 'FAIL %s\n' "$suite"
    fail=1
  fi
  rm -f /tmp/adapter-suite.$$
done

if (( fail )); then
  echo "FAILED — one or more adapter suites did not pass."
else
  echo "OK — every adapter suite passed."
fi
exit "$fail"
