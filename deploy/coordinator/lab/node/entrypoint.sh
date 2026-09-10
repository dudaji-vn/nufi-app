#!/bin/sh
# Wrapper around the tailscale image's own `containerboot`.
#
# Two things have to happen before tailscaled starts, and neither can be
# expressed in compose:
#
#   1. The default route has to leave through this LAN's NAT router instead of
#      the docker bridge gateway. Without it the node would reach the
#      coordinator directly on the bridge and there would be no NAT to
#      traverse — the whole point of the lab.
#   2. The pre-auth key has to come off disk. run.sh mints it *after* the
#      coordinator is up, long after compose rendered this service, so it
#      arrives as a file in the mounted keys/ directory rather than as an
#      environment variable.
#
#   LAB_DEFAULT_GW    this LAN's router, e.g. 10.10.0.2
#   LAB_AUTHKEY_FILE  file holding the pre-auth key (default /lab/<hostname>.key)
#
# Everything else is containerboot's own contract: TS_AUTHKEY, TS_EXTRA_ARGS,
# TS_USERSPACE, TS_ACCEPT_DNS, TS_STATE_DIR (all confirmed present in
# containerboot v1.102.3).
set -eu

log() { printf '[node %s] %s\n' "${TS_LAB_NAME:-?}" "$*"; }

: "${LAB_DEFAULT_GW:?LAB_DEFAULT_GW is required}"
LAB_AUTHKEY_FILE="${LAB_AUTHKEY_FILE:-/lab/${TS_LAB_NAME:-node}.key}"

# ip route replace is iproute2; the tailscale image ships busybox's `ip`, whose
# `route replace` is a no-op on some builds, so do it the long way.
ip route del default 2>/dev/null || true
ip route add default via "$LAB_DEFAULT_GW"
log "default route via $LAB_DEFAULT_GW"

# The coordinator's TLS is Caddy's internal CA in the lab. Go honours
# SSL_CERT_FILE (crypto/x509 root_unix.go reads $SSL_CERT_FILE in place of the
# system bundle), which is how tailscaled trusts it — compose sets that. Also
# drop the root into the system store so anything non-Go in this container
# (busybox wget, ssl_client) trusts it too.
if [ -n "${SSL_CERT_FILE:-}" ] && [ -s "${SSL_CERT_FILE}" ]; then
  mkdir -p /usr/local/share/ca-certificates
  cp "$SSL_CERT_FILE" /usr/local/share/ca-certificates/nufi-coordinator.crt
  update-ca-certificates >/dev/null 2>&1 || true
  log "trusting $SSL_CERT_FILE"
else
  log "WARNING: no coordinator CA at ${SSL_CERT_FILE:-<unset>}"
fi

# A pre-auth key is a secret; it is passed as a file so it never shows up in
# `docker inspect` or the compose render.
if [ -z "${TS_AUTHKEY:-}" ] && [ -s "$LAB_AUTHKEY_FILE" ]; then
  TS_AUTHKEY="$(cat "$LAB_AUTHKEY_FILE")"
  export TS_AUTHKEY
  log "pre-auth key read from $LAB_AUTHKEY_FILE"
fi

exec /usr/local/bin/containerboot
