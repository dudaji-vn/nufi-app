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
  # A regex literal that named the product. The rebrand rewrites string
  # literals only, so this pattern kept looking for the upstream name while
  # the server text it matches was rebranded -- the fallback could never fire.
  # Now matches the phrase instead of the brand. Candidate to send upstream.
  "ui/src/lib/successful-run-handoff.ts"
  # Its test moved with it. The fix above changed what the regex matches, so the
  # test that pins the match had to change in the same commit -- allowlisting the
  # source without its test left main red on the very guard that caught it.
  "ui/src/lib/successful-run-handoff.test.ts"
  # Upstream bug: the company-delete cascade removes `goals` before `projects`,
  # but projects.goal_id references goals.id, so deleting any company that has
  # both aborts on a foreign-key violation and silently leaves it in place.
  # Two lines swapped. Candidate to send upstream.
  "server/src/services/companies.ts"
  # Its test, for the same reason the successful-run-handoff test is listed
  # above: allowlisting a fix without its test leaves main red on the very
  # guard that would have caught the next one. This is the second time that
  # exact mistake shipped.
  "server/src/__tests__/companies-service.test.ts"
  # Builds nufi/adapter, which nothing else does: it is an external adapter, so
  # its dist is gitignored and no upstream build step touches it. Without these
  # lines the image ships a server that cannot offer `nufi_agent` -- the only
  # adapter that reaches the NuFi gateway -- and says nothing about it.
  "Dockerfile"
  # Which adapter a new company gets by default, and which one wears the
  # "Recommended" badge. Upstream picks Claude Code and Codex because upstream
  # ships pointed at Anthropic and OpenAI; this distribution ships pointed at
  # the NUFI gateway, which serves Gemini. Accepting upstream's default here
  # produces a team lead whose first run dies on
  # `Invalid model name passed in model=claude-opus-4-8`, and the vendor
  # harnesses narrate tool use they never performed when driven by a model
  # their prompts were not written for -- both measured on the live gateway.
  #
  # There is no server-side seam for either: `recommended` is a constant in the
  # display registry, and the default is component state. Two leaf edits, both
  # one line of behaviour, both distribution-specific by nature.
  "ui/src/components/OnboardingWizard.tsx"
  "ui/src/adapters/adapter-display-registry.ts"
  # Which company the app opens on. `GET /companies` returns every company to an
  # instance admin, while `hasCompanyAccess` -- guarding every other company
  # route -- requires membership and deliberately gives instance admins no
  # blanket access. Auto-selecting from the unfiltered list lands the operator
  # on a company where the dashboard, agents, issues, projects and routines all
  # 403, with no way out: the company cannot even be deleted, because delete
  # checks the same access. Observed on the live instance.
  #
  # The fix reads `cli-auth/me`, which the UI already fetches for
  # CloudAccessGate, so it costs no request. Candidate to send upstream, since
  # nothing here is NuFi-specific -- it is a mismatch between two upstream
  # endpoints.
  "ui/src/context/CompanyContext.tsx"

  # The four built-in agents (briefs, learning, reflection-coach, summarizer)
  # may only run on a vendor harness upstream: claude_local, codex_local,
  # gemini_local, opencode_local, process. NUFI Works serves none of those --
  # the container has no vendor CLI and no vendor key, and the egress check in
  # this same CI proves every enabled adapter must reach the NUFI gateway. So a
  # built-in was unusable by construction: enabling one produced an agent that
  # could never run, and correcting its adapter was refused with
  # `built_in_agent_adapter_not_allowed`. Observed on the live instance, where
  # Reflection Coach and Summarizer sat paused on claude_local.
  #
  # `nufi_agent` is added to each allowlist and made the default, and the
  # summarizer's pinned `claude-haiku-4-5` becomes `nufi-agent` -- the one model
  # that adapter serves. The test file carries the matching expectations.
  "server/src/services/built-in-agents.ts"
  "server/src/__tests__/built-in-agents.test.ts"
  "ui/src/context/CompanyContext.test.tsx"
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
  "ui/src/pages/Auth.test.tsx"
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
