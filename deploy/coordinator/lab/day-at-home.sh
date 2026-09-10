#!/bin/bash
# day-at-home.sh — the day's work, done from home, over the relay.
#
#   ./day-at-home.sh              run it; tear the lab down and stop the VM after
#   ./day-at-home.sh --keep       leave the lab up and the VM running
#   ./day-at-home.sh --dry-run    print the plan and the resolved settings only
#
# run.sh proves the *mesh* works between two containers. This proves the
# *product* works: a member on a laptop behind their own NAT, with every direct
# path blocked, using the real box — the one in the Lima VM, with its twelve
# containers, its own CA, its department drives and its four routines.
#
# The member is node-a: a container behind router-a, which drops every
# forwarded UDP packet except STUN, so the only way its packets reach the box
# is DERP over the coordinator's TCP 443. `tools-a` shares node-a's network
# namespace and holds what the member actually types — curl, smbclient and the
# two acceptance scripts from deploy/platform/scenarios.
#
# The box is NOT the lab's node-b stand-in. node-b is deliberately never
# started here: it would register as `nufi` and take the name the real box
# needs. The topology this script builds is
#
#   node-a (10.10.0.3, tag:member)                the Lima VM `nufi-ubuntu`
#     └─ router-a, UDP dropped ──┐          ┌── the Mac's own address, 443/3478
#                                ▼          ▼
#                       coordinator.lab (headscale + caddy, DERP + STUN)
#
# so the two sides meet on the mesh and nowhere else.
#
# The checks, in the order a person meets them:
#
#   box-on-mesh        the box joined and headscale lists it as `nufi`
#   path               node-a -> nufi goes via DERP, not direct
#   health-over-mesh   https://nufi.box.lab:3080/health is 200 through MagicDNS,
#                      with a certificate the box's own CA signs
#   login-over-mesh    the chat app takes the admin's credentials
#   drive-write        smbclient put onto //nufi.box.lab/legal — a probe whose
#                      name and contents are new every run, so neither this row
#                      nor the next can pass on a file an earlier run left
#   drive-ingested     nufi-ingest logs embedded=True for that file
#   agent-cites-drive  run_box.py --only legal gets an answer with a citation
#   routine            run_flows.py --only weekly returns text (--routine names
#                      another one; the budget is ROUTINE_BUDGET seconds)
#
# Exit 0 only when every check passed. A judge verdict inside run_box.py is the
# *model's* report card, not the box's: the VM runs qwen2.5:0.5b and gets some
# of the questions wrong. The answers print in full so the reader judges the
# model; this script judges the box, and its gate is that an answer carried a
# citation at all — that is what proves the drive reached the agent.
#
# bash 3.2 (macOS /bin/bash); no timeout(1) — every wait is a bounded loop.
set -uo pipefail

say()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m ok\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m !!\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m xx\033[0m %s\n' "$*" >&2; exit 1; }

KEEP=0
DRY=0
VM="${VM:-nufi-ubuntu}"
MIN_FREE_GB="${MIN_FREE_GB:-3}"
ROUTINE="${ROUTINE:-weekly}"
ROUTINE_BUDGET="${ROUTINE_BUDGET:-300}"
while [ $# -gt 0 ]; do
  case "$1" in
    --keep)         KEEP=1 ;;
    --dry-run)      DRY=1 ;;
    --vm)           shift; VM="${1:-}" ;;
    --min-free-gb)  shift; MIN_FREE_GB="${1:-3}" ;;
    --routine)      shift; ROUTINE="${1:-weekly}" ;;
    -h|--help)      sed -n '2,50p' "$0"; exit 0 ;;
    *)              die "unknown argument: $1 (try --help)" ;;
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
BOX_NODE=nufi
SHARE=legal

# The probe is new every run — its name and its contents both. A fixed
# `contract.txt` made two of the eight rows unable to fail on a box that had
# already seen it: `drive-write` gates on `test -s` at a path nothing removes,
# so a `put` refused with NT_STATUS_ACCESS_DENIED still found the previous
# run's file there, and `drive-ingested` greps a container log that survives a
# restart, so it matched the line an earlier run earned. run.sh:373 answers the
# same hazard by deleting the probe first ("so a stale file can never fake a
# pass"); this script cannot copy that, because it deliberately does not
# `down -v` and the drive belongs to a VM it does not own — so it makes the
# document new instead, and deletes it again in cleanup(). The contents carry
# the id too: nufi-ingest keys on a SHA-256 behind a size+mtime fast path
# (nufi_ingest.py:505), so a byte-identical file is correctly not re-embedded
# and would write no new log line at all.
PROBE_ID="$(date -u +%Y%m%d-%H%M%S)-$$-$RANDOM"
PROBE="contract-$PROBE_ID.txt"
PROBE_ON_BOX=0

