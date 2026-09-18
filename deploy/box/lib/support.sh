# support.sh — `nufi-box support`: a diagnostics bundle a person can send to
# Dudaji when a box misbehaves. Sourced by nufi-box; uses its `run`, `die`,
# `COMPOSE`, `HERE`, `OS` and the .env it already loaded.
#
# This is the local half only. It packages what the box already knows about
# itself into a file a person attaches to an email; it does not open a
# connection FROM Dudaji INTO the box, and nothing here listens for one. That
# is a different, and much bigger, decision — see the README's "What is not
# built yet".
#
# What goes in the bundle is decided by what an engineer asks for in the
# first three emails of any support thread: what version, what's running,
# what broke, and the logs from around when it broke. A backup answers "can
# we put it back"; this answers "what is wrong with it" — different question,
# so a different file, and this one is safe to attach to an email because it
# never holds a secret.
#
# Every value that COULD be a secret is kept out three different ways, all
# built on lib/support-redact.py's one .env parser (see that file for why a
# line-by-line read of .env is not good enough — the console's signing key
# is stored as a real multi-line PEM):
#   - env-keys.txt never prints a value, only whether a key is set, and is
#     built by walking .env as ENTRIES rather than lines, so a PEM body line
#     is never mistaken for a key of its own.
#   - compose.yml is `docker compose config` (which resolves every ${VAR} in
#     the compose files to its real value) piped through a filter that
#     blanks any text equal to a secret-looking .env VALUE, and — belt to
#     that value layer's braces — any environment entry whose NAME looks
#     like a secret, whatever it rendered as.
#   - every other regular file in the bundle (logs, doctor.txt, status.txt,
#     box.txt, ...) is swept for the same secret-looking VALUES once
#     collection is done and before the tar is made — a secret does not
#     only ever appear inside compose's own rendering of it; LiteLLM's debug
#     log, a failed `ALTER ROLE ... PASSWORD`, or an ingest daemon's login
#     error can all print one too.
#
# A stopped box, a box with a broken doctor, a box with no mesh, a box that
# has never been backed up — all still get a bundle. Nothing here calls
# `die`, and every step that touches Docker, the network, or a file that
# might not exist is guarded, not trusted.

_support_dir() { echo "${NUFI_DATA_DIR:?NUFI_DATA_DIR is not set}/support"; }

# --- box.txt ---------------------------------------------------------------

_support_box_txt() {
  local file="$1" _dd="${NUFI_DATA_DIR:-$HERE/data}"
  {
    echo "nufi-box version"
    # [A-Za-z0-9_]*, not [A-Za-z0-9]*: NUFI_WORKS_EGRESS_TAG has an
    # underscore inside the part between NUFI_ and _TAG, which the tighter
    # class used to miss entirely.
    grep -E '^NUFI_[A-Za-z0-9_]*_TAG=' "$ENVF" 2>/dev/null | sed 's/^/  /' \
      || echo "  (no NUFI_*_TAG keys in .env)"
    if [ -f "$_dd/updated-from" ]; then
      printf '  updated-from: '
      cat "$_dd/updated-from" 2>/dev/null || echo "(unreadable)"
    fi
    echo
    echo "OS:"
    uname -a 2>&1 || echo "(unavailable)"
    echo
    echo "docker:"
    docker --version 2>&1 || echo "(unavailable)"
    $COMPOSE version 2>&1 || echo "(unavailable)"
    echo
    echo "disk (NUFI_DATA_DIR):"
    df -h "$_dd" 2>&1 || echo "(unavailable)"
    echo "disk (/):"
    df -h / 2>&1 || echo "(unavailable)"
    echo
    echo "memory:"
    if [ "$OS" = "Darwin" ]; then
      sysctl hw.memsize 2>&1 || echo "(unavailable)"
    else
      free -h 2>&1 || echo "(unavailable)"
    fi
    echo
    echo "uptime:"
    uptime 2>&1 || echo "(unavailable)"
    echo "date:"
    date 2>&1 || echo "(unavailable)"
    echo
    echo "BOX_HOST: ${BOX_HOST:-?}"
    echo "BOX_IP: ${BOX_IP:-?}"
    echo "INFERENCE_PROFILE: ${INFERENCE_PROFILE:-?}"
    echo "INFERENCE_MODEL: ${INFERENCE_MODEL:-?}"
    echo "EMBEDDINGS_MODEL: ${EMBEDDINGS_MODEL:-?}"
    echo "DEPARTMENTS: ${DEPARTMENTS:-?}"
    echo "NUFI_WORKS: ${NUFI_WORKS:-0}"
  } > "$file" 2>&1
}

