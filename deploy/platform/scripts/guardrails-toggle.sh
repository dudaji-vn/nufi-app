#!/usr/bin/env bash
# Flip NuFi security between enforcing and logging_only, restart the gateway,
# and prove the gateway agrees.
#
#   ./scripts/guardrails-toggle.sh off      # every control -> logging_only
#   ./scripts/guardrails-toggle.sh on       # back to the documented deploy state
#   ./scripts/guardrails-toggle.sh status   # policy.yaml vs what the gateway runs
#
# `off` means logging_only, not `enabled: false`: every control keeps scanning
# and auditing, it just never blocks or redacts. A disabled mandatory control
# (G1, G4) logs ERROR on each boot and is what guardrails/health.py exists to
# catch, so that switch is left alone. Scanner latency therefore stays.
#
# policy.yaml is bind-mounted read-only into litellm-proxy, so an edit plus a
# restart is enough -- nothing here needs a rebuild. Run it from the checkout
# that runs the stack: docker-compose.yml carries `name: npuops`, so the
# restart lands on the live project wherever the checkout sits.
set -uo pipefail

CONTROLS=(G1 G2a G2b G3 G4)
# The state docs/2026-08-03-deploy-develop-to-production.md calls correct
# after a deploy. A change here needs the same change in
# tests/test_guardrails_toggle.py.
ENFORCING_MODES=(G1=pre_call G2a=logging_only G2b=post_call G3=post_call G4=post_call)
SHADOW_MODES=(G1=logging_only G2a=logging_only G2b=logging_only G3=logging_only G4=logging_only)

PROXY="${PROXY_URL:-http://localhost:4000}"
METRICS="${PROXY_METRICS:-${PROXY}/metrics/}"   # trailing slash: bare /metrics is a 307 with an empty body
POLICY="litellm/guardrails/policy.yaml"

die() { echo "guardrails-toggle: $*" >&2; exit 1; }

# policy_modes <file> -> "<control> <mode>" per control, in file order.
policy_modes() {
  awk '
    /^controls:/ { in_controls = 1; next }
    /^[^ #]/     { in_controls = 0 }
    in_controls && /^  [A-Za-z0-9_]+:[[:space:]]*$/ { ctrl = $1; sub(/:$/, "", ctrl) }
    in_controls && ctrl != "" && /^    mode:[[:space:]]*/ { print ctrl, $2 }
  ' "$1"
}

# set_modes <file> <on|off>: rewrite the `mode:` line of every control, in
# place, touching nothing else. Refuses -- and leaves the file as it was --
# when the file names a control this script does not know or lacks one it
# does: either way "off" would leave something enforcing.
set_modes() {
  local file=$1 state=$2 wanted tmp
  case "${state}" in
    on)  wanted="${ENFORCING_MODES[*]}" ;;
    off) wanted="${SHADOW_MODES[*]}" ;;
    *)   die "set_modes: expected on|off, got '${state}'" ;;
  esac
  tmp=$(mktemp) || die "mktemp failed"
  if ! awk -v wanted="${wanted}" '
    BEGIN {
      n = split(wanted, pairs, " ")
      for (i = 1; i <= n; i++) { split(pairs[i], kv, "="); want[kv[1]] = kv[2] }
    }
    /^controls:/ { in_controls = 1; print; next }
    /^[^ #]/     { in_controls = 0 }
    in_controls && /^  [A-Za-z0-9_]+:[[:space:]]*$/ { ctrl = $1; sub(/:$/, "", ctrl) }
    in_controls && ctrl != "" && /^    mode:[[:space:]]*/ {
      if (!(ctrl in want)) { unknown = unknown " " ctrl; print; next }
      sub(/mode:[[:space:]]*[A-Za-z_]+/, "mode: " want[ctrl])
      seen[ctrl]++
    }
    { print }
    END {
      for (c in want) if (!(c in seen)) missing = missing " " c
      if (unknown != "") printf "unknown control(s) in policy:%s\n", unknown > "/dev/stderr"
      if (missing != "") printf "control(s) missing from policy:%s\n", missing > "/dev/stderr"
      if (unknown != "" || missing != "") exit 1
    }
  ' "${file}" > "${tmp}"; then
    rm -f "${tmp}"
    die "refusing to rewrite ${file}"
  fi
  # Copied over, not renamed over: the container holds this file as a bind
  # mount, and a rename would swap the inode out from under it.
  cat "${tmp}" > "${file}" || die "could not write ${file}"
  rm -f "${tmp}"
}

