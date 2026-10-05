#!/bin/sh
# Bun does not honour NODE_EXTRA_CA_CERTS for fetch(); it reads SSL_CERT_FILE.
# Build one bundle = system roots + the self-hosted coordinator CA (if any), so
# minting invites against an internal-CA coordinator verifies. In the container
# the CA is mounted at /mesh-ca.crt (= NODE_EXTRA_CA_CERTS); MESH_CA_FILE wins
# when set explicitly.
cat /etc/ssl/certs/ca-certificates.crt "${MESH_CA_FILE:-${NODE_EXTRA_CA_CERTS:-/dev/null}}" > /tmp/ca-bundle.crt 2>/dev/null
export SSL_CERT_FILE=/tmp/ca-bundle.crt
exec bun run src/server.ts
