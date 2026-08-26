#!/usr/bin/env bash
#
# Fail if a string the backend renders into the UI still carries the upstream
# product name.
#
# check-brand-css.sh covers the compiled frontend, which is where almost all
# user-visible text lives -- nufi/rebrand.ts rewrites it at build time. But the
# rebrand plugin is a Vite plugin: it sees .ts/.tsx/.json under src/frontend
# and nothing else. Component metadata comes from Python on the backend,
# travels over the API, and is rendered verbatim on the canvas. That is a hole
# the frontend guards cannot see into.
#
# It was not theoretical. While building the hands-on scenarios, the Knowledge
# node sat in the middle of the flagship RAG demo reading "Ingest into or
# retrieve from a Langflow knowledge base", with every existing guard green.
# Six component descriptions and the default agent system prompt were in the
# same state, the latter baked into eight starter templates as well -- so a
# fresh Agent dropped on the canvas introduced itself as "a Langflow Agent".
#
# The check is a grep rather than a build because these strings are literals in
# source: there is nothing to compile and no ambiguity about what ships. It is
# deliberately narrow -- only the fields that reach a user's eyes:
#
#   description = "..."      component subtitle on the canvas and in the palette
#   info="..."               the tooltip on a field
#   "description": "..."     the same, inside generated/serialised JSON
#   You are a Langflow Agent the default agent instructions
#
# Code bodies, module paths, upstream URLs and the lower-case `langflow.*`
# import namespace are all left alone: they are not shown to anyone, and
# rewriting them would break the fork's ability to take upstream changes.
# Tests are excluded for the same reason -- they assert on upstream's own
# strings.
#
# Usage: apps/nufi-agent/nufi/check-backend-brand.sh
# Exits 0 when no user-facing backend string names the upstream product.

set -euo pipefail

cd "$(dirname "$0")/.."   # apps/nufi-agent

SEARCH_ROOTS=(
  "src/lfx/src/lfx/components"
  "src/lfx/src/lfx/base"
  "src/lfx/src/lfx/_assets"
  "src/backend/base/langflow/components"
  "src/backend/base/langflow/initial_setup/starter_projects"
)

EXISTING=()
for root in "${SEARCH_ROOTS[@]}"; do
  [[ -e "$root" ]] && EXISTING+=("$root")
done
if ((${#EXISTING[@]} == 0)); then
  echo "None of the expected backend source roots exist -- has the layout changed?"
  exit 1
fi

# One pattern per class of user-facing string. `grep -E` alternation keeps this
# a single pass over the tree.
PATTERN='description = "[^"]*Langflow|info="[^"]*Langflow|"description": "[^"]*Langflow|You are a Langflow Agent'

# --exclude-dir keeps upstream's own tests (which assert on upstream strings)
# and vendored node_modules out of the result. `|| true` because grep exits 1
# when it finds nothing, which is the PASS case, and `set -e` would kill the
# script before the count is read.
HITS="$({ grep -rnE "$PATTERN" "${EXISTING[@]}" \
    --exclude-dir=tests --exclude-dir=__tests__ --exclude-dir=node_modules \
    2>/dev/null || true; })"

# `grep -c` exits 1 when the count is zero -- the PASS case -- and `set -e`
# would kill the script here before the check below ever runs. Same trap the
# pipefail comments in check-brand-css.sh describe.
COUNT="$({ printf '%s' "$HITS" | grep -c . || true; } | tr -d '[:space:]')"

if [[ "$COUNT" -ne 0 ]]; then
  echo "MISSING ${COUNT} backend string(s) still name the upstream product:"
  printf '%s\n' "$HITS" | cut -c1-160 | sed 's/^/  /'
  cat <<'MSG'

These are rendered verbatim in the UI. The build-time rebrand transform is
frontend-only (see nufi/README.md "Rebrand boundary: frontend only"), so the
product name has to be correct at the source.

If a `git subtree pull` reintroduced them, re-apply the rename. If it is a new
string from upstream, rename it here and add the file to ALLOWLIST in
check-fork-diff.sh.
MSG
  exit 1
fi

# ---------------------------------------------------------------------------
# The component index carries its own SHA256, and renaming strings inside it
# invalidates that hash.
#
# The failure is quiet and costs real time. lfx/interface/components.py checks
# the hash and `return None` on a mismatch, so Langflow silently discards the
# prebuilt index and rescans every component at boot -- while logging
# "integrity check failed ... may be corrupted or tampered", which reads to
# whoever finds it like a security incident rather than a stale checksum.
#
# This went unnoticed from the moment the first brand string was edited into
# the file. Hence a check rather than a note.
#
# The hash is computed the same way components.py computes it. stdlib json
# reproduces orjson's OPT_SORT_KEYS output byte for byte here, so this needs no
# dependency beyond python3.
INDEX="src/lfx/src/lfx/_assets/component_index.json"

if [[ -f "$INDEX" ]]; then
  if ! python3 - "$INDEX" <<'PYCHECK'
import hashlib, json, sys

path = sys.argv[1]
with open(path, encoding="utf-8") as fh:
    blob = json.load(fh)

stored = blob.pop("sha256", None)
if not stored:
    print(f"MISSING {path} has no sha256 field")
    sys.exit(1)

calc = hashlib.sha256(
    json.dumps(blob, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
).hexdigest()

if stored != calc:
    print("MISMATCH the component index sha256 no longer matches its contents")
    print(f"  stored: {stored}")
    print(f"  actual: {calc}")
    print()
    print("Langflow will discard the prebuilt index and rescan components at boot,")
    print("logging an integrity warning that reads like tampering. Fix by replacing")
    print("the stored value with the actual one -- edit that one field in place, do")
    print("not re-serialise the file, or the diff becomes half a megabyte of noise.")
    sys.exit(1)

print("OK    component index sha256 matches its contents")
PYCHECK
  then
    exit 1
  fi
fi

echo "OK -- no user-facing backend string names the upstream product."
