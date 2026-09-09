#!/bin/bash
# lib/mesh.sh — headscale REST API calls and per-OS join-file rendering for
# `nufi-box invite | members | revoke`. bash 3.2 compatible; meant to be
# sourced by nufi-box (uses its $HERE, $die, and the .env vars it already
# exported), not executed directly. JSON via python3 -c since bash has none.
#
# API fact confirmed against headscale v0.29.3, not from memory: pulled
# gen/openapiv2/headscale/v1/headscale.swagger.json at tag v0.29.3.
# v1CreatePreAuthKeyRequest.user is `{"type": "string", "format": "uint64"}`
# — a numeric user id (protobuf-JSON serializes uint64 as a decimal string,
# not the username). This deviates from the plan brief's literal
# `{"user":"box",...}` body. The box's headscale user is always "box"
# (deploy/coordinator/bootstrap.sh creates it); mesh_preauth resolves that
# name to its id with GET /api/v1/user?name=box before minting a key.
MESH_HS_USER="${MESH_HS_USER:-box}"

# mesh_api METHOD PATH [JSON] — curl with the bearer token, --max-time 20;
# prints the response body on success. Exits 3 (naming MESH_API_KEY) on HTTP
# 401/403; exits 1 with the body on any other >=400 response.
#
# The request (including the bearer token) is built as a curl config file
# and passed with `-K`, rather than `-H "Authorization: Bearer $KEY"` on the
# command line — a command-line argument is visible to any other local user
# via `ps` for the life of the process; a config file (created by `mktemp`,
# mode 0600, owner-only) is not. `-K` on the file path achieves the same
# thing the review's suggested `-K -` (stdin) would, without depending on
# how the caller's stdin happens to be wired.
#
# The same rule has to hold for the python3 that WRITES that config file, and
# for a while it did not: the key was its `sys.argv[3]`, so on Linux, where
# /proc/<pid>/cmdline is world-readable, any local user polling `ps` during
# `nufi-box invite` or `members` saw a credential that can list and delete
# every node on the coordinator. It travels in the environment instead —
# /proc/<pid>/environ is readable only by the process's own owner — assigned
# on the command itself rather than trusted to have been exported, so this
# function is correct however it was sourced.
mesh_api() {
  local method="$1" path="$2" data="${3:-}" tmp cfg code ca=""
  [ -n "${MESH_SERVER_URL:-}" ] || { echo "MESH_SERVER_URL is not set in .env" >&2; exit 2; }
  [ -n "${MESH_API_KEY:-}" ] || { echo "MESH_API_KEY is not set in .env" >&2; exit 2; }
  # A coordinator on its own internal CA (the Docker lab, a dev VPS before it
  # has a public name) is exactly the case MESH_CA_FILE exists for, and the
  # tailscale container already trusts it through SSL_CERT_FILE. Without the
  # same file here, the box joins the mesh and then `nufi-box members` dies on
  # "unable to get local issuer certificate" — half-trusted, which is worse
  # than either answer. Naming the host's own bundle (the default) changes
  # nothing; a path that is not there is ignored rather than fatal.
  [ -n "${MESH_CA_FILE:-}" ] && [ -f "${MESH_CA_FILE}" ] && ca="$MESH_CA_FILE"
  tmp="$(mktemp)"
  cfg="$(mktemp)"
  MESH_API_KEY="$MESH_API_KEY" python3 -c '
import os, sys

def q(s):
    return "\"" + s.replace("\\", "\\\\").replace("\"", "\\\"") + "\""

method, url, data, out, ca = sys.argv[1:6]
key = os.environ["MESH_API_KEY"]   # never argv: /proc/<pid>/cmdline is world-readable
lines = [
    "silent", "show-error",
    "max-time = 20",
    "request = " + q(method),
    "url = " + q(url),
    "header = " + q("Authorization: Bearer " + key),
    "output = " + q(out),
    "write-out = " + q("%{http_code}"),
]
if ca:
    lines.append("cacert = " + q(ca))
if data:
    lines.append("header = " + q("Content-Type: application/json"))
    lines.append("data = " + q(data))
sys.stdout.write("\n".join(lines) + "\n")
' "$method" "${MESH_SERVER_URL}${path}" "$data" "$tmp" "$ca" > "$cfg"
  code="$(curl -K "$cfg")"
  rm -f "$cfg"
  case "$code" in
    401|403)
      rm -f "$tmp"
      echo "MESH_API_KEY is missing or rejected by ${MESH_SERVER_URL}" >&2
      exit 3 ;;
    2??) ;;
    *)
      echo "mesh API $method $path failed with HTTP $code:" >&2
      cat "$tmp" >&2
      rm -f "$tmp"
      exit 1 ;;
  esac
  cat "$tmp"
  rm -f "$tmp"
}

