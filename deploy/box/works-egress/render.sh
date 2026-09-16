#!/bin/sh
# The egress allow list, rendered to stdout as tinyproxy's filter file: one
# host per line, exact-match (FilterType fnmatch in the config that reads it).
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
# -f: the operator list is split on commas below, and a glob in it must
# reach the validator as text, not as a directory listing.
set -euf

ALWAYS="works litellm-proxy"
# Names the model host answers to on a box, in any spelling an operator
# might try, plus the box's own name (BOX_HOST serves the model on its own
# port on an ollama-profile box) and the proxy itself. The gateway
# (litellm-proxy) is the way to the model.
box_host=$(printf '%s' "${BOX_HOST:-}" | tr 'A-Z' 'a-z')
MODEL_HOSTS="ollama host.docker.internal gateway.docker.internal localhost works-egress ${box_host}"

echo "# rendered by works-egress/render.sh from WORKS_EGRESS_ALLOW; do not edit"
for h in $ALWAYS; do echo "$h"; done

seen=" $ALWAYS "
nl=$(printf '\nx'); nl=${nl%x}
IFS=','
for raw in ${WORKS_EGRESS_ALLOW:-}; do
  # Lowercased: the filter that reads this is case-sensitive and DNS is not.
  h=$(printf '%s' "$raw" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//' | tr 'A-Z' 'a-z')
  [ -n "$h" ] || continue
  # grep below validates one line at a time; an entry carrying a newline
  # would pass on its first line and smuggle its second, unvalidated, in.
  case "$h" in *"$nl"*) echo "WORKS_EGRESS_ALLOW: not a bare hostname (contains a newline): $raw" >&2; exit 2 ;; esac
  # Strip trailing :port before checking model hosts
  port_stripped=${h%%:*}
  # MODEL_HOSTS is space-separated; with the outer loop's IFS=',' it would never split and no model host would ever be refused.
  IFS=' '
  for m in $MODEL_HOSTS; do
    if [ "$port_stripped" = "$m" ]; then
      echo "WORKS_EGRESS_ALLOW: $raw is the model host; a sandbox reaches the model through the gateway (litellm-proxy), not directly" >&2; exit 2
    fi
  done
  IFS=','
  # A hostname: labels of [a-z0-9-], joined by dots, nothing else.
  case "$h" in
    *://*|*/*|*:*|*'*'*|*'?'*|*' '*|*'	'*)
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