# Four one-line predicates that decide three of the eight checks. They live
# here, each on a single line with a stable name, because ../tests/test_lab.py
# extracts them from this file and runs them against fixtures — so what CI
# pins is the string this script really uses, not a copy of it that can drift.
#
# CITED_CMD    reads box.md ($1) and prints the citation lines that name a
#              file; prints nothing (and exits non-zero) when every line is
#              `sources: none`, which is what run_box.py writes for an answer
#              with no citation.
# INGEST_CMD   reads nufi-ingest's whole log on stdin and prints the line that
#              says the probe named in $1 was embedded. Anchored to THIS run's
#              probe name, which is why grepping the whole log is safe: the
#              daemon writes `added <dept>/<file> → <id> (embedded=True)`
#              (nufi_ingest.py:527) and no earlier run can have named this
#              file. A time filter would be the wrong fix — an unchanged file
#              correctly produces no new line at all.
# SMB_FAILED_RE
#              matches smbclient's refusal lines (`NT_STATUS_ACCESS_DENIED
#              opening remote file \contract.txt`). smbclient prints these and
#              its exit status is checked as well, because the D1 acceptance
#              failure printed exactly this while the row still read PASS.
# ROUTINE_LINE_RE / ROUTINE_DRIFT_RE
#              match the line run_flows.py prints for a finished flow --
#              `f"{name:9} {'DRIFT' if drift else 'ok   '} {secs:4.0f}s"` --
#              as a whole shape. A substring test cannot be used: `ok` occurs
#              inside `broken`, so `weekly result: broken pipe, no output`
#              would read as a pass. FLOW is replaced with the flow's id.
CITED_CMD='grep "sources:" "$1" 2>/dev/null | grep -v "sources: none$"'
INGEST_CMD='grep -a "embedded=True" | grep -aF -e "$1" | tail -1'
SMB_FAILED_RE='NT_STATUS_[A-Z_]+'
ROUTINE_LINE_RE='^FLOW +(ok|DRIFT) +[0-9]+s *$'
ROUTINE_DRIFT_RE='^FLOW +DRIFT +[0-9]+s *$'

routine_said()    { printf '%s\n' "$2" | grep -qE "${ROUTINE_LINE_RE/FLOW/$1}"; }
routine_drifted() { printf '%s\n' "$2" | grep -qE "${ROUTINE_DRIFT_RE/FLOW/$1}"; }

R_JOIN=FAIL; R_PATH=FAIL; R_HTTP=FAIL; R_LOGIN=FAIL
R_WRITE=FAIL; R_INGEST=FAIL; R_AGENT=FAIL; R_ROUTINE=FAIL
OBSERVED_PATH="-"
NOTES=""
T_START=$(date +%s)
T_LAB=0; T_BOX=0; T_INGEST=-1; T_AGENT=0; T_ROUTINE=0

