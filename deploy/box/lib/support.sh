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
# Every value that COULD be a secret is kept out two different ways:
#   - env-keys.txt never prints a value, only whether a key is set.
#   - compose.yml is `docker compose config` (which resolves every
#     ${VAR} in the compose files to its real value) piped through a filter
#     that blanks out anything equal to a secret-looking .env value. Matching
#     is done by the VALUE, not by re-deriving which compose key holds which
#     secret: `docker compose config` does not use .env's key names, it uses
#     whatever each service's environment: block happens to call the
#     variable, and keeping that mapping in sync by hand is exactly the kind
#     of thing that goes stale. A secret's characters do not change just
#     because a different name pointed at them.
#
# A stopped box, a box with a broken doctor, a box with no mesh, a box that
# has never been backed up — all still get a bundle. Nothing here calls
# `die`, and every step that touches Docker, the network, or a file that
# might not exist is guarded, not trusted.

_support_dir() { echo "${NUFI_DATA_DIR:?NUFI_DATA_DIR is not set}/support"; }

# --- box.txt ---------------------------------------------------------------

_support_box_txt() {
  local file="$1"
  {
    echo "nufi-box version"
    grep -E '^NUFI_[A-Za-z0-9]*_TAG=' "$ENVF" 2>/dev/null | sed 's/^/  /' \
      || echo "  (no NUFI_*_TAG keys in .env)"
    if [ -f "${NUFI_DATA_DIR}/updated-from" ]; then
      printf '  updated-from: '
      cat "${NUFI_DATA_DIR}/updated-from" 2>/dev/null || echo "(unreadable)"
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
    df -h "${NUFI_DATA_DIR}" 2>&1 || echo "(unavailable)"
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

_support_env_keys() {
  local file="$1"
  awk '
    /^[[:space:]]*#/ { next }
    /^[[:space:]]*$/ { next }
    {
      n = index($0, "=")
      if (n == 0) { next }
      key = substr($0, 1, n - 1)
      val = substr($0, n + 1)
      if (length(val) > 0) { print key "=<set>" } else { print key "=<empty>" }
    }
  ' "$ENVF" 2>/dev/null | sort > "$file" \
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
# .env claims) and exactly what makes it dangerous unredacted. The filter
# reads .env itself for anything that LOOKS like a secret (a key ending in
# _KEY, _SECRET, _PASSWORD, PEM or TOKEN) and blanks every occurrence of that
# value in the compose text — not just the one place the key's own name
# suggests it should be, since a value can be threaded into more than one
# service's environment.
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
  if ! $COMPOSE config 2>/dev/null | python3 -c '
import re
import sys

SECRET_SUFFIXES = ("_KEY", "_SECRET", "_PASSWORD", "PEM", "TOKEN")


def secret_values(path):
    """Every secret-looking value in .env, read the way compose reads it.

    A double-quoted value may span lines (the console signing key is a PEM
    stored with real newlines -- install-box.sh says why), so a line-by-line
    read saw only its first line, and only with a stray quote on the front.
    The first real bundle carried the private key in compose.yml for exactly
    that reason. Each line of a multi-line value is a secret on its own, too:
    compose renders such a value as a block scalar, one line at a time.
    """
    values = []
    try:
        text = open(path).read()
    except OSError:
        return values
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        i += 1
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        eq = line.find("=")
        if eq == -1:
            continue
        key, val = line[:eq].strip(), line[eq + 1:]
        if val.startswith("\"") and not (len(val) > 1 and val.endswith("\"") and not val.endswith("\\\"")):
            # an opening quote with no closing quote on this line: read on
            body = [val[1:]]
            while i < len(lines):
                nxt = lines[i]
                i += 1
                if nxt.endswith("\""):
                    body.append(nxt[:-1])
                    break
                body.append(nxt)
            val = "\n".join(body)
        elif len(val) >= 2 and val[0] == val[-1] and val[0] in "\"\x27":
            val = val[1:-1]
        if key.endswith(SECRET_SUFFIXES):
            for piece in [val] + val.split("\n"):
                piece = piece.strip()
                if len(piece) >= 4 and piece not in values:
                    values.append(piece)
    return values


def redact_by_key(text):
    """Belt to the value braces: any environment entry whose NAME looks like
    a secret is blanked, block scalar included, whatever its value was."""
    out = []
    lines = text.split("\n")
    i = 0
    key_re = re.compile(r"^(\s+)([A-Za-z0-9_]+):\s*(.*)$")
    while i < len(lines):
        m = key_re.match(lines[i])
        if m and m.group(2).upper().endswith(SECRET_SUFFIXES):
            indent = len(m.group(1))
            out.append("%s%s: <redacted>" % (m.group(1), m.group(2)))
            i += 1
            while i < len(lines) and lines[i].strip() and (len(lines[i]) - len(lines[i].lstrip())) > indent:
                i += 1
            continue
        out.append(lines[i])
        i += 1
    return "\n".join(out)


secrets = secret_values(sys.argv[1])
text = sys.stdin.read()
for value in sorted(secrets, key=len, reverse=True):
    text = text.replace(value, "<redacted>")
sys.stdout.write(redact_by_key(text))
' "$ENVF" > "$file"; then
    echo "(unavailable: docker compose config)" > "$file"
  fi
}

# --- schedules.ini, caddy/mesh.caddy, the drive tree, data/backup, docker info -

_support_copies() {
  local out="$1" schedules="${NUFI_DATA_DIR}/schedules.ini" meshcaddy="$HERE/caddy/mesh.caddy"

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

  find "${NUFI_DATA_DIR}/drives" -maxdepth 3 > "$out/drive-tree.txt" 2>&1 \
    || echo "(unavailable: no drives)" > "$out/drive-tree.txt"

  ls -la "${NUFI_DATA_DIR}/backup" > "$out/backup-listing.txt" 2>&1 \
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

# --- README.txt ----------------------------------------------------------------

_support_readme() {
  local file="$1"
  {
    echo "This is a diagnostics bundle from a NuFi box, made with nufi-box support."
    echo "Nothing in here is a secret; the keys file lists names only."
  } > "$file"
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

  echo "  schedules.ini, caddy/mesh.caddy, drive tree, backup listing, docker info"
  run _support_copies "$_out"

  echo "  README.txt"
  run _support_readme "$_out/README.txt"

  if [ "$DRY" = 1 ]; then
    echo "  (dry run: nothing was written)"
    return 0
  fi

  _tar="$_to/nufi-box-support-$_stamp.tar.gz"
  echo "  packing $_tar"
  run tar -czf "$_tar" -C "$_to" "$_stamp"
  run rm -rf "$_out"

  _size="$(du -sh "$_tar" 2>/dev/null | cut -f1)"
  echo
  echo "Done. $_tar ($_size)"
  echo "Send this file to support@nufi.me with what you saw."
}
