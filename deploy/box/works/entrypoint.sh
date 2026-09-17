#!/bin/sh
# Trust the box CA, then start Works exactly as its image would.
#
# Works runs as uid 1000 (see docker-compose.yml: the docker group has to
# survive upstream's entrypoint), and Caddy keeps its PKI directory 0700
# root -- so the CA cannot be read off the caddy volume the way Studio,
# which runs as root, reads it. Caddy serves the same certificate over
# plain HTTP on :80 to every laptop; this container fetches it the same
# way. compose orders works after caddy is healthy, so :80 answers.
#
# The private key never enters this container: only the public root.
set -eu
CA=/tmp/nufi-box-ca.crt
i=0
until curl -fsS -o "$CA" http://caddy/nufi-box-ca.crt; do
  i=$((i+1)); [ "$i" -lt 30 ] || { echo "works-entrypoint: could not fetch the box CA from caddy; SSO to the console will fail" >&2; break; }
  sleep 2
done
# The start command is the image's CMD (apps/agents/Dockerfile) repeated
# here, because overriding ENTRYPOINT resets CMD; keep the two in step.
exec /usr/local/bin/docker-entrypoint.sh node --import ./server/node_modules/tsx/dist/loader.mjs server/dist/index.js