# --- env-keys.txt ------------------------------------------------------------
#
# The names of every key in .env, and whether each has a value — never the
# value itself. Which keys exist (and which an install left empty) is what an
# engineer actually needs to ask the right next question; the values are
# exactly what must never leave the box in this file.
#
# Built by lib/support-redact.py's `keys` command, not a line-by-line awk: a
# key=value split done one line at a time treats every line of a multi-line
# quoted value (the console's PEM) as ITS OWN key — and a base64 body line
# ending in `=` printed as if it were a key with a value, a real fragment of
# the private key sitting in the one file this bundle promises holds no
# secret. support-redact.py walks .env as entries, so a multi-line value is
# one key here, same as everywhere else.

_support_env_keys() {
  local file="$1"
  if ! command -v python3 >/dev/null 2>&1; then
    echo "(unavailable: python3 is required to read .env keys)" > "$file"
    return 0
  fi
  python3 "$HERE/lib/support-redact.py" keys "$ENVF" 2>/dev/null > "$file" \
    || echo "(unavailable: could not read .env)" > "$file"
}

# --- doctor.txt --------------------------------------------------------------
#
# Re-runs `nufi-box doctor` rather than re-implementing its checks here: two
# places that decide whether the box is healthy can disagree, and the whole
# point of shipping doctor's own output is that it can't. The `if`/`else`
# (not `_out=$(...) || true`) is deliberate: doctor legitimately exits 1 when
# something is off, and capturing that the "safe" way, under this script's
# own `set -e`, is what keeps a failing doctor from taking the whole bundle
# down with it.

_support_doctor_txt() {
  local file="$1" rc out
  if out="$("$HERE/nufi-box" doctor 2>&1)"; then
    rc=0
  else
    rc=$?
  fi
  {
    echo "exit status: $rc"
    printf '%s\n' "$out"
  } > "$file"
}

# --- status.txt --------------------------------------------------------------

_support_status_txt() {
  local file="$1"
  {
    echo "docker compose ps (all, including exited):"
    $COMPOSE ps -a 2>&1 || echo "(unavailable: docker compose ps)"
    echo
    echo "docker compose config --images:"
    $COMPOSE config --images 2>&1 || echo "(unavailable: docker compose config --images)"
  } > "$file"
}

# --- logs/<service>.log -------------------------------------------------------

_support_logs_all() {
  local dir="$1" svcs svc
  svcs="$($COMPOSE config --services 2>/dev/null)" || svcs=""
  if [ -z "$svcs" ]; then
    echo "(unavailable: could not list services — is the box's .env readable and Docker running?)" \
      > "$dir/unavailable.log"
    return 0
  fi
  for svc in $svcs; do
    { $COMPOSE logs --no-color -t --tail=300 "$svc" 2>&1 \
        || echo "(unavailable: logs for $svc)"; } > "$dir/$svc.log"
  done
}

# --- compose.yml (redacted) ---------------------------------------------------
#
# `docker compose config` prints the fully resolved compose file — every
# ${VAR} filled in with its .env value, which is exactly what makes it useful
# to an engineer (they can see what a service actually got, not just what
# .env claims) and exactly what makes it dangerous unredacted.
# lib/support-redact.py's `redact-compose` reads .env for anything that
# LOOKS like a secret and blanks it two ways: by value (wherever that text
# appears, not just the one place the key's own name suggests it should be —
# a value can be threaded into more than one service's environment) and by
# the rendered entry's own NAME (belt to the value layer's braces, and the
# only thing that catches a secret shorter than the value layer's 4-character
# floor).
#
# The secret values themselves never appear on a command line (readable
# through /proc/<pid>/cmdline on Linux): python reads .env by path, and the
# compose output arrives over a real pipe, not an argument.

_support_compose_yml() {
  local file="$1"
  if ! command -v python3 >/dev/null 2>&1; then
    echo "(unavailable: python3 is required to redact compose config)" > "$file"
    return 0
  fi
  if ! $COMPOSE config 2>/dev/null | python3 "$HERE/lib/support-redact.py" redact-compose "$ENVF" > "$file"; then
    echo "(unavailable: docker compose config)" > "$file"
  fi
}

# --- schedules.ini, caddy/mesh.caddy, data/backup, docker info -----------------

_support_copies() {
  local out="$1" dd="${NUFI_DATA_DIR:-$HERE/data}" schedules meshcaddy
  schedules="$dd/schedules.ini"
  meshcaddy="$HERE/caddy/mesh.caddy"

  if [ -f "$schedules" ]; then
    cp "$schedules" "$out/schedules.ini" 2>/dev/null \
      || echo "(unavailable: could not copy schedules.ini)" > "$out/schedules.ini"
  else
    echo "(unavailable: no schedules.ini)" > "$out/schedules.ini"
  fi

  if [ -f "$meshcaddy" ]; then
    cp "$meshcaddy" "$out/caddy/mesh.caddy" 2>/dev/null \
      || echo "(unavailable: could not copy caddy/mesh.caddy)" > "$out/caddy/mesh.caddy"
  else
    echo "(unavailable: no caddy/mesh.caddy — this box is not on the mesh)" > "$out/caddy/mesh.caddy"
  fi

  ls -la "$dd/backup" > "$out/backup-listing.txt" 2>&1 \
    || echo "(unavailable: no data/backup — this box has never been backed up)" > "$out/backup-listing.txt"

  if command -v python3 >/dev/null 2>&1 \
    && docker info --format '{{json .}}' 2>/dev/null | python3 -c '
import json, sys
data = json.load(sys.stdin)
trimmed = {k: data.get(k) for k in ("Runtimes", "ServerVersion", "OperatingSystem", "Driver")}
json.dump(trimmed, sys.stdout, indent=2)
' > "$out/docker-info.json"; then
    :
  else
    echo "(unavailable: docker info)" > "$out/docker-info.json"
  fi
}