# mesh_user_id NAME — the numeric id of a headscale user, by name.
#
# The `|| exit $?` below (and everywhere else a `mesh_api`/mesh_* call is
# captured with `$( )`) is not decorative: bash 3.2 has no `inherit_errexit`
# (that shopt is 4.4+), so `set -e` is simply never in effect *inside* a
# command-substitution subshell, at any nesting depth. `exit 3` from
# mesh_api's 401/403 case still ends that one subshell immediately (`exit`
# is unconditional, unrelated to errexit) — but the *caller* only notices if
# it explicitly checks the exit status, since errexit itself won't do it for
# a nested call. Without this, a 401 two levels down silently turns into
# whatever unrelated command runs next failing instead, with the wrong exit
# code reaching nufi-box's top level (confirmed by a failing test during
# development — this comment is here so nobody removes it as "redundant").
mesh_user_id() {
  local name="$1" body
  body="$(mesh_api GET "/api/v1/user?name=$name")" || exit $?
  printf '%s' "$body" | python3 -c '
import json, sys
name = sys.argv[1]
data = json.load(sys.stdin)
users = [u for u in (data.get("users") or []) if u.get("name") == name]
if not users:
    sys.exit("mesh: no headscale user named " + name + " — has the coordinator been bootstrapped?")
print(users[0]["id"])
' "$name"
}

# mesh_expiration_1h — now+1h as RFC3339 UTC. macOS `date` and GNU `date`
# spell "one hour from now" differently; try macOS's form first.
mesh_expiration_1h() {
  date -u -v+1H '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null || date -u -d '+1 hour' '+%Y-%m-%dT%H:%M:%SZ'
}

# mesh_preauth NAME — mints a single-use, non-ephemeral pre-auth key tagged
# tag:member, valid one hour, for the box's headscale user. NAME does not
# appear in the request — headscale keys belong to a user, not an invitee —
# it exists only for interface symmetry with invite/revoke.
mesh_preauth() {
  local uid exp body resp
  uid="$(mesh_user_id "$MESH_HS_USER")" || exit $?
  exp="$(mesh_expiration_1h)"
  body="$(python3 -c '
import json, sys
uid, exp = sys.argv[1], sys.argv[2]
print(json.dumps({
    "user": uid,
    "reusable": False,
    "ephemeral": False,
    "expiration": exp,
    "aclTags": ["tag:member"],
}))
' "$uid" "$exp")"
  # Capture the response before piping it to python3: `cmd | python3` runs
  # `cmd` in a subshell, so an `exit 3` inside mesh_api (its 401/403 case)
  # would only end that subshell — with pipefail, the pipeline's exit status
  # would then come from whichever side fails last, not necessarily
  # mesh_api's. A plain `resp="$(mesh_api ...)"` assignment does not have
  # this problem: its exit status is exactly mesh_api's (see the note on
  # mesh_user_id above for why the `|| exit $?` after it still matters).
  resp="$(mesh_api POST /api/v1/preauthkey "$body")" || exit $?
  printf '%s' "$resp" | python3 -c '
import json, sys
print(json.load(sys.stdin)["preAuthKey"]["key"])
'
}

# mesh_nodes — a table of every node the coordinator knows about.
mesh_nodes() {
  local body
  body="$(mesh_api GET /api/v1/node)" || exit $?
  printf '%s' "$body" | python3 -c '
import json, sys
data = json.load(sys.stdin)
nodes = data.get("nodes") or []
fmt = "%-20s %-30s %-8s %-25s %-10s"
print(fmt % ("NAME", "IP", "ONLINE", "LAST-SEEN", "USER"))
for n in nodes:
    ips = ",".join(n.get("ipAddresses") or []) or "-"
    online = "yes" if n.get("online") else "no"
    last = n.get("lastSeen") or "-"
    user = (n.get("user") or {}).get("name") or "-"
    print(fmt % (n.get("name") or "-", ips, online, last, user))
'
}

