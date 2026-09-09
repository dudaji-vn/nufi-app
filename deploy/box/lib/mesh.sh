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
mesh_api() {
  local method="$1" path="$2" data="${3:-}" tmp code
  [ -n "${MESH_SERVER_URL:-}" ] || { echo "MESH_SERVER_URL is not set in .env" >&2; exit 2; }
  [ -n "${MESH_API_KEY:-}" ] || { echo "MESH_API_KEY is not set in .env" >&2; exit 2; }
  tmp="$(mktemp)"
  if [ -n "$data" ]; then
    code="$(curl -sS --max-time 20 -o "$tmp" -w '%{http_code}' -X "$method" \
      -H "Authorization: Bearer $MESH_API_KEY" -H 'Content-Type: application/json' \
      -d "$data" "${MESH_SERVER_URL}${path}")"
  else
    code="$(curl -sS --max-time 20 -o "$tmp" -w '%{http_code}' -X "$method" \
      -H "Authorization: Bearer $MESH_API_KEY" "${MESH_SERVER_URL}${path}")"
  fi
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

# mesh_delete NAME — resolve a node name to its id and DELETE it.
mesh_delete() {
  local name="$1" body id
  body="$(mesh_api GET /api/v1/node)" || exit $?
  id="$(printf '%s' "$body" | python3 -c '
import json, sys
name = sys.argv[1]
data = json.load(sys.stdin)
matches = [n for n in (data.get("nodes") or []) if n.get("name") == name]
print(matches[0]["id"] if matches else "")
' "$name")"
  [ -n "$id" ] || { echo "revoke: no node named '$name' — run: nufi-box members" >&2; exit 2; }
  mesh_api DELETE "/api/v1/node/$id" >/dev/null
  echo "Revoked '$name' — that laptop can no longer reach the box until invited again."
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
        letter="$(printf '%s' "$letters" | cut -c$((i + 1)))"
        out="${out}net use ${letter}: \\\\${host}\\${d} /persistent:yes"$'\n' ;;
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
mesh_render_template() {
  local template="$1" out="$2"
  shift 2
  python3 -c '
import sys
template, out = sys.argv[1], sys.argv[2]
subs = {}
for kv in sys.argv[3:]:
    k, v = kv.split("=", 1)
    subs[k] = v
with open(template) as f:
    content = f.read()
for k, v in subs.items():
    content = content.replace("@" + k + "@", v)
with open(out, "w") as f:
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
  mesh_render_template "$template" "$out" \
    "MEMBER=$name" "MESH_SERVER_URL=$MESH_SERVER_URL" "AUTH_KEY=$key" \
    "BOX_MESH_HOST=$BOX_MESH_HOST" "CA_B64=$ca_b64" "DRIVES=$drives_block"
  chmod 600 "$out"
  echo "Wrote $out"
  echo "Send it to $name (email or chat — not a public link): \"Run this file, then open https://${BOX_MESH_HOST}:3080 — the key inside works once.\""
}
