#!/bin/bash
# run.sh — bring up the NAT lab and prove the five things P2 depends on.
#
#   ./run.sh                 direct or relayed, whichever NAT traversal finds
#   ./run.sh --force-relay   routers drop forwarded UDP except STUN, so the
#                            path MUST come out as DERP or the run fails
#   ./run.sh --keep          leave the stack up afterwards for poking at
#   ./run.sh --dry-run       print the plan and the resolved settings; touch
#                            neither docker nor the filesystem
#
# Exit 0 only if every check passed. The table it prints is the acceptance
# criterion for P2 until a real VPS exists:
#
#   join-a            node-a (tag:member) reached BackendState=Running and
#                     headscale lists it
#   join-b            same for node-b (tag:box, hostname `nufi`)
#   path              direct | DERP — how node-a's packets actually reach
#                     node-b, read from `tailscale ping`
#   http-over-mesh    curl --cacert box-ca https://nufi.box.lab:3080/health
#                     from node-a's namespace: MagicDNS name, mesh route, TLS
#                     that validates
#   smb-round-trip    smbclient put from node-a, file read back on node-b
#
# bash 3.2 (macOS /bin/bash); no timeout(1) — every wait is a bounded loop.
set -euo pipefail

# ---------- output helpers ----------------------------------------------------
say()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m ok\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m !!\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m xx\033[0m %s\n' "$*" >&2; exit 1; }

# ---------- arguments ---------------------------------------------------------
FORCE_RELAY=0
KEEP=0
DRY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --force-relay) FORCE_RELAY=1 ;;
    --keep)        KEEP=1 ;;
    --dry-run)     DRY=1 ;;
    -h|--help)     sed -n '2,26p' "$0"; exit 0 ;;
    *)             die "unknown argument: $1 (try --help)" ;;
  esac
  shift
done

HERE="$(cd "$(dirname "$0")" && pwd)"
COORD="$(cd "$HERE/.." && pwd)"
KEYS="$HERE/keys"
RENDERED="$HERE/rendered"

MESH_SERVER_HOST=coordinator.lab
MESH_BASE_DOMAIN=box.lab
BOX_MESH_HOST="nufi.$MESH_BASE_DOMAIN"
SHARE=lab
SHARE_USER=lab
SHARE_PASS=lab
PROBE_FILE=hello.txt

# ---------- results -----------------------------------------------------------
# bash 3.2 has no associative arrays; five plain variables are enough.
R_JOIN_A=FAIL; R_JOIN_B=FAIL; R_PATH=FAIL; R_HTTP=FAIL; R_SMB=FAIL
OBSERVED_PATH="-"
T_START=$(date +%s)
T_COORD=0; T_JOIN=0; T_TOTAL=0

# ---------- the plan (also the --dry-run output) ------------------------------
print_plan() {
  cat <<EOF
NAT lab plan
  project             nufi-lab   (never nufi-box or nufi-coordinator)
  compose file        $HERE/docker-compose.yml
  coordinator stack   $COORD/docker-compose.yml + $HERE/coordinator.lab.yml
  coordinator env     $HERE/lab.env
  keys / CAs          $KEYS  (gitignored)
  rendered config     $RENDERED  (gitignored)

  networks            wan 172.30.0.0/24 | lan-a 10.10.0.0/24 (no masq) | lan-b 10.20.0.0/24 (no masq)
  coordinator         172.30.0.10 = $MESH_SERVER_HOST  (443/tcp control+DERP, 3478/udp STUN)
  routers             router-a 172.30.0.11 / 10.10.0.2   router-b 172.30.0.12 / 10.20.0.2
  nodes               node-a 10.10.0.3 (tag:member)      node-b 10.20.0.3 (tag:box, "nufi")
  box stand-in        https://$BOX_MESH_HOST:3080/health   //$BOX_MESH_HOST/$SHARE

  force-relay         $FORCE_RELAY   (1 = routers DROP forwarded UDP except 3478)
  keep stack up       $KEEP

steps
   1  docker compose down -v --remove-orphans        (start from nothing)
   2  render $RENDERED/headscale.yaml and $RENDERED/Caddyfile
      via: MESH_SERVER_HOST=$MESH_SERVER_HOST MESH_BASE_DOMAIN=$MESH_BASE_DOMAIN TLS_MODE=internal ../bootstrap.sh --dry-run
   3  docker compose build router-a tools-a
   4  docker compose up -d headscale caddy router-a router-b
   5  wait for headscale + caddy healthy, export Caddy's internal root to
      $KEYS/coordinator-ca.crt
   6  headscale users create box (idempotent), read its numeric id
   7  headscale preauthkeys create --user <id> --tags tag:member|tag:box
      --expiration 1h  ->  $KEYS/node-a.key, $KEYS/node-b.key
   8  docker compose up -d node-a node-b     [join-a] [join-b]
   9  assert headscale nodes list shows node-a and nufi
  10  docker compose up -d tools-a box-caddy box-samba; export the box's
      internal root to $KEYS/box-ca.crt
  11  tailscale ping --c 3 --until-direct=false nufi   -> [path]
  12  curl --cacert box-ca https://$BOX_MESH_HOST:3080/health   -> [http-over-mesh]
  13  smbclient //$BOX_MESH_HOST/$SHARE put $PROBE_FILE, read it back on
      node-b                                                    -> [smb-round-trip]
  14  docker compose down -v$([ "$KEEP" = 1 ] && printf '   (skipped: --keep)')
EOF
}