# mesh_delete_by_id ID — DELETE a node directly, bypassing name resolution
# (used both for the ambiguous-name case below and `revoke --id`).
mesh_delete_by_id() {
  local id="$1"
  mesh_api DELETE "/api/v1/node/$id" >/dev/null
  echo "Revoked node $id — that laptop can no longer reach the box until invited again."
}

# mesh_delete NAME — resolve a node name to its id and DELETE it. Two nodes
# can legitimately share a `name` (headscale keeps `givenName` precisely
# because raw hostnames collide — two laptops named the same thing is not
# rare), so this refuses to guess: 0 matches is an error, 1 match deletes,
# 2+ matches lists every id and tells the admin to disambiguate with
# `nufi-box revoke --id <id>` instead of silently picking one and leaving
# the other node connected.
mesh_delete() {
  local name="$1" body result
  body="$(mesh_api GET /api/v1/node)" || exit $?
  result="$(printf '%s' "$body" | python3 -c '
import json, sys
name = sys.argv[1]
data = json.load(sys.stdin)
matches = [n for n in (data.get("nodes") or []) if n.get("name") == name]
if not matches:
    print("NONE")
elif len(matches) == 1:
    print("ONE " + matches[0]["id"])
else:
    print("MANY " + " ".join(m["id"] for m in matches))
' "$name")"
  case "$result" in
    NONE)
      echo "revoke: no node named '$name' — run: nufi-box members" >&2
      exit 2 ;;
    "ONE "*)
      mesh_api DELETE "/api/v1/node/${result#ONE }" >/dev/null
      echo "Revoked '$name' — that laptop can no longer reach the box until invited again." ;;
    "MANY "*)
      echo "revoke: '$name' matches more than one node (ids: ${result#MANY }) — run nufi-box revoke --id <id> to remove a specific one" >&2
      exit 2 ;;
    *)
      echo "revoke: could not read the node list" >&2
      exit 1 ;;
  esac
}

# ---------- join files -------------------------------------------------

# mesh_join_ext OS — the file extension a join file gets for that OS.
mesh_join_ext() {
  case "$1" in
    windows) echo cmd ;;
    macos) echo command ;;
    linux) echo sh ;;
    *) echo "mesh_join_ext: unknown os: $1" >&2; return 1 ;;
  esac
}

# mesh_drives_block OS HOST DRIVES — the OS-specific lines that map each
# requested department drive, one `net use` / `open smb://` / `gio mount`
# per drive. Windows drive letters count down from Z so they rarely collide
# with a laptop's own C:/D:.
mesh_drives_block() {
  local os="$1" host="$2" drives="$3" out="" d letters letter i oldifs
  if [ -z "$drives" ]; then
    printf 'echo "No drives were configured for this invite."\n'
    return 0
  fi
  letters="ZYXWVUTSRQPONMLKJIHGFEDCBA"
  i=0
  oldifs="$IFS"
  IFS=','
  set -- $drives
  IFS="$oldifs"
  for d in "$@"; do
    [ -n "$d" ] || continue
    case "$os" in
      windows)
        if [ "$i" -ge 26 ]; then
          out="${out}echo \"Too many drives to letter automatically -- map \\\\${host}\\${d} by hand\""$'\n'
        else
          letter="$(printf '%s' "$letters" | cut -c$((i + 1)))"
          out="${out}net use ${letter}: \\\\${host}\\${d} /persistent:yes"$'\n'
        fi ;;
      macos)
        out="${out}open \"smb://${host}/${d}\""$'\n' ;;
      linux)
        out="${out}gio mount \"smb://${host}/${d}\" || echo \"could not mount ${d} automatically -- open smb://${host}/${d} from your file manager\""$'\n' ;;
    esac
    i=$((i + 1))
  done
  printf '%s' "$out"
}

# mesh_ca_b64 — base64 (single line) of the box's CA certificate.
mesh_ca_b64() {
  local ca="${NUFI_DATA_DIR:-$HERE/data}/nufi-box-ca.crt"
  [ -f "$ca" ] || { echo "invite: no certificate at $ca — run nufi-box up first" >&2; exit 2; }
  base64 < "$ca" | tr -d '\n'
}

