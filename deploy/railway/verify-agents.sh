#!/usr/bin/env bash
#
# Asserts the public surface of both agent products: reachable, carrying the
# NuFi name, and shut to anyone without a NUFI session.
#
# The negative cases are the point. A deploy that returns 200 tells you the
# process started; it tells you nothing about whether the door is closed. Every
# 401 below is a claim that could quietly become a 200 after a refactor, and
# nobody would notice from the outside.
#
# Usage: deploy/railway/verify-agents.sh [--base-suffix .nufi.me]

set -uo pipefail

SUFFIX="${1:-.nufi.me}"
STUDIO="https://studio${SUFFIX}"
WORKS="https://works${SUFFIX}"
AGENTS="https://agents${SUFFIX}"
CONSOLE="https://console${SUFFIX}"

fail=0
check() { # check <label> <actual> <expected>
  if [[ "$2" == "$3" ]]; then
    printf 'OK    %-46s %s\n' "$1" "$2"
  else
    printf 'FAIL  %-46s got %s want %s\n' "$1" "$2" "$3"
    fail=1
  fi
}

code() { curl -sS -o /dev/null -w '%{http_code}' --max-time 20 "$1" 2>/dev/null || echo "000"; }
body() { curl -sS --max-time 20 "$1" 2>/dev/null || true; }
# grep -c exits 1 on zero matches, which under pipefail would abort the script
# with no output. Counting this way keeps a legitimate zero a legitimate zero.
count() { { printf '%s' "$2" | grep -ci "$1" || true; } | tr -d '[:space:]'; }
# Case-SENSITIVE, for the white-label checks. The upstream names survive in
# places a user never sees -- build markers like PAPERCLIP_FAVICON_START and a
# localStorage key "paperclip.theme" -- and a case-insensitive count reports
# those as a leak. It cried wolf on a correct deploy once; the thing that is
# actually forbidden is the capitalised product name a user could read.
countcs() { { printf '%s' "$2" | grep -c "$1" || true; } | tr -d '[:space:]'; }

echo "== reachable =="
check "studio responds"            "$(code "$STUDIO/")"   "200"
check "works responds"             "$(code "$WORKS/")"    "200"
# `/` on the chooser host 302s to /choose by design, so asserting 200 on `/`
# fails a working deploy. Assert the redirect AND its destination.
check "the chooser redirects"      "$(code "$AGENTS/")"        "302"
check "the chooser renders"        "$(code "$AGENTS/choose")"  "200"
check "console publishes JWKS"     "$(code "$CONSOLE/.well-known/jwks.json")" "200"

echo
echo "== white label =="
check "studio names no upstream"   "$(countcs Langflow "$(body "$STUDIO/")")"  "0"
check "works names no upstream"    "$(countcs Paperclip "$(body "$WORKS/")")"  "0"
check "studio carries the product" "$(count 'NUFI Studio' "$(body "$STUDIO/")" | awk '{print ($1>0)?"yes":"no"}')" "yes"

echo
echo "== the door is shut =="
JWKS="$(body "$CONSOLE/.well-known/jwks.json")"
for private in '"d"' '"p"' '"q"' '"dp"' '"dq"' '"qi"'; do
  check "jwks hides $private"      "$(count "$private" "$JWKS")" "0"
done
check "entering studio needs a session" "$(code "$CONSOLE/enter/studio")" "401"
check "authorize needs a session"  "$(code "$CONSOLE/oidc/authorize?client_id=nufi-works&redirect_uri=https%3A%2F%2Fworks${SUFFIX}%2Fapi%2Fauth%2Foauth2%2Fcallback%2Fnufi&state=x")" "401"
check "userinfo refuses no token"  "$(code "$CONSOLE/oidc/userinfo")" "401"

echo
if (( fail )); then
  echo "FAILED — read the lines above before deploying anything else."
else
  echo "OK — both products are up, branded, and closed to anonymous callers."
fi
exit "$fail"
