#!/usr/bin/env bash
#
# Falsify the containment claim.
#
# A flow whose model node is deliberately pointed at a vendor must FAIL. If it
# succeeds, the egress policy is not in force and every statement we make
# about governed model traffic is wrong for this deployment. Passing proves
# the chokepoint; not running it proves nothing, and a green badge on the
# other checks does not substitute.
#
# This script does not build confidence — it tries to destroy it. Read the
# result as: "I tried to break out and could not," not "I checked a box."
#
# WHY A VENDOR CALL, NOT A POLICY DESCRIBE
# ------------------------------------------
# `kubectl describe cnp` proves a CiliumNetworkPolicy object exists in etcd.
# It does not prove Cilium is installed, that the policy's endpointSelector
# actually matches the running pod's labels, or that an earlier, broader
# policy (e.g. a leftover standard-mode NetworkPolicy, or a second
# CiliumNetworkPolicy someone added later) isn't unioned on top and quietly
# reopening the vendor. The only evidence that means anything is a network
# call attempted from inside the pod itself.
#
# WHAT COUNTS AS A PASS
# ----------------------
# curl exits non-zero (connection refused, timed out, TLS failure, DNS
# failure, ...) -- the vendor was unreachable at the network layer. That is
# the pass condition, inverted from what a normal healthcheck wants: here,
# failing to reach api.openai.com is success.
#
# curl exiting zero means TCP+TLS to the vendor succeeded and an HTTP
# response came back -- ANY response, not just a 2xx. Without an API key,
# api.openai.com/v1/models legitimately answers 401, not 200; that 401 still
# proves the connection went through, which is exactly the failure this
# script exists to catch. So this script treats curl exit 0 as a hard
# failure regardless of status code, and additionally calls out a 2xx
# specifically per the brief this script was written against, since a 2xx
# is the least ambiguous possible proof the vendor was reached.
#
# WHY EXEC INTO THE RUNNING POD, NOT A FRESH PROBE POD
# -------------------------------------------------------
# A separately-launched probe pod only proves the *namespace* is confined if
# its labels happen to match the policy's endpointSelector -- easy to get
# subtly wrong. Exec'ing into the actual NuFi Agent pod removes that
# variable: whatever labels it already carries are definitionally the ones
# the policy must be matching (or failing to match).
#
# Usage: apps/nufi-agent/nufi/egress/verify-egress.sh <namespace> [pod-label-selector]
#
#   <namespace>            Namespace the NuFi Agent pod runs in. Required.
#   [pod-label-selector]   kubectl label selector for the NuFi Agent pod.
#                          Default: app.kubernetes.io/name=nufi-agent -- must
#                          match networkpolicy.yaml's endpointSelector. If
#                          that file's selector was changed to match a real
#                          deployment, pass the matching selector here too.
#
# Example:
#   apps/nufi-agent/nufi/egress/verify-egress.sh nufi-agent
#   apps/nufi-agent/nufi/egress/verify-egress.sh nufi-agent app=nufi-agent-web
set -euo pipefail

NS="${1:?usage: verify-egress.sh <namespace> [pod-label-selector]}"
POD_LABEL_SELECTOR="${2:-app.kubernetes.io/name=nufi-agent}"

GATEWAY="api.codechi.me"
VENDOR="api.openai.com"
VENDOR_PATH="/v1/models"

echo "Finding a running NuFi Agent pod in namespace '$NS' (selector: $POD_LABEL_SELECTOR)…"
POD=$(kubectl -n "$NS" get pod -l "$POD_LABEL_SELECTOR" \
  --field-selector=status.phase=Running \
  -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)

if [ -z "$POD" ]; then
  echo "FAIL: no running pod in namespace '$NS' matches selector '$POD_LABEL_SELECTOR'."
  echo "      Check the namespace is right, the deployment is up, and that"
  echo "      POD_LABEL_SELECTOR matches the real pod's labels (and matches"
  echo "      networkpolicy.yaml's endpointSelector -- they must agree)."
  exit 1
fi
echo "  using pod: $POD"

probe() {
  # $1 = host, $2 = path (may be empty)
  local host="$1" path="${2:-/}"
  kubectl -n "$NS" exec "$POD" -- \
    curl -sS -o /dev/null -w '%{http_code}' --max-time 10 "https://${host}${path}" 2>/dev/null
}

fail=0

echo
echo "Sanity check: is the gateway itself reachable? (if not, a blocked vendor"
echo "call would prove nothing -- it could mean the pod has no network at all)"
gw_code=$(probe "$GATEWAY" "/" || echo "000")
echo "  $GATEWAY -> ${gw_code:-000}"
if [ -z "$gw_code" ] || [ "$gw_code" = "000" ]; then
  echo "FAIL: $GATEWAY is unreachable from the pod. This run cannot conclude"
  echo "      anything about containment -- fix connectivity to the gateway"
  echo "      first (DNS rule in networkpolicy.yaml, the FQDN rule itself,"
  echo "      or the gateway being up) and re-run."
  fail=1
fi

echo
echo "Falsification attempt: curling $VENDOR directly, as a flow author could"
echo "by typing it into an advanced 'API Base' field on any provider node."
set +e
kubectl -n "$NS" exec "$POD" -- \
  curl -sS --max-time 10 "https://${VENDOR}${VENDOR_PATH}"
curl_exit=$?
set -e

if [ "$curl_exit" -ne 0 ]; then
  echo
  echo "  curl exit code: $curl_exit (network-level failure -- expected)"
  echo "PASS: $VENDOR was unreachable from the pod. The egress policy held."
else
  echo
  echo "  curl exit code: 0 -- an HTTP response came back from $VENDOR."
  echo "FAIL: $VENDOR is reachable. The chokepoint does NOT exist for this"
  echo "      deployment -- every claim that NuFi Agent's model traffic is"
  echo "      confined to the gateway is false here. Check: is the"
  echo "      CiliumNetworkPolicy actually applied in namespace '$NS'"
  echo "      (kubectl -n $NS get cnp)? Does its endpointSelector really"
  echo "      match this pod's labels (kubectl -n $NS get pod $POD --show-labels)?"
  echo "      Is Cilium the active CNI on this cluster at all, or is this a"
  echo "      cluster still running the plain-NetworkPolicy fallback that"
  echo "      cannot express FQDNs? Do not mark egress containment as done"
  echo "      until this prints PASS."
  fail=1
fi

echo
if [ "$fail" -eq 0 ]; then
  echo "PASS: only the gateway is reachable from the NuFi Agent pod."
else
  echo "FAIL: see above. Fix the cluster, not this script."
fi
exit "$fail"