# mesh_render_template TEMPLATE OUT KEY=VALUE... — replace @KEY@ placeholders
# with python3 (values may hold backslashes/newlines that would break sed).
# A join file holds a live auth key and the box's CA, so it is created with
# mode 0600 from the very first byte (`os.open` with the mode, after
# removing any stale file at that path) rather than written with the
# process's default umask and `chmod`ed afterward — the latter leaves a
# window, however short, where the file exists at a wider mode.
#
# @AUTH_KEY@ is the one substitution that is NOT a KEY=VALUE argument. It is
# the pre-auth key just minted for this invite, and argv is world-readable on
# Linux through /proc/<pid>/cmdline, so it comes from MESH_JOIN_AUTH_KEY in
# the environment (which is not) — the same rule mesh_api follows for the
# coordinator's API key and lib/flows.sh for the Studio one. Unset is fatal:
# a join file rendered with an empty key is a file that cannot work and does
# not say why.
mesh_render_template() {
  local template="$1" out="$2"
  shift 2
  python3 -c '
import os, sys
template, out = sys.argv[1], sys.argv[2]
if "MESH_JOIN_AUTH_KEY" not in os.environ:
    sys.exit("mesh: MESH_JOIN_AUTH_KEY is not in the environment — the join file would have no key")
subs = {"AUTH_KEY": os.environ["MESH_JOIN_AUTH_KEY"]}
for kv in sys.argv[3:]:
    k, v = kv.split("=", 1)
    if k == "AUTH_KEY":
        sys.exit("mesh: the auth key must not be passed as an argument — it is readable through ps")
    subs[k] = v
with open(template) as f:
    content = f.read()
for k, v in subs.items():
    content = content.replace("@" + k + "@", v)
try:
    os.remove(out)
except FileNotFoundError:
    pass
fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w") as f:
    f.write(content)
' "$template" "$out" "$@"
}

# mesh_invite NAME OS DRIVES — mint a key, render the join file from its
# template, write it under NUFI_DATA_DIR/invites (mode 0600), and print
# where it is and what to tell the member.
mesh_invite() {
  local name="$1" os="$2" drives="$3"
  local key ca_b64 drives_block ext template out data_dir
  data_dir="${NUFI_DATA_DIR:-$HERE/data}"
  ext="$(mesh_join_ext "$os")" || exit 2
  template="$HERE/lib/join-templates/$os.$ext"
  [ -f "$template" ] || { echo "invite: no template for os '$os'" >&2; exit 2; }
  key="$(mesh_preauth "$name")" || exit $?
  ca_b64="$(mesh_ca_b64)" || exit $?
  drives_block="$(mesh_drives_block "$os" "$BOX_MESH_HOST" "$drives")"
  mkdir -p "$data_dir/invites"
  out="$data_dir/invites/nufi-join-$name.$ext"
  MESH_JOIN_AUTH_KEY="$key" mesh_render_template "$template" "$out" \
    "MEMBER=$name" "MESH_SERVER_URL=$MESH_SERVER_URL" \
    "BOX_MESH_HOST=$BOX_MESH_HOST" "CA_B64=$ca_b64" "DRIVES=$drives_block"
  echo "Wrote $out"
  echo "Send it to $name (email or chat — not a public link): \"Run this file, then open https://${BOX_MESH_HOST}:3080 — the key inside works once.\""
}

# ---------- the box as a mesh node (Task 6) --------------------------------
#
# `nufi-box mesh up | status | down`. Everything below is sourced by nufi-box
# and uses its $HERE, $ENVF, $OS, $DRY, $COMPOSE and its run()/die().

# The Tailscale CLI inside the app bundle; a macOS box joins with the native
# app because Docker Desktop's "host" network is the Linux VM's, not the Mac's.
MESH_MACOS_TS="/Applications/Tailscale.app/Contents/MacOS/Tailscale"

# mesh_compose_cmd — the base compose command plus the mesh layer. Not a
# variable at source time: $COMPOSE is assembled by nufi-box from the OS, the
# GPU answer and NUFI_BOX_COMPOSE_EXTRA, and the mesh layer goes on last.
mesh_compose_cmd() { printf '%s -f %s --profile mesh' "$COMPOSE" "$HERE/docker-compose.mesh.yml"; }

# mesh_ts_cmd — how this box asks its own tailscaled a question.
mesh_ts_cmd() {
  if [ "$OS" = "Darwin" ]; then printf '%s' "$MESH_MACOS_TS"
  else printf '%s exec -T tailscale tailscale' "$(mesh_compose_cmd)"; fi
}

# mesh_ts ARGS… — run that command for real.
mesh_ts() {
  if [ "$OS" = "Darwin" ]; then "$MESH_MACOS_TS" "$@"
  else $(mesh_compose_cmd) exec -T tailscale tailscale "$@"; fi
}

