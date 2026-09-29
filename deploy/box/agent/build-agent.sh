#!/bin/bash
# Build the NufiBox Agent bundle for Linux: fetch the pinned tailscale static
# binaries (BSD-3), ship them under nufibox names alongside the wrapper,
# install.sh and the systemd unit, as ONE tarball a member installs. The fetch
# happens here at build time, so at INSTALL time there is no tailscale.com — the
# box serves this tarball itself.
#
#   ARCH=arm64 ./build-agent.sh        # -> dist/nufibox-agent-linux-arm64.tar.gz
#
# TS_VERSION is kept in step with docker-compose.mesh.yml's tailscale image.
set -euo pipefail
TS_VERSION="${TS_VERSION:-1.102.3}"
ARCH="${ARCH:-amd64}"                       # amd64 | arm64
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="${OUT:-$HERE/dist}"

work="$(mktemp -d)"; trap 'rm -rf "$work"' EXIT
tgz="tailscale_${TS_VERSION}_${ARCH}.tgz"
echo "==> fetching https://pkgs.tailscale.com/stable/$tgz"
curl -fsSL "https://pkgs.tailscale.com/stable/$tgz" -o "$work/$tgz"
tar -xzf "$work/$tgz" -C "$work"
src="$work/tailscale_${TS_VERSION}_${ARCH}"
[ -x "$src/tailscaled" ] && [ -x "$src/tailscale" ] || { echo "tailscaled/tailscale not in $tgz" >&2; exit 1; }

stage="$work/nufibox-agent"
mkdir -p "$stage/bin"
cp "$src/tailscaled" "$stage/bin/nufibox-tailscaled"   # de-branded: our name, BSD-3 engine
cp "$src/tailscale"  "$stage/bin/nufibox-tailscale"
cp "$HERE/nufibox-agent" "$stage/bin/nufibox-agent"
cp "$HERE/install.sh" "$stage/install.sh"
cp "$HERE/nufibox-agent.service" "$stage/nufibox-agent.service"
chmod +x "$stage/bin/"* "$stage/install.sh"

mkdir -p "$OUT"
out="$OUT/nufibox-agent-linux-${ARCH}.tar.gz"
tar -C "$work" -czf "$out" nufibox-agent
echo "==> wrote $out ($(du -h "$out" | cut -f1))"