note() { NOTES="$NOTES
  - $*"; }

print_plan() {
  cat <<EOF
The day at home, in the lab
  compose project     nufi-lab   (never nufi-box or nufi-coordinator)
  lab compose         $HERE/docker-compose.yml
  host-port override  $RENDERED/host-ports.yml   (generated; gitignored)
  the member          node-a + tools-a, behind router-a with FORCE_RELAY=1
  the box             Lima VM '$VM', its own deploy/box, joined as $BOX_MESH_HOST
  the probe           $SHARE/$PROBE  (a new name and new contents every run,
                      removed from the drive at the end — a fixed one let
                      drive-write and drive-ingested pass on an old file)
  keys / CAs          $KEYS  (gitignored; the credential files are deleted at the end)
  routine             $ROUTINE, given ${ROUTINE_BUDGET}s to answer
  disk floor          ${MIN_FREE_GB} GB free on / — the run stops rather than fill the disk
  keep it up          $KEEP

steps
   1  free space, docker, limactl, and TCP 443 / UDP 3478 free on the Mac
   2  render $RENDERED/headscale.yaml + Caddyfile via ../bootstrap.sh --dry-run,
      and $RENDERED/host-ports.yml (443 + 3478 on the Mac, so the VM can dial in)
   3  up -d headscale caddy router-a          (NOT down -v: node registrations
      and the coordinator's CA live in the volumes and must survive)
   4  export Caddy's internal root to $KEYS/coordinator-ca.crt
   5  mint a tag:member pre-auth key -> $KEYS/node-a.key; up -d node-a tools-a
   6  limactl start $VM; wait for the box's containers; nufi-box mesh up
   7  copy the box's CA and its credentials out of the VM into $KEYS (0600)
   8  the eight checks
   9  delete the credential files; lab down (volumes kept); limactl stop $VM
EOF
}

if [ "$DRY" = 1 ]; then print_plan; exit 0; fi

# ---------- 1. preflight ------------------------------------------------------
command -v docker  >/dev/null 2>&1 || die "docker is not on PATH"
command -v limactl >/dev/null 2>&1 || die "limactl is required: brew install lima"
docker info >/dev/null 2>&1        || die "the docker daemon is not reachable"
limactl list --format '{{.Name}}' 2>/dev/null | grep -qx "$VM" || die "no Lima VM named '$VM'"

free_gb() { df -k / | awk 'NR==2 {printf "%d", $4 / 1048576}'; }
check_disk() {  # check_disk <what is about to happen>
  local free; free="$(free_gb)"
  if [ "$free" -lt "$MIN_FREE_GB" ]; then
    warn "only ${free} GB free on / — the floor is ${MIN_FREE_GB} GB"
    die "stopping before $1. Reclaiming space is the owner's call: this script will not prune images or delete the VM."
  fi
  say "$(printf '%s GB free on / — going ahead with %s' "$free" "$1")"
}
check_disk "starting the lab"

cd "$HERE"
export LAB_FORCE_RELAY=1
mkdir -p "$KEYS" "$RENDERED"
chmod 700 "$KEYS"

cat > "$RENDERED/host-ports.yml" <<'YAML'
# GENERATED by day-at-home.sh; gitignored, never committed.
#
# The VM box is a real machine outside docker's networks: it reaches this
# coordinator through the Mac's own address (Lima's vzNAT gateway), so the
# control plane has to be published on the Mac, on the two ports headscale
# advertises in its DERP map — TCP 443 (control + DERP) and UDP 3478 (STUN).
#
# It is generated rather than committed on purpose. deploy/coordinator/tests
# asserts the lab publishes only 8443/tcp and 13478/udp, because on a developer
# Mac 443 belongs to deploy/box's Caddy; a box on the same machine as the lab
# is exactly the case this script sets up and no other.
services:
  headscale:
    ports: !override
      - "443:443"
      - "3478:3478/udp"
YAML

DC() { docker compose -f "$HERE/docker-compose.yml" -f "$RENDERED/host-ports.yml" "$@"; }
hs() { DC exec -T headscale headscale "$@"; }
vm() { limactl shell "$VM" -- bash -lc "$1"; }
# Every guest docker command goes through `sg docker`: limactl reuses one SSH
# session, and that session is older than the docker group the installer made.
box() { vm "cd \$HOME/deploy/box && sg docker -c 'docker compose -f docker-compose.yml -f docker-compose.linux.yml --profile linux --profile mesh $1'"; }

# 443/tcp and 3478/udp are not free choices: headscale builds its DERP map from
# server_url (https://coordinator.lab), so a client dials TCP 443 for control
# and DERP and UDP 3478 for STUN. The lab's committed 8443/13478 map is for an
# operator poking at the coordinator from the Mac; a VM box dialling those
# would find no relay at all. A lab left up by a previous run already holds
# them, and that is not a collision -- so ask docker whose they are first.
if [ -z "$(DC ps -q headscale 2>/dev/null)" ]; then
  lsof -nP -iTCP:443 -sTCP:LISTEN >/dev/null 2>&1 \
    && die "something already listens on TCP 443; the coordinator needs it for control + DERP"
  lsof -nP -iUDP:3478 >/dev/null 2>&1 \
    && die "something already listens on UDP 3478; the coordinator needs it for STUN"
else
  say "the lab's coordinator is already up; leaving its 443/3478 bindings alone"
fi

cleanup() {
  # The credentials are read out of the box's .env for the member to use; they
  # are the box's, not the lab's, and they do not outlive the run.
  rm -f "$KEYS/box-admin.env" "$KEYS/box-smb.auth" "$KEYS/studio-api.key"
  # And neither does the probe. It is a different document every run, so
  # leaving it behind would add one to the Legal drive each time and grow the
  # corpus the agent has to read past; removing it is also what makes
  # nufi-ingest delete its embedding on the next scan. Before `limactl stop`,
  # while the VM can still be reached.
  if [ "$PROBE_ON_BOX" = 1 ]; then
    vm "rm -f \$HOME/deploy/box/data/drives/$SHARE/$PROBE" >/dev/null 2>&1 \
      || warn "could not remove $SHARE/$PROBE from the box — delete it by hand"
  fi
  if [ "$KEEP" = 1 ]; then
    warn "--keep: the lab is up and $VM is running. Tear down with:"
    warn "  LAB_FORCE_RELAY=1 docker compose -f $HERE/docker-compose.yml -f $RENDERED/host-ports.yml down && limactl stop $VM"
  else
    say "Putting the machine back: lab down (volumes kept), $VM stopped"
    DC down --remove-orphans >/dev/null 2>&1 || true
    limactl stop "$VM" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

# ---------- 2. render ---------------------------------------------------------
# Same renderer a VPS runs, exactly as run.sh does it — the lab is never a
# second copy of the coordinator's config.
say "Rendering the coordinator config from ../bootstrap.sh"
render="$(
  MESH_SERVER_HOST="$MESH_SERVER_HOST" MESH_BASE_DOMAIN="$MESH_BASE_DOMAIN" \
  TLS_MODE=internal ACME_EMAIL= COORDINATOR_ENV="$KEYS/no-such.env" \
  bash "$COORD/bootstrap.sh" --dry-run
)" || die "bootstrap.sh --dry-run failed"
printf '%s\n' "$render" | awk '/^--- config\/headscale.yaml ---$/{f=1;next} /^--- /{f=0} f' > "$RENDERED/headscale.yaml"
printf '%s\n' "$render" | awk '/^--- Caddyfile.rendered ---$/{f=1;next} /^--- /{f=0} f' > "$RENDERED/Caddyfile"
grep -q "server_url: https://$MESH_SERVER_HOST" "$RENDERED/headscale.yaml" \
  || die "the rendered headscale.yaml has no server_url for $MESH_SERVER_HOST"

ok "rendered/headscale.yaml and rendered/Caddyfile"

# ---------- 3-4. the coordinator ----------------------------------------------
# Deliberately no `down -v`: the headscale volume holds the box's and the
# member's node registrations and the caddy volume holds the CA the box already
# trusts at /etc/nufi/coordinator-ca.crt. Wiping them would make this a
# first-join test instead of a day-at-home one.
say "Starting the coordinator and the member's NAT router (volumes kept)"
DC up -d headscale caddy router-a >/dev/null 2>&1 || die "the coordinator would not start"

health_of() {
  local cid; cid="$(DC ps -q "$1" 2>/dev/null || true)"
  [ -n "$cid" ] || { echo gone; return 0; }
  docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$cid" 2>/dev/null || echo gone
}
wait_healthy() {  # wait_healthy <service> <tries> <sleep>
  local i=0 st
  while [ "$i" -lt "$2" ]; do
    st="$(health_of "$1")"
    [ "$st" = healthy ] && return 0
    [ "$st" = running ] && return 0
    i=$((i + 1)); sleep "$3"
  done
  return 1
}
wait_healthy headscale 40 3 || { DC logs --tail 30 headscale >&2; die "headscale never became healthy"; }
wait_healthy caddy 40 3     || { DC logs --tail 30 caddy >&2; die "caddy never became healthy"; }
T_LAB=$(( $(date +%s) - T_START ))
ok "coordinator healthy in ${T_LAB}s"

say "Exporting the coordinator's root CA"
i=0
while [ "$i" -lt 20 ]; do
  DC cp caddy:/data/caddy/pki/authorities/local/root.crt "$KEYS/coordinator-ca.crt" >/dev/null 2>&1 \
    && [ -s "$KEYS/coordinator-ca.crt" ] && break
  i=$((i + 1)); sleep 2
done
[ -s "$KEYS/coordinator-ca.crt" ] || die "could not export the coordinator's root CA"
ok "keys/coordinator-ca.crt"

# ---------- 5. the member joins -----------------------------------------------
say "Minting a tag:member pre-auth key and starting the member's laptop"
user_id="$(hs users list -o json 2>/dev/null | python3 -c '
import json, sys
for u in json.load(sys.stdin) or []:
    if u.get("name") == "box":
        print(u.get("id", "")); break
' 2>/dev/null)"
if [ -z "$user_id" ]; then
  hs users create box >/dev/null 2>&1
  user_id="$(hs users list -o json 2>/dev/null | python3 -c '
import json, sys
for u in json.load(sys.stdin) or []:
    if u.get("name") == "box":
        print(u.get("id", "")); break
' 2>/dev/null)"
fi
[ -n "$user_id" ] || die "could not find or create the headscale user 'box'"
# The key lands in a file, never an environment variable or an argument: it
# would otherwise show up in `docker inspect` and in `ps`.
( umask 077; hs preauthkeys create --user "$user_id" --tags tag:member --expiration 2h -o json \
  | python3 -c 'import json, sys; print(json.load(sys.stdin)["key"])' > "$KEYS/node-a.key" )
[ -s "$KEYS/node-a.key" ] || die "empty pre-auth key for the member"

DC up -d node-a tools-a >/dev/null 2>&1 || die "the member's laptop would not start"
i=0
while [ "$i" -lt 30 ]; do
  st="$(DC exec -T node-a tailscale status --json 2>/dev/null | python3 -c 'import json,sys
try: print(json.load(sys.stdin).get("BackendState",""))
except Exception: print("")' 2>/dev/null)"
  [ "$st" = Running ] && break
  i=$((i + 1)); sleep 3
done
[ "$st" = Running ] || { DC logs --tail 30 node-a >&2; die "node-a never reached BackendState=Running"; }
ok "node-a is on the mesh at $(DC exec -T node-a tailscale ip -4 2>/dev/null | tr -d '\r')"

# ---------- 6. the box --------------------------------------------------------
check_disk "starting the box VM"
say "Starting the box VM '$VM'"
t_box=$(date +%s)
limactl start "$VM" >/dev/null 2>&1 || die "limactl start $VM failed"
vm 'test -d $HOME/deploy/box' >/dev/null 2>&1 || die "$VM has no deploy/box — this is not an installed box"

say "Waiting for the box's containers"
i=0
while [ "$i" -lt 40 ]; do
  # An empty listing means compose has not answered yet, not that every
  # container is healthy -- so require at least one healthy line as well as no
  # unhealthy ones.
  svc="$(box 'ps --format "{{.Service}} {{.Status}}"' 2>/dev/null)"
  up="$(printf '%s\n' "$svc" | grep -c '(healthy)')"
  down="$(printf '%s\n' "$svc" | grep -v '(healthy)' | grep -c '[^[:space:]]')"
  [ "${up:-0}" -gt 0 ] && [ "${down:-9}" = 0 ] && break
  i=$((i + 1)); sleep 5
done
box 'ps --format "{{.Service}}\t{{.Status}}"' 2>/dev/null | sort | sed 's/^/    /'

say "Joining the mesh (nufi-box mesh up)"
# `mesh up` writes caddy/mesh.caddy and then asks Caddy to reload it. If Caddy
# is not running the reload cannot land, so check afterwards rather than trust
# the exit status — and say loudly what happened, because a front door that
# will not start is the worst failure this box has.
vm "cd \$HOME/deploy/box && sg docker -c './nufi-box mesh up'" 2>&1 | sed 's/^/    /'
if ! vm 'cd $HOME/deploy/box && sg docker -c "docker inspect -f {{.State.Health.Status}} nufi-box-caddy-1"' 2>/dev/null | grep -q healthy; then
  warn "the box's Caddy is not healthy after 'mesh up'; its last lines were:"
  box 'logs --no-log-prefix --tail 6 caddy' 2>&1 | sed 's/^/    /' >&2
  warn "restarting it so the freshly rendered caddy/mesh.caddy is the config it reads"
  note "the box's Caddy needed an explicit restart after 'mesh up' — see the report"
  box 'restart caddy' >/dev/null 2>&1
  i=0
  while [ "$i" -lt 20 ]; do
    vm 'sg docker -c "docker inspect -f {{.State.Health.Status}} nufi-box-caddy-1"' 2>/dev/null | grep -q healthy && break
    i=$((i + 1)); sleep 3
  done
fi
T_BOX=$(( $(date +%s) - t_box ))

MESH_NAME="$(vm 'cd $HOME/deploy/box && grep "^BOX_MESH_HOST=" .env | cut -d= -f2' 2>/dev/null | tr -d '\r')"
[ -n "$MESH_NAME" ] && BOX_MESH_HOST="$MESH_NAME"
# Being LISTED is not evidence of this run: the headscale volume is kept on
# purpose (see step 3), so a box that joined a week ago is still in the list
# whether or not `mesh up` did anything today. `online` is the coordinator's
# view of a live connection, so that is what the row gates on; a registration
# with nobody behind it is reported as its own failure rather than a pass.
join_state="$(hs nodes list -o json 2>/dev/null | python3 -c '
import json, sys
want = sys.argv[1]
state = "absent"
for n in (json.load(sys.stdin) or []):
    if (n.get("given_name") or n.get("name")) == want:
        state = "online" if n.get("online") else "registered"
        if state == "online":
            break
print(state)' "$BOX_NODE" 2>/dev/null)"
case "$join_state" in
  online)
    R_JOIN=PASS; ok "headscale lists the box as '$BOX_NODE' ($BOX_MESH_HOST) and online, joined in ${T_BOX}s" ;;
  registered)
    warn "headscale knows '$BOX_NODE' from an earlier run but it is not online now — this run did not join" ;;
  *)
    warn "headscale does not list a node called '$BOX_NODE'" ;;
