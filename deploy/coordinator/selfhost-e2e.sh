#!/bin/bash
# selfhost-e2e.sh — prove the self-hosted-coordinator path end to end.
#
# `install-box.sh --self-host-coordinator` (deploy/box) runs THIS coordinator
# on the box itself, layered with docker-compose.selfhost.yml, and joins the
# box with a tag:box pre-auth key that lib/coordinator.sh mints. The static
# suites assert the compose shape and the plan; this boots the real thing and
# proves the runtime chain the box depends on:
#
#   1. the coordinator comes up HEALTHY with the selfhost overlay — i.e.
#      dropping the host :80 publish (internal TLS, no ACME) does not break it;
#   2. at runtime it publishes :443 and NOT :80 (the co-host port map);
#   3. lib/coordinator.sh's mint — users list -> numeric id -> preauthkeys
#      create --tags tag:box — actually works against headscale v0.29.3;
#   4. a node joins with that tag:box key and the coordinator tags it tag:box.
#
#   ./selfhost-e2e.sh          run it; tear the stack down after
#   ./selfhost-e2e.sh --keep   leave it up to poke at
#
# Needs host ports 443 and 3478/udp free (the selfhost overlay's real map) and
# the pinned headscale + tailscale images (pulled by the host's Docker daemon;
# a real box pre-loads them from media). No box stack is involved — just the
# coordinator and one member node, so it is as light as airgap.sh.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
KEEP=0; [ "${1:-}" = "--keep" ] && KEEP=1
say()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m ok\033[0m %s\n' "$*"; }
bad()  { printf '\033[1;31m xx\033[0m %s\n' "$*" >&2; }
FAIL=0
check() { if [ "$1" = "$2" ]; then ok "$3"; else bad "$3 (got: $1, want: $2)"; FAIL=1; fi; }

NODE_IMAGE=tailscale/tailscale:v1.102.3
# The same names install-box.sh --self-host-coordinator defaults to.
PROJ=nufi-selfhost; HOST=coordinator.internal; BASE=box.internal
TMP="$(mktemp -d)"; DIR="$TMP/$PROJ"

teardown() {
  [ "$KEEP" = 1 ] && { say "left up (--keep): project $PROJ, node selfhost-node"; return; }
  docker rm -f selfhost-node >/dev/null 2>&1 || true
  docker compose -p "$PROJ" -f "$DIR/docker-compose.yml" -f "$DIR/docker-compose.selfhost.yml" down -v >/dev/null 2>&1 || true
  rm -rf "$TMP"
}
trap teardown EXIT

dc()   { docker compose -p "$PROJ" -f "$DIR/docker-compose.yml" -f "$DIR/docker-compose.selfhost.yml" "$@"; }
hs()   { dc exec -T headscale headscale "$@"; }
caddy_ip() { docker inspect -f "{{(index .NetworkSettings.Networks \"${PROJ}_coord\").IPAddress}}" "${PROJ}-caddy-1"; }
box_uid()  { hs users list -o json 2>/dev/null | python3 -c 'import sys,json;u=json.load(sys.stdin) or [];b=[x for x in u if x.get("name")=="box"];print(b[0]["id"] if b else "")'; }
joined()  { docker exec selfhost-node tailscale status --json 2>/dev/null | python3 -c 'import sys,json;d=json.load(sys.stdin);s=d.get("Self") or {};print("yes" if (s.get("Online") or (d.get("BackendState")=="Running" and s.get("TailscaleIPs"))) else "no")' 2>/dev/null || echo no; }
mesh_ip() { docker exec selfhost-node tailscale ip -4 2>/dev/null | head -1; }
lists_node() { hs nodes list -o json 2>/dev/null | python3 -c 'import sys,json;d=sys.stdin.read().strip();L=json.loads(d) if d else [];L=L if isinstance(L,list) else [];print("yes" if any((n.get("givenName") or n.get("name"))==sys.argv[1] for n in L) else "no")' "$1"; }
node_tagged() { hs nodes list -o json 2>/dev/null | python3 -c '
import sys, json
d = sys.stdin.read().strip()
L = json.loads(d) if d else []
for n in (L if isinstance(L, list) else []):
    if (n.get("givenName") or n.get("name")) == sys.argv[1]:
        # v0.29.3 lists the key-derived tags under "tags"; keep the older
        # field names as a fallback in case the shape shifts.
        tags = (n.get("tags") or []) + (n.get("forcedTags") or []) + (n.get("validTags") or [])
        print("yes" if sys.argv[2] in tags else "no"); break
else:
    print("no")' "$1" "$2"; }

# --- bring up the coordinator with the selfhost overlay ----------------------
say "Bringing up the coordinator with docker-compose.selfhost.yml (co-host map)"
cp -r "$HERE" "$DIR"
rm -rf "$DIR/data" "$DIR/Caddyfile.rendered" "$DIR/config/headscale.yaml" \
  "$DIR/selfhost-e2e.sh" "$DIR/airgap.sh" "$DIR/two-customers.sh"
( cd "$DIR" && COMPOSE_PROJECT_NAME="$PROJ" \
    MESH_SERVER_HOST="$HOST" MESH_BASE_DOMAIN="$BASE" TLS_MODE=internal \
    COORDINATOR_COMPOSE_EXTRA=docker-compose.selfhost.yml \
    ./bootstrap.sh >"$TMP/up.log" 2>&1 ) \
  || { tail -25 "$TMP/up.log" >&2; bad "coordinator did not come up healthy with the selfhost overlay"; exit 1; }
ok "coordinator up HEALTHY with the selfhost overlay (internal TLS, host :80 dropped)"

say "It serves its own internal CA — no ACME, no Let's Encrypt"
SUBJ="$(openssl x509 -in "$DIR/data/coordinator-ca.crt" -noout -subject 2>/dev/null || true)"
case "$SUBJ" in
  *"Caddy Local Authority"*) ok "cert issuer is the internal CA: ${SUBJ#subject=}" ;;
  *) bad "unexpected CA subject: ${SUBJ:-none}"; FAIL=1 ;;