if [ "$DRY" = 1 ]; then
  print_plan
  exit 0
fi

command -v docker >/dev/null 2>&1 || die "docker is not on PATH"
docker info >/dev/null 2>&1 || die "the docker daemon is not reachable"

cd "$HERE"
export LAB_FORCE_RELAY="$FORCE_RELAY"

dc() { docker compose -f "$HERE/docker-compose.yml" "$@"; }
hs() { dc exec -T headscale headscale "$@"; }

cleanup() {
  if [ "$KEEP" = 1 ]; then
    warn "--keep: leaving the stack up (tear down with: LAB_FORCE_RELAY=$FORCE_RELAY docker compose -f $HERE/docker-compose.yml down -v)"
  else
    say "Tearing the lab down"
    dc down -v --remove-orphans >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

# ---------- 1. start from nothing ---------------------------------------------
say "Removing anything left from a previous run"
dc down -v --remove-orphans >/dev/null 2>&1 || true
rm -rf "$KEYS" "$RENDERED"
mkdir -p "$KEYS" "$RENDERED"

# ---------- 2. render the coordinator's config --------------------------------
# bootstrap.sh --dry-run prints the two rendered files, delimited by "--- name
# ---" lines, and touches nothing. Reusing it (rather than repeating its two
# `sed` calls here) is what keeps the lab honest: whatever a VPS would run is
# exactly what the lab runs. COORDINATOR_ENV points at a path that does not
# exist so a real coordinator's .env on this machine can never leak in, and the
# output lands in lab/rendered/ so a lab run cannot overwrite the config of a
# real coordinator that shares this machine.
say "Rendering the coordinator config from ../bootstrap.sh"
render="$(
  MESH_SERVER_HOST="$MESH_SERVER_HOST" \
  MESH_BASE_DOMAIN="$MESH_BASE_DOMAIN" \
  TLS_MODE=internal \
  ACME_EMAIL= \
  COORDINATOR_ENV="$KEYS/no-such.env" \
  bash "$COORD/bootstrap.sh" --dry-run
)"
printf '%s\n' "$render" \
  | awk '/^--- config\/headscale.yaml ---$/{f=1;next} /^--- /{f=0} f' > "$RENDERED/headscale.yaml"
printf '%s\n' "$render" \
  | awk '/^--- Caddyfile.rendered ---$/{f=1;next} /^--- /{f=0} f' > "$RENDERED/Caddyfile"
grep -q "server_url: https://$MESH_SERVER_HOST" "$RENDERED/headscale.yaml" \
  || die "the rendered headscale.yaml has no server_url for $MESH_SERVER_HOST"
grep -q 'tls internal' "$RENDERED/Caddyfile" \
  || die "the rendered Caddyfile is not in internal-CA mode"