esac

# ---------- 7. what the member carries ----------------------------------------
# In real life a member gets these from their join file and their own account.
# In the lab they come out of the box's .env, into 0600 files under keys/ that
# the trap deletes — never onto a command line another user could read.
say "Copying the box's CA and the member's credentials out of the VM"
limactl copy "$VM:deploy/box/data/nufi-box-ca.crt" "$KEYS/nufi-box-ca.crt" >/dev/null 2>&1 \
  || die "the box did not export its CA to data/nufi-box-ca.crt"
( umask 077
  vm 'cd $HOME/deploy/box && grep -E "^(ADMIN_EMAIL|ADMIN_PASSWORD)=" .env' > "$KEYS/box-admin.env"
  vm 'cd $HOME/deploy/box && awk -F= "/^SAMBA_PASSWORD=/{print \"username = nufi\"; print \"password = \" substr(\$0, index(\$0,\"=\")+1)}" .env' > "$KEYS/box-smb.auth"
  vm 'cd $HOME/deploy/box && awk -F= "/^STUDIO_API_KEY=/{print substr(\$0, index(\$0,\"=\")+1)}" .env' > "$KEYS/studio-api.key" )
[ -s "$KEYS/box-admin.env" ]  || die "no ADMIN_EMAIL/ADMIN_PASSWORD in the box's .env"
[ -s "$KEYS/box-smb.auth" ]   || die "no SAMBA_PASSWORD in the box's .env"
[ -s "$KEYS/studio-api.key" ] || warn "no STUDIO_API_KEY in the box's .env — the routine check will fail"
chmod 600 "$KEYS/nufi-box-ca.crt" "$KEYS/box-admin.env" "$KEYS/box-smb.auth" "$KEYS/studio-api.key" 2>/dev/null
ok "keys/nufi-box-ca.crt and three 0600 credential files"

