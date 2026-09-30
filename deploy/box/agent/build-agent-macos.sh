#!/bin/bash
# Build the NufiBox Agent for macOS as a SIGNED, NOTARIZED .pkg — the member
# installs one thing, sees no "Tailscale", and Gatekeeper raises no warning.
#
# Like the Linux build, the tailscale engine (BSD-3) is fetched/built HERE, at
# build time, and shipped under nufibox names. This runs on a Mac with the Go
# toolchain, the Dudaji Developer ID certs in the keychain, and (to notarize) a
# stored notarytool profile. It is the reference for the eventual CI signing
# job; nothing here runs on the box or the member's machine.
#
#   ./build-agent-macos.sh                 # build + sign + notarize + staple
#   NOTARIZE=0 ./build-agent-macos.sh      # build + sign only (skip notarize)
#
# Env overrides: TS_VERSION, APP_ID, INSTALLER_ID, NOTARY_PROFILE, OUT.
set -euo pipefail

TS_VERSION="${TS_VERSION:-1.102.3}"
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="${OUT:-$HERE/dist}"
PKG_ID="vn.dudaji.nufibox-agent"
TEAM_ID="Z52QH9UXD8"
APP_ID="${APP_ID:-Developer ID Application: Dudaji Vn ($TEAM_ID)}"
INSTALLER_ID="${INSTALLER_ID:-Developer ID Installer: Dudaji Vn ($TEAM_ID)}"
NOTARY_PROFILE="${NOTARY_PROFILE:-nufibox-notary}"
NOTARIZE="${NOTARIZE:-1}"
PKG="$OUT/nufibox-agent-macos.pkg"

command -v go >/dev/null 2>&1 || { echo "go is required (brew install go)"; exit 1; }
security find-identity -v -p codesigning | grep -q "$APP_ID"   || { echo "missing signing identity: $APP_ID"; exit 1; }
security find-identity -v | grep -q "$INSTALLER_ID"            || { echo "missing installer identity: $INSTALLER_ID"; exit 1; }

work="$(mktemp -d)"; trap 'rm -rf "$work"' EXIT
gobin="$work/gobin"; mkdir -p "$gobin"

# --- build the de-branded engine, universal (arm64 + amd64) -----------------
# CGO off so the build is hermetic and cross-compiles cleanly; the darwin
# resolver falls back to pure Go, which is what we want for an appliance client.
# A throwaway module pins the tailscale version, then `go build -o` builds each
# arch (go install can't cross-compile with GOBIN set; go build -o can).
mod="$work/mod"; mkdir -p "$mod"
( cd "$mod"
  go mod init nufibox-agent-build >/dev/null
  echo "==> pinning tailscale.com@v$TS_VERSION (records go.sum for both commands)"
  # get the COMMAND packages, not just the root module, so every transitive
  # go.sum entry needed to build them is recorded before the cross-builds.
  go get "tailscale.com/cmd/tailscaled@v$TS_VERSION" "tailscale.com/cmd/tailscale@v$TS_VERSION"
)
build_arch() {  # $1 = GOARCH
  local a="$1"; mkdir -p "$gobin/$a"
  echo "==> building tailscaled/tailscale for darwin/$a"
  ( cd "$mod"
    CGO_ENABLED=0 GOOS=darwin GOARCH="$a" go build -o "$gobin/$a/tailscaled" tailscale.com/cmd/tailscaled
    CGO_ENABLED=0 GOOS=darwin GOARCH="$a" go build -o "$gobin/$a/tailscale"  tailscale.com/cmd/tailscale
  )
}
build_arch arm64
build_arch amd64

stage="$work/stage"
bindst="$stage/usr/local/bin"
lddst="$stage/Library/LaunchDaemons"
mkdir -p "$bindst" "$lddst"

echo "==> lipo -> universal binaries"
lipo -create "$gobin/arm64/tailscaled" "$gobin/amd64/tailscaled" -output "$bindst/nufibox-tailscaled"
lipo -create "$gobin/arm64/tailscale"  "$gobin/amd64/tailscale"  -output "$bindst/nufibox-tailscale"
cp "$HERE/nufibox-agent" "$bindst/nufibox-agent"
cp "$HERE/nufibox-agent.plist" "$lddst/vn.dudaji.nufibox-agent.plist"
chmod 0755 "$bindst"/* ; chmod 0644 "$lddst"/*.plist

# --- sign the Mach-O binaries (hardened runtime + secure timestamp) ---------
# Required for notarization. The wrapper is a shell script — not Mach-O — so it
# is not codesigned; notarization only inspects executable code.
for b in nufibox-tailscaled nufibox-tailscale; do
  echo "==> codesign $b"
  codesign --force --options runtime --timestamp --sign "$APP_ID" "$bindst/$b"
  codesign --verify --strict --verbose=2 "$bindst/$b"
done

# --- build + sign the installer package -------------------------------------
# Note: pkgbuild emits AppleDouble `._*` entries in the payload (the standard
# encoding for a file's xattrs/ACLs) and a few benign "write: Permission
# denied" lines during bundle inference. The Installer applies those entries as
# metadata on the real files — they are NOT installed as literal `._*` files —
# so this is expected and harmless.
mkdir -p "$OUT"
scripts="$HERE/macos-scripts"
chmod 0755 "$scripts/postinstall"
echo "==> pkgbuild (signed with Developer ID Installer)"
pkgbuild --root "$stage" --scripts "$scripts" \
  --identifier "$PKG_ID" --version "$TS_VERSION" \
  --install-location / \
  --sign "$INSTALLER_ID" --timestamp \
  "$PKG"
echo "==> wrote $PKG ($(du -h "$PKG" | cut -f1))"

if [ "$NOTARIZE" != 1 ]; then
  echo "==> NOTARIZE=0 — signed but not notarized (Gatekeeper will still warn on first open)."
  pkgutil --check-signature "$PKG" | head -8
  exit 0
fi

# --- notarize + staple ------------------------------------------------------
echo "==> submitting to Apple notary service (this waits for the verdict)"
xcrun notarytool submit "$PKG" --keychain-profile "$NOTARY_PROFILE" --wait
echo "==> stapling the notarization ticket (so it verifies OFFLINE — air-gap safe)"
xcrun stapler staple "$PKG"

echo "==> verification"
xcrun stapler validate "$PKG"
pkgutil --check-signature "$PKG" | head -8
spctl -a -vvv -t install "$PKG" 2>&1 || true
echo "==> done: $PKG"