ok "rendered/headscale.yaml and rendered/Caddyfile written (gitignored)"

# ---------- 3-4. build and start the coordinator + the routers ----------------
say "Building the router and tools images"
dc build router-a tools-a

say "Starting the coordinator and both NAT routers"
dc up -d headscale caddy router-a router-b

# ---------- helpers -----------------------------------------------------------
health_of() {  # health_of <service> -> healthy|starting|unhealthy|<state>|gone
  local cid
  cid="$(dc ps -q "$1" 2>/dev/null || true)"
  [ -n "$cid" ] || { echo gone; return 0; }
  docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$cid" 2>/dev/null || echo gone
}

wait_healthy() {  # wait_healthy <service> <tries> <sleep>
  local svc="$1" tries="$2" nap="$3" i state
  i=0
  while [ "$i" -lt "$tries" ]; do
    state="$(health_of "$svc")"
    [ "$state" = healthy ] && return 0
    [ "$state" = running ] && return 0
    i=$((i + 1))
    sleep "$nap"
  done
  warn "$svc never became healthy (last state: $(health_of "$svc"))"
  return 1
}

# ---------- 5. wait for the coordinator, export its CA ------------------------
say "Waiting for headscale and caddy"
wait_healthy headscale 40 3 || { dc logs --tail 40 headscale >&2; die "headscale never became healthy"; }
wait_healthy caddy 40 3     || { dc logs --tail 40 caddy >&2; die "caddy never became healthy"; }
T_COORD=$(( $(date +%s) - T_START ))
ok "coordinator healthy in ${T_COORD}s"

say "Exporting Caddy's internal root CA"
i=0
while [ "$i" -lt 20 ]; do
  if dc cp caddy:/data/caddy/pki/authorities/local/root.crt "$KEYS/coordinator-ca.crt" >/dev/null 2>&1; then
    [ -s "$KEYS/coordinator-ca.crt" ] && break
  fi
  i=$((i + 1)); sleep 2
done
[ -s "$KEYS/coordinator-ca.crt" ] || die "could not export the coordinator's internal root CA"
ok "keys/coordinator-ca.crt"

# ---------- 6. the headscale user ---------------------------------------------
say "Making sure the headscale user 'box' exists"
# `users list -o json` prints the bare literal `null` on an empty table, not
# `[]` — hence the `or []` guard (recorded in the Task 4 report).
user_id="$(hs users list -o json | python3 -c '
import json, sys
for u in json.load(sys.stdin) or []:
    if u.get("name") == "box":
        print(u.get("id", ""))
        break
')"
if [ -z "$user_id" ]; then
  hs users create box >/dev/null
  user_id="$(hs users list -o json | python3 -c '
import json, sys
for u in json.load(sys.stdin) or []:
    if u.get("name") == "box":
        print(u.get("id", ""))
        break
')"
fi
[ -n "$user_id" ] || die "could not find or create the headscale user 'box'"
ok "user box (id $user_id)"

# ---------- 7. two single-use pre-auth keys -----------------------------------
# --user takes the numeric ID, not the name. The keys land in files rather than
# environment variables so they never appear in `docker inspect`.
mint_key() {  # mint_key <tag> <file>
  local out
  out="$(hs preauthkeys create --user "$user_id" --tags "$1" --expiration 1h -o json)"
  printf '%s' "$out" | python3 -c 'import json, sys; print(json.load(sys.stdin)["key"])' > "$2"
  chmod 600 "$2"
  [ -s "$2" ] || die "empty pre-auth key for $1"
}
say "Minting one pre-auth key per node (tag:member, tag:box; 1h)"
mint_key tag:member "$KEYS/node-a.key"
mint_key tag:box    "$KEYS/node-b.key"
ok "keys/node-a.key, keys/node-b.key"

# ---------- 8. the nodes join -------------------------------------------------
say "Starting node-a and node-b"
t_join_start=$(date +%s)
dc up -d node-a node-b

backend_state() {  # backend_state <service>
  dc exec -T "$1" tailscale status --json 2>/dev/null \
    | python3 -c 'import json,sys
try:
    print(json.load(sys.stdin).get("BackendState", ""))
except Exception:
    print("")' 2>/dev/null || true
}

