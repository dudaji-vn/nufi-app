#!/bin/bash
# lib/flows.sh — the department routines as real Studio flows: mint the box's
# own Studio API key, install the flows, list what is there. bash 3.2
# compatible; meant to be sourced by nufi-box (uses its $HERE, $ENVF, $DRY and
# $run, and the .env it has already exported), not executed directly.
#
# The builder itself lives with the scenarios it shares a component catalogue
# with (deploy/platform/scenarios/studio/build_flows.py) and ships alongside
# deploy/box, so this file is the box-shaped wrapper around it: which URL,
# which CA, which drives, and where the key is kept.
#
# The API key never appears in an argument. It is a bearer credential for the
# whole Studio, and an argument is readable by any other local user through
# `ps`; the builder reads $STUDIO_API_KEY from the environment, and curl reads
# a mode-0600 config file, exactly as lib/mesh.sh does with the coordinator's.

FLOWS_BASE="${NUFI_STUDIO_URL:-https://localhost:7860}"
FLOWS_DATA="${NUFI_DATA_DIR:-$HERE/data}"
FLOWS_CA="$FLOWS_DATA/nufi-box-ca.crt"
FLOWS_JSON="$FLOWS_DATA/studio-flows.json"
FLOWS_KEYFILE="$FLOWS_DATA/.studio-api-key"
FLOWS_BUILDER="$HERE/../platform/scenarios/studio/build_flows.py"

# flows_set_args — FLOWS_ARGS describes THIS box to the builder. An array, not
# a string: NUFI_DATA_DIR is an operator-chosen path and a space in it must not
# split into two arguments.
flows_set_args() {
  FLOWS_ARGS=(--box "$FLOWS_BASE")
  # The box's own CA, once install-box.sh has exported it. Before that (and on
  # a box whose CA copy was deleted) fall back to skipping verification: this
  # call never leaves the machine — it is localhost through the box's own
  # Caddy — and refusing to install the routines over it helps nobody.
  if [ -f "$FLOWS_CA" ]; then FLOWS_ARGS+=(--cacert "$FLOWS_CA"); else FLOWS_ARGS+=(--insecure); fi
  FLOWS_ARGS+=(--drives-root /drives)
  FLOWS_ARGS+=(--departments "${DEPARTMENTS:-legal}")
  FLOWS_ARGS+=(--model "${INFERENCE_MODEL:-qwen2.5:7b}")
  FLOWS_ARGS+=(--embeddings "${EMBEDDINGS_MODEL:-bge-m3}")
  FLOWS_ARGS+=(--ollama "${OLLAMA_BASE_URL:-http://host.docker.internal:11434}")
  FLOWS_ARGS+=(--out "$FLOWS_JSON")
  FLOWS_ARGS+=(--login "${ADMIN_EMAIL:-admin@nufi.local}" --key-out "$FLOWS_KEYFILE")
}

# flows_wait — Studio answers its health check, or say so and give up. The
# installer reaches this minutes after `compose up`, so this is a guard against
# a Studio that failed to start, not a real wait.
flows_wait() {
  local i tls="--cacert $FLOWS_CA"
  [ -f "$FLOWS_CA" ] || tls="-k"
  for i in 1 2 3 4 5 6 7 8 9 10 11 12; do
    curl -fs $tls "$FLOWS_BASE/health_check" >/dev/null 2>&1 && return 0
    sleep 5
  done
  return 1
}

# flows_install — install (or keep) the department routines. Idempotent: the
# builder keeps a flow that is already there by name, so re-running it after
# someone has edited a routine does not overwrite their work.
flows_install() {
  if [ ! -f "$FLOWS_BUILDER" ]; then
    echo "flows: the builder is missing ($FLOWS_BUILDER)." >&2
    echo "       It ships beside deploy/box as deploy/platform/scenarios; copy that too." >&2
    return 1
  fi
  command -v python3 >/dev/null 2>&1 || { echo "flows: python3 is required" >&2; return 1; }
  flows_set_args
  if [ "$DRY" = 1 ]; then
    run python3 "$FLOWS_BUILDER" "${FLOWS_ARGS[@]}"
    return 0
  fi
  flows_wait || {
    echo "flows: Studio is not answering at $FLOWS_BASE — check: nufi-box logs studio" >&2
    return 1; }
  # A key that was revoked (or a .env carried over from a box that no longer
  # exists) answers 401 on every call. Rather than leave the operator with a box
  # that cannot install its own routines, drop the stored key once and let the
  # builder mint a fresh one from the superuser login it already has.
  if ! python3 "$FLOWS_BUILDER" "${FLOWS_ARGS[@]}"; then
    [ -n "${STUDIO_API_KEY:-}" ] || return 1
    echo "flows: the stored Studio key did not work; minting a new one" >&2
    STUDIO_API_KEY="" python3 "$FLOWS_BUILDER" "${FLOWS_ARGS[@]}" || return 1
  fi
  if [ -f "$FLOWS_KEYFILE" ]; then
    . "$HERE/lib/envfile.sh"
    envfile_set "$ENVF" STUDIO_API_KEY "$(cat "$FLOWS_KEYFILE")"
    rm -f "$FLOWS_KEYFILE"
  fi
  echo "The routines are in Studio: https://${BOX_HOST:-nufi.local}:7860"
}

# flows_list — name and id of every flow the box's Studio account holds.
flows_list() {
  local url="$FLOWS_BASE/api/v1/flows/?get_all=true&header_flows=true"
  if [ "$DRY" = 1 ]; then
    run curl "$url"
    return 0
  fi
  [ -n "${STUDIO_API_KEY:-}" ] || {
    echo "flows: no STUDIO_API_KEY in .env — run: nufi-box flows install" >&2; return 2; }
  local cfg out rc
  cfg="$(mktemp)"; out="$(mktemp)"
  : > "$cfg"
  chmod 600 "$cfg"
  {
    printf 'silent\nshow-error\nmax-time = 20\n'
    printf 'url = "%s"\n' "$url"
    printf 'header = "x-api-key: %s"\n' "$STUDIO_API_KEY"
    printf 'header = "Accept-Encoding: identity"\n'
    [ -f "$FLOWS_CA" ] && printf 'cacert = "%s"\n' "$FLOWS_CA"
    [ -f "$FLOWS_CA" ] || printf 'insecure\n'
  } >> "$cfg"
  curl -K "$cfg" -o "$out" || {
    rm -f "$cfg" "$out"; echo "flows: could not reach $FLOWS_BASE" >&2; return 1; }
  rm -f "$cfg"
  # Studio gzips a long listing whatever Accept-Encoding asked for, so decide on
  # the magic number rather than on the header.
  python3 - "$out" <<'PY'
import gzip, json, sys
raw = open(sys.argv[1], "rb").read()
if raw[:2] == b"\x1f\x8b":
    raw = gzip.decompress(raw)
try:
    flows = json.loads(raw or b"[]")
except ValueError:
    sys.exit("flows: Studio did not answer with a flow list:\n"
             + raw.decode("utf-8", "replace")[:200])
if isinstance(flows, dict):
    flows = flows.get("items", [])
for f in sorted(flows, key=lambda f: f.get("name") or ""):
    print("  %s  %s" % (f.get("id"), f.get("name")))
print("\n%d flow(s)" % len(flows))
PY
  rc=$?
  rm -f "$out"
  return $rc
}
