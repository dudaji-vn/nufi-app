# Gateway egress for NuFi Agent

## Status: NOT RUN — needs a human

**Gateway containment for NuFi Agent is a claim, not a measurement, until
`verify-egress.sh` has run against a real cluster and printed `PASS`.** There
is no Kubernetes cluster, no Cilium, and no NuFi Agent deployment available in
the environment this was authored in. Nothing in this directory has been
executed. See "Running the verification" below for the exact commands and
what to do with the result.

Three earlier guards in this fork (`check-fork-diff.sh`, `check-brand-css.sh`,
`check-locale-parity.sh`) shipped only after someone had watched them fail and
then pass. This one could not even be attempted here — read every "PASS"
claim below as "PASS is what this is designed to print," not as "this
printed PASS."

## Why this exists

`docs/2026-08-10-nufi-agent-langflow-fork.md` §4 measured that Langflow ships
an SSRF allowlist (`ssrf_allowed_hosts`, `is_host_allowed()` in
`src/lfx/src/lfx/utils/ssrf_protection.py`, with a protected client in
`ssrf_httpx.py`) that looks like a ready-made gateway chokepoint and is not
one:

- Only bundles making raw `httpx` calls route through it — `lmstudio`,
  `chroma`, `clickhouse`, `homeassistant`.
- The real provider components call LangChain SDKs, which bring their own
  HTTP client and never touch the protected transport.
- Where a base URL *is* settable, it's a per-node field a flow author types
  into — e.g. `openai_api_base` in
  `src/bundles/openai/src/lfx_openai/components/openai/openai.py:41`,
  declared `advanced=True` but not locked.
- There are 71 provider bundles. Patching all of them to force a gateway base
  URL is the fat fork this entire plan exists to avoid.

**Consequence: the network egress boundary is not the second layer of
defence for NuFi Agent's model traffic. It is the only one.** An unverified
claim about the only layer of defence is worse than no claim, which is why
this directory exists and why Step 4 below is not optional.

## The citation that shapes the policy shape — verified against this repo

The essential prior art for this task,
`docs/superpowers/plans/2026-08-04-nufi-agents-remaining-phases.md` (Task 4
and Task 5), records this fact with a source citation:

> `packages/plugins/sandbox-providers/kubernetes/src/network-policy.ts:8-16`
> states that standard Kubernetes NetworkPolicy cannot express FQDNs, and
> that when `allowFqdns` is set without explicit CIDRs it falls back to
> "public IPv4 except RFC1918/link-local/loopback/multicast" — the whole
> internet.

**This was checked against the actual file in this repo, not taken on
faith.** `apps/agents/packages/plugins/sandbox-providers/kubernetes/src/
network-policy.ts` lines 8–16 (as of this task) read:

```
 * Adapter-configured FQDNs (e.g. `api.anthropic.com`). Standard
 * NetworkPolicy cannot express FQDNs natively — only Cilium can.
 * When this list is non-empty AND no explicit `egressAllowCidrs`
 * was provided, the standard NetworkPolicy falls back to "public
 * IPv4 except RFC1918/link-local/loopback/multicast" so the
 * configured FQDNs at least become reachable. This is broader
 * than the operator probably wants — switch to `egressMode:
 * "cilium"` for exact FQDN allow-listing in production.
```

**The citation checks out.** Same claim, same file, same line range. The
`PRIVATE_AND_LINK_LOCAL_EXCEPT_CIDRS` list a few lines below it
(`network-policy.ts:25-34`) confirms the fallback really is "all public IPv4
minus RFC1918/CGNAT/link-local/loopback/this-network/multicast" — i.e. the
entire public internet minus the ranges nobody wants reachable anyway.

**Consequence for this task:** a plain `networking.k8s.io/v1` NetworkPolicy
naming `api.codechi.me` would either (a) not compile as a host match at all
(stock NetworkPolicy has no FQDN selector), or (b) if built the way the
`kubernetes` sandbox provider's *standard* mode does — falling back to the
broad public-IPv4 CIDR carve-out to make the named FQDN reachable — would
permit essentially the whole internet while *looking* like it names one
host. That is worse than shipping nothing, because it reads as containment
in a diff review. `networkpolicy.yaml` in this directory is therefore a
`cilium.io/v2` **CiliumNetworkPolicy**, not a `networking.k8s.io/v1`
`NetworkPolicy` — see the header comment in that file for the full reasoning
and the manifest itself, which mirrors the known-good shape in
`apps/agents/packages/plugins/sandbox-providers/kubernetes/src/
cilium-network-policy.ts` (DNS resolution rule + a single `toFQDNs` rule).

## What's in this directory