# mesh_current_ip — the box's 100.64.x.y, or empty if it is not joined yet.
mesh_current_ip() {
  local ip
  ip="$(mesh_ts ip -4 2>/dev/null | head -1 | tr -d '[:space:]')" || true
  case "$ip" in 100.*) printf '%s' "$ip" ;; esac
}

# mesh_wait_ip SECONDS — poll until tailscaled reports an address. No
# timeout(1) on macOS, so this is a bounded loop like everything else here.
mesh_wait_ip() {
  local budget="$1" i=0 ip
  while [ "$i" -lt "$budget" ]; do
    ip="$(mesh_current_ip)"
    [ -n "$ip" ] && { printf '%s' "$ip"; return 0; }
    i=$((i + 2)); sleep 2
  done
  return 1
}

# mesh_dns_name — the MagicDNS name the coordinator gave this node, read from
# tailscaled itself (Self.DNSName, e.g. "nufi.box.lab."). Deliberately NOT
# ${BOX_NAME}.${MESH_BASE_DOMAIN}: the base domain is the coordinator's
# setting, and a box that recomputed it locally would be a second source of
# truth that silently disagrees the day the coordinator changes it. Falls
# back to that composition only if tailscaled has no name for us.
mesh_dns_name() {
  local name
  name="$(mesh_ts status --json 2>/dev/null | python3 -c '
import json, sys
try:
    print(((json.load(sys.stdin).get("Self") or {}).get("DNSName") or "").rstrip("."))
except Exception:
    print("")
' 2>/dev/null)" || true
  if [ -z "$name" ] && [ -n "${MESH_BASE_DOMAIN:-}" ]; then
    name="${BOX_NAME:-nufi}.${MESH_BASE_DOMAIN}"
  fi
  printf '%s' "$name"
}

# --- keeping the generated caddy/mesh.caddy in step with the Caddyfile --------
#
# caddy/mesh.caddy is generated, gitignored, and was versioned by nothing. Its
# blocks import the Caddyfile's snippets by name, so the two are coupled — and
# when that coupling changed (Task 6 rendered `import landing`, then deleted
# the `(landing)` snippet from the Caddyfile after proving the bare `:80`
# already served it), every box that had already joined a mesh kept its old
# render. Caddy then read `import landing` with no such snippet, fell back to
# treating it as a path, hit the real caddy/landing DIRECTORY, and refused the
# entire front door: six ports down, LAN and mesh, at the next restart — which
# is exactly what an upgrade causes. A fresh box was fine, which is why this
# was invisible from the repo.
#
# Two checks, because they fail differently:
#
#   the stamp   — bump MESH_CADDY_REV whenever the shape of the generated file
#                 or the snippets it leans on change. Catches drift a person
#                 knows about, including a change that is still valid Caddy
#                 config but no longer means the same thing. rev 1 is the
#                 unstamped render this fix replaces.
#   the imports — every `import <name>` in the generated file must be a
#                 `(<name>)` snippet in this Caddyfile. Catches the drift
#                 nobody remembered to bump, which is the one that happened.
MESH_CADDY_REV=2

# mesh_caddy_stale FILE CADDYFILE — 0 (true) when FILE was written by an older
# box, or asks CADDYFILE for a snippet it no longer defines. A file that is not
# there is not stale: the installer seeds the empty template for that.
mesh_caddy_stale() {
  local file="$1" caddyfile="$2" name
  [ -f "$file" ] || return 1
  grep -q "^# nufi-box mesh.caddy rev ${MESH_CADDY_REV}\$" "$file" || return 0
  for name in $(sed -n 's/^[[:space:]]*import[[:space:]][[:space:]]*\([A-Za-z_][A-Za-z0-9_]*\)[[:space:]]*$/\1/p' "$file"); do
    grep -q "^[[:space:]]*(${name})[[:space:]]*{" "$caddyfile" || return 0
  done
  return 1
}

