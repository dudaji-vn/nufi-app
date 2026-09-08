#!/bin/sh
# Trust the box CA (Caddy's internal root) system-wide, then start Studio.
# Caddy writes the root on first boot; compose orders studio after caddy is healthy.
set -eu
ROOT=/caddy/caddy/pki/authorities/local/root.crt
if [ -f "$ROOT" ]; then
  if command -v update-ca-certificates >/dev/null 2>&1; then
    cp "$ROOT" /usr/local/share/ca-certificates/nufi-box.crt
    update-ca-certificates >/dev/null 2>&1 || true
  else
    # No update-ca-certificates in this image: append the root straight into
    # the bundle SSL_CERT_FILE/REQUESTS_CA_BUNDLE point at.
    cat "$ROOT" >> /etc/ssl/certs/ca-certificates.crt
  fi
else
  echo "studio-entrypoint: box CA not found at $ROOT; JWKS over https will fail" >&2
fi
exec langflow run --host 0.0.0.0 --port "${PORT:-7860}"