| File | What it does |
|---|---|
| `networkpolicy.yaml` | A `CiliumNetworkPolicy` scoping the NuFi Agent pod's egress to cluster DNS plus `api.codechi.me:443`, and nothing else. Namespace is left unset in the manifest — apply with `kubectl apply -n <namespace> -f networkpolicy.yaml`. The pod selector (`app.kubernetes.io/name: nufi-agent`) is a naming assumption, not read off a real Deployment manifest, because none exists in this repo yet — see the file's header comment. |
| `verify-egress.sh` | Tries to break the containment claim from inside a running NuFi Agent pod: curls `api.codechi.me` (must succeed, or the run is inconclusive) and `api.openai.com` (must fail, or the chokepoint doesn't exist). Inverted-logic pass/fail, matching a falsification test rather than a healthcheck. |
| `README.md` | This file. |

## Running the verification

Requires: a Kubernetes cluster with Cilium installed as the CNI, a NuFi Agent
pod deployed and labeled to match `networkpolicy.yaml`'s `endpointSelector`,
this `CiliumNetworkPolicy` applied in that pod's namespace, and `kubectl`
configured against that cluster.

```bash
kubectl apply -n <nufi-agent-namespace> -f apps/nufi-agent/nufi/egress/networkpolicy.yaml
apps/nufi-agent/nufi/egress/verify-egress.sh <nufi-agent-namespace>
```

Expected output on success:

```
PASS: only the gateway is reachable from the NuFi Agent pod.
```

If it prints `FAIL`, read the message — it names the specific thing to check
next (policy actually applied, selector actually matching, Cilium actually
the active CNI rather than a plain-NetworkPolicy fallback). **Fix the
cluster, not the script.** None of this has been run in the environment this
task was completed in; running it, reading the result, and recording the
date and outcome here (or in the design doc's phase tracker) is a follow-up
a human with cluster access has to do before "NuFi Agent's model traffic is
gateway-confined" is said as a fact rather than a design intention.

## What this does and does not cover

**This constrains where traffic can go. It does not constrain what a flow
does with the access it's given once traffic is allowed to leave.** The
egress policy is a network-layer boundary around the pod, not an
application-layer audit of flow behavior. Two concrete gaps that follow
directly from that:

1. **A flow with a database or git component still has whatever access its
   own credentials carry, and the gateway sees none of it.** If a flow
   author wires in a Postgres component pointed at a real production
   database, or a component that clones and pushes to a git remote, this
   policy neither blocks that connection (it's not model traffic, and
   `api.codechi.me` isn't in the path) nor logs it anywhere the gateway's
   observability covers. `docs/2026-08-03-nufi-agent-app-design.md` §10
   raises the identical gap for Paperclip/`apps/agents` — "Agents get a git
   workspace... Egress control answers 'which model did it call', not 'what
   did it commit'. Scoping those credentials is Phase 1 work that this
   document does not yet specify" — and it is still open there. It is open
   here too, for the same reason: this task scopes model-traffic egress
   only, not credential scoping for every other component type Langflow
   ships (there are far more than 71 non-provider bundles with network or
   filesystem access — database connectors, HTTP request nodes, the
   `homeassistant`/`chroma`/`clickhouse` bundles the SSRF allowlist does
   cover, git-adjacent tooling, and so on).

2. **What happens to the 71 provider bundles under this policy — loud
   failure or a hang until timeout — is not determined here, and this
   report will not guess.** Whether an OpenAI/Anthropic/etc. SDK call
   blocked by a Cilium egress deny surfaces to the user as an immediate
   connection-refused-style error or hangs until the SDK's own client
   timeout depends on: (a) what Cilium actually returns for a denied `toFQDNs`
   connection at this cluster's CNI/kernel version — a `REJECT` sent back
   immediately vs. packets silently dropped and left to time out is a real,
   configurable difference in how Cilium enforces `toFQDNs` policies, and
   this repo has no cluster to observe it on; and (b) each LangChain-wrapped
   SDK's own connect-timeout default, which was not audited across 71
   bundles as part of this task. If it's a silent drop, a flow author
   pointing a node at a live vendor won't get a crisp "blocked by policy"
   error — they'll see the SDK's own timeout error (typically 30–60s
   depending on the SDK), which reads as "the vendor is slow/down," not
   "this deployment doesn't allow that." That's a real UX gap worth
   revisiting once `verify-egress.sh` has actually run and someone can watch
   what a blocked call looks like end to end — but stating a specific
   behavior here without having observed it would be a second unverified
   claim stacked on top of the first, which is exactly the failure mode this
   whole task is about avoiding.

## Assumptions this policy makes, spelled out

- **Pod label.** `app.kubernetes.io/name: nufi-agent` is invented here, not
  read from an existing Deployment. Confirm or correct it — in both
  `networkpolicy.yaml`'s `endpointSelector` and `verify-egress.sh`'s default
  `POD_LABEL_SELECTOR` — against whatever manifest actually deploys NuFi
  Agent before applying this in a real cluster.
- **Namespace.** Left unset in the manifest; supplied at apply time.
- **Scope.** DNS + `api.codechi.me:443` only, per the task brief. This policy
  does not attempt to allow-list anything else NuFi Agent's own runtime might
  need (its database, an object store, an internal service mesh endpoint,
  etc.) — if the real deployment needs additional egress for its own
  infrastructure dependencies (not model traffic), those need their own
  explicit rules added deliberately, not folded into this file by default,
  so the allow-list stays legible as "this is the model-traffic gateway
  rule" rather than a grab-bag.
- **Ingress is untouched.** This file governs egress only. NuFi Agent is a
  UI application; something still needs to reach it inbound. That's a
  separate concern from model-traffic containment and out of scope here.