wait_running() {  # wait_running <service> <tries>
  local i=0 st
  while [ "$i" -lt "$2" ]; do
    st="$(backend_state "$1")"
    [ "$st" = Running ] && return 0
    i=$((i + 1)); sleep 3
  done
  return 1
}

if wait_running node-a 30; then R_JOIN_A=PASS; ok "node-a BackendState=Running"; else warn "node-a never reached Running"; dc logs --tail 30 node-a >&2 || true; fi
if wait_running node-b 30; then R_JOIN_B=PASS; ok "node-b BackendState=Running"; else warn "node-b never reached Running"; dc logs --tail 30 node-b >&2 || true; fi
T_JOIN=$(( $(date +%s) - t_join_start ))

# ---------- 9. the coordinator agrees -----------------------------------------
say "Asking headscale what it sees"
nodes_json="$(hs nodes list -o json || echo null)"
node_names="$(printf '%s' "$nodes_json" | python3 -c '
import json, sys
for n in json.load(sys.stdin) or []:
    print(n.get("given_name") or n.get("name") or "")
' || true)"
printf '%s\n' "$node_names" | sed 's/^/    /'
printf '%s\n' "$node_names" | grep -qx 'node-a' || { warn "headscale does not list node-a"; R_JOIN_A=FAIL; }
printf '%s\n' "$node_names" | grep -qx 'nufi'   || { warn "headscale does not list nufi";   R_JOIN_B=FAIL; }

[ "$R_JOIN_A" = PASS ] && [ "$R_JOIN_B" = PASS ] || warn "skipping the mesh checks: both nodes must be joined first"

