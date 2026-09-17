#!/bin/bash
# lib/works.sh — NUFI Works on the box: register the Docker sandbox
# environment, and say whether it is registered. bash 3.2 compatible; sourced
# by nufi-box (uses its $HERE, $ENVF, $DRY, $COMPOSE, $run and the exported
# .env), not executed.
#
# The work is done by works/register_works.py, and it runs INSIDE the box
# network through `compose run`: there the box's name resolves to Caddy (the
# alias every container has) and the CA is a file on the caddy volume, so the
# SSO round trip -- chat login, console authorize, Works callback -- goes over
# the exact URLs a browser would use, TLS verified. From the host that would
# need mDNS to resolve the name and a trusted CA, neither of which a fresh
# Ubuntu box has.
#
# Secrets never appear in an argument: `-e NAME` passes them from this shell's
# environment (nufi-box has exported .env), and what the registrar mints comes
# back on stdout as KEY=VALUE lines that are written to .env here.

WORKS_DATA="${NUFI_DATA_DIR:-$HERE/data}"
WORKS_CA="$WORKS_DATA/nufi-box-ca.crt"
WORKS_REGISTRAR="$HERE/works/register_works.py"
WORKS_URL="https://${BOX_HOST:-nufi.local}:3003"

works_guard() {
  [ "${NUFI_WORKS:-0}" = 1 ] || {
    echo "works: this box was installed without Works — re-run install-box.sh --with-works (Ubuntu only)" >&2; return 2; }
  [ -f "$WORKS_REGISTRAR" ] || {
    echo "works: the registrar is missing ($WORKS_REGISTRAR); deploy/box/works ships with the box" >&2; return 2; }
}

# works_run ARGS… — the registrar, inside the network. `-T`: no tty, so the
# KEY=VALUE lines come back clean. `--no-deps`: nufi-cron's own dependency
# (Studio healthy) is not this call's concern.
works_run() {
  run $COMPOSE run --rm --no-deps -T \
    -v "$WORKS_REGISTRAR:/register_works.py:ro" \
    -v "$WORKS_CA:/ca.crt:ro" \
    -e ADMIN_PASSWORD -e LITELLM_MASTER_KEY -e WORKS_BOX_KEY -e WORKS_MODEL_KEY \
    nufi-cron python3 /register_works.py --works "$WORKS_URL" --cacert /ca.crt "$@"
}

works_wait() {
  local i
  for i in $(seq 1 36); do
    curl -fsk "https://localhost:3003/api/health" >/dev/null 2>&1 && return 0
    sleep 5
  done
  return 1
}

# The database Works migrates into. postgres-init.sh creates it on a fresh box;
# a box installed before Works existed has to get it here.
works_ensure_db() {
  if [ "$DRY" = 1 ]; then printf '  $ psql: CREATE DATABASE nufi_works  # unless it exists\n'; return 0; fi
  if ! $COMPOSE exec -T postgres psql -U "${POSTGRES_USER:-nufi}" -d postgres -tAc \
       "SELECT 1 FROM pg_database WHERE datname='nufi_works'" 2>/dev/null | grep -qx 1; then
    $COMPOSE exec -T postgres psql -U "${POSTGRES_USER:-nufi}" -d postgres -c "CREATE DATABASE nufi_works" >/dev/null
  fi
}

works_install() {
  works_guard || return $?
  [ -n "${WORKS_SANDBOX_IMAGE:-}" ] || {
    echo "works: no WORKS_SANDBOX_IMAGE in .env — the installer pins the sandbox image by digest; run install-box.sh --with-works" >&2; return 2; }
  works_ensure_db
  if [ "$DRY" = 1 ]; then
    works_run --chat "https://${BOX_HOST:-nufi.local}:3080" --litellm "http://litellm-proxy:4000" \
      --login "${ADMIN_EMAIL:-admin@nufi.local}" --company "${BOX_NAME:-nufi}" --image "$WORKS_SANDBOX_IMAGE"
    return 0
  fi
  $COMPOSE up -d works >/dev/null
  works_wait || { echo "works: Works is not answering at $WORKS_URL — check: nufi-box logs works" >&2; return 1; }
  local out rc=0; out="$(mktemp)"
  works_run --chat "https://${BOX_HOST:-nufi.local}:3080" --litellm "http://litellm-proxy:4000" \
    --login "${ADMIN_EMAIL:-admin@nufi.local}" --company "${BOX_NAME:-nufi}" --image "$WORKS_SANDBOX_IMAGE" \
    > "$out" || rc=$?
  # Written whatever the exit status: a key can be minted and printed several
  # steps before a later one fails (the plugin install, the environment
  # registration), and a failed run that then discards the file leaves an
  # orphan key on Works with nothing here to show for it.
  local line new_model_key=0
  if grep -qE '^(WORKS_BOX_KEY|WORKS_MODEL_KEY)=' "$out"; then
    . "$HERE/lib/envfile.sh"
    while IFS= read -r line; do
      case "$line" in
        WORKS_BOX_KEY=*|WORKS_MODEL_KEY=*)
          envfile_set "$ENVF" "${line%%=*}" "${line#*=}"
          [ "${line%%=*}" = WORKS_MODEL_KEY ] && new_model_key=1 ;;
      esac
    done < "$out"
  fi
  rm -f "$out"
  [ "$rc" = 0 ] || return "$rc"
  # The model key is read by the works container at creation; a key minted
  # just now is not in the running one. Recreate it, once, with the new .env.
  if [ "$new_model_key" = 1 ]; then
    set -a; . "$ENVF"; set +a
    $COMPOSE up -d works >/dev/null
    works_wait || { echo "works: Works did not come back after the model key was set — check: nufi-box logs works" >&2; return 1; }
  fi
  echo "Works is at $WORKS_URL — enter it from https://${BOX_HOST:-nufi.local}:3001/choose as ${ADMIN_EMAIL:-the box admin}"
}

# works_check — reads only; 0 when registered as install leaves it. Used by
# doctor, and by `works status`.
works_check() {
  works_guard || return $?
  works_run --check --image "${WORKS_SANDBOX_IMAGE:-}"
}

works_status() {
  if [ "$DRY" = 1 ]; then works_check; return $?; fi
  if works_check 2>&1; then echo "Works is registered: $WORKS_URL"; else
    echo "Works is not fully registered — run: nufi-box works install" >&2; return 1; fi
}
