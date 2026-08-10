#!/usr/bin/env bash
#
# Fail if the compiled frontend CSS does not carry the NuFi brand override
# tokens in both theme scopes: :root:root (light) and .dark.dark (dark).
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
# Usage: apps/nufi-agent/nufi/check-brand-css.sh
# Requires: apps/nufi-agent/src/frontend's dependencies already installed
# (`npm ci` in that directory). This script only builds and inspects the
# output -- it does not install anything, matching check-fork-diff.sh's
# separation of "install" from "check".
# Exits 0 when the compiled CSS contains the NuFi tokens in both scopes,
# 1 otherwise.

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