esac

# --- the co-host port map at runtime -----------------------------------------
say "Caddy publishes :443 and NOT host :80 (the co-host map, at runtime)"
PORTS="$(docker port "${PROJ}-caddy-1" 2>/dev/null || true)"
case "$PORTS" in *"443/tcp"*) ok "caddy publishes 443/tcp" ;; *) bad "caddy does not publish 443 (got: ${PORTS:-none})"; FAIL=1 ;; esac
case "$PORTS" in *"80/tcp"*) bad "caddy still publishes host :80 — the selfhost overlay did not drop it"; FAIL=1 ;; *) ok "caddy does not publish host :80" ;; esac

# --- mint this box's tag:box key the way lib/coordinator.sh does -------------
say "Minting a tag:box key: users list -> numeric id -> preauthkeys create"
UID_BOX="$(box_uid)"
case "$UID_BOX" in
  ''|*[!0-9]*) bad "user 'box' has no numeric id (got: ${UID_BOX:-none})"; FAIL=1 ;;
  *) ok "user 'box' resolves to numeric id $UID_BOX (v0.29.3's --user wants this, not the name)" ;;
esac
KEY="$(hs preauthkeys create --user "$UID_BOX" --tags tag:box --expiration 1h 2>/dev/null | tr -d '\r\n')"
case "$KEY" in
  '') bad "no tag:box pre-auth key was minted"; FAIL=1 ;;
  *) ok "minted a tag:box pre-auth key" ;;
esac

# --- a node joins with that key ----------------------------------------------
say "A node joins with the tag:box key, trusting only the internal CA"
docker rm -f selfhost-node >/dev/null 2>&1 || true
docker run -d --name selfhost-node --hostname selfhost-node --network "${PROJ}_coord" \
  --add-host "$HOST:$(caddy_ip)" \
  -v "$DIR/data/coordinator-ca.crt:/ca.crt:ro" -e SSL_CERT_FILE=/ca.crt \
  -e TS_USERSPACE=true -e TS_STATE_DIR=/var/lib/tailscale -e TS_AUTHKEY="$KEY" \
  -e TS_EXTRA_ARGS="--login-server=https://$HOST --hostname=selfhost-node --accept-dns=false" \
  "$NODE_IMAGE" >/dev/null
sleep 8

check "$(joined)" yes "selfhost-node is up on the mesh"
IP="$(mesh_ip)"; case "$IP" in
  100.*) ok "selfhost-node has a mesh IP: $IP" ;;
  *) bad "no mesh IP (got: ${IP:-none})"; FAIL=1 ;;
esac
check "$(lists_node selfhost-node)" yes "the coordinator lists selfhost-node"
check "$(node_tagged selfhost-node tag:box)" yes "the coordinator tags selfhost-node tag:box (from the key)"

echo
if [ "$FAIL" = 0 ]; then
  ok "PASS — self-hosted coordinator boots on the co-host map, mints a tag:box key, and a node joins"
else
  bad "FAIL — see the rows above"
fi
exit "$FAIL"