# mesh_caddy_refresh DIR — make DIR/caddy/mesh.caddy something DIR/Caddyfile can
# read, before anything asks Caddy to start with it. Called by the installer
# (before `compose up`, so an upgraded box comes up on its own) and by
# `nufi-box up | restart`. A box that still knows its mesh address gets the
# sites re-rendered; one that does not gets the empty template back rather than
# a file that would take the whole front door down.
mesh_caddy_refresh() {
  local dir="$1" file="$1/caddy/mesh.caddy" empty="$1/caddy/mesh.caddy.empty"
  if [ "$DRY" = 1 ]; then
    printf '  $ refresh %s   # re-render it if an older box wrote it\n' "$file"
    return 0
  fi
  if [ ! -f "$file" ]; then cp "$empty" "$file"; return 0; fi
  mesh_caddy_stale "$file" "$dir/Caddyfile" || return 0
  if [ -n "${BOX_MESH_HOST:-}" ] && [ -n "${BOX_MESH_IP:-}" ]; then
    mesh_render_caddy "$BOX_MESH_HOST" "$BOX_MESH_IP" "$file"
    echo "caddy/mesh.caddy was written by an older box; re-rendered for $BOX_MESH_HOST"
  else
    cp "$empty" "$file"
    echo "caddy/mesh.caddy was written by an older box and this one has no mesh address; emptied it — run: nufi-box mesh up"
  fi
}

# mesh_render_caddy HOST IP OUT — the box's five TLS sites again, on the mesh
# name and the mesh address. Nothing for :80 — see the note in the generated
# header, and test_the_plain_http_site_answers_for_every_host_including_the_mesh_name. Literal values, not {$BOX_MESH_HOST} placeholders:
# Caddy resolves an env placeholder to the empty string when it is unset,
# which would turn every site address into ":3080" and hand the whole box to
# whoever asks. The bodies are the Caddyfile's own snippets, so the LAN and
# the mesh can never serve different things.
mesh_render_caddy() {
  local host="$1" ip="$2" out="$3"
  cat > "$out" <<EOF
# nufi-box mesh.caddy rev $MESH_CADDY_REV
# caddy/mesh.caddy — GENERATED by \`nufi-box mesh up\`; do not edit.
# The box's sites on the mesh: $host and $ip.
# \`nufi-box mesh down\` replaces this with caddy/mesh.caddy.empty.
#
# Five blocks, one per TLS product port. Plain HTTP needs none: the
# Caddyfile's bare \`:80\` has no host matcher and Caddy binds it on every
# interface, so the landing page and the CA download already answer on the
# mesh name and the mesh address.

$host:3080, $ip:3080 {
	import box_tls
	reverse_proxy librechat:3080
}

$host:3001, $ip:3001 {
	import box_tls
	reverse_proxy console:3000
}

$host:3002, $ip:3002 {
	import box_tls
	reverse_proxy admin-panel:3000
}

$host:7860, $ip:7860 {
	import studio_routes
}

$host:4000, $ip:4000 {
	import box_tls
	reverse_proxy litellm-proxy:4000
}
EOF
}

# mesh_write_addresses IP HOST — record where the box now answers, so
# `nufi-box invite` can put it in a join file and `mesh status` can show it.
mesh_write_addresses() {
  if [ "$DRY" = 1 ]; then
    echo "BOX_MESH_IP=$1"
    echo "BOX_MESH_HOST=$2"
  else
    . "$HERE/lib/envfile.sh"
    envfile_set "$ENVF" BOX_MESH_IP "$1"
    envfile_set "$ENVF" BOX_MESH_HOST "$2"
  fi
}

# mesh_reload_caddy — pick up caddy/mesh.caddy without dropping a connection.
# The Caddyfile is mounted read-only and ./caddy with it, so there is nothing
# to copy into the container first.
mesh_reload_caddy() {
  if [ "$DRY" = 1 ]; then run $COMPOSE exec caddy caddy reload --config /etc/caddy/Caddyfile; return 0; fi
  $COMPOSE exec caddy caddy reload --config /etc/caddy/Caddyfile && return 0
  # `exec` needs a container that is running, and a Caddy holding a config it
  # cannot read is not — it is crash-looping ("Container … is restarting, wait
  # until the container is running"), which is precisely the box this command
  # is being run to rescue. The file on disk is already correct by here, so a
  # restart is what makes it read it.
  echo "caddy would not reload (it is probably restarting); restarting it instead" >&2
  $COMPOSE restart caddy
}

