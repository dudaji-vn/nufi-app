#!/usr/bin/env bash
# =============================================================================
# bootstrap.sh — first-run setup for nufi-chat
#
# Creates .env from .env.example, fills missing secrets, prompts for
# user-supplied values (with auto-detect where possible), then optionally
# brings the stack up.
#
# Idempotent — re-running will not overwrite values that are already set.
#
# USAGE
#   ./bootstrap.sh             # interactive (default)
#   ./bootstrap.sh --no-up     # configure only, don't run docker compose up
#   ./bootstrap.sh --yes       # accept defaults / auto-detect, no prompts
#   ./bootstrap.sh --help
# =============================================================================

set -euo pipefail
cd "$(dirname "$0")"

# --- pretty output -----------------------------------------------------------
if [ -t 1 ]; then
  BOLD=$'\033[1m'; DIM=$'\033[2m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'
  RED=$'\033[31m'; CYAN=$'\033[36m'; RESET=$'\033[0m'
else
  BOLD=""; DIM=""; GREEN=""; YELLOW=""; RED=""; CYAN=""; RESET=""
fi
step() { echo "${CYAN}==>${RESET} ${BOLD}$*${RESET}"; }
ok()   { echo "    ${GREEN}✓${RESET} $*"; }
warn() { echo "    ${YELLOW}!${RESET} $*"; }
die()  { echo "${RED}error:${RESET} $*" >&2; exit 1; }

# --- args --------------------------------------------------------------------
NO_UP=0
ASSUME_YES=0
while [ $# -gt 0 ]; do
  case "$1" in
    --no-up) NO_UP=1; shift ;;
    --yes|-y) ASSUME_YES=1; shift ;;
    -h|--help) sed -n '2,15p' "$0"; exit 0 ;;
    *) die "unknown flag: $1 (try --help)" ;;
  esac
done

# --- helpers -----------------------------------------------------------------
gen() {
  case "$1" in
    hex32) openssl rand -hex 32 ;;
    hex16) openssl rand -hex 16 ;;
    *) die "unknown generator: $1" ;;
  esac
}

# Escape a value for safe use as sed's replacement when '|' is the delimiter.
sed_escape() { printf '%s' "$1" | sed 's|[\\&|]|\\&|g'; }

# Set KEY=VALUE in .env. Replaces existing line, or appends if absent.
set_env_var() {
  local key=$1 value=$2
  local esc; esc=$(sed_escape "$value")
  if grep -qE "^${key}=" .env; then
    sed -i.bak "s|^${key}=.*|${key}=${esc}|" .env && rm -f .env.bak
  else
    echo "${key}=${value}" >> .env
  fi
}

# Read current value of KEY from .env (empty string if unset or "KEY=").
get_env_var() {
  local line; line=$(grep -E "^$1=" .env || true)
  printf '%s' "${line#"$1"=}"
}

# If KEY's current value is empty, fill with a freshly generated secret.
# Never overwrites an existing value — re-runs of bootstrap are safe.
fill_secret_if_empty() {
  local key=$1 generator=$2
  if [ -z "$(get_env_var "$key")" ]; then
    set_env_var "$key" "$(gen "$generator")"
    ok "generated ${key}"
  else
    ok "${key} already set (kept)"
  fi
}

# Show current value of KEY, ask user for new one. Empty input = keep.
# In --yes mode, keeps the current value silently.
prompt_var() {
  local key=$1 hint=$2
  local current; current=$(get_env_var "$key")
  if [ "$ASSUME_YES" -eq 1 ]; then
    ok "${key} = ${current:-(empty)} (kept)"
    return
  fi
  printf "    ${BOLD}%s${RESET} ${DIM}— %s${RESET}\n" "$key" "$hint"
  printf "    current: %s\n" "${current:-(empty)}"
  printf "    new (enter to keep): "
  local new; read -r new
  if [ -n "$new" ]; then
    set_env_var "$key" "$new"
    ok "${key} updated"
  else
    ok "${key} kept"
  fi
  echo
}

# --- 1. prerequisites --------------------------------------------------------
step "1/4 Checking prerequisites"
command -v docker >/dev/null || die "docker not installed"
docker compose version >/dev/null 2>&1 || die "docker compose plugin missing"
command -v openssl >/dev/null || die "openssl not installed"
docker info >/dev/null 2>&1 || die "Docker daemon not running"
ok "docker + openssl ok"

# Shared-network mode is opt-in via the override symlink. Only check that the
# referenced external network actually exists when the override is active —
# teammates who reach the backend by URL never need it.
shared_mode=0
if [ -L docker-compose.override.yml ] && \
   [ "$(readlink docker-compose.override.yml)" = "docker-compose.shared-network.yml" ]; then
  shared_mode=1
  net_name=$(grep -E "^SHARED_DOCKER_NETWORK=" .env 2>/dev/null | head -1 | cut -d= -f2-)
  net_name="${net_name:-npuops_npuops}"
  if docker network ls --format '{{.Name}}' | grep -qx "$net_name"; then
    ok "shared docker network '$net_name' found"
  else
    warn "shared-network mode is on but '$net_name' does not exist yet"
    warn "create that network (or the upstream stack) before bringing nufi-chat up"
  fi
fi

# --- 2. .env scaffold --------------------------------------------------------
step "2/4 Bootstrapping .env"
if [ ! -f .env ]; then
  [ -f .env.example ] || die ".env.example missing — are you in the repo root?"
  cp .env.example .env
  ok ".env created from .env.example"
else
  ok ".env exists — only filling missing values"
fi