# --- drive-tree.txt --------------------------------------------------------
#
# What an engineer needs is "mounted, how many departments, how many files
# in each, is _routines there" — never a document's own name. The old
# `find -maxdepth 3` printed every path under drives/, which is every file
# name on every department's drive, mailed straight to the vendor; this
# lists directories only (two levels: a department, and anything under it
# such as _routines) and a per-department file count instead.

_support_drive_tree() {
  local file="$1" drives="${NUFI_DATA_DIR:-$HERE/data}/drives" d name count
  {
    echo "directories (2 levels deep, names only — never a document name):"
    find "$drives" -maxdepth 2 -type d 2>&1 | sort || echo "  (unavailable)"
    echo
    echo "files per department (not their names):"
    if [ -d "$drives" ]; then
      for d in "$drives"/*/; do
        [ -d "$d" ] || continue
        name="$(basename "$d")"
        count="$(find "$d" -type f 2>/dev/null | wc -l | tr -d ' ')"
        echo "  $name: $count file(s)"
      done
    else
      echo "  (unavailable: no drives)"
    fi
  } > "$file" 2>&1
}

# --- README.txt ----------------------------------------------------------------

_support_readme() {
  local file="$1"
  {
    echo "This is a diagnostics bundle from a NuFi box, made with nufi-box support."
    echo "Nothing in here is a secret; the keys file lists names only, and every"
    echo "file has been swept for secret-looking .env values before packing."
  } > "$file"
}

# --- the final sweep --------------------------------------------------------
#
# compose.yml gets the richer, YAML-aware redaction (redact-compose, above)
# at the moment it is written. Everything else — every log, doctor.txt,
# status.txt, box.txt — is plain text collected from a service or a command
# that never promised not to print a secret: LiteLLM under
# --detailed_debug, LibreChat with DEBUG_CONSOLE=true, a failing
# `ALTER ROLE ... PASSWORD` in postgres, an ingest daemon's login-error body
# can all carry one. So the value layer runs a second time here, after
# every artifact exists and before the tar, over every regular file in the
# bundle — compose.yml included, harmlessly: its secrets are already gone,
# so this pass finds nothing left to replace there.

_support_redact_all() {
  local out="$1"
  command -v python3 >/dev/null 2>&1 || return 0
  find "$out" -type f -print0 2>/dev/null \
    | xargs -0 python3 "$HERE/lib/support-redact.py" redact "$ENVF" 2>/dev/null
  return 0
}

# --- the whole bundle ----------------------------------------------------------

support_run() {
  local _to _stamp _out _tar _size
  _to="${SUPPORT_TO:-$(_support_dir)}"
  _stamp="$(date -u +%Y%m%d-%H%M%S)"
  _out="$_to/$_stamp"

  echo "Collecting a support bundle in $_out"
  run mkdir -p "$_out/logs" "$_out/caddy"

  echo "  box.txt"
  run _support_box_txt "$_out/box.txt"

  echo "  env-keys.txt"
  run _support_env_keys "$_out/env-keys.txt"

  echo "  doctor.txt"
  run _support_doctor_txt "$_out/doctor.txt"

  echo "  status.txt"
  run _support_status_txt "$_out/status.txt"

  echo "  logs/<service>.log"
  run _support_logs_all "$_out/logs"

  echo "  compose.yml (redacted)"
  run _support_compose_yml "$_out/compose.yml"

  echo "  schedules.ini, caddy/mesh.caddy, backup listing, docker info"
  run _support_copies "$_out"

  echo "  drive-tree.txt"
  run _support_drive_tree "$_out/drive-tree.txt"

  echo "  README.txt"
  run _support_readme "$_out/README.txt"

  echo "  redacting secret values across the whole bundle"
  run _support_redact_all "$_out"

  if [ "$DRY" = 1 ]; then
    echo "  (dry run: nothing was written)"
    return 0
  fi

  _tar="$_to/nufi-box-support-$_stamp.tar.gz"
  echo "  packing $_tar"
  run tar -czf "$_tar" -C "$_to" "$_stamp"
  run rm -rf "$_out"

  _size="$(du -sh "$_tar" 2>/dev/null | cut -f1)" || _size="?"
  echo
  echo "Done. $_tar ($_size)"
  echo "Send this file to support@nufi.me with what you saw."
}
