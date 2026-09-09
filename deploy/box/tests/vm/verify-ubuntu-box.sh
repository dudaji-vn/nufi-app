#!/bin/bash
# verify-ubuntu-box.sh — the other half of the acceptance run-ubuntu-install.sh
# starts. That script proves a blank machine reaches the banner; this one
# proves the box the banner announced actually works, and it checks it the way
# a colleague would: from the Mac, over the LAN, against the box's own CA.
#
#   deploy/box/tests/vm/verify-ubuntu-box.sh          # after run-ubuntu-install.sh
#
# Three things, in the order a customer meets them:
#   1. the CA comes out of the box and /health answers over TLS
#   2. a document dropped in a department drive reaches the agent (embedded=True)
#   3. that department's agent answers a question about it, with a citation
#
# Exits non-zero only when the box is broken. A judge verdict is NOT a failure
# here: the model is whatever the box was installed with, and the smallest one
# it offers (qwen2.5:0.5b) gets some of these wrong. The answers are printed in
# full so the reader judges the model; the script judges the box.
set -uo pipefail

VM="${VM:-nufi-ubuntu}"
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../../../.." && pwd)"
WORK="$(mktemp -d -t nufi-box-verify-XXXXXX)"
trap 'rm -rf "$WORK"' EXIT

say() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m xx\033[0m %s\n' "$*" >&2; exit 1; }

command -v limactl >/dev/null || die "limactl is required: brew install lima"
# Every command into the guest goes through `bash -lc`: a bare ~ or $HOME in a
# limactl argument is expanded by the Mac's shell, not the guest's. And every
# docker command goes through `sg docker`, because limactl reuses one SSH
# session and that session is older than the docker group the installer made.
vm() { limactl shell "$VM" -- bash -lc "$1"; }
box() { vm "cd \$HOME/deploy/box && sg docker -c 'docker compose $1'"; }

# ---------- 1. reach the box from the Mac ------------------------------------
say "The addresses the box has, and the one it put in the banner"
vm "ip -4 -o addr show scope global | awk '{print \$2, \$4}'"
vm 'sed -n "/is up\./,/Day two/p" $HOME/install.log' || die "no banner in ~/install.log"

# The banner's IP is the first `hostname -I` prints, which on a machine with
# two networks need not be the one anybody can reach — see the README's
# troubleshooting table. The name is on the certificate either way, so pin it.
# 192.168.64.0/24 is Virtualization.framework's NAT, the one vzNAT puts the
# guest on and the only one of the VM's addresses the Mac can route to: eth0 is
# Lima's user-mode NAT (which is what the banner picks) and 172.1[78] is
# Docker's own bridge.
ADDRS=$(vm "ip -4 -o addr show scope global | awk '{print \$4}' | cut -d/ -f1")
IP=$(printf '%s\n' "$ADDRS" | grep '^192\.168\.64\.' | head -1)
[ -n "$IP" ] || die "no vzNAT (192.168.64.x) address on $VM; it has: $(echo $ADDRS)"
say "Reaching the box on $IP"

limactl copy "$VM:deploy/box/data/nufi-box-ca.crt" "$WORK/ca.crt" \
  || die "the box did not export its CA to data/nufi-box-ca.crt"
openssl x509 -in "$WORK/ca.crt" -noout -subject

CURL=(curl -sS --max-time 30 --cacert "$WORK/ca.crt" --resolve "nufi.local:3080:$IP")
CODE=$("${CURL[@]}" -o "$WORK/health" -w '%{http_code}' "https://nufi.local:3080/health")
[ "$CODE" = 200 ] || die "https://nufi.local:3080/health answered $CODE, not 200"
say "/health over TLS from the Mac: $CODE $(cat "$WORK/health")"

# ---------- 2. a drive becomes knowledge -------------------------------------
# The same document run_box.py asks about, carried as base64 so no shell and no
# transfer step has to be trusted with its Korean filename.
python3 - "$ROOT" "$WORK" <<'PY'
import base64, json, pathlib, sys
root, out = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
depts = json.load(open(root / "deploy/platform/scenarios/departments.json"))["departments"]
doc = next(d for d in depts if d["id"] == "legal")["documents"][0]
(out / "name.b64").write_text(base64.b64encode(doc["name"].encode()).decode())
(out / "text.b64").write_text(base64.b64encode(doc["text"].encode()).decode())
print(f'  document: {doc["name"]} ({len(doc["text"])} chars)')
PY
DOC_NAME=$(printf %s "$(cat "$WORK/name.b64")" | base64 -d)

say "Dropping it into data/drives/legal"
# `|| die`, and then the file is checked on the drive. Without both, a write
# that failed (the drive owned by another uid is exactly the acceptance's D1)
# fell through to an ingest check that matched an EARLIER run's log line, and
# the pair read as a pass on a re-used VM. This document cannot be made unique
# per run the way day-at-home.sh's probe is — step 3 asks the agent about this
# particular contract — so the write is gated instead, and the log match is
# only ever confirmation that this named file is embedded, never a stand-in
# for the write having happened.
vm "set -e
    N=\$(printf %s '$(cat "$WORK/name.b64")' | base64 -d)
    printf %s '$(cat "$WORK/text.b64")' | base64 -d > \"\$HOME/deploy/box/data/drives/legal/\$N\"" \
  || die "could not write the document to data/drives/legal — is the drive owned by the Samba uid? (nufi-box doctor)"
vm "test -s \"\$HOME/deploy/box/data/drives/legal/$DOC_NAME\"" \
  || die "the document is not on the box's legal drive after the write"

say "Waiting for nufi-ingest to embed it (up to 5 minutes)"
# Matched on the whole log, not a recent window: the daemon keys on the file's
# hash and correctly writes no new line for a document it already holds, so a
# time filter would fail spuriously on the second run. Anchored to this file's
# name rather than to `legal/`, so an unrelated document someone left on the
# drive cannot answer for it.
EMBEDDED=""
for _ in $(seq 1 60); do
  EMBEDDED=$(box "logs --no-log-prefix nufi-ingest 2>&1" \
             | grep -a 'embedded=True' | grep -aF -e "legal/$DOC_NAME" | tail -1)
  [ -n "$EMBEDDED" ] && break
  sleep 5
done
[ -n "$EMBEDDED" ] || {
  box "logs --no-log-prefix --tail 30 nufi-ingest 2>&1"
  die "nufi-ingest never logged embedded=True for legal/$DOC_NAME"
}
say "$EMBEDDED"

# ---------- 3. the agent answers about it ------------------------------------
LOGIN=$(vm 'grep -a "Admin login:" $HOME/install.log | tail -1')
EMAIL=$(printf '%s' "$LOGIN" | sed -E 's#.*Admin login: *([^ ]+) */ *([^ ]+).*#\1#')
PASS=$(printf '%s' "$LOGIN" | sed -E 's#.*Admin login: *([^ ]+) */ *([^ ]+).*#\2#')
[ -n "$PASS" ] || die "could not read the admin login out of ~/install.log"

say "Asking the Legal agent, as $EMAIL, through https://nufi.local:3080"
mkdir -p "$WORK/drives"
# run_box.py's own verdicts are the model's report card, not the box's, so its
# exit status is deliberately not this script's.
(cd "$ROOT/deploy/platform/scenarios" && python3 run_box.py \
  --base https://nufi.local:3080 --email "$EMAIL" --password "$PASS" \
  --drives "$WORK/drives" --only legal --timeout 300 \
  --cacert "$WORK/ca.crt" --connect-to "nufi.local:3080:$IP:3080" \
  --out "$WORK/evidence") || true

# The same predicate day-at-home.sh ships as CITED_CMD, and for the same
# reason: run_box.py writes the literal `sources: none` for an answer that
# cited nothing (`', '.join(q['sources']) or 'none'`), so `sources: .*[^ ]`
# matched the exact case this check exists to catch. Drop the `none` lines
# first and require something to be left.
CITED=$(grep "sources:" "$WORK/evidence/box.md" 2>/dev/null | grep -v "sources: none$")
[ -n "$CITED" ] \
  || die "not one answer carried a citation — every 'sources:' line is 'none', so the agent never read the drive"
say "Cited:"
printf '%s\n' "$CITED" | sed 's/^ *- /    /'
say "Answers (the model's, verbatim — judge verdicts included)"
cat "$WORK/evidence/box.md"
printf '\n  the box works: TLS from the Mac, drive → embedded=True, and a cited answer\n'