fill_secret_if_empty JWT_SECRET         hex32
fill_secret_if_empty JWT_REFRESH_SECRET hex32
fill_secret_if_empty CREDS_KEY          hex32
fill_secret_if_empty CREDS_IV           hex16

# --- 3. user-supplied values -------------------------------------------------
step "3/4 Configuration values"
echo "    (Press enter at any prompt to keep the current value)"
echo

prompt_var IMAGE_TAG         "Image tag of ghcr.io/dudaji-vn/nufichat — empty = rolling default (main), 'nufi-v0.8.6' = pinned release"
prompt_var DOMAIN_CLIENT     "Public URL clients connect to (e.g. https://chat.nufi.me)"
prompt_var DOMAIN_SERVER     "Public URL the server uses for emails / OAuth callbacks"
prompt_var APP_TITLE         "Brand title shown in the UI"
prompt_var BACKEND_BASE_URL  "Backend OpenAI-compatible endpoint (e.g. https://api.openai.com/v1)"

# BACKEND_API_KEY: try auto-detecting from sibling stacks. The npuops-platform
# repo stores its bearer key as LITELLM_MASTER_KEY, so we read that name from
# the source and write it under our generic name.
candidates=(
  "${HOME}/npuops-platform/.env"
  "$(cd .. 2>/dev/null && pwd)/npuops-platform/.env"
)
detected=""
detected_from=""
for c in "${candidates[@]}"; do
  if [ -f "$c" ]; then
    v=$(grep -E "^LITELLM_MASTER_KEY=" "$c" | head -1 | cut -d= -f2-)
    if [ -n "$v" ]; then detected="$v"; detected_from="$c"; ok "found a bearer key in $c"; break; fi
  fi
done

if [ -z "$(get_env_var BACKEND_API_KEY)" ] && [ -n "$detected" ]; then
  if [ "$ASSUME_YES" -eq 1 ]; then
    ans=Y
  else
    printf "    Use that as BACKEND_API_KEY? [Y/n] "
    read -r ans
  fi
  if [[ ! "$ans" =~ ^[Nn]$ ]]; then
    set_env_var BACKEND_API_KEY "$detected"
    ok "BACKEND_API_KEY copied from ${detected_from}"
  fi
  echo
elif [ -z "$(get_env_var BACKEND_API_KEY)" ]; then
  warn "could not auto-detect a bearer key from a sibling stack — paste it manually below"
  echo
fi

prompt_var BACKEND_API_KEY "Bearer key sent to the endpoint above"

# --- 3b. shared Docker network (optional) -----------------------------------
# Enable this when BACKEND_BASE_URL uses a Docker service name (e.g.
# http://litellm-proxy:4000/v1) — the api container then joins an existing
# external network so Docker DNS can resolve that hostname.
echo
step "Shared Docker network (optional)"
echo "    Enable only if the backend URL above uses a Docker service name."
echo

if [ "$ASSUME_YES" -ne 1 ]; then
  if [ "$shared_mode" -eq 1 ]; then
    current_net=$(get_env_var SHARED_DOCKER_NETWORK)
    ok "currently ON (network: ${current_net:-npuops_npuops})"
    printf "    keep / change name / disable [K/c/d]: "
    read -r ans
    case "${ans:-K}" in
      d|D)
        rm -f docker-compose.override.yml
        ok "disabled"
        ;;
      c|C)
        printf "    new network name: "; read -r net
        if [ -n "$net" ]; then
          set_env_var SHARED_DOCKER_NETWORK "$net"
          ok "network set to '$net'"
        fi
        ;;
      *) ok "kept" ;;
    esac
  else
    printf "    Enable shared-network mode? [y/N] "
    read -r ans
    if [[ "${ans:-N}" =~ ^[Yy]$ ]]; then
      default_net=$(get_env_var SHARED_DOCKER_NETWORK)
      default_net="${default_net:-npuops_npuops}"
      printf "    Network name [%s]: " "$default_net"
      read -r net
      net="${net:-$default_net}"
      set_env_var SHARED_DOCKER_NETWORK "$net"
      ln -sf docker-compose.shared-network.yml docker-compose.override.yml
      ok "enabled (network: $net)"
    fi
  fi
fi
echo

# --- 4. up -------------------------------------------------------------------
step "4/4 Stack"

# Bail loudly if anything required is still empty after prompts.
missing=()
for k in JWT_SECRET JWT_REFRESH_SECRET CREDS_KEY CREDS_IV BACKEND_BASE_URL BACKEND_API_KEY; do
  [ -z "$(get_env_var "$k")" ] && missing+=("$k")
done
if [ "${#missing[@]}" -gt 0 ]; then
  warn "still empty: ${missing[*]}"
  warn "fill these in .env (or re-run bootstrap) before starting the stack"
  exit 1
fi

if [ "$NO_UP" -eq 1 ]; then
  ok "skipping docker compose up (--no-up)"
  echo
  echo "    when ready: docker compose pull && docker compose up -d"
  exit 0
fi

if [ "$ASSUME_YES" -ne 1 ]; then
  printf "    Run docker compose up now? [Y/n] "
  read -r ans
  if [[ "$ans" =~ ^[Nn]$ ]]; then
    ok "skipped — run later with: docker compose pull && docker compose up -d"
    exit 0
  fi
fi

step "Pulling image"
docker compose pull
step "Starting stack"
docker compose up -d
ok "stack started"

echo
echo "    ${BOLD}Open${RESET} http://localhost:3081 (or http://<VM_IP>:3081)"
echo "    ${BOLD}Logs${RESET} docker compose logs -f api"
echo "    ${BOLD}Down${RESET} docker compose down       (keeps mongo data)"
echo "    ${BOLD}Wipe${RESET} docker compose down -v    (drops mongo data)"
