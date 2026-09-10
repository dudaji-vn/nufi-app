#!/bin/bash
# run-ubuntu-install.sh — install a NuFi box on a blank Ubuntu 24.04 VM and time it.
#
#   REGISTRY=192.168.1.26:5001 deploy/box/tests/vm/run-ubuntu-install.sh
#
# The acceptance the README's "Ubuntu 24.04: needs curl and openssl, the
# installer brings Docker" claim rests on. The VM (lima-ubuntu.yaml) has no
# Docker, no checkout and no host mount, so the two things a real customer box
# without GitHub access has are the only two channels used here: a tarball of
# this repo (`git archive` + `limactl copy`) and a registry on the LAN.
#
# Prints the wall time of the single install command and exits non-zero if the
# banner never appears.
#
#   REGISTRY   host:port of a registry holding the six NuFi images (required;
#              `make -C deploy/box registry-up registry-push` builds one)
#   VM         lima instance name (default nufi-ubuntu)
#   DEPARTMENTS, INFERENCE_PROFILE, INFERENCE_MODEL, EMBEDDINGS_MODEL
#              passed to the installer; the defaults are the smallest models
#              that exercise the whole path on a CPU-only VM.
set -euo pipefail

VM="${VM:-nufi-ubuntu}"
REGISTRY="${REGISTRY:-}"
DEPARTMENTS="${DEPARTMENTS:-legal}"
INFERENCE_PROFILE="${INFERENCE_PROFILE:-ollama-docker}"
INFERENCE_MODEL="${INFERENCE_MODEL:-qwen2.5:0.5b}"
EMBEDDINGS_MODEL="${EMBEDDINGS_MODEL:-bge-m3}"
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../../../.." && pwd)"

say() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m xx\033[0m %s\n' "$*" >&2; exit 1; }

[ -n "$REGISTRY" ] || die "REGISTRY=<host:port> is required (see the header)"
command -v limactl >/dev/null || die "limactl is required: brew install lima"

say "Checking the registry $REGISTRY"
curl -fsS --max-time 10 "http://$REGISTRY/v2/_catalog" | grep -q nufichat \
  || die "$REGISTRY does not serve the NuFi images: make -C deploy/box registry-up registry-push REGISTRY=$REGISTRY"

if ! limactl list "$VM" >/dev/null 2>&1; then
  say "Creating the blank Ubuntu VM $VM (first run downloads the image)"
  limactl start --name "$VM" "$HERE/lima-ubuntu.yaml" --tty=false
elif [ "$(limactl list "$VM" --format '{{.Status}}')" != "Running" ]; then
  say "Starting $VM"
  limactl start "$VM" --tty=false
fi

say "Copying this checkout into $VM as a tarball (no GitHub, no host mount)"
TAR="$(mktemp -t nufi-box-XXXXXX).tar"
git -C "$ROOT" archive -o "$TAR" HEAD \
  deploy/box deploy/platform/scenarios deploy/platform/adapters/nufi-ingest docs
limactl copy "$TAR" "$VM:box.tar"
rm -f "$TAR"
limactl shell "$VM" -- bash -lc 'rm -rf ~/deploy && tar xf ~/box.tar -C ~'

say "Installing (one command, timed)"
START=$(date +%s)
set +e
# pipefail, or `| tee` reports its own success as the installer's and a failed
# install looks like a clean one.
limactl shell "$VM" -- bash -lc "set -o pipefail; cd \$HOME/deploy/box && \
  DEPARTMENTS='$DEPARTMENTS' INFERENCE_PROFILE='$INFERENCE_PROFILE' \
  INFERENCE_MODEL='$INFERENCE_MODEL' EMBEDDINGS_MODEL='$EMBEDDINGS_MODEL' \
  ./install-box.sh --yes --registry '$REGISTRY' 2>&1 | tee \$HOME/install.log"
rc=$?
set -e
END=$(date +%s)
SECS=$((END - START))

say "Install returned $rc after $((SECS / 60)) min $((SECS % 60)) s"
# Every path into the guest goes through bash -lc: a bare `~` or $HOME in a
# `limactl shell` argument is expanded by the Mac's shell, not the guest's.
limactl shell "$VM" -- bash -lc 'grep -q "is up\." $HOME/install.log' \
  || die "no banner in ~/install.log — the install did not finish"
[ "$rc" = 0 ] || die "the installer exited $rc"
limactl shell "$VM" -- bash -lc 'free -h; df -h / | tail -1'
printf '\n  blank Ubuntu 24.04 (4 vCPU, 8 GB): %d min %d s from first command to banner\n' \
  "$((SECS / 60))" "$((SECS % 60))"
