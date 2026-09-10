#!/bin/bash
# bootstrap.sh — bring up the NuFi mesh coordinator (headscale + Caddy).
#
#   MESH_SERVER_HOST=mesh.nufi.me MESH_BASE_DOMAIN=box.nufi.me \
#     TLS_MODE=acme ACME_EMAIL=ops@nufi.me ./bootstrap.sh
#
#   ./bootstrap.sh --dry-run          print the rendered config.yaml and
#                                      Caddyfile.rendered, touch nothing
#   ./bootstrap.sh --rotate-key       mint a new API key even if one already
#                                      exists (the old one still works until
#                                      it expires or you run `apikeys expire`)
#
# Renders config/headscale.yaml.tmpl and Caddyfile with `sed` (@VAR@
# placeholders), starts the stack, creates the headscale user `box`
# (idempotent), mints its API key (printed once — headscale itself cannot
# show it again), and prints the DNS facts the operator must set. Re-running
# with the same env keeps .env's answers, same as deploy/box/install-box.sh.
# bash 3.2 compatible.
#
# COORDINATOR_ENV        — where .env lives (tests point this at a scratch
#                           file so they never touch a real coordinator's).
# COORDINATOR_COMPOSE_EXTRA — space-separated extra `-f` compose files layered
#                           last, e.g. docker-compose.lab-ports.yml.
set -euo pipefail

# ---------- tiny helpers -----------------------------------------------------
say()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m ok\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m !!\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m xx\033[0m %s\n' "$*" >&2; exit 1; }

DRY=0; ROTATE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY=1 ;;
    --rotate-key) ROTATE=1 ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) die "unknown argument: $1" ;;
  esac
  shift
done

HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

# ---------- resolve config: keep previous answers on a re-run ----------------
# Same pattern as install-box.sh: caller-provided env vars always win; an
# existing .env fills in whatever the caller did not set; a fresh coordinator
# with neither must be told explicitly.
COORDINATOR_ENV="${COORDINATOR_ENV:-$HERE/.env}"
REUSE_VARS="MESH_SERVER_HOST MESH_BASE_DOMAIN TLS_MODE ACME_EMAIL"
for v in $REUSE_VARS; do eval "_caller_$v=\${$v:-}"; done
if [ -f "$COORDINATOR_ENV" ]; then
  ok ".env exists; keeping its answers"
  # shellcheck disable=SC1090
  set -a; . "$COORDINATOR_ENV"; set +a
fi
for v in $REUSE_VARS; do
  eval "_cv=\${_caller_$v}"
  [ -n "$_cv" ] && eval "$v=\"\$_cv\""
done

[ -n "${MESH_SERVER_HOST:-}" ] || die "MESH_SERVER_HOST is not set (env or $COORDINATOR_ENV)"
[ -n "${MESH_BASE_DOMAIN:-}" ] || die "MESH_BASE_DOMAIN is not set (env or $COORDINATOR_ENV)"
TLS_MODE="${TLS_MODE:-acme}"
ACME_EMAIL="${ACME_EMAIL:-}"
case "$TLS_MODE" in
  acme|internal) ;;
  *) die "TLS_MODE must be acme or internal, got: $TLS_MODE" ;;
esac
[ "$TLS_MODE" = "acme" ] && [ -z "$ACME_EMAIL" ] && die "ACME_EMAIL is required when TLS_MODE=acme"

# headscale hard-requires dns.base_domain to differ from the server_url
# domain; a base_domain that is a suffix of (or equal to) the server host is
# exactly the case the config-example.yaml comment warns about.
case ".$MESH_SERVER_HOST" in
  *".$MESH_BASE_DOMAIN") die "MESH_BASE_DOMAIN ($MESH_BASE_DOMAIN) must not be a suffix of MESH_SERVER_HOST ($MESH_SERVER_HOST) — headscale requires the MagicDNS base_domain to differ from the server hostname" ;;
esac

# ---------- render ------------------------------------------------------------
render_headscale_yaml() {
  sed -e "s|@MESH_SERVER_HOST@|$MESH_SERVER_HOST|g" -e "s|@MESH_BASE_DOMAIN@|$MESH_BASE_DOMAIN|g" \
    "$HERE/config/headscale.yaml.tmpl"
}

render_caddyfile() {
  local global_opt site_tls
  if [ "$TLS_MODE" = "internal" ]; then
    # Caddy would otherwise try (and fail, harmlessly but noisily) to install
    # its self-signed root into a system trust store that does not exist
    # inside the container.
    global_opt="skip_install_trust"
    site_tls="tls internal"
  else
    # No explicit per-site `tls`: Caddy's automatic HTTPS obtains a public
    # cert from Let's Encrypt for {\$MESH_SERVER_HOST} using this contact.
    global_opt="email {\$ACME_EMAIL}"
    site_tls=""
  fi
  sed -e "s|@GLOBAL_TLS_OPT@|$global_opt|" -e "s|@SITE_TLS@|$site_tls|" "$HERE/Caddyfile"
}