# ---------- 10. the box's two services and its CA -----------------------------
if [ "$R_JOIN_A" = PASS ] && [ "$R_JOIN_B" = PASS ]; then
  say "Starting the box stand-in (caddy + samba) and the member's tools"
  dc up -d tools-a box-caddy box-samba
  wait_healthy box-caddy 30 3 || warn "box-caddy never became healthy"
  wait_healthy box-samba 30 3 || warn "box-samba never became healthy"
  wait_healthy tools-a 20 2   || warn "tools-a never became healthy"

  say "Exporting the box's internal root CA"
  i=0
  while [ "$i" -lt 20 ]; do
    if dc cp box-caddy:/data/caddy/pki/authorities/local/root.crt "$KEYS/box-ca.crt" >/dev/null 2>&1; then
      [ -s "$KEYS/box-ca.crt" ] && break
    fi
    i=$((i + 1)); sleep 2
  done
  [ -s "$KEYS/box-ca.crt" ] && ok "keys/box-ca.crt" || warn "could not export the box's root CA"

  # ---------- 11. which path do the packets take? -----------------------------
  # The first pings always go over DERP while NAT traversal runs, so give a
  # direct path a bounded number of chances before believing DERP. With
  # --force-relay there is nothing to wait for: DERP is the answer or the lab
  # is broken.
  say "Measuring the path node-a -> nufi"
  attempts=1
  [ "$FORCE_RELAY" = 0 ] && attempts=6
  i=0
  while [ "$i" -lt "$attempts" ]; do
    ping_out="$(dc exec -T node-a tailscale ping --c 3 --until-direct=false nufi 2>&1 || true)"
    last="$(printf '%s\n' "$ping_out" | grep '^pong from' | tail -1)"
    if [ -n "$last" ]; then
      case "$last" in
        *"via DERP"*) OBSERVED_PATH=DERP ;;
        # A direct path is only worth anything if it goes through the NAT. If
        # the endpoint that won is on one of the LANs, the two nodes found each
        # other behind the routers' backs and the lab is proving nothing —
        # that is a topology bug, not a pass. (It happened: the docker host has
        # an interface on every lab bridge and will happily route between them
        # unless the routers refuse to hand private destinations upstream.)
        *"via 10.10.0."*|*"via 10.20.0."*)
          OBSERVED_PATH=lan-leak ;;
        *via*)        OBSERVED_PATH=direct ;;
      esac
    fi
    printf '    %s\n' "${last:-<no pong>}"
    [ "$OBSERVED_PATH" = direct ] && break
    i=$((i + 1))
    [ "$i" -lt "$attempts" ] && sleep 5
  done

  if [ "$FORCE_RELAY" = 1 ]; then
    if [ "$OBSERVED_PATH" = DERP ]; then
      R_PATH=PASS; ok "path is DERP, as --force-relay requires"
    else
      warn "--force-relay but the path is '$OBSERVED_PATH' — the UDP block did not hold"
    fi
  else
    case "$OBSERVED_PATH" in
      direct|DERP) R_PATH=PASS; ok "path is $OBSERVED_PATH" ;;
      lan-leak)    warn "the 'direct' path used a LAN address — the two LANs are reaching each other around the routers" ;;
      *)           warn "no pong from nufi at all" ;;
    esac
  fi

  # ---------- 12. HTTPS to the box's MagicDNS name ----------------------------
  say "GET https://$BOX_MESH_HOST:3080/health from node-a's namespace"
  http_out="$(dc exec -T tools-a curl -sS --max-time 20 --retry 3 --retry-delay 3 \
      --cacert /lab/keys/box-ca.crt "https://$BOX_MESH_HOST:3080/health" 2>&1 || true)"
  printf '    %s\n' "$http_out"
  case "$http_out" in
    ok) R_HTTP=PASS; ok "the box answered over the mesh, with a certificate that validates" ;;
    *)  warn "unexpected answer from https://$BOX_MESH_HOST:3080/health" ;;
  esac

  # ---------- 13. an SMB round trip -------------------------------------------
  say "SMB round trip //$BOX_MESH_HOST/$SHARE"
  dc exec -T box-samba mkdir -p "/shares/$SHARE" >/dev/null 2>&1 || true
  dc exec -T box-samba chown 1000:1000 "/shares/$SHARE" >/dev/null 2>&1 || true
  # Remove any earlier probe so a stale file can never fake a pass.
  dc exec -T box-samba rm -f "/shares/$SHARE/$PROBE_FILE" >/dev/null 2>&1 || true
  if dc exec -T box-samba test -e "/shares/$SHARE/$PROBE_FILE" >/dev/null 2>&1; then
    warn "could not clear the previous $PROBE_FILE"
  else
    smb_out="$(dc exec -T tools-a smbclient "//$BOX_MESH_HOST/$SHARE" \
        -U "$SHARE_USER%$SHARE_PASS" -m SMB3 \
        -c "put /etc/hostname $PROBE_FILE" 2>&1 || true)"
    printf '    %s\n' "$(printf '%s' "$smb_out" | tail -2)"
    if dc exec -T box-samba test -s "/shares/$SHARE/$PROBE_FILE" >/dev/null 2>&1; then
      R_SMB=PASS
      ok "$PROBE_FILE arrived on node-b: $(dc exec -T box-samba cat "/shares/$SHARE/$PROBE_FILE" 2>/dev/null | tr -d '\r\n')"
    else
      warn "$PROBE_FILE never appeared in the box's share"
    fi
  fi
fi

# ---------- the table ---------------------------------------------------------
T_TOTAL=$(( $(date +%s) - T_START ))
echo
printf '  %-16s %s\n' "check" "result"
printf '  %-16s %s\n' "----------------" "------"
printf '  %-16s %s\n' "join-a"         "$R_JOIN_A"
printf '  %-16s %s\n' "join-b"         "$R_JOIN_B"
printf '  %-16s %s\n' "path"           "$R_PATH ($OBSERVED_PATH)"
printf '  %-16s %s\n' "http-over-mesh" "$R_HTTP"
printf '  %-16s %s\n' "smb-round-trip" "$R_SMB"
echo
printf '  force-relay %s | coordinator up %ss | both nodes joined %ss | total %ss\n' \
  "$FORCE_RELAY" "$T_COORD" "$T_JOIN" "$T_TOTAL"
echo

for r in "$R_JOIN_A" "$R_JOIN_B" "$R_PATH" "$R_HTTP" "$R_SMB"; do
  [ "$r" = PASS ] || die "the lab did not pass"
done
ok "PASS"
