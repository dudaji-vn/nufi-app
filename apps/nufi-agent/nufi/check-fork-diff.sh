#!/usr/bin/env bash
#
# Fail if apps/nufi-agent has drifted from its vendored upstream anywhere
# outside the NuFi allowlist.
#
# The fork is only rebasable while the diff stays tiny and confined to leaves
# (docs/2026-08-10-nufi-agent-langflow-fork.md §3, §6). Left to review
# discipline that erodes: someone hardcodes a colour in a component, the next
# `git subtree pull` conflicts, and the fork freezes the way apps/chat did.
# So it is checked.
#
# Usage: apps/nufi-agent/nufi/check-fork-diff.sh
# Exits 0 when every changed path is allowlisted, 1 otherwise.

set -euo pipefail

cd "$(dirname "$0")/../../.."   # repo root

PIN="apps/nufi-agent/nufi/upstream.json"
REPO=$(node -p "require('./$PIN').repository")
TAG=$(node -p "require('./$PIN').tag")

# Paths NuFi owns, relative to apps/nufi-agent/. Anything else must match
# upstream.
ALLOWLIST=(
  "nufi/"
  "src/frontend/index.html"
  "src/frontend/src/style/index.css"
  "src/frontend/vite.config.mts"
  "src/frontend/public/favicon.ico"
  "src/frontend/public/manifest.json"
  "src/frontend/src/assets/LangflowLogo.svg"
  "src/frontend/src/assets/LangflowLogoColor.svg"
  "src/frontend/src/assets/langflow_logo_white.svg"
  "src/frontend/src/assets/langflow_logo_black.svg"
  "src/frontend/src/assets/logo_dark.png"
  "src/frontend/src/assets/logo_light.png"
  "src/frontend/src/assets/langflow_assistant.svg"
  "src/frontend/src/assets/langflow_assistant_idle.svg"
  "src/frontend/src/assets/MCPLangflow.png"
)

echo "Comparing apps/nufi-agent against ${REPO} @ ${TAG}"
git fetch --depth 1 --quiet "$REPO" "refs/tags/${TAG}" 2>/dev/null

# Both sides are trees, so diff paths come out relative to apps/nufi-agent/.
mapfile -t CHANGED < <(git diff --name-only FETCH_HEAD^{tree} HEAD:apps/nufi-agent)

allowed() {
  local path="$1" entry
  for entry in "${ALLOWLIST[@]}"; do
    case "$entry" in
      */) [[ "$path" == "$entry"* ]] && return 0 ;;
      *)  [[ "$path" == "$entry"  ]] && return 0 ;;
    esac
  done
  return 1
}

VIOLATIONS=()
for path in "${CHANGED[@]}"; do
  [[ -z "$path" ]] && continue
  allowed "$path" || VIOLATIONS+=("$path")
done

echo "changed: ${#CHANGED[@]}  allowlisted: $(( ${#CHANGED[@]} - ${#VIOLATIONS[@]} ))  violations: ${#VIOLATIONS[@]}"

if (( ${#VIOLATIONS[@]} > 0 )); then
  echo
  echo "These files diverge from upstream but are not NuFi-owned:"
  printf '  %s\n' "${VIOLATIONS[@]}"
  cat <<'MSG'

Every such edit makes the next `git subtree pull` a conflict. Prefer, in order:
  1. Put the change in an external adapter package or nufi/.
  2. Send it upstream as a pull request.
  3. If it genuinely must live here, add the path to ALLOWLIST in this script
     and say why in apps/nufi-agent/nufi/README.md — deliberately, not by
     reflex.
MSG
  exit 1
fi

echo "OK — the fork diff is confined to the NuFi allowlist."
