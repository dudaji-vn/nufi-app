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
# Requires bash >= 4 (uses `mapfile`, added in bash 4.0). macOS ships bash
# 3.2 as its system /bin/bash for licensing reasons (GPLv3 vs. Apple's
# GPLv2 cutoff) -- this script only works there because a newer Homebrew
# bash resolves first on PATH via `#!/usr/bin/env bash`. The guard below
# makes that requirement a clear message instead of a cryptic
# "mapfile: command not found" further down.

set -euo pipefail

if ((BASH_VERSINFO[0] < 4)); then
  echo "This script requires bash >= 4 (uses \`mapfile\`); running under ${BASH_VERSION}." >&2
  echo "macOS ships bash 3.2 as /bin/bash. Install a newer bash (e.g. \`brew install bash\`)" >&2
  echo "and either put it ahead of /bin/bash on PATH, or run explicitly:" >&2
  echo "  \$(brew --prefix)/bin/bash $0" >&2
  exit 1
fi

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
  "src/frontend/src/locales/ko.json"
  "src/frontend/src/i18n.ts"
  "src/frontend/src/constants/languages.ts"
  "src/frontend/src/customization/components/custom-langflow-counts.tsx"
  "src/frontend/src/customization/components/custom-get-started-progress.tsx"
  "src/frontend/src/customization/components/custom-empty-page.tsx"
  "src/frontend/src/customization/utils/urls.ts"
  "src/frontend/src/customization/components/custom-AccountMenu.tsx"
  "src/frontend/src/components/core/canvasControlsComponent/HelpDropdown.tsx"
  "src/frontend/src/components/core/canvasControlsComponent/HelpDropdownView.tsx"
  "src/frontend/src/components/core/canvasControlsComponent/__tests__/HelpDropdown.spec.tsx"
  "src/frontend/src/components/core/canvasControlsComponent/__tests__/Dropdowns.test.tsx"
  "src/frontend/src/pages/MainPage/pages/homePage/components/McpServerTab.tsx"
  "src/frontend/src/pages/MainPage/pages/homePage/components/McpJsonContent.tsx"
  "src/frontend/src/pages/MainPage/pages/homePage/components/__tests__/McpJsonContent.test.tsx"
  "src/frontend/src/modals/IOModal/components/chatView/chatInput/components/no-input.tsx"
  "src/frontend/src/customization/config-constants.ts"
)

echo "Comparing apps/nufi-agent against ${REPO} @ ${TAG}"

# `set -euo pipefail` means a failed `git fetch` would otherwise kill the
# script immediately -- but the old `2>/dev/null` threw away git's own
# error text first, so that death was silent: no message distinguishing
# "couldn't reach upstream" (network down, rate-limited, VPN/proxy
# required) from "the fork actually drifted" (a real violation, the thing
# this guard exists to catch). Capturing git's stderr and checking the
# fetch's own exit code explicitly, before touching the tree diff at all,
# means a network failure now says so.
FETCH_LOG="$(mktemp)"
trap 'rm -f "$FETCH_LOG"' EXIT
if ! git fetch --depth 1 --quiet "$REPO" "refs/tags/${TAG}" 2>"$FETCH_LOG"; then
  echo
  echo "FAILED to fetch ${REPO} @ refs/tags/${TAG} -- cannot compare against upstream." >&2
  echo "This is a network/access failure, not a fork-diff violation:" >&2
  cat "$FETCH_LOG" >&2
  echo >&2
  echo "Check network access to github.com (or GITHUB_TOKEN rate limits in CI)" >&2
  echo "before assuming apps/nufi-agent has drifted." >&2
  exit 1
fi

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