# ---------- 8. the checks -----------------------------------------------------
if [ "$R_JOIN" != PASS ]; then
  warn "skipping the member's checks: the box is not on the mesh"
else

# --- path: it has to be the relay ---------------------------------------------
say "Which way do the member's packets reach the box?"
ping_out="$(DC exec -T node-a tailscale ping --c 3 --until-direct=false "$BOX_NODE" 2>&1)"
printf '%s\n' "$ping_out" | sed 's/^/    /'
last="$(printf '%s\n' "$ping_out" | grep '^pong from' | tail -1)"
case "$last" in
  *"via DERP"*) OBSERVED_PATH=DERP; R_PATH=PASS; ok "via DERP — router-a's UDP block held" ;;
  *via*)        OBSERVED_PATH=direct
                warn "the path is direct; router-a was supposed to make that impossible" ;;
  *)            warn "no pong from $BOX_NODE at all" ;;
esac

# --- the front door -----------------------------------------------------------
say "GET https://$BOX_MESH_HOST:3080/health from the member's laptop"
http_out="$(DC exec -T tools-a curl -sS --max-time 30 --retry 3 --retry-delay 3 \
    -o /tmp/health -w '%{http_code} %{remote_ip}' \
    --cacert /lab/keys/nufi-box-ca.crt "https://$BOX_MESH_HOST:3080/health" 2>&1)"
