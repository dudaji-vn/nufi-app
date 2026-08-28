#!/usr/bin/env bash
# =============================================================================
# demo.sh — park the Railway stack between demos, wake it on demand
#
# The nufi project runs eight services 24/7 but is demo-driven. Measured CPU
# across the whole production environment averages 0.015 vCPU -- about 1.5% of a
# single core -- so roughly 84% of the Railway bill is idle RAM rather than work
# anyone asked for.
#
# Three services can auto-sleep through Railway's Serverless toggle. The other
# five cannot, and that is not a configuration oversight: Railway decides a
# service is idle from OUTBOUND traffic, so anything holding a database
# connection pool (nufi-chat, the RAG API) or receiving private-network traffic
# (the databases) never goes quiet and never sleeps, no matter how the toggle is
# set. Those five need an explicit switch. This is that switch.
#
# WHAT IT TOUCHES
#   PARKED    pgvector, meilisearch, librechat-rag-api-dev-lite
#             Torn down between demos. The service, its variables, its domains
#             and its VOLUME all survive -- no data is lost. Disk keeps billing,
#             which is ~$0.12 per month project-wide.
#   RESIDENT  MongoDB, nufi-chat
#             Left running so chat.nufi.me stays reachable. Pass --all to park
#             these too when nothing needs to answer at all.
#   SLEEPERS  nufi-docs, nufi-console, nufichat-admin-panel
#             Owned by Railway Serverless, not by this script. Reported in
#             `status`, and pre-warmed by `up` so their cold start happens
#             before an audience is watching instead of during.
#
# WHY THIS TALKS TO THE GRAPHQL API
# Parking uses `railway down`, which works. Waking cannot use `railway redeploy`
# -- and this is the trap. `down` deletes the deployment record outright, so
# `redeploy` afterwards fails with "No deployment found for service" and there
# is nothing left to redeploy. An earlier version of this script did exactly
# that: it parked the stack cleanly and then could not bring it back. Waking a
# parked service has to CREATE a deployment from the service's configured
# source, which the CLI does not expose at all. That is serviceInstanceDeployV2,
# and it is the only reason this script needs an API token.
#
# ORDER MATTERS
# pgvector has to be accepting connections before the RAG API starts, or the RAG
# API comes up healthy and fails on its first query. nufi-chat holds long-lived
# clients to Meilisearch that do not survive the backend disappearing, so it is
# restarted last to force a clean reconnect. Skipping that restart leaves search
# silently broken behind a UI that looks completely normal -- which is the exact
# failure this script exists to prevent, since it surfaces mid-demo.
#
# ONE CAVEAT ON --all
# The image-backed services (databases, RAG API) wake by re-pulling a pinned
# image, so waking restores exactly what was parked. nufi-chat is built from the
# repo, so waking it REBUILDS from the current default branch -- it is a fresh
# deploy, not a byte-identical restore, and it takes minutes rather than
# seconds. Prefer plain `down` unless you really need chat.nufi.me dark.
#
# USAGE
#   ./demo.sh up                 # wake everything, wait until healthy, pre-warm
#   ./demo.sh up --no-restart    # skip the nufi-chat reconnect restart
#   ./demo.sh down               # park the demo stack
#   ./demo.sh down --all         # also park MongoDB + nufi-chat (see caveat)
#   ./demo.sh status             # what is running right now
#
# Reads RAILWAY_PROJECT_ID / RAILWAY_ENV to override the defaults below.
# =============================================================================

set -uo pipefail

PROJECT_ID="${RAILWAY_PROJECT_ID:-06c8dad0-f74c-412e-b9cf-f563676520d5}"
ENVIRONMENT="${RAILWAY_ENV:-production}"

# Space-separated, not arrays: this has to run under the bash 3.2 that ships
# with macOS, which has no associative arrays and no `mapfile`.
PARKED="pgvector meilisearch librechat-rag-api-dev-lite"
RESIDENT="MongoDB nufi-chat"
SLEEPERS="nufi-docs nufi-console nufichat-admin-panel"

