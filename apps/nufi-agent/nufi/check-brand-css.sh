#!/usr/bin/env bash
#
# Fail if the compiled frontend CSS does not carry the NuFi brand override
# tokens in both theme scopes: :root:root (light) and .dark.dark (dark), OR
# if the compiled JS still carries the literal word "Langflow" -- evidence
# that the rebrand transform isn't actually running.
#
# nufi/brand.css is wired in by exactly one line in
# src/frontend/src/style/index.css: `@import "../../../../nufi/brand.css";`
# on line 1. CSS requires @import to be the first statement in a stylesheet
# (only @charset/@layer may precede it) -- an @import anywhere else is
# silently dropped by the build. No error, no warning, nothing in `npm run
# build` output; the compiled CSS just quietly reverts to upstream's
# Langflow colours. That exact bug shipped once during Task 3 of this fork
# and was only caught by hand-grepping the compiled output.
#
# check-fork-diff.sh diffs file *paths* against upstream -- it has no way to
# know whether an allowlisted file's *content* still does what it claims.
# The app defaults to dark mode (index.html ships `<body class="dark">`), so
# a silently-dropped import doesn't degrade gracefully into "light theme
# only" -- it un-brands the theme every user sees first, with a green CI
# run. This check closes that gap the same way check-fork-diff.sh's own
# header says it must: as a check, not a comment relying on review
# discipline.
#
# A real build was chosen over a static "is @import line 1" check because
# the static version only catches this one failure mode. Building and
# inspecting the actual compiled CSS also catches a renamed/emptied
# nufi/brand.css, a broken import path, or brand.css itself losing its
# :root:root / .dark.dark selectors -- the thing that actually matters
# (what ships) rather than a proxy for it. The build takes ~20s once
# dependencies are installed; that cost is paid once per PR that touches
# apps/nufi-agent, not per commit.
#
# THE SECOND CHECK (JS rebrand wiring) exists for a sharper reason: the
# whole white-label rests on two lines in an upstream-owned file --
# src/frontend/vite.config.mts's `import { nufiRebrand } from "../../nufi/
# rebrand"` and `nufiRebrand()` in the plugins array. check-fork-diff.sh
# only diffs paths (vite.config.mts is allowlisted, so ANY edit to it,
# including deleting the plugin line, passes that guard). check-brand-css.sh
# until now only asserted the CSS override survived -- it said nothing about
# whether the JS-side product-name rewrite (nufi/rebrand.ts, which turns the
# bare word "Langflow" into "NuFi Agent" across every .ts/.tsx/.json module)
# is still wired in. Drop the plugin entry in a resync and the app would
# ship as literal "Langflow" everywhere -- title, buttons, error strings --
# with all three guards (fork-diff, brand-css's CSS half, locale-parity)
# green. `grep -c '\bLangflow\b' build/assets/*.js` closes that gap: it's
# case-sensitive (so the deliberately-untouched lower-case
# `docs.langflow.org` URLs never trip it) and word-bounded (so it doesn't
# false-positive on compound identifiers baked into the bundle as string
# literals -- asset filenames like `LangflowLogo.svg`/`MCPLangflow.png`,
# where "Langflow" has no boundary against the letters glued to it). Proven
# to actually go red: commented out the `nufiRebrand()` line, ran this
# script, confirmed MISSING with a nonzero hit count, then restored the line
# and confirmed OK again -- see nufi/README.md "Verifying the rebrand-wiring
# guard" for the full transcript.
#
# Usage: apps/nufi-agent/nufi/check-brand-css.sh
# Requires: apps/nufi-agent/src/frontend's dependencies already installed
# (`npm ci` in that directory). This script only builds and inspects the
# output -- it does not install anything, matching check-fork-diff.sh's
# separation of "install" from "check".
# Exits 0 when the compiled CSS contains the NuFi tokens in both scopes, the
# compiled JS contains zero occurrences of the bare word "Langflow", and
# nothing the build emits (JS, CSS or index.html) references a third-party
# host this product does not name; 1 otherwise.

set -euo pipefail

