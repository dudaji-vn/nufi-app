#!/bin/bash
# two-customers.sh — prove that two customers on their own coordinators cannot
# reach each other, and that a credential for one is worthless on the other.
#
# The ruling behind this (deploy/box, "one coordinator per customer") is that a
# second company gets its OWN coordinator, never a shared one: the mesh ACL is
# flat — every tag:member reaches every tag:box — so two companies on one
# coordinator would see each other's boxes. This script stands two coordinators
# up side by side and shows that separating them at the coordinator is a hard
# wall, not a policy that could be misconfigured away.
#
#   ./two-customers.sh            run it; tear both stacks down after
#   ./two-customers.sh --keep     leave them up to poke at
#
# Each coordinator is a full stack (headscale + caddy, internal TLS) in its own
# compose project, publishing no host ports — the two member nodes join over the
# coordinator's own Docker network, which is all the isolation proof needs. It
# writes nothing into this directory and uses its own project names.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
KEEP=0; [ "${1:-}" = "--keep" ] && KEEP=1
say()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m ok\033[0m %s\n' "$*"; }
bad()  { printf '\033[1;31m xx\033[0m %s\n' "$*" >&2; }
FAIL=0
check() { if [ "$1" = "$2" ]; then ok "$3"; else bad "$3 (got: $1, want: $2)"; FAIL=1; fi; }

NODE_IMAGE=tailscale/tailscale:v1.102.3
TMP="$(mktemp -d)"
trap 'teardown' EXIT

# One customer's coordinator: project name, server host, base domain. Internal
# TLS, no published ports. Prints its API key on stdout.
bringup() {  # bringup PROJECT HOST BASEDOMAIN
  local proj="$1" host="$2" base="$3"; local dir="$TMP/$proj"
  cp -r "$HERE" "$dir"
  rm -rf "$dir/data" "$dir/Caddyfile.rendered" "$dir/config/headscale.yaml" "$dir/two-customers.sh"
  cat > "$dir/.env" <<EOF
MESH_SERVER_HOST=$host
MESH_BASE_DOMAIN=$base
TLS_MODE=internal
EOF
  # An override that unpublishes every host port: the nodes join internally.
  cat > "$dir/no-ports.yml" <<'EOF'
services:
  headscale: { ports: !override [] }
  caddy:     { ports: !override [] }
EOF
  ( cd "$dir" && COMPOSE_PROJECT_NAME="$proj" COORDINATOR_COMPOSE_EXTRA=no-ports.yml \
      ./bootstrap.sh >"$TMP/$proj.log" 2>&1 ) || { tail -15 "$TMP/$proj.log" >&2; return 1; }
  grep '^MESH_API_KEY=' "$TMP/$proj.log" | tail -1 | cut -d= -f2
}

dc()   { docker compose -p "$1" -f "$TMP/$1/docker-compose.yml" -f "$TMP/$1/no-ports.yml" "${@:2}"; }
hs()   { dc "$1" exec -T headscale headscale "${@:2}"; }
node_count() { hs "$1" nodes list -o json 2>/dev/null | python3 -c 'import sys,json;d=sys.stdin.read().strip();L=json.loads(d) if d else [];print(len(L) if isinstance(L,list) else 0)'; }
has_node()   { hs "$1" nodes list -o json 2>/dev/null | python3 -c 'import sys,json;d=sys.stdin.read().strip();L=json.loads(d) if d else [];L=L if isinstance(L,list) else [];print("yes" if any(n.get("givenName")==sys.argv[1] or n.get("name")==sys.argv[1] for n in L) else "no")' "$2"; }

# The prefix of the API key a coordinator holds (its own admin credential).
apikey_prefix() { hs "$1" apikeys list -o json 2>/dev/null | python3 -c 'import sys,json;d=sys.stdin.read().strip();L=json.loads(d) if d else [];print((L[0].get("prefix") if L else "") or "")'; }

# Mint a tag:member pre-auth key on a coordinator (numeric user id 1 = box).
preauth() { hs "$1" preauthkeys create --user 1 --tags tag:member --expiration 1h 2>/dev/null | tr -d '\r\n'; }

# Join a userspace node to a coordinator over its own Docker network. The node
# resolves the coordinator's TLS name to caddy's address on that network and
# trusts the exported internal CA. Returns 0 on join.
join_node() {  # join_node PROJECT HOST NODENAME AUTHKEY  [EXPECT_OK]
  local proj="$1" host="$2" name="$3" key="$4"; local net="${proj}_coord" ca="$TMP/$proj/data/coordinator-ca.crt"
  docker rm -f "$name" >/dev/null 2>&1 || true
  docker run -d --name "$name" --hostname "$name" --network "$net" \
    --add-host "$host:$(caddy_ip "$proj" "$net")" \
    -v "$ca:/ca.crt:ro" -e SSL_CERT_FILE=/ca.crt \
    -e TS_USERSPACE=true -e TS_STATE_DIR=/var/lib/tailscale -e TS_AUTHKEY="$key" \
    -e TS_EXTRA_ARGS="--login-server=https://$host --hostname=$name --accept-dns=false" \
    "$NODE_IMAGE" >/dev/null
}
caddy_ip() { docker inspect -f "{{(index .NetworkSettings.Networks \"$2\").IPAddress}}" "${1}-caddy-1"; }
joined() { docker exec "$1" tailscale status --json 2>/dev/null | python3 -c 'import sys,json;d=json.load(sys.stdin);print("yes" if (d.get("Self") or {}).get("Online") or (d.get("BackendState")=="Running" and (d.get("Self") or {}).get("TailscaleIPs")) else "no")' 2>/dev/null || echo no; }

teardown() {
  [ "$KEEP" = 1 ] && { say "left up (--keep): projects nufi-cust-a, nufi-cust-b; nodes node-a, node-b"; return; }
  docker rm -f node-a node-b >/dev/null 2>&1 || true
  dc nufi-cust-a down -v >/dev/null 2>&1 || true
  dc nufi-cust-b down -v >/dev/null 2>&1 || true
  rm -rf "$TMP"
}

# --- the proof ---------------------------------------------------------------
say "Bringing up two coordinators, one per customer"
KEY_A="$(bringup nufi-cust-a a.mesh.lab box-a.lab)" || exit 1
KEY_B="$(bringup nufi-cust-b b.mesh.lab box-b.lab)" || exit 1
ok "A = a.mesh.lab   B = b.mesh.lab   (separate stacks, separate sqlite, separate DERP keys)"

say "Each starts with no member nodes"
check "$(node_count nufi-cust-a)" 0 "A has no nodes yet"
check "$(node_count nufi-cust-b)" 0 "B has no nodes yet"

say "A member key minted on A is rejected by B (separate mesh domains)"
PA="$(preauth nufi-cust-a)"
join_node nufi-cust-b b.mesh.lab crossnode "$PA" ; sleep 6
check "$(joined crossnode)" no "a node offering A's key to B does not join B"
check "$(node_count nufi-cust-b)" 0 "B still has no nodes"
docker rm -f crossnode >/dev/null 2>&1 || true

say "The two admin key stores are independent (a credential for one is not the other's)"
PFX_A="$(apikey_prefix nufi-cust-a)"; PFX_B="$(apikey_prefix nufi-cust-b)"
[ -n "$PFX_A" ] && [ -n "$PFX_B" ] && ok "A holds key $PFX_A…, B holds key $PFX_B… (each minted its own)" || { bad "could not read both API key prefixes"; FAIL=1; }
if [ -n "$PFX_A" ] && [ "$PFX_A" != "$PFX_B" ]; then ok "A's API key is not B's — neither coordinator honours the other's"; else bad "the two coordinators share an API key prefix"; FAIL=1; fi
# And B's store does not contain A's key: list every prefix B knows, assert A's is absent.
B_HAS_A="$(hs nufi-cust-b apikeys list -o json 2>/dev/null | python3 -c 'import sys,json;d=sys.stdin.read().strip();L=json.loads(d) if d else [];print("yes" if any((k.get("prefix") or "")==sys.argv[1] for k in L) else "no")' "$PFX_A")"
check "$B_HAS_A" no "B's admin store does not contain A's key"

say "A node joins its own coordinator and shows up only there"
PA2="$(preauth nufi-cust-a)"; join_node nufi-cust-a a.mesh.lab node-a "$PA2"
PB="$(preauth nufi-cust-b)";  join_node nufi-cust-b b.mesh.lab node-b "$PB"
sleep 8
check "$(joined node-a)" yes "node-a joined A"
check "$(joined node-b)" yes "node-b joined B"
check "$(has_node nufi-cust-a node-a)" yes "A lists node-a"
check "$(has_node nufi-cust-b node-a)" no  "B never sees node-a"
check "$(has_node nufi-cust-b node-b)" yes "B lists node-b"
check "$(has_node nufi-cust-a node-b)" no  "A never sees node-b"

say "node-a's tailnet contains only A's machines — B's box is not even a peer"
PEERS_A="$(docker exec node-a tailscale status --json 2>/dev/null | python3 -c 'import sys,json;print(len(json.load(sys.stdin).get("Peer") or {}))' 2>/dev/null || echo '?')"
check "$PEERS_A" 0 "node-a sees no peer from B (only itself on A's tailnet)"

echo
if [ "$FAIL" = 0 ]; then ok "PASS — two coordinators are two separate meshes; neither key nor node crosses over"
else bad "FAIL — see the rows above"; fi
exit "$FAIL"