# live_enabled -> "<control> <1|0|->" per control from the gateway's own
# nufi_guardrail_enabled gauge (1 = enabled AND enforcing). "-" is an absent
# series: the control never loaded, which is not the same thing as 0.
live_enabled() {
  local scrape c v
  if ! scrape=$(curl -fsS "${METRICS}" 2>/dev/null); then
    for c in "${CONTROLS[@]}"; do echo "${c} -"; done
    return 1
  fi
  for c in "${CONTROLS[@]}"; do
    v=$(printf '%s\n' "${scrape}" | awk -v c="${c}" '
      index($0, "nufi_guardrail_enabled{") == 1 && index($0, "control=\"" c "\"") { print $NF; exit }')
    case "${v}" in
      1|1.0) echo "${c} 1" ;;
      0|0.0) echo "${c} 0" ;;
      *)     echo "${c} -" ;;
    esac
  done
}

# check_live: the gateway must report exactly what policy.yaml says. Prints
# one line per control; returns non-zero on any mismatch or absent series.
check_live() {
  local live modes bad=0 c mode want got mark
  live=$(live_enabled)
  modes=$(policy_modes "${POLICY}")
  printf '    %-5s %-13s %s\n' control policy.yaml gateway
  for c in "${CONTROLS[@]}"; do
    mode=$(printf '%s\n' "${modes}" | awk -v c="${c}" '$1 == c { print $2 }')
    got=$(printf '%s\n' "${live}" | awk -v c="${c}" '$1 == c { print $2 }')
    want=1; [ "${mode}" = "logging_only" ] && want=0
    if [ "${got}" = "${want}" ]; then mark=ok; else mark=MISMATCH; bad=1; fi
    printf '    %-5s %-13s enabled=%-2s %s\n' "${c}" "${mode:-?}" "${got}" "${mark}"
  done
  [ "${bad}" -eq 0 ]
}

restart_and_wait() {
  echo "==> docker compose restart litellm-proxy"
  docker compose restart litellm-proxy || die "restart failed"
  for _ in $(seq 1 45); do
    curl -fsS "${PROXY}/health/liveliness" >/dev/null 2>&1 && return 0
    sleep 2
  done
  die "litellm-proxy not live at ${PROXY} after 90s -- see: docker compose logs litellm-proxy"
}

summary() {
  local modes enforcing
  modes=$(policy_modes "${POLICY}")
  enforcing=$(printf '%s\n' "${modes}" | awk '$2 != "logging_only" { out = out (out ? " " : "") $1 } END { print out }')
  if [ -z "${enforcing}" ]; then
    echo "!!! NuFi security is OFF: every control is logging_only, nothing is blocked or redacted."
    echo "!!! Turn it back on with: ./scripts/guardrails-toggle.sh on"
  else
    echo "==> NuFi security is ON: enforcing ${enforcing}"
  fi
}

usage() {
  sed -n '2,7p' "$0" | sed 's/^# \{0,1\}//'
  exit 2
}

main() {
  cd "$(dirname "$0")/.." || exit 1
  [ -f "${POLICY}" ] || die "${POLICY} not found"
  local state=${1:-} before after report
  case "${state}" in
    on|off)
      before=$(policy_modes "${POLICY}")
      set_modes "${POLICY}" "${state}"
      after=$(policy_modes "${POLICY}")
      if [ "${before}" = "${after}" ]; then
        echo "==> policy.yaml already '${state}'"
        if report=$(check_live); then
          echo "==> gateway agrees, nothing to restart"
          echo "${report}"
          summary
          exit 0
        fi
        echo "==> gateway disagrees with policy.yaml (edited without a restart?)"
      else
        echo "==> policy.yaml rewritten"
      fi
      restart_and_wait
      echo "==> gateway reports"
      check_live || die "gateway does not match policy.yaml -- see: docker compose logs litellm-proxy"
      summary
      ;;
    status)
      check_live
      local rc=$?
      summary
      exit "${rc}"
      ;;
    *) usage ;;
  esac
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  main "$@"
fi
