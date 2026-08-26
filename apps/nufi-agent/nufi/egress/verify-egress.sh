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
# THREE OUTCOMES, NOT TWO
# -------------------------
# A naive read of "curl failed" as "the network blocked it" is a false-green
# waiting to happen: `curl` can also fail because it never ran at all —
# missing from the image, `pods/exec` denied by RBAC, or the exec transport
# itself breaking — and none of those says anything about whether the egress
# policy works. Collapsing that into the same "PASS" bucket as a genuine
# network block is exactly the false containment claim this script exists to
# prevent, and it's the kind of bug nobody running this script would notice
# without reading the fine print. So every probe is classified into one of
# three buckets, never two:
#
#   reached      curl exited 0 -- TCP+TLS (and an HTTP exchange) succeeded.
#   blocked      curl ran and failed for a network-layer reason (DNS,
#                connection refused/reset, TLS, timeout, ...). Curl's own
#                documented exit codes are all below 126 (see `man curl`,
#                EXIT CODES) and none of curl's own failure modes produce
#                the specific stderr text `kubectl exec` prints when it
#                could not launch the remote process at all -- so "not
#                `reached`, not one of the exec-layer signatures below" is
#                what `blocked` means.
#   inconclusive curl (or kubectl exec itself) never actually ran the probe:
#                exit code >= 126 (126 = "found but not executable", 127 =
#                "command not found" -- POSIX shell/exec-layer conventions,
#                never a code curl itself returns), or stderr carries a
#                recognizable exec/RBAC-layer failure signature (missing
#                binary, exec transport upgrade failure, RBAC denial, pod
#                not found). This is the case a naive nonzero-exit check
#                would misreport as a PASS.
#
# An `inconclusive` classification NEVER prints PASS and always makes the
# script exit non-zero, distinctly from FAIL (see exit codes below), naming
# the missing prerequisite so the reader fixes the harness, not the cluster.
#
# WHAT COUNTS AS A PASS ON THE VENDOR PROBE
# --------------------------------------------
# `blocked` -- the vendor was unreachable at the network layer. That is the
# pass condition, inverted from what a normal healthcheck wants: here,
# failing to reach api.openai.com is success.
#
# `reached` is always a hard FAIL, regardless of HTTP status code. Without an
# API key, api.openai.com/v1/models legitimately answers 401, not 200; that
# 401 still proves the TCP+TLS connection went through, which is exactly the
# failure this script exists to catch. So `reached` fails on curl exit 0
# alone -- it does not require a 2xx -- while still calling out a 2xx
# specifically in the failure message, since a 2xx is the least ambiguous
# possible proof the vendor was reached.
#
# WHY EXEC INTO THE RUNNING POD, NOT A FRESH PROBE POD
# -------------------------------------------------------
# A separately-launched probe pod only proves the *namespace* is confined if
# its labels happen to match the policy's endpointSelector -- easy to get
# subtly wrong. Exec'ing into the actual NUFI Studio pod removes that
# variable: whatever labels it already carries are definitionally the ones
# the policy must be matching (or failing to match).
#
# EXIT CODES
# -----------
#   0   PASS         only the gateway is reachable; vendor call was blocked.
#   1   FAIL         the vendor was reached, or the gateway itself was not
#                     (either way, a real result was obtained and it's bad).
#   2   INCONCLUSIVE the probe itself could not run to completion -- fix the
#                     harness (image, RBAC, exec transport) and re-run. Never
#                     read a 2 as a pass.
#
# Usage: apps/nufi-agent/nufi/egress/verify-egress.sh <namespace> [pod-label-selector]
#
#   <namespace>            Namespace the NUFI Studio pod runs in. Required.
#   [pod-label-selector]   kubectl label selector for the NUFI Studio pod.
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

echo "Finding a running NUFI Studio pod in namespace '$NS' (selector: $POD_LABEL_SELECTOR)…"
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
echo "  prerequisite this script cannot check for you: curl must be present"
echo "  inside this pod's image, or every probe below reports inconclusive."

# probe HOST PATH -- runs curl inside $POD via kubectl exec. Sets three
# globals: PROBE_EXIT (the exit code), PROBE_CODE (HTTP status if curl
# reached the server, empty otherwise), PROBE_STDERR (combined kubectl+curl
# stderr, for classifying an inconclusive result).
probe() {
  local host="$1" path="$2" stderr_file
  stderr_file=$(mktemp)
  set +e
  PROBE_CODE=$(kubectl -n "$NS" exec "$POD" -- \
    curl -sS -o /dev/null -w '%{http_code}' --max-time 10 "https://${host}${path}" 2>"$stderr_file")
  PROBE_EXIT=$?
  set -e
  PROBE_STDERR=$(cat "$stderr_file")
  rm -f "$stderr_file"
}

