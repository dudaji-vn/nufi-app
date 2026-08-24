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

echo "OK -- no user-facing backend string names the upstream product."