cd "$(dirname "$0")/../src/frontend"   # apps/nufi-agent/src/frontend

BUILD_LOG="$(mktemp)"
trap 'rm -f "$BUILD_LOG"' EXIT

echo "Building apps/nufi-agent/src/frontend..."
if ! npm run build >"$BUILD_LOG" 2>&1; then
  echo "Build failed -- output:"
  cat "$BUILD_LOG"
  exit 1
fi

CSS_FILES=(build/assets/*.css)
if [[ ! -e "${CSS_FILES[0]}" ]]; then
  echo "No compiled CSS found under build/assets/ -- did the build output layout change?"
  exit 1
fi

# Read from stdin rather than passing files to grep -o directly: with
# multiple files, grep prefixes matches with "filename:", which would land
# inside the captured block and break the fixed-string check below.
COMPILED_CSS="$(cat "${CSS_FILES[@]}")"

# selector_pattern is a basic regex (only `.` needs escaping, `{`/`}`/`[^}]`
# are literal/valid in POSIX BRE); needle is matched with grep -F so the
# literal dots in HSL values ("33.3%") aren't read as regex wildcards.
check_scope() {
  local selector_pattern="$1" needle="$2" label="$3"
  local block
  block="$(grep -o "${selector_pattern}{[^}]*}" <<<"$COMPILED_CSS" | head -1 || true)"
  if [[ -n "$block" ]] && grep -qF -- "$needle" <<<"$block"; then
    echo "OK      ${label}"
    return 0
  fi
  echo "MISSING ${label}"
  return 1
}

FAIL=0
check_scope "root:root" "236.2 42.7% 56.9%" ":root:root carries --primary (light-mode brand primary)" || FAIL=1
check_scope "\.dark\.dark" "240 33.3% 4.7%" ".dark.dark carries --background (dark-mode navy surface)" || FAIL=1

if [[ "$FAIL" -ne 0 ]]; then
  cat <<'MSG'

The compiled CSS is missing the NuFi brand override in at least one theme
scope. The usual cause: nufi/brand.css's @import in
src/frontend/src/style/index.css is no longer the first statement in the
file. Check:

  head -3 apps/nufi-agent/src/frontend/src/style/index.css

`@import "../../../../nufi/brand.css";` must be line 1 -- only @charset or
@layer may precede an @import, and CSS silently drops one that isn't first.
If nufi/brand.css itself changed, confirm it still defines --primary in
:root:root and --background in .dark.dark.
MSG
  exit 1
fi

echo "OK -- the compiled CSS carries the NuFi brand tokens in both theme scopes."

JS_FILES=(build/assets/*.js)
if [[ ! -e "${JS_FILES[0]}" ]]; then
  echo "No compiled JS found under build/assets/ -- did the build output layout change?"
  exit 1
fi

# -h suppresses the "filename:" prefix grep -o would otherwise add per
# match with multiple files; -o so `wc -l` counts occurrences, not just
# matching lines (a minified bundle is often one enormous line, where
# grep -c would report "1" no matter how many times "Langflow" appears
# on it). Case-sensitive, word-bounded per the header comment above.
# `|| true` on grep itself (not the pipeline): under `set -o pipefail`,
# grep's own exit status is 1 when it finds nothing -- which is the PASS
# case here -- and pipefail would otherwise turn that into a script-ending
# failure via `set -e` before LANGFLOW_HITS is ever read, so this check
# would abort silently on exactly the outcome it's supposed to report as
# OK. Grouped so `|| true` only absorbs grep's exit status, not wc/tr's.
LANGFLOW_HITS="$({ grep -ohE '\bLangflow\b' "${JS_FILES[@]}" || true; } | wc -l | tr -d '[:space:]')"

if [[ "$LANGFLOW_HITS" -ne 0 ]]; then
  cat <<MSG

MISSING compiled JS still carries ${LANGFLOW_HITS} occurrence(s) of the
literal word "Langflow" -- the rebrand transform did not rewrite them.

The usual cause: the nufi-rebrand plugin is no longer wired into
src/frontend/vite.config.mts. Check:

  grep -n "nufiRebrand" apps/nufi-agent/src/frontend/vite.config.mts

Both the import (\`import { nufiRebrand } from "../../nufi/rebrand";\`) and
the call in the \`plugins\` array (\`nufiRebrand(),\`) must be present. If
both are present, a hit here means a new hardcoded "Langflow" string shipped
somewhere the transform's own exclusions (import specifiers, URLs,
LANGFLOW_* env names, lower-case langflow.* module paths) don't cover --
see nufi/rebrand.ts's own header comment for what those exclusions are and
why.
MSG
  exit 1
fi

echo "OK      compiled JS carries 0 occurrences of the literal word \"Langflow\""
echo "OK -- the rebrand transform is wired in and the build reflects it."

# THE THIRD CHECK (third-party calls). Removing a link from the UI does not
# remove the request behind it. Upstream's app header carried a live GitHub
# star badge and a Discord member count; C1 removed both from the rendered
# UI via the customization seam, and every guard stayed green -- while
# AppInitPage went on calling api.github.com once per app init and
# discord.com/api once per route change. Measured against the running build
# before the fix: 2 requests to api.github.com and 6 to
# discord.com/api/v9/invites over one browsing session, from a product that
# names neither. That is a white-label leak (each request announces the
# user's IP to a third party, attributed to the upstream project) and an
# egress-policy hole (nufi/egress/networkpolicy.yaml would have to allow
# two FQDNs for features with no UI).
#
# Grepping the compiled bundle rather than the source is deliberate, for
# the same reason as the Langflow check above: it is what ships. Source
# comments mentioning these hosts (controllers/API/index.ts and api.tsx
# both explain the removal in prose) are stripped by the minifier, so they
# do not trip this. A resync that restores upstream's getRepoStars body
# would put the literal back in the bundle and fail here.
#
# Proven to actually go red: restored `axios.get("https://api.github.com/
# repos/" + owner + "/" + repo)` in controllers/API/index.ts, ran this
# script, confirmed MISSING with a nonzero hit count, then re-applied the
# fix and confirmed OK again -- transcript in nufi/README.md.
THIRD_PARTY_HOSTS=(
  "api.github.com"
  "discord.com/api"
  "fonts.googleapis.com"
  "fonts.gstatic.com"
)

# Unlike the two checks above, this one cannot look at the JS alone. A
# webfont arrives through three different doors: a <link> in index.html, a
# url() in the compiled CSS, and a fetch built in JS. Upstream used the
# first; scanning only build/assets/*.js would have declared the Google
# Fonts links clean while every page load still hit fonts.googleapis.com.
# So scan everything the build emits at the top level.
SCAN_FILES=(build/assets/*.js build/assets/*.css build/index.html)
EXISTING_SCAN=()
for f in "${SCAN_FILES[@]}"; do
  [[ -e "$f" ]] && EXISTING_SCAN+=("$f")
done
if ((${#EXISTING_SCAN[@]} == 0)); then
  echo "Nothing to scan for third-party hosts -- did the build output layout change?"
  exit 1
fi

TP_FAIL=0
for host in "${THIRD_PARTY_HOSTS[@]}"; do
  # -F: the dots are literal hostname characters, not regex wildcards.
  # `|| true` for the same pipefail reason documented above -- no match is
  # the PASS case here, and grep exits 1 on no match.
  HITS="$({ grep -ohF "$host" "${EXISTING_SCAN[@]}" || true; } | wc -l | tr -d '[:space:]')"
  if [[ "$HITS" -ne 0 ]]; then
    echo "MISSING build output references ${host} (${HITS} occurrence(s))"
    TP_FAIL=1
  else
    echo "OK      build output carries 0 references to ${host}"
  fi
done

if [[ "$TP_FAIL" -ne 0 ]]; then
  cat <<'MSG'

A third-party host this product does not name is back in the shipped
output. The usual causes, by host:

  api.github.com / discord.com
    A `git subtree pull` restored upstream's getRepoStars/getDiscordCount
    bodies in src/frontend/src/controllers/API/index.ts, or re-added the
    host to a domain list in src/frontend/src/controllers/API/api.tsx.
    Both functions must return without making a network call.

  fonts.googleapis.com / fonts.gstatic.com
    The Google Fonts <link> tags are back in src/frontend/index.html.
    The fonts ship with the app instead -- see the @font-face blocks at
    the top of nufi/brand.css and the woff2 files in nufi/fonts/.

See the comments in those files for why each was removed.
MSG
  exit 1
fi

echo "OK -- the build makes no calls to hosts this product does not name."

# THE FOURTH CHECK (webfont integrity). The fonts in nufi/fonts/ are the
# only binary files this fork owns, and binaries are exactly what a
# line-ending rule silently destroys. Upstream's apps/nufi-agent/
# .gitattributes opens with `* text eol=lf` and lists the binary types it
# knows about -- png, jpg, ico, gif, mp4, svg, wav, raw -- but not woff2.
# On their first commit, eight of the eighteen files lost 1-3 bytes to CRLF
# normalisation. Nothing failed: `npm run build` happily emitted the
# truncated files, the CSS still referenced them, every other check here
# stayed green, and the damage would only surface as a browser quietly
# refusing to render the font. nufi/.gitattributes now marks them binary;
# this check is what makes that stick.
#
# A WOFF2 file starts with the signature `wOF2` and stores its own total
# length as a big-endian uint32 at offset 8 (W3C WOFF2 spec, section 5.1).
# Any byte dropped from the middle leaves that field disagreeing with the
# file on disk, which is precisely the corruption above -- so comparing the
# two catches it without needing a font parser.
# cwd is apps/nufi-agent/src/frontend (set at the top of this script), so
# nufi/ is two levels up. Deliberately not derived from $0: by this point
# the script has already cd'd, and a relative $0 no longer resolves.
FONT_DIR="../../nufi/fonts"
FONT_FILES=("$FONT_DIR"/*.woff2)
if [[ ! -e "${FONT_FILES[0]}" ]]; then
  echo "MISSING no webfonts under nufi/fonts/ -- the self-hosted fonts are gone"
  exit 1
fi

FONT_FAIL=0
for font in "${FONT_FILES[@]}"; do
  sig="$(head -c 4 "$font")"
  if [[ "$sig" != "wOF2" ]]; then
    echo "MISSING $(basename "$font") is not a WOFF2 file (signature: '${sig}')"
    FONT_FAIL=1
    continue
  fi
  # bytes 8-11, big-endian uint32
  # GNU od supports --endian; BSD od (macOS) does not and exits nonzero,
  # which `set -e` would turn into a silent script death right here -- so
  # absorb its status and fall through to the byte-by-byte path below.
  declared="$({ od -An -tu4 --endian=big -j8 -N4 "$font" 2>/dev/null || true; } | tr -d '[:space:]')"
  if [[ -z "$declared" ]]; then
    # BSD od (macOS) has no --endian; assemble the four bytes by hand.
    read -r b0 b1 b2 b3 <<<"$(od -An -tu1 -j8 -N4 "$font" | tr -s ' ')"
    declared=$(( b0 * 16777216 + b1 * 65536 + b2 * 256 + b3 ))
  fi
  actual="$(wc -c <"$font" | tr -d '[:space:]')"
  if [[ "$declared" != "$actual" ]]; then
    echo "MISSING $(basename "$font") is truncated: header declares ${declared} bytes, file is ${actual}"
    FONT_FAIL=1
  fi
done

if [[ "$FONT_FAIL" -ne 0 ]]; then
  cat <<'MSG'

At least one self-hosted webfont is damaged. The usual cause: the file was
committed as text and line-ending-normalised, dropping the CRLF byte pairs
inside its compressed stream.

  git check-attr text -- apps/nufi-agent/nufi/fonts/inter-latin-wght-normal.woff2

must report `text: unset`. If it does not, nufi/.gitattributes is missing
or no longer applies, and every .woff2 under it needs re-adding from a
clean copy -- `git add` alone will not undo the normalisation.
MSG
  exit 1
fi

echo "OK      all ${#FONT_FILES[@]} self-hosted webfonts have intact WOFF2 headers"