PUBLIC_URLS="https://chat.nufi.me https://docs.app.nufi.me https://admin.app.nufi.me https://console.nufi.me"
HEALTH_URL="https://chat.nufi.me/health"

DEPLOY_TIMEOUT="${DEPLOY_TIMEOUT:-600}"   # seconds to wait per service
API="https://backboard.railway.com/graphql/v2"
CALLER="script:demo.sh"
SESSION="demo-$(date +%s)-$$"

if [ -t 1 ]; then
  C_RED=$'\033[31m'; C_GRN=$'\033[32m'; C_YLW=$'\033[33m'
  C_DIM=$'\033[2m';  C_BLD=$'\033[1m';  C_OFF=$'\033[0m'
else
  C_RED=""; C_GRN=""; C_YLW=""; C_DIM=""; C_BLD=""; C_OFF=""
fi
red()  { printf '%s%s%s\n' "$C_RED" "$*" "$C_OFF"; }
grn()  { printf '%s%s%s\n' "$C_GRN" "$*" "$C_OFF"; }
ylw()  { printf '%s%s%s\n' "$C_YLW" "$*" "$C_OFF"; }
dim()  { printf '%s%s%s\n' "$C_DIM" "$*" "$C_OFF"; }
step() { printf '\n%s==> %s%s\n' "$C_BLD" "$*" "$C_OFF"; }
die()  { red "ERROR: $*"; exit 1; }

# --- prerequisites --------------------------------------------------------
# The Railway CLI installs to ~/.railway/bin, which is not on the PATH of a
# non-login shell. Resolving it here rather than assuming `railway` is callable
# is the difference between this script working from cron/CI and failing with a
# bare "command not found" ten minutes before a demo.
RAILWAY=""
for candidate in "$(command -v railway 2>/dev/null)" "$HOME/.railway/bin/railway" /usr/local/bin/railway /opt/homebrew/bin/railway; do
  if [ -n "$candidate" ] && [ -x "$candidate" ]; then RAILWAY="$candidate"; break; fi
done
[ -n "$RAILWAY" ] || die "Railway CLI not found. Install: brew install railway"
command -v python3 >/dev/null 2>&1 || die "python3 not found (needed to parse Railway JSON)"
command -v curl    >/dev/null 2>&1 || die "curl not found"

rw() { RAILWAY_CALLER="$CALLER" RAILWAY_AGENT_SESSION="$SESSION" "$RAILWAY" "$@" -p "$PROJECT_ID" -e "$ENVIRONMENT"; }

require_auth() {
  RAILWAY_CALLER="$CALLER" RAILWAY_AGENT_SESSION="$SESSION" "$RAILWAY" whoami >/dev/null 2>&1 \
    || die "Not signed in to Railway. Run: $RAILWAY login"
}