body="$(DC exec -T tools-a cat /tmp/health 2>/dev/null | tr -d '\r\n')"
printf '    HTTP %s  body: %s\n' "$http_out" "$body"
case "$http_out" in
  200\ *) R_HTTP=PASS; ok "200 over the relay, through MagicDNS, with a certificate that validates" ;;
  *)      warn "the box's front door did not answer 200 over the mesh" ;;
esac

# --- signing in ---------------------------------------------------------------
say "Signing in to the chat app over the mesh"
login_out="$(DC exec -T tools-a sh -c '
set -eu
. /lab/keys/box-admin.env
code=$(curl -sS --max-time 30 -o /tmp/login.json -w "%{http_code}" \
  --cacert /lab/keys/nufi-box-ca.crt -H "Content-Type: application/json" \
  -A "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36" \
  --data-binary "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$ADMIN_PASSWORD\"}" \
  "https://'"$BOX_MESH_HOST"':3080/api/auth/login")
python3 -c "
import json, sys
d = {}
try:
    d = json.load(open(\"/tmp/login.json\"))
except Exception:
    pass
u = d.get(\"user\") or {}
print(\"$code\", u.get(\"email\") or \"-\", u.get(\"role\") or \"-\", \"token\" if d.get(\"token\") else \"no-token\")
"' 2>&1 | tail -1)"
printf '    %s\n' "$login_out"
case "$login_out" in
  200\ *\ token) R_LOGIN=PASS; ok "the app took the member's credentials over the mesh" ;;
  *)             warn "login over the mesh did not return a token" ;;
esac

# --- putting a document on the department drive -------------------------------
say "Putting $PROBE on //$BOX_MESH_HOST/$SHARE with smbclient"
# The heredoc stays quoted so nothing in the Korean text is ever expanded; the
# run's id is appended after it, which is what makes the CONTENTS new too.
DC exec -T tools-a sh -c \
  "mkdir -p /tmp/home && { cat; echo; echo '(이 초안의 실행 식별자: $PROBE_ID)'; } > /tmp/home/$PROBE" <<'DOC'
용역계약서 부속 합의 (2026-09 개정, 집에서 올린 초안)

제1조(하자보수) 납품 완료일로부터 하자보수 보증기간은 24개월로 한다.
제2조(지체상금) 지체상금률은 1일당 계약금액의 0.1%로 하며, 상한은 계약금액의 10%로 한다.
제3조(검수) 발주처는 납품일로부터 14일 이내에 검수를 완료하여야 하며,
        기간 내 통지가 없으면 검수에 합격한 것으로 본다.
제4조(비밀유지) 본 부속 합의의 비밀유지 의무는 계약 종료 후 3년간 존속한다.
DOC
# -A reads username and password from a 0600 file, so neither reaches argv.
PROBE_ON_BOX=1   # from here on, cleanup() has a file to remove
smb_out="$(DC exec -T tools-a smbclient "//$BOX_MESH_HOST/$SHARE" \
    -A /lab/keys/box-smb.auth -m SMB3 \
    -c "put /tmp/home/$PROBE $PROBE" 2>&1)"
smb_rc=$?
printf '%s\n' "$smb_out" | sed 's/^/    /'
# Three gates, because the row that proves D1 used to have none that could
# fail: smbclient's own exit status (printed and discarded before), the
# NT_STATUS refusal it prints on the way out, and the file itself — at a path
# no earlier run can have written, since the probe is new every run.
if [ "$smb_rc" != 0 ]; then
  warn "smbclient exited $smb_rc — the put was refused"
elif printf '%s\n' "$smb_out" | grep -qE "$SMB_FAILED_RE"; then
  warn "smbclient printed an NT_STATUS error — the put was refused"
elif vm "test -s \$HOME/deploy/box/data/drives/$SHARE/$PROBE" >/dev/null 2>&1; then
  R_WRITE=PASS; ok "$PROBE is on the box's $SHARE drive"
else
  warn "$PROBE never arrived on the box's $SHARE drive"
fi

# --- and the box learning it --------------------------------------------------
# 60 seconds, the brief's number: nufi-ingest watches /drives every 20s.
# `$INGEST_CMD` reads the whole container log, which survives a restart — safe
# only because the probe's name belongs to this run alone. With a fixed probe
# this row matched the line an earlier run had earned and could not fail; the
# third acceptance run's `PASS (0s)` was exactly that. Filtering the log by
# time instead would have been wrong in the other direction: the daemon
# deduplicates by SHA-256 and correctly writes no new line for a file it
# already holds, so an unchanged probe would start failing spuriously.
if [ "$R_WRITE" = PASS ]; then
  say "Waiting up to 60s for nufi-ingest to embed it"
  t_ing=$(date +%s); i=0
  while [ "$i" -lt 12 ]; do
    line="$(box 'logs --no-log-prefix nufi-ingest' 2>/dev/null | sh -c "$INGEST_CMD" _ "$PROBE")"
    [ -n "$line" ] && break
    i=$((i + 1)); sleep 5
  done
  T_INGEST=$(( $(date +%s) - t_ing ))
  if [ -n "$line" ]; then
    R_INGEST=PASS; ok "${T_INGEST}s: $(printf '%s' "$line" | tr -d '\r')"
  else
    box 'logs --no-log-prefix --tail 10 nufi-ingest' 2>&1 | sed 's/^/    /' >&2
    warn "nufi-ingest never logged embedded=True for $PROBE"
  fi
else
  warn "skipping the ingest check: $PROBE never reached the drive"
fi

# --- the department agent, asked from home ------------------------------------
say "Asking the Legal agent from the member's laptop (run_box.py --only legal)"
t_a=$(date +%s)
DC exec -T tools-a sh -c '
set -eu
. /lab/keys/box-admin.env
# The evidence directory goes first. tools-a survives a run that ended with
# --keep or was killed before the trap, and a box.md left in it would be read
# as this run in exactly the way a stale probe file was.
rm -rf /tmp/home/evidence
mkdir -p /tmp/home/drives /tmp/home/evidence
python3 /lab/scenarios/run_box.py \
  --base "https://'"$BOX_MESH_HOST"':3080" \
  --email "$ADMIN_EMAIL" --password "$ADMIN_PASSWORD" \
  --drives /tmp/home/drives --only legal \
  --cacert /lab/keys/nufi-box-ca.crt --timeout 300 \
  --out /tmp/home/evidence' 2>&1 | sed 's/^/    /'
T_AGENT=$(( $(date +%s) - t_a ))
# `$CITED_CMD` is the whole verdict, so it is worth being exact about. run_box.py
# renders one `  - sources: ...` line per question and writes the literal
# `sources: none` when an answer carried no citation at all
# (deploy/platform/scenarios/run_box.py: `', '.join(q['sources']) or 'none'`).
# A check that merely looks for a non-empty `sources:` line therefore passes on
# the exact case it exists to catch. Drop the `none` lines first and require
# something to be left.
cited="$(DC exec -T tools-a sh -c "$CITED_CMD" _ /tmp/home/evidence/box.md 2>/dev/null)"
if [ -n "$cited" ]; then
  R_AGENT=PASS; ok "an answer carried a citation — the drive reached the agent (${T_AGENT}s)"
  printf '%s\n' "$cited" | sed 's/^ *- /    /'
else
  warn "not one answer cited a file — every 'sources:' line is 'none', so the agent never read the drive"
fi

# --- and a routine ------------------------------------------------------------
# Bounded, because a routine that never returns is a failure mode this box
# really has: with no cap on the generation, a small model that never emits a
# stop token rambles for as long as anything will listen. run_flows.py's own
# socket timeout does not save you — the job keeps running on the box after the
# client has gone.
run_routine() {  # run_routine <flow id> <budget seconds> -> prints the output
  local flow="$1" budget="$2" tries=$(( $2 / 5 ))
  DC exec -T tools-a sh -c '
set -u
STUDIO_API_KEY=$(cat /lab/keys/studio-api.key); export STUDIO_API_KEY
python3 /lab/scenarios/studio/run_flows.py \
  --base "https://'"$BOX_MESH_HOST"':7860" \
  --flows /lab/scenarios/studio/flows.json --only '"$flow"' \
  --cacert /lab/keys/nufi-box-ca.crt &
pid=$!
i=0
while [ $i -lt '"$tries"' ]; do
  kill -0 $pid 2>/dev/null || break
  sleep 5; i=$((i + 1))
done
if kill -0 $pid 2>/dev/null; then
  kill $pid 2>/dev/null
  echo "NO ANSWER within '"$budget"'s"
fi
wait $pid 2>/dev/null || true' 2>&1
}

say "Running the $ROUTINE routine through the mesh (run_flows.py --only $ROUTINE)"
t_w=$(date +%s)
routine_out="$(run_routine "$ROUTINE" "$ROUTINE_BUDGET")"
T_ROUTINE=$(( $(date +%s) - t_w ))
printf '%s\n' "$routine_out" | sed 's/^/    /'
# `ok` or `DRIFT` both mean Studio ran the flow and gave back text over the
# mesh; DRIFT is the model finishing a Korean sentence in Chinese, which is the
# model's problem and is reported, not hidden. Both are read off the whole
# printed line (see ROUTINE_LINE_RE), never as a substring of the output.
if routine_said "$ROUTINE" "$routine_out"; then
  R_ROUTINE=PASS; ok "the routine answered over the mesh (${T_ROUTINE}s)"
else
  case "$routine_out" in
    *"NO ANSWER"*)
      warn "$ROUTINE returned nothing in ${ROUTINE_BUDGET}s"
      # Two very different reasons a routine can time out. Ask the box which one
      # it is before running anything else: if ollama is still generating for the
      # run whose client we just killed, that is a finding in itself -- the job
      # outlived the client -- and it also explains why everything after it is
      # slow, which would otherwise read as a mesh fault and is not one.
      say "Is the box still generating for the run whose client was just killed?"
      gen1="$(box 'logs --no-log-prefix --tail 40 ollama' 2>/dev/null | grep -a 'n_gen' | tail -1)"
      sleep 10
      gen2="$(box 'logs --no-log-prefix --tail 40 ollama' 2>/dev/null | grep -a 'n_gen' | tail -1)"
      printf '    %s\n' "${gen1:-<no generation in the log>}" "${gen2:-<no generation in the log>}"
      if [ -n "$gen2" ] && [ "$gen1" != "$gen2" ]; then
        warn "yes — the token count is still climbing with nothing listening"
        note "the abandoned $ROUTINE run outlived its client and still holds the model, so every other routine queues behind it (watch the control's time below against the seconds it takes on an idle box)"
      fi
      # Which half is broken? `meeting` is the cheapest routine the box has --
      # one prompt, no drive -- so if it answers over the same connection, the
      # mesh is not what is wrong. It is run whether or not the model is still
      # busy, because how LONG it takes is itself the evidence for the line above.
      say "Control: the same Studio, same key, same mesh, running 'meeting' instead"
      ctl="$(run_routine meeting 180)"
      printf '%s\n' "$ctl" | sed 's/^/    /'
      if routine_said meeting "$ctl"; then
        note "$ROUTINE did not finish in ${ROUTINE_BUDGET}s but 'meeting' answered over the same mesh — the mesh is fine and the routine is not"
      else
        note "neither $ROUTINE nor the 'meeting' control answered — if the model was still busy above, that is why; otherwise suspect Studio over the mesh"
      fi ;;
    *) warn "the $ROUTINE routine did not return text over the mesh" ;;
  esac