if [ "$DRY" = 1 ]; then
  echo "--- config/headscale.yaml ---"
  render_headscale_yaml
  echo "--- Caddyfile.rendered ---"
  render_caddyfile
  echo "--- DNS facts ---"
  echo "1. Create an A record for $MESH_SERVER_HOST pointing at this VPS's public IP."
  echo "2. $MESH_BASE_DOMAIN is not a suffix of $MESH_SERVER_HOST — good, headscale requires that."
  exit 0
fi

say "Rendering config/headscale.yaml and Caddyfile.rendered"
render_headscale_yaml > "$HERE/config/headscale.yaml"
render_caddyfile > "$HERE/Caddyfile.rendered"
mkdir -p "$HERE/data"

if [ ! -f "$COORDINATOR_ENV" ]; then
  say "Writing $COORDINATOR_ENV"
  cat > "$COORDINATOR_ENV" <<EOF
MESH_SERVER_HOST=$MESH_SERVER_HOST
MESH_BASE_DOMAIN=$MESH_BASE_DOMAIN
TLS_MODE=$TLS_MODE
ACME_EMAIL=$ACME_EMAIL
EOF
  ok ".env written"
fi

COMPOSE="docker compose -f docker-compose.yml"
for f in ${COORDINATOR_COMPOSE_EXTRA:-}; do
  [ -f "$f" ] || die "COORDINATOR_COMPOSE_EXTRA: no such file: $f"
  COMPOSE="$COMPOSE -f $f"
done

say "Starting the stack ($COMPOSE up -d)"
$COMPOSE up -d

say "Waiting for headscale and caddy to report healthy (up to 5 minutes)"
healthy=0
for _ in $(seq 1 60); do
  hs="$($COMPOSE ps --format '{{.Name}} {{.Health}}' | grep -c 'headscale.*healthy' || true)"
  cd_="$($COMPOSE ps --format '{{.Name}} {{.Health}}' | grep -c 'caddy.*healthy' || true)"
  if [ "$hs" -ge 1 ] && [ "$cd_" -ge 1 ]; then healthy=1; break; fi
  sleep 5
done
[ "$healthy" = 1 ] || die "headscale/caddy did not become healthy in time; $COMPOSE logs"
ok "headscale and caddy are healthy"

# ---------- user `box` (idempotent) -------------------------------------------
say "Checking for the headscale user 'box'"
users_json="$($COMPOSE exec -T headscale headscale users list -o json)"
have_box_user="$(printf '%s' "$users_json" | python3 -c '
import json, sys
users = json.load(sys.stdin) or []
print("1" if any(u.get("name") == "box" for u in users) else "0")
')"
if [ "$have_box_user" = "1" ]; then
  ok "user 'box' already exists"
else
  $COMPOSE exec -T headscale headscale users create box
  ok "created user 'box'"
fi

# ---------- API key (idempotent unless --rotate-key) --------------------------
say "Checking for an existing API key"
keys_json="$($COMPOSE exec -T headscale headscale apikeys list -o json)"
key_count="$(printf '%s' "$keys_json" | python3 -c 'import json, sys; print(len(json.load(sys.stdin) or []))')"
if [ "$key_count" -gt 0 ] && [ "$ROTATE" != 1 ]; then
  ok "api key already minted; rotate with --rotate-key"
else
  say "Minting an API key (365d)"
  api_key="$($COMPOSE exec -T headscale headscale apikeys create --expiration 365d)"
  echo
  echo "MESH_API_KEY=$api_key"
  echo "Store this in the box's MESH_API_KEY now — headscale will not show it again."
  echo
fi

# ---------- internal CA (TLS_MODE=internal only) -------------------------------
if [ "$TLS_MODE" = "internal" ]; then
  say "Exporting Caddy's internal root CA to data/coordinator-ca.crt"
  $COMPOSE cp caddy:/data/caddy/pki/authorities/local/root.crt "$HERE/data/coordinator-ca.crt"
  ok "data/coordinator-ca.crt written — trust it on the lab/VM"
fi

# ---------- done ----------------------------------------------------------------
cat <<EOF

  Coordinator is up.

  MESH_SERVER_URL: https://$MESH_SERVER_HOST
  MagicDNS base:   $MESH_BASE_DOMAIN

  DNS facts:
    1. Create an A record for $MESH_SERVER_HOST pointing at this VPS's public IP.
    2. $MESH_BASE_DOMAIN must not be a suffix of $MESH_SERVER_HOST (already true).

  Give the box's installer MESH_SERVER_URL above and the MESH_API_KEY printed
  when it was minted (only shown once; rotate with: ./bootstrap.sh --rotate-key).
EOF
