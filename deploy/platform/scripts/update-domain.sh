#!/usr/bin/env bash
# =============================================================================
# scripts/update-domain.sh — rewrite URL-bearing env vars to a new base domain.
# =============================================================================
#
# Run after the Cloudflare Tunnel hostnames are pointed at a new domain
# (see docs/cloudflare-tunnel-setup.md). This script edits the `.env` file
# so LibreChat, Console, Langfuse, etc. emit the right absolute URLs in
# emails, OAuth callbacks, share links, and invite flows.
#
# USAGE
#   ./scripts/update-domain.sh                    # interactive prompt
#   ./scripts/update-domain.sh codechi.me         # non-interactive
#   ./scripts/update-domain.sh codechi.me --yes   # skip confirmation
#
# What it does
#   - Backs up .env to .env.bak.<timestamp>
#   - Updates every URL-bearing env var below to https://<sub>.<domain>
#   - Leaves all other env vars untouched
#   - Prints the docker compose command to apply the change
#
# Mapping (edit here when adding a new public surface):
#   chat.<domain>      -> DOMAIN_CLIENT, DOMAIN_SERVER
#   langfuse.<domain>  -> NEXTAUTH_URL, LANGFUSE_HOST_PUBLIC
#   console.<domain>   -> CONSOLE_PUBLIC_URL
#   api.<domain>       -> LITELLM_PUBLIC_URL
# =============================================================================

set -euo pipefail

ENV_FILE="${ENV_FILE:-.env}"
DOMAIN="${1:-}"
ASSUME_YES=0
[[ "${2:-}" == "--yes" ]] && ASSUME_YES=1

# --- Mapping: env var -> subdomain ------------------------------------------
# Keys are env-var names; values are the subdomain that should front them.
# Add new entries here when a new public surface is introduced.
declare -a VARS=(
  "DOMAIN_CLIENT:chat"
  "DOMAIN_SERVER:chat"
  "NEXTAUTH_URL:langfuse"
  "LANGFUSE_HOST_PUBLIC:langfuse"
  "CONSOLE_PUBLIC_URL:console"
  "LITELLM_PUBLIC_URL:api"
)

# --- Pre-flight --------------------------------------------------------------

if [[ ! -f "$ENV_FILE" ]]; then
  echo "error: $ENV_FILE not found (run from repo root)" >&2
  exit 1
fi

if [[ -z "$DOMAIN" ]]; then
  read -r -p "Base domain (e.g. codechi.me): " DOMAIN
fi

if [[ ! "$DOMAIN" =~ ^[a-z0-9.-]+\.[a-z]{2,}$ ]]; then
  echo "error: '$DOMAIN' does not look like a base domain (expected something like 'codechi.me')" >&2
  exit 1
fi

# --- Show planned diff -------------------------------------------------------

echo
echo "Planned changes to $ENV_FILE:"
echo
printf "  %-26s %-50s -> %s\n" "VAR" "CURRENT" "NEW"
echo "  ----------------------------------------------------------------------------------------"

NEW_LINES=()
for entry in "${VARS[@]}"; do
  key="${entry%%:*}"
  sub="${entry##*:}"
  new_val="https://${sub}.${DOMAIN}"

  current=$(grep -E "^${key}=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- || true)
  current="${current:-(not set)}"

  printf "  %-26s %-50s -> %s\n" "$key" "$current" "$new_val"
  NEW_LINES+=("${key}=${new_val}")
done

echo

if [[ $ASSUME_YES -ne 1 ]]; then
  read -r -p "Apply these changes? [y/N] " reply
  [[ "$reply" =~ ^[Yy]$ ]] || { echo "aborted."; exit 0; }
fi

# --- Backup ------------------------------------------------------------------

BACKUP="${ENV_FILE}.bak.$(date +%Y%m%d-%H%M%S)"
cp "$ENV_FILE" "$BACKUP"
echo "backup: $BACKUP"

# --- Apply -------------------------------------------------------------------

for entry in "${VARS[@]}"; do
  key="${entry%%:*}"
  sub="${entry##*:}"
  new_val="https://${sub}.${DOMAIN}"

  if grep -qE "^${key}=" "$ENV_FILE"; then
    # Use a delimiter that won't appear in URLs (|)
    sed -i.tmp "s|^${key}=.*|${key}=${new_val}|" "$ENV_FILE"
    rm -f "${ENV_FILE}.tmp"
  else
    echo "${key}=${new_val}" >> "$ENV_FILE"
  fi
done

echo "done."
echo
echo "next: recreate the services that read .env at startup:"
echo
echo "  docker compose up -d --force-recreate librechat console langfuse-web"
echo
