#!/bin/bash
# lib/coordinator.sh — run the mesh coordinator ON this box, so a single
# machine is a self-contained appliance with no external VPS. Sourced by
# nufi-box (which provides HERE, run, die, DRY, ENVF, OS); bash 3.2 compatible.
# Turned on by install-box.sh --self-host-coordinator (NUFI_SELF_HOST_COORD=1).
#
# The coordinator itself lives in deploy/coordinator (headscale + Caddy). This
# only orchestrates it for the co-hosted case and does NOT reimplement it:
# deploy/coordinator/bootstrap.sh renders the config, starts the stack, waits
# for health, creates the user `box`, mints the API key and exports the
# internal CA — all idempotent. The glue here is the two things bootstrap.sh
# deliberately leaves to the caller: mint THIS box's own tag:box pre-auth key,
# and hand the API key / CA path back into the box's .env. Co-hosting rides
# docker-compose.selfhost.yml (internal TLS, host :80 dropped so it never
# fights the box's own Caddy) and docker-compose.mesh-selfhost.yml (resolves
# the coordinator's name to loopback for the host-network node).

# The coordinator sources, fetched next to deploy/box.
coordinator_dir() {
  local d
  d="$(cd "$HERE/../coordinator" 2>/dev/null && pwd || true)"
  { [ -n "$d" ] && [ -f "$d/bootstrap.sh" ]; } \
    || die "self-host needs deploy/coordinator fetched next to deploy/box — see README \"Self-host the coordinator on this box\""
  printf '%s' "$d"
}

# The compose invocation for the co-hosted coordinator project (its own
# compose sets name: nufi-coordinator), always with the selfhost port overlay
# that drops the host :80 publish.
coordinator_compose() {
  local d; d="$(coordinator_dir)"
  printf 'docker compose --project-directory %s -f %s/docker-compose.yml -f %s/docker-compose.selfhost.yml' "$d" "$d" "$d"
}

# The one-time API key line bootstrap.sh prints on a fresh mint (`MESH_API_KEY=…`);
# empty on a re-run, where it prints "api key already minted" instead and the
# stored key is kept. The pure string seam the tests drive.
coordinator_api_key_from_output() {
  local all
  all="$(printf '%s\n' "$1" | sed -n 's/^MESH_API_KEY=//p')"
  # First line only, but WITHOUT a `| head` — under the pipefail nufi-box runs
  # with, head closing the pipe on its first line makes sed take SIGPIPE and
  # the whole function exit 141. `${all%%$'\n'*}` does the same trim in-shell.
  printf '%s\n' "${all%%$'\n'*}"
}

# Mint THIS box's own single-use tag:box pre-auth key against the local
# coordinator. headscale v0.29.3's `preauthkeys create` takes the user's
# NUMERIC id, not its name, so resolve it from `users list -o json` first.
coordinator_mint_box_key() {
  local cc; cc="$(coordinator_compose)"
  if [ "$DRY" = 1 ]; then
    printf '  $ %s exec -T headscale headscale users list -o json   # -> numeric id of user box\n' "$cc"
    printf '  $ %s exec -T headscale headscale preauthkeys create --user <id> --tags tag:box --expiration 24h\n' "$cc"
    return 0
  fi
  local uid
  uid="$($cc exec -T headscale headscale users list -o json | python3 -c '
import json, sys
users = json.load(sys.stdin) or []
box = [u for u in users if u.get("name") == "box"]
print(box[0]["id"] if box else "")
')"
  [ -n "$uid" ] || die "the coordinator has no user 'box' yet — did bootstrap run?"
  $cc exec -T headscale headscale preauthkeys create --user "$uid" --tags tag:box --expiration 24h
}

# Bring up the co-hosted coordinator and point this box at itself.
coordinator_up() {
  [ "${NUFI_SELF_HOST_COORD:-0}" = "1" ] \
    || die "this box does not self-host a coordinator — install with: install-box.sh --self-host-coordinator"
  [ "$OS" = "Linux" ] \
    || die "self-hosting the coordinator is Ubuntu-only (the mesh node needs the host's own network namespace; Docker Desktop's host network is the Linux VM's)"
  [ -n "${MESH_SERVER_HOST:-}" ] || die "MESH_SERVER_HOST is not set (install-box.sh --self-host-coordinator sets it)"
  [ -n "${MESH_BASE_DOMAIN:-}" ] || die "MESH_BASE_DOMAIN is not set (install-box.sh --self-host-coordinator sets it)"

  local d ca_dst hs_env
  d="$(coordinator_dir)"
  ca_dst="${NUFI_DATA_DIR:-$HERE/data}/mesh-coordinator-ca.crt"
  # A --registry box mirrors headscale into its LAN registry (install-box.sh
  # derives NUFI_HEADSCALE_IMAGE); hand it to the coordinator as
  # COORD_HEADSCALE_IMAGE so its `up -d` pulls from the mirror, not ghcr.io.
  # Empty (a plain self-host box) leaves the coordinator's own pinned default.
  hs_env=""
  [ -n "${NUFI_HEADSCALE_IMAGE:-}" ] && hs_env="COORD_HEADSCALE_IMAGE=$NUFI_HEADSCALE_IMAGE "

  if [ "$DRY" = 1 ]; then
    printf '  $ TLS_MODE=internal MESH_SERVER_HOST=%s MESH_BASE_DOMAIN=%s %sCOORDINATOR_COMPOSE_EXTRA=docker-compose.selfhost.yml %s/bootstrap.sh\n' \
      "$MESH_SERVER_HOST" "$MESH_BASE_DOMAIN" "$hs_env" "$d"
    printf '  $ cp %s/data/coordinator-ca.crt %s\n' "$d" "$ca_dst"
    coordinator_mint_box_key
    printf '  $ envfile_set %s MESH_CA_FILE %s\n' "$ENVF" "$ca_dst"
    printf '  $ envfile_set %s MESH_AUTH_KEY <box tag:box key>\n' "$ENVF"
    printf '  $ envfile_set %s MESH_API_KEY <api key, on a fresh mint>\n' "$ENVF"
    return 0
  fi

  local out box_key api_key
  out="$(TLS_MODE=internal MESH_SERVER_HOST="$MESH_SERVER_HOST" MESH_BASE_DOMAIN="$MESH_BASE_DOMAIN" \
    COORD_HEADSCALE_IMAGE="${NUFI_HEADSCALE_IMAGE:-}" \
    COORDINATOR_COMPOSE_EXTRA=docker-compose.selfhost.yml "$d/bootstrap.sh" 2>&1)"
  printf '%s\n' "$out"

  cp "$d/data/coordinator-ca.crt" "$ca_dst"
  box_key="$(coordinator_mint_box_key | tail -1)"
  api_key="$(coordinator_api_key_from_output "$out")"

  . "$HERE/lib/envfile.sh"
  envfile_set "$ENVF" MESH_CA_FILE "$ca_dst"
  [ -n "$box_key" ] && envfile_set "$ENVF" MESH_AUTH_KEY "$box_key"
  [ -n "$api_key" ] && envfile_set "$ENVF" MESH_API_KEY "$api_key"
  echo "Coordinator is up on this box; join it with: nufi-box mesh up"
}

coordinator_status() { local cc; cc="$(coordinator_compose)"; run $cc ps ; }
coordinator_down()   { local cc; cc="$(coordinator_compose)"; run $cc down ; }