# classify EXIT_CODE STDERR_TEXT -- prints one of: reached | blocked | inconclusive
#
# Known imprecision, deliberately not fixed here: curl's own internal init
# failures (exit codes 1-5 -- unsupported protocol, failed init, malformed
# URL, not built-in, couldn't resolve proxy) fall through the checks below
# into the "blocked" bucket, not "inconclusive", even though they mean the
# probe never really attempted the network call at all. This is harmless in
# practice only because of this script's call ORDER, not because the bucket
# is right: the gateway sanity probe always runs before the vendor
# falsification attempt (see below), so a curl-internal failure hits the
# gateway probe first and prints FAIL ("fix connectivity") rather than
# silently letting a mis-classified vendor probe read as PASS. If a future
# change ever probed the vendor without probing the gateway first, this
# imprecision would stop being harmless.
classify() {
  local exit_code="$1" stderr_text="$2"
  if [ "$exit_code" -eq 0 ]; then
    echo "reached"
    return
  fi
  # curl's own documented exit codes are all < 126 (`man curl`, EXIT CODES).
  # 126/127 are POSIX shell/exec-layer conventions ("found but not
  # executable" / "command not found") that curl itself never returns --
  # seeing one here means the container never launched curl at all.
  if [ "$exit_code" -ge 126 ]; then
    echo "inconclusive"
    return
  fi
  case "$stderr_text" in
    *"executable file not found"*|*"OCI runtime exec failed"*|*"unable to start container process"*|*"unable to upgrade connection"*|*"error: unable to upgrade connection"*|*"exit code 127"*|*"exit code 126"*|*[Ff]orbidden*|*[Uu]nauthorized*|*"not found"*"pods"*|*"pods"*"not found"*)
      echo "inconclusive" ;;
    *)
      echo "blocked" ;;
  esac
}

report_inconclusive() {
  local label="$1" host="$2"
  echo
  echo "  curl exit code: $PROBE_EXIT"
  [ -n "$PROBE_STDERR" ] && echo "  stderr: $PROBE_STDERR"
  echo "INCONCLUSIVE: could not determine whether $host is reachable ($label)."
  echo "      The probe itself did not run to completion -- this is NOT a"
  echo "      PASS and NOT a FAIL, it is a broken harness. Likely causes:"
  echo "      curl missing from the pod's image, 'kubectl exec' denied by"
  echo "      RBAC (pods/exec), or the exec transport failing outright."
  echo "      Fix the harness and re-run -- do not interpret this as"
  echo "      containment either way."
}

echo
echo "Sanity check: is the gateway itself reachable? (if not, a blocked vendor"
echo "call would prove nothing -- it could mean the pod has no network at all)"
probe "$GATEWAY" "/"
gw_outcome=$(classify "$PROBE_EXIT" "$PROBE_STDERR")
echo "  $GATEWAY -> exit=$PROBE_EXIT code=${PROBE_CODE:-<none>} ($gw_outcome)"

case "$gw_outcome" in
  inconclusive)
    report_inconclusive "gateway sanity check" "$GATEWAY"
    exit 2
    ;;
  blocked)
    echo "FAIL: $GATEWAY is unreachable from the pod. This run cannot conclude"
    echo "      anything about containment -- fix connectivity to the gateway"
    echo "      first (DNS rule in networkpolicy.yaml, the FQDN rule itself,"
    echo "      or the gateway being up) and re-run."
    exit 1
    ;;
  reached)
    : # good, continue to the falsification attempt
    ;;
esac

echo
echo "Falsification attempt: curling $VENDOR directly, as a flow author could"
echo "by typing it into an advanced 'API Base' field on any provider node."
probe "$VENDOR" "$VENDOR_PATH"
vendor_outcome=$(classify "$PROBE_EXIT" "$PROBE_STDERR")
echo "  $VENDOR -> exit=$PROBE_EXIT code=${PROBE_CODE:-<none>} ($vendor_outcome)"

case "$vendor_outcome" in
  inconclusive)
    report_inconclusive "vendor falsification attempt" "$VENDOR"
    exit 2
    ;;
  reached)
    echo
    echo "FAIL: $VENDOR is reachable (HTTP ${PROBE_CODE:-<unknown>}). The"
    echo "      chokepoint does NOT exist for this deployment -- every claim"
    echo "      that NUFI Studio's model traffic is confined to the gateway is"
    echo "      false here. A 2xx would be the least ambiguous proof of this,"
    echo "      but any status code (${PROBE_CODE:-<unknown>} included) means"
    echo "      TCP+TLS to the vendor succeeded, which is already the failure."
    echo "      Check: is the CiliumNetworkPolicy actually applied in"
    echo "      namespace '$NS' (kubectl -n $NS get cnp)? Does its"
    echo "      endpointSelector really match this pod's labels"
    echo "      (kubectl -n $NS get pod $POD --show-labels)? Is Cilium the"
    echo "      active CNI on this cluster at all, or is this a cluster"
    echo "      still running the plain-NetworkPolicy fallback that cannot"
    echo "      express FQDNs? Do not mark egress containment as done until"
    echo "      this prints PASS."
    exit 1
    ;;
  blocked)
    echo
    echo "PASS: only the gateway is reachable from the NUFI Studio pod."
    exit 0
    ;;
esac
