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

if docker network ls --format '{{.Name}}' | grep -qx npuops_npuops; then
  ok "npuops_npuops network found"
else
  warn "Docker network 'npuops_npuops' not found"
  warn "Bring up the npuops-platform stack first:"
  warn "  cd ~/npuops-platform && docker compose up -d"
  warn "nufi-chat will fail to start until that network exists"
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

prompt_var DOMAIN_CLIENT "Public URL clients connect to (e.g. https://chat.nufi.me)"
prompt_var DOMAIN_SERVER "Public URL the server uses for emails / OAuth callbacks"
prompt_var APP_TITLE     "Brand title shown in the UI"

# LITELLM_MASTER_KEY: try auto-detecting from sibling npuops-platform/.env.
# Both repos usually live next to each other under ~/Workspace/DudajiVN/ on
# dev machines and under ~/ on the VM, so we check both spots.
candidates=(
  "${HOME}/npuops-platform/.env"
  "$(cd .. 2>/dev/null && pwd)/npuops-platform/.env"
)
detected=""
for c in "${candidates[@]}"; do
  if [ -f "$c" ]; then
    v=$(grep -E "^LITELLM_MASTER_KEY=" "$c" | head -1 | cut -d= -f2-)
    if [ -n "$v" ]; then detected="$v"; ok "found LITELLM_MASTER_KEY in $c"; break; fi
  fi
done

if [ -z "$(get_env_var LITELLM_MASTER_KEY)" ] && [ -n "$detected" ]; then
  if [ "$ASSUME_YES" -eq 1 ]; then
    ans=Y
  else
    printf "    Copy that value into nufi-chat .env? [Y/n] "
    read -r ans
  fi
  if [[ ! "$ans" =~ ^[Nn]$ ]]; then
    set_env_var LITELLM_MASTER_KEY "$detected"
    ok "LITELLM_MASTER_KEY copied from npuops-platform"
  fi
  echo
fi

prompt_var LITELLM_MASTER_KEY "Master key for codechi LiteLLM (paste manually if not detected)"

# --- 4. up -------------------------------------------------------------------
step "4/4 Stack"

# Bail loudly if anything required is still empty after prompts.
missing=()
for k in JWT_SECRET JWT_REFRESH_SECRET CREDS_KEY CREDS_IV LITELLM_MASTER_KEY; do
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
