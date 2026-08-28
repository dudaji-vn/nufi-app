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

# Register the NuFi adapter.
#
# `nufi_agent` is an external adapter, which means the server only loads it if
# it is named in $PAPERCLIP_HOME/adapter-plugins.json -- a file that lives on
# the data volume, not in the image. Without it the instance comes up with the
# fourteen upstream built-ins and no way to reach the NuFi gateway, and the
# omission is silent: nothing errors, `nufi_agent` is simply absent from the
# adapter list when someone tries to create an employee.
#
# Written here rather than by hand on the volume so it survives a redeploy and
# a fresh volume. Existing records are left alone: this only adds the entry
# when it is missing, so an operator who disabled or edited it keeps their
# change.
STORE="$HOME_DIR/adapter-plugins.json"
ADAPTER_PATH="/app/nufi/adapter"
RECORD='{"packageName":"@nufi/paperclip-adapter","localPath":"/app/nufi/adapter","type":"nufi_agent","installedAt":"1970-01-01T00:00:00.000Z"}'

if [ -d "$ADAPTER_PATH/dist" ]; then
  if [ ! -s "$STORE" ]; then
    echo "nufi-entrypoint: registering nufi_agent adapter in $STORE"
    mkdir -p "$HOME_DIR"
    printf '[%s]\n' "$RECORD" > "$STORE"
  elif ! jq -e 'map(select(.type == "nufi_agent")) | length > 0' "$STORE" >/dev/null 2>&1; then
    # Merge rather than replace. Anything an operator installed through the
    # Plugins page also lives in this file, and overwriting it would silently
    # uninstall their adapters on the next deploy.
    echo "nufi-entrypoint: adding nufi_agent to existing $STORE"
    if jq --argjson rec "$RECORD" '. + [$rec]' "$STORE" > "$STORE.tmp" 2>/dev/null; then
      mv "$STORE.tmp" "$STORE"
    else
      echo "nufi-entrypoint: WARNING could not parse $STORE; leaving it untouched" >&2
      rm -f "$STORE.tmp"
    fi
  fi
  [ "$(id -u)" -eq 0 ] && [ -f "$STORE" ] && chown node:node "$STORE"
fi

exec upstream-docker-entrypoint.sh "$@"
