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
| `verify-egress.sh` | Tries to break the containment claim from inside a running NuFi Agent pod: curls `api.codechi.me` (must succeed) and `api.openai.com` (must fail, or the chokepoint doesn't exist). Inverted-logic pass/fail, matching a falsification test rather than a healthcheck. Every probe is classified as `reached` / `blocked` / `INCONCLUSIVE` (exit 0/1/2 respectively) — a probe that never ran to completion (`curl` missing, RBAC denial, ...) is never reported as PASS, only as INCONCLUSIVE. |
| `README.md` | This file. |

## Running the verification

Requires:

- A Kubernetes cluster with Cilium installed **and active as the CNI** —
  not merely present alongside another CNI. Confirm before applying, e.g.
  `kubectl -n kube-system get pods -l k8s-app=cilium` are Running, and
  `cilium status` (if the CLI is available) reports the agent healthy. A
  cluster that has Cilium installed but is still running a different
  primary CNI will accept this manifest and enforce nothing.
- A NuFi Agent pod deployed and labeled to match `networkpolicy.yaml`'s
  `endpointSelector`.
- **`curl` present inside the NuFi Agent pod's own image.**
  `verify-egress.sh` execs into the pod and runs `curl` there — if the
  image doesn't ship it, every probe reports `INCONCLUSIVE`, not `PASS` or
  `FAIL` (see that script's own header comment for why this is classified
  as a third outcome rather than folded into either). Check with
  `kubectl -n <namespace> exec <pod> -- which curl` before relying on the
  verification script's result.
- `kubectl` configured against that cluster.

Apply cautiously — this policy can affect a live pod's network access the
moment it's applied. Dry-run against the API server first, and know the
rollback:

```bash
# Validate against the live API server without actually applying:
kubectl apply -n <nufi-agent-namespace> -f apps/nufi-agent/nufi/egress/networkpolicy.yaml --dry-run=server

# Apply for real:
kubectl apply -n <nufi-agent-namespace> -f apps/nufi-agent/nufi/egress/networkpolicy.yaml

# Confirm the pod is actually enforced before trusting the manifest exists
# (see "What happens if the selector is wrong" in networkpolicy.yaml):
kubectl -n <nufi-agent-namespace> get ciliumendpoints -o wide

apps/nufi-agent/nufi/egress/verify-egress.sh <nufi-agent-namespace>

# Rollback, if something breaks and needs to come out immediately:
kubectl delete -n <nufi-agent-namespace> -f apps/nufi-agent/nufi/egress/networkpolicy.yaml
```

Expected output on success:

```
PASS: only the gateway is reachable from the NuFi Agent pod.
```

`verify-egress.sh` exits `0` for `PASS`, `1` for `FAIL`, and `2` for
`INCONCLUSIVE` — these are not the same thing and must not be read as the
same thing. `FAIL` means a real result was obtained and it's bad (the
vendor was reached, or even the gateway wasn't). `INCONCLUSIVE` means no
result was obtained at all — the probe itself didn't run to completion
(most likely: `curl` missing from the image, or `kubectl exec` denied by
RBAC) — and says nothing about whether containment holds either way. If it
prints `FAIL`, read the message — it names the specific thing to check next
(policy actually applied, selector actually matching, Cilium actually the
active CNI rather than a plain-NetworkPolicy fallback). **Fix the cluster,
not the script.** None of this has been run in the environment this task
was completed in; running it, reading the result, and recording the date
and outcome here (or in the design doc's phase tracker) is a follow-up a
human with cluster access has to do before "NuFi Agent's model traffic is
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

3. **`toFQDNs` enforcement is IP-based after DNS snooping, not
   SNI/Host-header-based.** Cilium implements `toFQDNs` by observing the DNS
   answer for `api.codechi.me` and allowlisting the resolved IP(s), not by
   inspecting the TLS SNI or HTTP Host header on every connection. If
   `api.codechi.me` ever resolves to an IP address shared with another
   hostname (a CDN edge node, a load balancer fronting multiple domains,
   etc.), that other host becomes reachable too, incidentally, for as long
   as the shared IP is cached as "belongs to an allowed FQDN." This is a
   property of how Cilium's FQDN filtering works, not a misconfiguration in
   this file — worth knowing before treating "only api.codechi.me" as an
   absolute guarantee at the IP level.

4. **This policy has one `endpointSelector` and assumes one pod type.** If
   NuFi Agent's real deployment ever splits into more than one pod role —
   e.g. a separate worker or executor pod that actually runs flows,
   distinct from a web/API pod — a pod of a role this policy's selector
   doesn't match sits entirely outside its reach, with Cilium's default-allow
   egress. Nothing here detects that automatically; a new pod role needs
   either the same label the selector already matches, or its own
   CiliumNetworkPolicy authored deliberately, not inherited by assumption.

5. **Telemetry is on by default and this policy blocks it, incidentally.**
   `src/lfx/src/lfx/services/settings/groups/telemetry.py:17` sets
   `telemetry_base_url = "https://langflow.gateway.scarf.sh"`, gated only by
   `do_not_track` / the `DO_NOT_TRACK` env var (checked: `service.py:49`
   reads `DO_NOT_TRACK` from the environment; default is tracking **on**).
   This is not fatal to anything — `send_telemetry_data` in
   `src/lfx/src/lfx/services/telemetry/service.py:110-123` wraps the whole
   HTTP call in `try/except Exception` off an async queue, so a blocked
   telemetry call cannot crash or hang the app — but it will emit
   `Telemetry send failed` / `Telemetry response …` debug-level log lines
   continuously, in the same log stream as a real startup problem, and
   nobody reading logs after this policy ships should mistake "expected,
   harmless, policy-blocked telemetry noise" for a genuine connectivity
   fault. Set `DO_NOT_TRACK=true` on the NuFi Agent deployment to silence it
   at the source rather than filtering it out of logs after the fact.

## Assumptions this policy makes, spelled out

- **Pod label.** `app.kubernetes.io/name: nufi-agent` is invented here, not
  read from an existing Deployment. Confirm or correct it — in both
  `networkpolicy.yaml`'s `endpointSelector` and `verify-egress.sh`'s default
  `POD_LABEL_SELECTOR` — against whatever manifest actually deploys NuFi
  Agent before applying this in a real cluster. **If it's wrong, `kubectl
  apply` will not tell you** — Cilium accepts and silently no-ops a policy
  whose selector matches zero pods, leaving the pod on Cilium's
  default-allow egress (the whole internet). See "What happens if the
  selector is wrong" in `networkpolicy.yaml`'s header comment for both ways
  to catch this: `verify-egress.sh` reporting FAIL as a byproduct, or
  checking `kubectl -n <namespace> get ciliumendpoints -o wide` directly for
  the pod's `EGRESS ENFORCEMENT` state before ever running the probe.
- **Namespace.** Left unset in the manifest; supplied at apply time.
- **Scope.** DNS + `api.codechi.me:443` only, per the task brief. Whether
  that's sufficient for NuFi Agent's *own* runtime dependencies (as opposed
  to model traffic) depends on how it's actually deployed: **by default,
  Langflow needs neither** — `database_url` defaults to `None`, which
  `src/lfx/src/lfx/services/settings/groups/database.py:22-25` documents as
  "Langflow will use a SQLite database" (a local file, no network egress),
  and `storage_type` defaults to `"local"`
  (`src/lfx/src/lfx/services/settings/groups/storage.py:7`, confirmed
  against `src/backend/base/langflow/services/storage/factory.py`) — a
  local-disk store, also no egress. **If an operator configures an external
  Postgres `database_url` or switches `storage_type` to `s3`, those become
  real egress needs this policy does not cover**, and need their own
  explicit rules added deliberately (not folded into this file by default,
  so the allow-list stays legible as "this is the model-traffic gateway
  rule" rather than a grab-bag) before this policy is applied to a
  deployment configured that way — otherwise the database/storage
  connection breaks the moment this policy is enforced, not just model
  calls to an unlisted vendor.
- **Ingress is untouched.** This file governs egress only. NuFi Agent is a
  UI application; something still needs to reach it inbound. That's a
  separate concern from model-traffic containment and out of scope here.