# --- GraphQL --------------------------------------------------------------
RW_TOKEN=""
load_token() {
  [ -n "$RW_TOKEN" ] && return 0
  [ -f "$HOME/.railway/config.json" ] || die "No ~/.railway/config.json -- run: $RAILWAY login"
  # The field is .user.accessToken. .user.token also exists and looks plausible,
  # but backboard rejects it with an opaque "Not Authorized" -- worth naming
  # here because the failure gives no hint that the wrong key was picked.
  RW_TOKEN=$(python3 -c '
import json, os, sys
try:
    sys.stdout.write(json.load(open(os.path.expanduser("~/.railway/config.json")))["user"]["accessToken"])
except Exception:
    pass
')
  [ -n "$RW_TOKEN" ] || die "No accessToken in ~/.railway/config.json -- run: $RAILWAY login"
}

gql() {
  load_token
  curl -s --max-time 60 "$API" \
    -H "Authorization: Bearer $RW_TOKEN" -H "Content-Type: application/json" -d "$1"
}

# Service and environment IDs, resolved once by name. Looked up rather than
# hardcoded so the script keeps working if a service is ever recreated.
ENV_ID=""
SVC_MAP=""
resolve_ids() {
  [ -n "$ENV_ID" ] && return 0
  local resp
  # shellcheck disable=SC2016  # $vars here are GraphQL, not shell
  resp=$(gql "$(printf '{"query":"query($id:String!){project(id:$id){environments{edges{node{id name}}}services{edges{node{id name}}}}}","variables":{"id":"%s"}}' "$PROJECT_ID")")
  ENV_ID=$(printf '%s' "$resp" | ENVNAME="$ENVIRONMENT" python3 -c '
import json, os, sys
try:
    d = json.load(sys.stdin)
    want = os.environ["ENVNAME"]
    for e in d["data"]["project"]["environments"]["edges"]:
        if e["node"]["name"] == want:
            sys.stdout.write(e["node"]["id"]); break
except Exception:
    pass
')
  SVC_MAP=$(printf '%s' "$resp" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
    for e in d["data"]["project"]["services"]["edges"]:
        print(e["node"]["name"] + "\t" + e["node"]["id"])
except Exception:
    pass
')
  [ -n "$ENV_ID" ]  || die "Environment \"$ENVIRONMENT\" not found in project $PROJECT_ID"
  [ -n "$SVC_MAP" ] || die "Could not list services for project $PROJECT_ID"
}

svc_id() {
  resolve_ids
  printf '%s\n' "$SVC_MAP" | awk -F'\t' -v n="$1" '$1 == n { print $2; exit }'
}

# --- state ----------------------------------------------------------------
# Status of a service's live deployment. SUCCESS means it is up; REMOVED means
# parked; NONE means the service has never deployed.
#
# Deliberately NOT just the newest record. A push that misses a service's watch
# patterns still writes a SKIPPED deployment, so nufi-chat's newest entry is
# routinely SKIPPED while the SUCCESS deployment underneath it is the one
# actually serving traffic. Reading the newest row blind reports a healthy
# service as down, which makes `up` bounce it for no reason and makes `status`
# lie. Filter the build-only states out and take the newest real one.
svc_status() {
  local out
  out=$(rw deployment list -s "$1" --limit 15 --json 2>/dev/null)
  [ -n "$out" ] || { printf 'UNKNOWN'; return; }
  printf '%s' "$out" | python3 -c '
import json, sys
NOISE = {"SKIPPED"}
try:
    d = json.load(sys.stdin)
    real = [x for x in d if x.get("status") not in NOISE]
    sys.stdout.write(real[0]["status"] if real else ("NONE" if not d else "SKIPPED"))
except Exception:
    sys.stdout.write("UNKNOWN")
'
}

# Deployment id of the live deployment. Same SKIPPED filtering as svc_status --
# a build-only record has an id too, and restarting that one does nothing.
svc_deployment_id() {
  local out
  out=$(rw deployment list -s "$1" --limit 15 --json 2>/dev/null)
  [ -n "$out" ] || return 1
  printf '%s' "$out" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
    real = [x for x in d if x.get("status") != "SKIPPED"]
    sys.stdout.write(real[0]["id"] if real else "")
except Exception:
    pass
'
}

wait_for() {
  local svc="$1" waited=0 st
  while [ "$waited" -lt "$DEPLOY_TIMEOUT" ]; do
    st=$(svc_status "$svc")
    case "$st" in
      SUCCESS)         grn "    ✓ $svc live (${waited}s)"; return 0 ;;
      FAILED|CRASHED)  red "    ✗ $svc -> $st"; return 1 ;;
    esac
    sleep 5
    waited=$((waited + 5))
    [ $((waited % 30)) -eq 0 ] && dim "    … $svc: $st (${waited}s)"
  done
  red "    ✗ $svc did not reach SUCCESS within ${DEPLOY_TIMEOUT}s (last: ${st:-?})"
  return 1
}

# Idempotent: a service already live is left alone, so re-running `up` after a
# partial failure costs nothing and does not bounce a working service.
ensure_up() {
  local svc="$1" st id out
  st=$(svc_status "$svc")
  if [ "$st" = "SUCCESS" ]; then
    dim "    · $svc already live"
    return 0
  fi
  id=$(svc_id "$svc")
  [ -n "$id" ] || { red "    ✗ no such service: $svc"; return 1; }
  printf '    → deploying %s (was %s)\n' "$svc" "$st"
  # shellcheck disable=SC2016  # $vars here are GraphQL, not shell
  out=$(gql "$(printf '{"query":"mutation($s:String!,$e:String!){serviceInstanceDeployV2(serviceId:$s,environmentId:$e)}","variables":{"s":"%s","e":"%s"}}' "$id" "$ENV_ID")" \
    | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    print("ERR unparseable response"); sys.exit()
if d.get("errors"):
    print("ERR " + str(d["errors"][0].get("message", "unknown")))
else:
    v = (d.get("data") or {}).get("serviceInstanceDeployV2")
    print("OK " + v if v else "ERR empty response")
')
  case "$out" in
    OK\ *) return 0 ;;
    *)     red "    ✗ deploy failed for $svc: ${out#ERR }"; return 1 ;;
  esac
}

