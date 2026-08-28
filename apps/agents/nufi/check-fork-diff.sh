#!/usr/bin/env bash
#
# Fail if apps/agents has drifted from its vendored upstream anywhere outside
# the NuFi allowlist.
#
# The fork is only rebasable while the diff stays tiny and confined to leaves
# (docs/2026-08-03-nufi-agent-app-design.md §7). Left to review discipline that
# erodes: someone hardcodes a colour in a component, the next `git subtree pull`
# conflicts, and the fork freezes the way apps/chat did. So it is checked.
#
# Usage: apps/agents/nufi/check-fork-diff.sh
# Exits 0 when every changed path is allowlisted, 1 otherwise.

set -euo pipefail

cd "$(dirname "$0")/../../.."   # repo root

PIN="apps/agents/nufi/upstream.json"
REPO=$(node -p "require('./$PIN').repository")
TAG=$(node -p "require('./$PIN').tag")

# Paths NuFi owns, relative to apps/agents/. Anything else must match upstream.
ALLOWLIST=(
  "nufi/"
  # Upstream bug fix, see nufi/README.md "Upstream patches". Sent upstream;
  # drop this entry once a release carries the fix.
  "ui/src/plugins/slots.tsx"
  # Single sign-on. See nufi/README.md, "Signing in with a NUFI account".
  "server/src/auth/better-auth.ts"
  # The button that reaches the plugin above. Enabling generic-oauth on the
  # server is invisible without it: better-auth's sign-in is a POST that also
  # sets the state cookie, so it cannot be a link, and upstream's login page
  # offers email and password only. Shipped without these two, SSO is
  # configured, verifiable by curl, and unreachable by a person -- which is how
  # it shipped the first time.
  "ui/src/api/auth.ts"
  "ui/src/pages/Auth.tsx"
  "ui/src/nufi-brand.css"
  "ui/nufi-rebrand.ts"
  "ui/nufi-rebrand.test.ts"
  "ui/src/index.css"
  "ui/vite.config.ts"
  "ui/public/favicon.ico"
  "ui/public/favicon.svg"
  "ui/public/favicon-16x16.png"
  "ui/public/favicon-32x32.png"
  "ui/public/apple-touch-icon.png"
  "ui/public/android-chrome-192x192.png"
  "ui/public/android-chrome-512x512.png"
  "ui/public/site.webmanifest"
)

echo "Comparing apps/agents against ${REPO} @ ${TAG}"
git fetch --depth 1 --quiet "$REPO" "refs/tags/${TAG}" 2>/dev/null

# Both sides are trees, so diff paths come out relative to apps/agents/.
mapfile -t CHANGED < <(git diff --name-only FETCH_HEAD^{tree} HEAD:apps/agents)

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
  1. Put the change in an external adapter package or ui/nufi-*.
  2. Send it upstream as a pull request.
  3. If it genuinely must live here, add the path to ALLOWLIST in this script
     and say why in apps/agents/nufi/README.md — deliberately, not by reflex.
MSG
  exit 1
fi

echo "OK — the fork diff is confined to the NuFi allowlist."
