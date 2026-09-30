#!/bin/bash
# Build the de-branded NufiBox Agent binaries for Windows. Like the Linux build,
# the tailscale engine (BSD-3) is compiled HERE at build time and shipped under
# nufibox names; unlike Linux/macOS this is a SCAFFOLD — see README-windows.md
# for what is proven (the cross-compile) and what still needs a Windows machine
# (wintun runtime, service registration, the .msi, and EV/Azure-Trusted-Signing).
#
#   ./build-agent-windows.sh            # -> dist/nufibox-agent-windows-amd64.zip
#   ARCH=arm64 ./build-agent-windows.sh
#
# Cross-compiles from macOS/Linux with Go (CGO off); no Windows host needed to
# PRODUCE the binaries. Packaging them into a signed .msi does need Windows.
set -euo pipefail

TS_VERSION="${TS_VERSION:-1.102.3}"
ARCH="${ARCH:-amd64}"          # amd64 | arm64
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="${OUT:-$HERE/dist}"

command -v go >/dev/null 2>&1 || { echo "go is required (brew install go)"; exit 1; }
command -v zip >/dev/null 2>&1 || { echo "zip is required"; exit 1; }

work="$(mktemp -d)"; trap 'rm -rf "$work"' EXIT
mod="$work/mod"; mkdir -p "$mod"
( cd "$mod"
  go mod init nufibox-agent-win >/dev/null
  echo "==> pinning tailscale.com@v$TS_VERSION"
  go get "tailscale.com/cmd/tailscaled@v$TS_VERSION" "tailscale.com/cmd/tailscale@v$TS_VERSION"
)

stage="$work/nufibox-agent"; mkdir -p "$stage"
echo "==> cross-compiling the de-branded engine for windows/$ARCH (CGO off)"
( cd "$mod"
  CGO_ENABLED=0 GOOS=windows GOARCH="$ARCH" go build -o "$stage/nufibox-tailscaled.exe" tailscale.com/cmd/tailscaled
  CGO_ENABLED=0 GOOS=windows GOARCH="$ARCH" go build -o "$stage/nufibox-tailscale.exe"  tailscale.com/cmd/tailscale
)
cp "$HERE/nufibox-agent.ps1" "$stage/nufibox-agent.ps1"

mkdir -p "$OUT"
out="$OUT/nufibox-agent-windows-${ARCH}.zip"
rm -f "$out"
( cd "$work" && zip -qr "$out" nufibox-agent )
echo "==> wrote $out ($(du -h "$out" | cut -f1))"
echo
echo "NEXT (needs a Windows machine — see README-windows.md):"
echo "  * confirm the .exe drives a wintun interface and registers as a service"
echo "  * package as a signed .msi (WiX) or signed installer"
echo "  * sign with an EV or Azure Trusted Signing certificate"