park() {
  local svc="$1" st
  st=$(svc_status "$svc")
  if [ "$st" = "REMOVED" ] || [ "$st" = "NONE" ]; then
    dim "    · $svc already parked"
    return 0
  fi
  printf '    → parking %s\n' "$svc"
  rw down -s "$svc" -y >/dev/null 2>&1 \
    || { ylw "    ! could not park $svc (already gone?)"; return 0; }
  grn "    ✓ $svc parked"
}

# --- commands -------------------------------------------------------------
cmd_status() {
  require_auth
  printf '\n%-32s %-10s %s\n' "SERVICE" "STATUS" "ROLE"
  printf -- '---------------------------------------------------------------\n'
  for s in $RESIDENT; do printf '%-32s %-10s %s\n' "$s" "$(svc_status "$s")" "resident"; done
  for s in $PARKED;   do printf '%-32s %-10s %s\n' "$s" "$(svc_status "$s")" "parked between demos"; done
  for s in $SLEEPERS; do printf '%-32s %-10s %s\n' "$s" "$(svc_status "$s")" "serverless (auto)"; done
  printf '\n'
  # A serverless service reports SUCCESS whether awake or asleep -- the
  # deployment stays valid while the container is stopped -- so the table above
  # cannot tell you which of the sleepers is actually warm. Only a request can.
  dim "Note: sleepers show SUCCESS even while asleep; only a request wakes them."
}