# mesh_up_native — macOS. Prints the two commands (the app cannot be driven
# headlessly, and `login` wants the operator's own authorisation), then waits
# for tailscaled to answer before going on with the .env and Caddy steps.
mesh_up_native() {
  echo "This is a Mac: the box joins with the native Tailscale app, not a container."
  echo "Install it from https://tailscale.com/download/mac, then run these two:"
  echo
  printf '  %s login --login-server=%s --auth-key=%s --hostname=%s\n' \
    "$MESH_MACOS_TS" "$MESH_SERVER_URL" "$MESH_AUTH_KEY" "${BOX_NAME:-nufi}"
  printf '  %s up --accept-dns=false\n' "$MESH_MACOS_TS"
  echo
  [ "$DRY" = 1 ] && return 0
  echo "Waiting up to 120 s for this Mac to come up on the mesh…"
  mesh_wait_ip 120 >/dev/null && return 0
  echo "Not on the mesh yet. Run the two commands above, then: nufi-box mesh up" >&2
  return 1
}

# mesh_up — join the coordinator and serve everything on the mesh address too.
mesh_up() {
  local ip host
  [ -n "${MESH_SERVER_URL:-}" ] || die "mesh up: MESH_SERVER_URL is not set in $ENVF — install-box.sh --mesh <coordinator-url> --auth-key <key> writes it"
  [ -n "${MESH_AUTH_KEY:-}" ] || die "mesh up: MESH_AUTH_KEY is not set in $ENVF — ask the coordinator for a pre-auth key. On the coordinator: headscale users list -o json for the box user's numeric id (v0.29.3's --user does not take a name), then headscale preauthkeys create --user <id> --tags tag:box — deploy/coordinator/README.md \"Hand it to a box\""
  if [ "$OS" = "Darwin" ]; then
    mesh_up_native || exit 1
  else
    echo "Joining $MESH_SERVER_URL as ${BOX_NAME:-nufi}…"
    run $(mesh_compose_cmd) up -d tailscale
  fi
  if [ "$DRY" = 1 ]; then
    printf '  $ %s ip -4\n' "$(mesh_ts_cmd)"
    printf '  $ %s status --json    # .Self.DNSName\n' "$(mesh_ts_cmd)"
    ip="<the address tailscaled reports>"
    host="<the MagicDNS name the coordinator gave this box>"
  else
    ip="$(mesh_wait_ip 120)" || die "mesh up: tailscaled never reported an address; look at: nufi-box logs tailscale"
    host="$(mesh_dns_name)"
    [ -n "$host" ] || die "mesh up: the coordinator gave this box no MagicDNS name — is magic_dns enabled on it?"
  fi
  mesh_write_addresses "$ip" "$host"
  if [ "$DRY" = 1 ]; then
    printf '  $ render %s for %s / %s\n' "$HERE/caddy/mesh.caddy" "$host" "$ip"
  else
    mesh_render_caddy "$host" "$ip" "$HERE/caddy/mesh.caddy"
  fi
  mesh_reload_caddy
  # Samba needs nothing: it publishes 445 through Docker, which binds every
  # address the host has, the mesh one included (verified in the Ubuntu VM —
  # see the Task 6 report). Pinning smbd's `interfaces` to the mesh address
  # instead would break it outright: the container has neither the LAN nor
  # the mesh address on any of its own interfaces.
  cat <<EOF

  The box is on the mesh.

    address       $ip
    name          $host
    chat          https://$host:3080
    drives        \\\\$host\\<department>

  Invite a laptop:  nufi-box invite <name> --os macos|windows|linux
EOF
}

# mesh_status — where the box is on the mesh, and what tailscaled thinks.
mesh_status() {
  echo "  coordinator    ${MESH_SERVER_URL:-(none — this box is LAN-only)}"
  echo "  mesh address   ${BOX_MESH_IP:-(not joined)}"
  echo "  MagicDNS name  ${BOX_MESH_HOST:-(not joined)}"
  echo
  run $(mesh_ts_cmd) status
}

# mesh_down — leave the mesh: stop the node, forget the addresses, and take
# the mesh sites off Caddy. The node stays registered on the coordinator on
# purpose, so `mesh up` rejoins with the same address and the invites already
# sent keep working; `nufi-box revoke` is what removes a node for good.
mesh_down() {
  if [ "$OS" = "Darwin" ]; then
    printf '  %s logout\n' "$MESH_MACOS_TS"
  else
    run $(mesh_compose_cmd) stop tailscale
  fi
  mesh_write_addresses "" ""
  run cp "$HERE/caddy/mesh.caddy.empty" "$HERE/caddy/mesh.caddy"
  mesh_reload_caddy
  echo "The box is off the mesh; it still answers on the LAN."
}