fi
routine_drifted "$ROUTINE" "$routine_out" \
  && note "the $ROUTINE answer drifted into Han characters — the box's model, not the mesh"

fi  # R_JOIN

# ---------- the table ---------------------------------------------------------
T_TOTAL=$(( $(date +%s) - T_START ))
echo
printf '  %-18s %s\n' "check" "result"
printf '  %-18s %s\n' "------------------" "------"
printf '  %-18s %s\n' "box-on-mesh"       "$R_JOIN"
printf '  %-18s %s\n' "path"              "$R_PATH ($OBSERVED_PATH)"
printf '  %-18s %s\n' "health-over-mesh"  "$R_HTTP"
printf '  %-18s %s\n' "login-over-mesh"   "$R_LOGIN"
printf '  %-18s %s\n' "drive-write"       "$R_WRITE"
printf '  %-18s %s\n' "drive-ingested"    "$R_INGEST$([ "$T_INGEST" -ge 0 ] && printf ' (%ss)' "$T_INGEST")"
printf '  %-18s %s\n' "agent-cites-drive" "$R_AGENT"
printf '  %-18s %s\n' "routine-$ROUTINE" "$R_ROUTINE"
echo
printf '  relay forced | lab up %ss | box up + joined %ss | agent %ss | routine %ss | total %ss\n' \
  "$T_LAB" "$T_BOX" "$T_AGENT" "$T_ROUTINE" "$T_TOTAL"
[ -n "$NOTES" ] && printf '\n  notes:%s\n' "$NOTES"
echo

for r in "$R_JOIN" "$R_PATH" "$R_HTTP" "$R_LOGIN" "$R_WRITE" "$R_INGEST" "$R_AGENT" "$R_ROUTINE"; do
  [ "$r" = PASS ] || die "the day at home did not pass"
done
ok "PASS — a member at home can do the day's work"
