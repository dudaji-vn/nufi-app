#!/bin/sh
# The egress allow list, rendered to stdout as tinyproxy's filter file: one
# host per line, exact-match (FilterExtended Off in the config that reads it).
#
# Two hosts are always here and are not the operator's to remove: the Works
# server the sandbox reports back to, and the gateway the model is reached
# through. Everything else comes from WORKS_EGRESS_ALLOW in .env, comma-
# separated bare hostnames -- no scheme, no path, no port, no glob, no
# address. A sandbox is a place untrusted code runs; the list of where it may
# talk to is not a place to be generous with syntax.
#
# The model host can never be added. A sandbox that reaches Ollama directly is
# a sandbox outside the gateway's rate limits, budgets and guardrails, and the
# gateway is on this list precisely so that it does not have to be.
set -eu

ALWAYS="works litellm-proxy"
# Names the model is served under on the box, in any spelling an operator
# might try. The gateway (litellm-proxy) is the way to it.
MODEL_HOSTS="ollama host.docker.internal"

echo "# rendered by works-egress/render.sh from WORKS_EGRESS_ALLOW; do not edit"
for h in $ALWAYS; do echo "$h"; done

seen=" $ALWAYS "
IFS=','
for raw in ${WORKS_EGRESS_ALLOW:-}; do
  h=$(printf '%s' "$raw" | tr -d '[:space:]')
  [ -n "$h" ] || continue
  # Strip trailing :port before checking model hosts
  port_stripped=${h%%:*}
  IFS=' '
  for m in $MODEL_HOSTS; do
    if [ "$port_stripped" = "$m" ]; then
      echo "WORKS_EGRESS_ALLOW: $raw is the model host; a sandbox reaches the model through the gateway (litellm-proxy), not directly" >&2; exit 2
    fi
  done
  IFS=','
  # A hostname: labels of [a-z0-9-], joined by dots, nothing else.
  case "$h" in
    *://*|*/*|*:*|*'*'*|*'?'*)
      echo "WORKS_EGRESS_ALLOW: not a bare hostname: $raw" >&2; exit 2 ;;
  esac
  if ! printf '%s' "$h" | grep -Eq '^[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?)*$'; then
    echo "WORKS_EGRESS_ALLOW: not a bare hostname: $raw" >&2; exit 2
  fi
  if printf '%s' "$h" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$'; then
    echo "WORKS_EGRESS_ALLOW: not a bare hostname (an address): $raw" >&2; exit 2
  fi
  case "$seen" in *" $h "*) continue ;; esac
  seen="$seen$h "
  echo "$h"
done