cmd_up() {
  local restart_chat=1
  for a in "$@"; do [ "$a" = "--no-restart" ] && restart_chat=0; done
  require_auth
  resolve_ids

  step "1/5  Databases (pgvector, meilisearch)"
  # Started together, waited on together: they are independent of each other,
  # and serialising them would double the slowest path for no benefit.
  ensure_up pgvector    || die "could not start pgvector"
  ensure_up meilisearch || die "could not start meilisearch"
  wait_for  pgvector    || die "pgvector failed to start"
  wait_for  meilisearch || die "meilisearch failed to start"

  step "2/5  RAG API (needs pgvector accepting connections)"
  ensure_up librechat-rag-api-dev-lite || die "could not start RAG API"
  wait_for  librechat-rag-api-dev-lite || die "RAG API failed to start"

  step "3/5  Resident services"
  for s in $RESIDENT; do ensure_up "$s" || die "could not start $s"; done
  for s in $RESIDENT; do wait_for  "$s" || die "$s failed to start"; done

  if [ "$restart_chat" -eq 1 ]; then
    step "4/5  Restarting nufi-chat so it reconnects to Meilisearch + Mongo"
    # Not `railway restart`: the CLI fires the restart and then blocks. It was
    # measured still running 10 minutes after chat.nufi.me was already answering
    # 200 again, which stalls this script indefinitely at the worst moment --
    # right before a demo. The mutation does the same work and returns at once.
    local dep
    dep=$(svc_deployment_id nufi-chat)
    if [ -n "$dep" ]; then
      # shellcheck disable=SC2016  # $id here is GraphQL, not shell
      gql "$(printf '{"query":"mutation($id:String!){deploymentRestart(id:$id)}","variables":{"id":"%s"}}' "$dep")" >/dev/null
    else
      ylw "    ! could not resolve nufi-chat deployment -- skipping restart"
    fi
    # Deliberately NOT wait_for here. A restart reuses the existing deployment,
    # so its status reads SUCCESS for the whole restart -- wait_for would return
    # in 0s having verified nothing, and print a tick that means nothing. The
    # health endpoint is the only signal that the process actually came back.
    # The old process keeps answering for a moment after the restart is issued,
    # so polling immediately can latch onto a 200 from the container being
    # replaced and report success before the restart has happened at all.
    local hwaited=15 hcode=""
    sleep 15
    while [ "$hwaited" -lt 195 ]; do
      hcode=$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 "$HEALTH_URL" 2>/dev/null)
      [ "$hcode" = "200" ] && break
      sleep 5
      hwaited=$((hwaited + 5))
      [ $((hwaited % 30)) -eq 0 ] && dim "    … nufi-chat: ${hcode:-no response} (${hwaited}s)"
    done
    [ "$hcode" = "200" ] || die "nufi-chat did not answer $HEALTH_URL after restart (last: ${hcode:-no response})"
    grn "    ✓ nufi-chat answering again (${hwaited}s)"
  else
    step "4/5  Skipping nufi-chat restart (--no-restart)"
    ylw "    ! search may stay broken until nufi-chat is restarted"
  fi

  step "5/5  Warming public URLs"
  # The serverless three return 502 on the very first request after sleeping.
  # Absorbing that here means the demo does not open on an error page.
  local code
  for url in $PUBLIC_URLS; do
    code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 60 "$url" 2>/dev/null)
    if [ "$code" = "200" ] || [ "$code" = "301" ] || [ "$code" = "302" ]; then
      grn "    ✓ $url ($code)"
    else
      ylw "    ! $url ($code) -- retrying once"
      sleep 8
      code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 60 "$url" 2>/dev/null)
      if [ "$code" = "200" ]; then grn "    ✓ $url ($code)"; else red "    ✗ $url ($code)"; fi
    fi
  done

  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 30 "$HEALTH_URL" 2>/dev/null)
  printf '\n'
  if [ "$code" = "200" ]; then
    grn "READY — chat.nufi.me is healthy. Everything is up."
  else
    red "chat.nufi.me/health returned $code — check: $RAILWAY logs -s nufi-chat"
    exit 1
  fi
}

cmd_down() {
  local all=0
  for a in "$@"; do [ "$a" = "--all" ] && all=1; done
  require_auth

  step "Parking demo stack"
  # Reverse of bring-up: the RAG API goes first so it is not left holding a
  # connection to a pgvector that is disappearing underneath it.
  park librechat-rag-api-dev-lite
  park meilisearch
  park pgvector

  if [ "$all" -eq 1 ]; then
    step "Parking resident services (--all)"
    park nufi-chat
    park MongoDB
    printf '\n'
    ylw "chat.nufi.me is now OFFLINE. Run './demo.sh up' before the next demo."
    ylw "Waking nufi-chat REBUILDS it from the default branch -- allow ~5 min."
  else
    printf '\n'
    grn "Demo stack parked. chat.nufi.me stays live."
    dim "Search and file-upload/RAG will error until './demo.sh up'."
  fi
}

case "${1:-}" in
  up)     shift; cmd_up "$@" ;;
  down)   shift; cmd_down "$@" ;;
  status) cmd_status ;;
  *)      sed -n '/^# USAGE/,/^# ====/{ /^# ====/d; s/^# \{0,1\}//; p; }' "$0"; exit 1 ;;
esac
