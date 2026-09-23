#!/bin/bash
# airgap.sh — prove the coordinator + a member node work with NO internet.
#
# An internal-TLS coordinator on a Docker network whose egress to the public
# internet is disabled (`internal: true`), and a member node on that same
# network: the node cannot reach anything outside, yet it still joins the mesh,
# gets an address, and trusts the coordinator through its internal CA alone.
# This makes the on-prem / air-gap claim falsifiable instead of a promise.
#
#   ./airgap.sh          run it; tear the stack down after
#   ./airgap.sh --keep   leave it up to poke at
#
# Images are pulled by the host's Docker daemon before the run; a real air-gap
# site pre-loads them from media. What the internal network proves is RUNTIME:
# once the stack is up, nothing it does reaches outside the site.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
KEEP=0; [ "${1:-}" = "--keep" ] && KEEP=1
say()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m ok\033[0m %s\n' "$*"; }
bad()  { printf '\033[1;31m xx\033[0m %s\n' "$*" >&2; }
FAIL=0
check() { if [ "$1" = "$2" ]; then ok "$3"; else bad "$3 (got: $1, want: $2)"; FAIL=1; fi; }

NODE_IMAGE=tailscale/tailscale:v1.102.3
PROJ=nufi-airgap; HOST=coordinator.airgap; BASE=box.airgap
TMP="$(mktemp -d)"; DIR="$TMP/$PROJ"

teardown() {
  [ "$KEEP" = 1 ] && { say "left up (--keep): project $PROJ, node airgap-node"; return; }
  docker rm -f airgap-node >/dev/null 2>&1 || true
  docker compose -p "$PROJ" -f "$DIR/docker-compose.yml" -f "$DIR/airgap.yml" down -v >/dev/null 2>&1 || true
  rm -rf "$TMP"
}
trap teardown EXIT

dc()   { docker compose -p "$PROJ" -f "$DIR/docker-compose.yml" -f "$DIR/airgap.yml" "$@"; }
hs()   { dc exec -T headscale headscale "$@"; }
caddy_ip() { docker inspect -f "{{(index .NetworkSettings.Networks \"${PROJ}_coord\").IPAddress}}" "${PROJ}-caddy-1"; }
joined()  { docker exec airgap-node tailscale status --json 2>/dev/null | python3 -c 'import sys,json;d=json.load(sys.stdin);s=d.get("Self") or {};print("yes" if (s.get("Online") or (d.get("BackendState")=="Running" and s.get("TailscaleIPs"))) else "no")' 2>/dev/null || echo no; }
mesh_ip() { docker exec airgap-node tailscale ip -4 2>/dev/null | head -1; }
lists_node() { hs nodes list -o json 2>/dev/null | python3 -c 'import sys,json;d=sys.stdin.read().strip();L=json.loads(d) if d else [];L=L if isinstance(L,list) else [];print("yes" if any((n.get("givenName") or n.get("name"))==sys.argv[1] for n in L) else "no")' "$1"; }

# --- bring up an internal coordinator on an egress-disabled network ----------
say "Bringing up an internal-TLS coordinator on an egress-disabled network"
cp -r "$HERE" "$DIR"
rm -rf "$DIR/data" "$DIR/Caddyfile.rendered" "$DIR/config/headscale.yaml" "$DIR/airgap.sh" "$DIR/two-customers.sh"
cat > "$DIR/.env" <<EOF
MESH_SERVER_HOST=$HOST
MESH_BASE_DOMAIN=$BASE
TLS_MODE=internal
EOF
# One override: no host ports, and the coord network has no gateway to the
# internet (internal: true). Images are already local, so the up still works.
cat > "$DIR/airgap.yml" <<'EOF'
services:
  headscale: { ports: !override [] }
  caddy:     { ports: !override [] }
networks:
  coord:
    internal: true
EOF
( cd "$DIR" && COMPOSE_PROJECT_NAME="$PROJ" COORDINATOR_COMPOSE_EXTRA=airgap.yml \
    ./bootstrap.sh >"$TMP/up.log" 2>&1 ) || { tail -20 "$TMP/up.log" >&2; bad "coordinator did not come up"; exit 1; }
ok "coordinator up: $HOST (internal CA · no host ports · coord network internal:true)"

say "It serves its own internal CA — no ACME, no Let's Encrypt"
SUBJ="$(openssl x509 -in "$DIR/data/coordinator-ca.crt" -noout -subject 2>/dev/null || true)"
case "$SUBJ" in
  *"Caddy Local Authority"*) ok "cert issuer is the internal CA: ${SUBJ#subject=}" ;;
  *) bad "unexpected CA subject: ${SUBJ:-none}"; FAIL=1 ;;
esac

# --- join a member node over the internal network ----------------------------
say "A member node joins over the internal network, trusting only that CA"
KEY="$(hs preauthkeys create --user 1 --tags tag:member --expiration 1h 2>/dev/null | tr -d '\r\n')"
docker rm -f airgap-node >/dev/null 2>&1 || true
docker run -d --name airgap-node --hostname airgap-node --network "${PROJ}_coord" \
  --add-host "$HOST:$(caddy_ip)" \
  -v "$DIR/data/coordinator-ca.crt:/ca.crt:ro" -e SSL_CERT_FILE=/ca.crt \
  -e TS_USERSPACE=true -e TS_STATE_DIR=/var/lib/tailscale -e TS_AUTHKEY="$KEY" \
  -e TS_EXTRA_ARGS="--login-server=https://$HOST --hostname=airgap-node --accept-dns=false" \
  "$NODE_IMAGE" >/dev/null
sleep 8

say "The node has no route to the public internet (this is the air-gap)"
EGRESS="$(docker exec airgap-node sh -c 'wget -T 3 -q --spider http://1.1.1.1 >/dev/null 2>&1 && echo reachable || echo blocked')"
check "$EGRESS" blocked "the node cannot reach a public address"

say "…yet it still joined the mesh and got an address"
check "$(joined)" yes "airgap-node is up on the mesh"
IP="$(mesh_ip)"; case "$IP" in
  100.*) ok "airgap-node has a mesh IP: $IP" ;;
  *) bad "no mesh IP (got: ${IP:-none})"; FAIL=1 ;;
esac
check "$(lists_node airgap-node)" yes "the coordinator lists airgap-node"

echo
if [ "$FAIL" = 0 ]; then
  ok "PASS — coordinator + node run with zero internet: internal CA, no ACME, egress blocked, mesh up"
else
  bad "FAIL — see the rows above"
fi
exit "$FAIL"
