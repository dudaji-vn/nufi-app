#!/usr/bin/env bash
#
# Guard the SUBSET, not full parity, between
# src/frontend/src/locales/ko.json and src/frontend/src/locales/en.json.
#
# Task 4 (docs/superpowers/sdd/2026-08-10-nufi-agent-fork-whitelabel/
# task-4-brief.md) deliberately translates the demo path only -- the
# screens a JDC evaluation panel actually sees -- not all 2,232 keys in
# en.json. i18n.ts sets fallbackLng: "en" with returnEmptyString: false,
# so any key absent from ko.json renders its English string rather than a
# blank or a raw key path: partial coverage degrades gracefully by
# design. A script that failed on "en.json has keys ko.json doesn't" would
# be asserting the wrong thing entirely -- that IS the intended state, not
# a defect -- so this script never checks that direction.
#
# What this DOES assert, and why each one earns its place:
#
#   1. No orphan keys: every key ko.json defines must still exist in
#      en.json. A typo in a key path is invisible at review time -- it
#      just falls back to English and looks exactly like a key someone
#      chose not to translate (see task-4-brief.md's warning on this). The
#      same shape of bug reappears for real, not just typos, the moment
#      upstream renames or removes an English key during a `git subtree
#      pull` resync (nufi/upstream.json's "resyncAlsoDo" field calls this
#      out by name) -- the Korean entry for the old name keeps shipping in
#      the bundle but i18next's lookup on the new name misses it, and
#      nothing ever renders it again. Silent, not loud.
#
#   2. The declared demo path is fully present: nufi/demo-path-keys.txt is
#      the frozen list of keys Task 4 decided belong in ko.json (see that
#      file's own header, and nufi/README.md, for the surface-by-surface
#      reasoning). Checking ko.json's key COUNT against a number would let
#      any 551 keys satisfy it, including an accidental swap that drops
#      real demo-path coverage while adding unrelated keys. Checking the
#      exact declared set instead means coverage can only shrink by
#      editing this repo's own list, deliberately -- never by accident in
#      a merge or a bad resync.
#
# Usage: apps/nufi-agent/nufi/check-locale-parity.sh
# Exits 0 when both checks pass, 1 otherwise.

set -euo pipefail

cd "$(dirname "$0")/.."   # apps/nufi-agent

EN_JSON="src/frontend/src/locales/en.json"
KO_JSON="src/frontend/src/locales/ko.json"
DEMO_PATH_KEYS="nufi/demo-path-keys.txt"

for f in "$EN_JSON" "$KO_JSON" "$DEMO_PATH_KEYS"; do
  if [[ ! -f "$f" ]]; then
    echo "Missing required file: apps/nufi-agent/$f"
    exit 1
  fi
done

# node, not jq: check-fork-diff.sh already requires node on the PATH (it
# reads upstream.json with `node -p`), so this doesn't add a new tool
# dependency to either local runs or nufi-agent-ci.yml.
EN_KEYS="$(node -p 'Object.keys(require("./'"$EN_JSON"'")).join("\n")')"
KO_KEYS="$(node -p 'Object.keys(require("./'"$KO_JSON"'")).join("\n")')"

# Blank lines and #-comments are not keys.
DECLARED_KEYS="$(grep -v '^\s*#' "$DEMO_PATH_KEYS" | grep -v '^\s*$')"

FAIL=0

# --- Check 1: no orphan keys -------------------------------------------
mapfile -t ORPHANS < <(comm -23 <(sort <<<"$KO_KEYS") <(sort <<<"$EN_KEYS"))
if (( ${#ORPHANS[@]} > 0 )); then
  echo "FAIL  orphan keys in ko.json with no matching key in en.json:"
  printf '  %s\n' "${ORPHANS[@]}"
  echo "  (an upstream rename/removal, or a typo when ko.json was authored --"
  echo "  either way, i18next's lookup on this key now silently misses.)"
  FAIL=1
else
  echo "OK    no orphan keys -- every ko.json key exists in en.json"
fi

# --- Check 2: declared demo-path keys are all present -------------------
mapfile -t MISSING < <(comm -23 <(sort <<<"$DECLARED_KEYS") <(sort <<<"$KO_KEYS"))
if (( ${#MISSING[@]} > 0 )); then
  echo "FAIL  demo-path keys declared in $DEMO_PATH_KEYS but missing from ko.json:"
  printf '  %s\n' "${MISSING[@]}"
  echo "  (coverage shrank. If that's deliberate, remove the key from"
  echo "  $DEMO_PATH_KEYS in the same change; otherwise restore it in ko.json.)"
  FAIL=1
else
  DECLARED_COUNT="$(wc -l <<<"$DECLARED_KEYS" | tr -d ' ')"
  echo "OK    all $DECLARED_COUNT declared demo-path keys are present in ko.json"
fi

if (( FAIL != 0 )); then
  exit 1
fi

echo "OK -- ko.json is a clean, declared subset of en.json."
