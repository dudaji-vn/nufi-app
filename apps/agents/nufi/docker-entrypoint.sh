#!/bin/sh
#
# Own the data volume, then hand over to upstream's entrypoint unchanged.
#
# Installed AS /usr/local/bin/docker-entrypoint.sh, with upstream's moved to
# upstream-docker-entrypoint.sh. That keeps the image's ENTRYPOINT and CMD
# exactly as upstream declared them -- see nufi/Dockerfile for why declaring
# ENTRYPOINT here would break the start command.
#
# Upstream chowns /paperclip only when a UID remap was requested:
#
#     if [ "$changed" = "1" ]; then
#         chown -R node:node /paperclip
#     fi
#     exec gosu node "$@"
#
# On a platform that bind-mounts the volume as root and needs no remap --
# Railway, among others -- `changed` stays 0, nothing is chowned, and the
# server drops to `node` over a root-owned mount. It then dies at import time:
#
#     Error: EACCES: permission denied, mkdir '/paperclip/instances/default/logs'
#
# Build-time ownership does not help, because a bind mount replaces whatever
# the image had at that path.
#
# So fix it here, while we are still root. Guarded on the current owner so the
# recursive chown is a first-boot cost rather than a per-restart one.
set -e

HOME_DIR="${PAPERCLIP_HOME:-/paperclip}"

if [ "$(id -u)" -eq 0 ] && [ -d "$HOME_DIR" ]; then
  want="$(id -u node)"
  have="$(stat -c %u "$HOME_DIR" 2>/dev/null || echo "$want")"
  if [ "$have" != "$want" ]; then
    echo "nufi-entrypoint: taking ownership of $HOME_DIR for uid $want"
    chown -R node:node "$HOME_DIR"
  fi
fi

exec upstream-docker-entrypoint.sh "$@"
