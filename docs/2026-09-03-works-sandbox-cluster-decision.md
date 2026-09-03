# Where the NUFI Works sandbox runs

2026-09-03

A member can sign in to NUFI Works and cannot make an agent do anything. That is
not a missing sandbox. `apps/agents/packages/plugins/sandbox-providers/kubernetes/`
is a finished first-party provider — tenant namespaces, pod security baseline,
network policy, two orchestration backends — and
`apps/agents/server/src/services/execution-policy-bootstrap.ts` will force every
company onto it from environment variables alone. What is missing is a cluster
that can honour the two words the policy sets: `gvisor` and `cilium`.

So this is not a build-a-sandbox decision and not a pick-an-abstraction
decision. It is: which cluster do we point the shipped provider at, and what
does it cost.

## What the cluster must provide

Every row here came out of the code, not out of a generic sandbox checklist.

| Requirement | Where it comes from | Why it is not negotiable |
|---|---|---|
| A `RuntimeClass` named `gvisor`, with `runsc` and its containerd shim on the nodes | `execution-policy-bootstrap.ts:107` (`PAPERCLIP_K8S_RUNTIME_CLASS_NAME`); the value is pinned to `"gvisor"` in `execution-policy-bootstrap.test.ts:57` and `__tests__/environment-service.test.ts:571`; the plugin README states "Cluster must have the RuntimeClass installed" | Agent code is untrusted. With a shared host kernel, the kernel is the boundary being defended, and `runtimeClassName` is the only place we defend it. |
| Upstream Cilium as the CNI, with the L7 DNS proxy | `execution-policy-bootstrap.ts:97-104` (`PAPERCLIP_K8S_EGRESS_MODE`); `cilium-network-policy.ts:56-57` emits `apiVersion: cilium.io/v2`, `kind: CiliumNetworkPolicy`, with `toFQDNs`/`matchName` at line 32 and a DNS visibility rule (`rules: { dns: [{ matchPattern: "*" }] }`) at line 25 | Gateway-only egress is enforced by name or it is not enforced. `network-policy.ts:7` says it in one line: "NetworkPolicy cannot express FQDNs natively — only Cilium can." |
| The `sandboxes.agents.x-k8s.io/v1alpha1` CRD and its controller, on Kubernetes 1.27+ | plugin README, "Prerequisites"; `types.ts:68` defaults `backend` to `"sandbox-cr"`, which `execution-policy-bootstrap.ts:87-95` accepts from `PAPERCLIP_K8S_BACKEND` | The stable fallback (`job`) runs one container entrypoint and exits. The README is explicit that "paperclip-server's adapter-install pattern requires sandbox-cr", so without the CRD the adapter never installs and the run is a no-op. |
| Namespaces we may create and fully configure, under a prefix | `environments.ts:61` and `execution-policy-bootstrap.ts:110` (`PAPERCLIP_K8S_NAMESPACE_PREFIX`); `tenant-orchestrator.ts` creates Namespace, ServiceAccount, Role, RoleBinding, ResourceQuota, LimitRange and two NetworkPolicies per company | One company's run must not see another's. The credential we hand the server is therefore close to cluster-admin scoped to that prefix, which a locked-down managed platform will not issue. |
| A reachable image registry, expressed as a URL | `execution-policy-bootstrap.ts:113` (`PAPERCLIP_K8S_IMAGE_REGISTRY`); `types.ts:15` types it `z.string().url()` and `types.ts:16-17` adds `imageAllowList` / `imagePullSecrets` | Every run pulls a runtime image per adapter. |
| A kube-apiserver reachable from outside the cluster, allowing exec/attach upgrades | `execution-policy-bootstrap.ts:84` (`PAPERCLIP_K8S_IN_CLUSTER`, default `false`); `types.ts:71-74` refines the config to require `inCluster` *or* `kubeconfig` | Works runs on Railway. `docs/superpowers/specs/2026-08-26-nufi-agents-cloud-design.md` established that `onEnvironmentExecute` opens a WebSocket from the server out to the apiserver and execs into the pod — the pod never dials back. The cluster must accept that connection from Railway. |

Three of these are worth a sentence each, because they are the ones a
provider comparison gets wrong.

**Cilium means Cilium, not "a CNI that does network policy."** The policy the
plugin writes is a namespaced `cilium.io/v2` custom resource whose FQDN clause
is inert without Cilium's DNS proxy: Cilium intercepts the pod's DNS query,
learns the addresses from the response, and admits those addresses for that
identity. A platform that offers Kubernetes `NetworkPolicy`, or its own
FQDN-policy CRD, does not satisfy this — the plugin will `POST` a
`ciliumnetworkpolicies` resource (`tenant-orchestrator.ts:268-275`) into an API
that has no such kind, and tenant provisioning fails.

**gVisor does not need nested virtualisation.** Worth stating because it is the
usual reason people conclude they need bare metal. gVisor's default platform
since mid-2023 is systrap, which the project documents as "a better choice when
running inside a VM, or on a machine without virtualization support". An
ordinary cloud VM is enough. The optional `kata-fc` path in the plugin README
is what needs nested virt, and we are not using it.

**The direction of travel is server to apiserver to pod.** The Cilium policy
contains an egress rule to `app: paperclip-server` on port 3100
(`cilium-network-policy.ts:37-47`), which reads as though the server must live
in the cluster. The 2026-08-26 design doc chased that and found the callback
scheme has not landed; the rule is provision for a future. Works stays on
Railway, and the network requirement is the mirror image: Railway must reach
the apiserver.

## Candidates, and the capability gate they pass or fail

A missing capability is a disqualification, not a low score. If the provider
cannot run a `gvisor` RuntimeClass, or cannot run upstream Cilium, it cannot
host this plugin at all and its price is irrelevant.

| Candidate | `runtimeClass: gvisor` | `cilium.io/v2` + DNS proxy | agent-sandbox CRD | Verdict |
|---|---|---|---|---|
| GKE Autopilot | Yes — GKE Sandbox, 1.27.4-gke.800+ | **No** | Yes, `--enable-agent-sandbox` | **Disqualified** |
| Railway | No Kubernetes API at all | No | No | **Disqualified** |
| GKE Standard | Yes (GKE Sandbox, COS nodes only), or self-installed | Yes, self-installed | Yes, self-installed | Survives |
| EKS | Self-installed on self-managed nodes | Yes, self-installed | Yes, self-installed | Survives |
| k3s on one rented server | Self-installed | Yes, self-installed | Yes, self-installed | Survives |
| E2B (Firecracker microVMs) | Not Kubernetes — the question does not apply | Vendor firewall instead | — | Survives only by replacing the provider |

**GKE Autopilot is disqualified on the CNI, not the sandbox.** Its gVisor half
is genuinely good: Google documents "GKE Sandbox is ready to use in Autopilot
clusters running GKE version 1.27.4-gke.800 and later", and Agent Sandbox —
the same `agents.x-k8s.io` CRDs our default backend uses — is available on
Autopilot behind `--enable-agent-sandbox` at no extra charge. The egress half
fails twice over, and Autopilot mandates GKE Dataplane V2.

The CRD kind is not the problem — Dataplane V2 does accept the namespaced
`CiliumNetworkPolicy` the plugin writes; its concepts page discusses node
limits for "Clusters using the CiliumNetworkPolicy CRD" and only recommends the
clusterwide kind past 1,000 nodes. The problem is what the policy contains.
GKE's own Cilium network policy documentation states "Layer 7 policies are not
supported", and `toFQDNs` is nothing without the L7 DNS proxy — the resource
would be accepted and enforce nothing, which is the worst of the three outcomes.

Nor can we bring our own Cilium to sit underneath it. The Dataplane V2 concepts
page settles that in one sentence: "Because these programs are essential for
network connectivity, GKE doesn't support installing custom eBPF programs on
nodes that use GKE Dataplane V2." Autopilot's separate refusal to run privileged
or `hostNetwork` containers points the same way, but the eBPF sentence is the
one that closes the door.

**Railway is disqualified on the first row.** It exposes no Kubernetes API.
There is no object on which to set `runtimeClassName` and no CNI to choose.
This is where Works itself runs, and it stays there; it is not where the
sandbox can run.

**EKS survives but is dominated.** It charges the same $0.10 per cluster per
hour as GKE for the control plane, Cilium is a self-managed install either way,
and unlike GKE it has no managed gVisor at all — `runsc`, the containerd shim
and the RuntimeClass are ours to install on self-managed node groups. It is
GKE Standard with one advantage removed, so it is not carried into the cost
comparison.

## What the survivors cost

Load model, stated so it can be argued with: three companies, roughly twenty
agent runs a week, each under ten minutes of wall clock, two vCPU and 4 GiB per
run. That is about 14 hours of sandbox time a month. The plugin's own ceiling
(`podActivityDeadlineSec`, default 3600) matches the shape.

| Option | Idle, at zero runs | Plus ~14 h/month of runs | Who operates it |
|---|---|---|---|
| k3s on a Hetzner CCX23 (4 dedicated vCPU, 16 GB) | €85.99 verified for Germany/Finland; **Singapore, the location recommended below, runs ≈26% higher** — $0.2013/hour against $0.1595/hour — so budget **≈ €108/month** | €0, but only inside the included traffic, and Singapore's is much smaller than Europe's: "varies from 0.5 TB to 5 TB of outbound traffic per month" by plan, overage at $8.49/TB | Us, entirely |
| GKE Standard, asia-northeast3 | $0.10/cluster/hour ≈ $73, less a reported $74.40 monthly free-tier credit, plus one always-on system node pool — estimated $50–70/month | A few dollars of node time on a gVisor pool that can scale to zero | Google for the control plane and node images; us for Cilium, gVisor and agent-sandbox |
| E2B Hobby | $0 | ≈ $2.38 at verified rates ($0.1008/hour for 2 vCPU, $0.0162/GiB/hour) | E2B — and us, writing a new sandbox provider |

The E2B numbers and the Hetzner German price are verified. The Hetzner
Singapore figure is derived, not quoted: Hetzner publishes the monthly cap per
location but the ratio above comes from hourly rates, so €108 is the German cap
scaled by 26% rather than a price Hetzner printed. The GKE line is an estimate
throughout: the $0.10 cluster-hour fee and the $74.40 credit are consistently
reported but the primary pricing page did not render on fetch, and I did not
verify Seoul-region node prices at all.

Note that the E2B row is the cheapest by an order of magnitude and is still not
the recommendation, for reasons that are not about money.

## Recommendation

**Run the sandbox on a single self-managed k3s node on rented hardware —
Hetzner Cloud CCX23 (4 dedicated vCPU, 16 GB), Singapore — with upstream Cilium
as the CNI, `runsc` installed as the `gvisor` RuntimeClass, and the
agent-sandbox controller applied on top.**

The argument is a subtraction. The `egressMode: "cilium"` requirement means we
install and operate upstream Cilium ourselves on every candidate that is not
disqualified: GKE's own dataplane cannot serve the policy we write, EKS has no
opinion, and k3s ships flannel that one flag turns off. So the CNI is ours in
every world. That leaves the control plane and node lifecycle as the only thing a
managed provider sells us here — and the control plane was never the hard part
of this problem. We are paying a cluster-hour fee, a cloud account and an IAM
model for the easy half.

At the corrected Singapore price this is no longer the cheap option — €108 is
within noise of the GKE Standard estimate, and E2B is an order of magnitude
below both. That does not move the decision, because the decision was never
made on price: it was made on the observation that the CNI is ours in every
surviving world. If the price were the argument, E2B would already have won.

Dedicated vCPUs rather than shared ones, because gVisor's systrap platform adds
syscall overhead and a noisy neighbour would make agent run times
unreproducible, which is the one thing a demo cannot afford.

If the Seoul facility that hosts the NPUOps box
(`deploy/platform/docs/deployment-infra.md`) can take a second machine, that is
the same build in a better location and should be preferred — same k3s, same
Cilium, same Cloudflare Tunnel pattern that already fronts `api.codechi.me`.
Do not wait on it. The rented box is orderable today and every hour of
provisioning work transfers.

It must be a *second* machine. The existing box runs the LiteLLM gateway and its
keys, and its own sizing note already says 12 vCPU is "tight vs. 13 baseline".
Putting untrusted agent code on that kernel is precisely what the gVisor
requirement exists to prevent.

**Runner-up 1: GKE Standard in asia-northeast3.** Lost on its one managed
advantage evaporating. GKE Sandbox's `gvisor` RuntimeClass is the real reason to
choose GKE, and it is documented only for `cos_containerd` node pools; Cilium's
GKE install requires a cluster without Dataplane V2 plus a node-init DaemonSet
that reconfigures kubelet and mounts the eBPF filesystem. Neither vendor
documents that combination. So we would end up self-managing the CNI, and
probably the runtime too, while paying a $0.10 cluster-hour fee and an
always-on system node pool for a control plane we did not need.

**Runner-up 2: E2B.** Lost on code, not price — it is roughly $2.38 a month at
our load against €85.99. Choosing it means not using the shipped Kubernetes
provider: `KUBERNETES_PROVIDER_KEY` in `environments.ts:42`, the
`executionMode: "kubernetes"` path that `execution-policy-bootstrap.ts` forces,
`ensureKubernetesEnvironment`, and the entire plugin under
`sandbox-providers/kubernetes/` become a second-best path beside a provider we
have not written. It also puts untrusted execution and a gateway key inside a
third party's account, which the on-prem line in `deploy/platform/` — whose own
adapter guard refuses to forward a member's payload to any public host
(`adapters/meshbox-agent/nufi_egress.py`) — cannot use at all.

## Checking it against the invariant it exists to protect

`docs/2026-08-04-nufi-agents-spike-findings.md` §1 draws the distinction this
whole exercise turns on: reaching the gateway and being checked by it are
different claims. The spike proved the second half on the gateway — G1 blocking
with `enforced="true"` — and left the first half open: "the half that says
*agents cannot leave the gateway* still does not — that is Task 4-5, and it
needs Cilium."

The recommendation clears the bar. A self-managed cluster runs upstream Cilium
with the DNS proxy, which is exactly what `toFQDNs` + `matchName` requires, so
the policy the plugin already writes is enforced rather than decorative. No
reversal is needed on the provider.

Two things do threaten the invariant, and neither is fixed by picking a cluster.
They belong to whoever builds it.

**The adapter registry re-opens the allow-list.** `plugin.ts:250` passes
`egressAllowFqdns: [...adapterDefaults.allowFqdns, ...config.egressAllowFqdns]`
into the tenant policy, and `adapter-defaults.ts:16-46` hard-codes
`api.anthropic.com`, `api.openai.com`, `generativelanguage.googleapis.com` and
`openrouter.ai` per adapter type. Left alone, the CiliumNetworkPolicy will
permit an agent to call a model vendor directly, off-gateway, on a cluster
chosen specifically to prevent that.

The lever is `PAPERCLIP_ADAPTERS` / `PAPERCLIP_ADAPTERS_FILE`
(`adapter-registry-bootstrap.ts:30-31`), which rides onto the same environment
config — but it has to be used in the plural, and under the existing keys.
Two details decide that. `types.ts:42-47` refines `adapterType` against
`KNOWN_ADAPTER_TYPES`, which `adapter-defaults.ts:51` derives from the six
built-in registry keys (`claude_local`, `codex_local`, `gemini_local`,
`cursor_local`, `opencode_local`, `pi_local`), so inventing a `nufi_*` adapter
name fails config validation. And the type is resolved per run, not per
environment: `plugin.ts:215` calls `resolveRunAdapterType`
(`adapter-defaults.ts:96-106`), which prefers the run's own adapter "so one
environment can serve mixed harnesses" — pinning a single entry leaves the
other five reachable.

So: redeclare each adapter type we intend to allow, under its existing key,
each with `allowFqdns` holding the gateway and nothing else. The behaviour that
makes this safe is at `adapter-defaults.ts:81-87` — once a registry is
configured it is authoritative, and a run whose adapter type is absent from it
throws `Adapter "X" is not in the configured adapter registry`. Any harness left
out of the registry therefore fails the run rather than opening egress, which is
the direction a mistake here should fall.

**An FQDN allow-list is only as narrow as the address the name resolves to.**
Cilium admits the addresses it observed in the DNS response. `api.codechi.me` is
fronted by a Cloudflare Tunnel (`deploy/platform/docs/cloudflare-tunnel-setup.md`),
so it resolves to anycast addresses shared with a very large number of unrelated
sites; a pod that opens a TLS connection to one of those addresses with a
different SNI is not stopped by an L3/L4 rule. Pin the gateway to an address we
control and express it as `PAPERCLIP_K8S_EGRESS_ALLOW_CIDRS`, or accept that the
policy proves "traffic went to Cloudflare" rather than "traffic went to the
gateway."

## Follow-up

**What the deployment sets.** On the `nufi-works` Railway service:

| Variable | Value | Note |
|---|---|---|
| `PAPERCLIP_EXECUTION_MODE` | `kubernetes` | Anything else leaves local execution allowed. |
| `PAPERCLIP_K8S_BACKEND` | `sandbox-cr` | The default, stated explicitly so a schema change cannot silently move us to `job`. |
| `PAPERCLIP_K8S_RUNTIME_CLASS_NAME` | `gvisor` | Must match the RuntimeClass name installed on the node. |
| `PAPERCLIP_K8S_EGRESS_MODE` | `cilium` | |
| `PAPERCLIP_K8S_NAMESPACE_PREFIX` | `nufi-` | Constrained to `^[a-z0-9-]{1,32}$` (`types.ts:12`). |
| `PAPERCLIP_K8S_IMAGE_REGISTRY` | the GHCR path for the runtime images | Must parse as a URL (`types.ts:15`). |
| `PAPERCLIP_K8S_EGRESS_ALLOW_FQDNS` | the gateway host | |
| `PAPERCLIP_K8S_EGRESS_ALLOW_CIDRS` | the gateway origin, once it has a dedicated address | See the anycast note above. |
| `PAPERCLIP_K8S_RPC_TIMEOUT_MS` | a few minutes | `environments.ts:64-71` exists for exactly the cold-start case. |
| `PAPERCLIP_ADAPTERS` | the NUFI adapter, `allowFqdns` gateway-only | Closes the vendor-FQDN union. |
| `PAPERCLIP_K8S_IN_CLUSTER` | `false` | Works is on Railway. **Not sufficient on its own — see the gap below before deploying this table.** |

**One gap to close before any of that works.** `types.ts:71-74` refines the
provider config to require `inCluster` *or* `kubeconfig`, and
`execution-policy-bootstrap.ts` parses no kubeconfig variable at all. With
`PAPERCLIP_K8S_IN_CLUSTER=false` the env-driven bootstrap therefore produces a
config the plugin's own schema rejects. Either the bootstrap gains a
kubeconfig source, or the environment row is seeded another way. Related and
smaller: the plugin README documents a `kubeconfigSecretRef` field that the
schema does not accept. Both are code changes and are deliberately not made
here.

**How the cluster gets its Cilium.** Install k3s with the bundled network layer
off (`--flannel-backend=none --disable-network-policy`, and `--disable=traefik`
since nothing here needs an ingress), then install Cilium by Helm with the L7
proxy enabled so the DNS proxy exists — that is the component `toFQDNs` depends
on, and a Cilium install with it disabled will accept the policy and enforce
nothing. Then `kubectl apply` the agent-sandbox controller, install `runsc` and
`containerd-shim-runsc-v1` on the node with a containerd runtime handler, and
create the `gvisor` RuntimeClass pointing at it. The plugin creates everything
else per company on first dispatch. Railway should reach the apiserver through
a tunnel rather than an open 6443, because Railway's egress addresses are not
fixed and an IP allow-list would be theatre; the ServiceAccount in the
kubeconfig is scoped to the namespace prefix.

**What the first end-to-end run has to demonstrate** before this is called
done. Five things, in order, none of them "it returned a completion":

1. A lease creates a `Sandbox` CR in `nufi-<slug>` and the resulting pod reports
   `spec.runtimeClassName: gvisor`, with a gVisor kernel banner inside it — the
   RuntimeClass being *named* is not evidence it was *used*.
2. `CiliumNetworkPolicy/paperclip-egress-fqdn` exists in that namespace, and
   from inside the pod the gateway is reachable while `api.openai.com` and the
   node's own private address are not.
3. A model call made by the agent shows up on the gateway as a guardrail
   decision. This is the claim the spike left open: routed *and* inspected.
4. Releasing the lease deletes the `Sandbox` CR, and the pod and the
   `pc-*-env` Secret go with it.
5. A second company gets its own namespace and cannot list the first's pods.

## What is not verified here

Stated plainly so nobody spends against a number I did not check.

- **Verified from primary sources:** Hetzner's June 2026 prices (CCX13 €42.99,
  CCX23 €85.99, CCX33 €138.49, CPX41 €69.49, AX42-1 ≈ €97.30, from Hetzner's own
  price-adjustment page, monthly, excluding IPv4, Germany/Finland); the EKS
  control-plane price ($0.10 per cluster-hour standard support, $0.60 extended);
  E2B's rates and plan limits ($0.0504/vCPU/hour, $0.0000045/GiB/s, Hobby free
  with a 1-hour session cap, Pro $150/month); GKE Sandbox's Autopilot version
  floor and its `cos_containerd`-only restriction; Agent Sandbox on GKE
  requiring 1.35.2-gke.1269000+ and being offered at no extra charge; Dataplane
  V2's "Layer 7 policies are not supported" and "GKE doesn't support installing
  custom eBPF programs on nodes that use GKE Dataplane V2"; Autopilot's
  privileged-container and hostNetwork restrictions; Hetzner Singapore's
  included traffic ("varies from 0.5 TB to 5 TB of outbound traffic per month",
  overage $8.49/TB); gVisor's systrap platform not requiring hardware
  virtualisation.
- **Estimated, not verified:** every GKE cost figure. The $0.10 cluster-hour fee
  and $74.40 free-tier credit come from secondary sources because Google's
  pricing page truncated on fetch; Seoul-region node prices were not checked at
  all. The ≈ €108 Singapore figure is derived rather than quoted — the +26%
  comes from a third-party index of Hetzner's hourly rates ($0.2013 against
  $0.1595), applied to the German monthly cap, so confirm it in the Hetzner
  console before it goes in a budget. The 14-hours-a-month load model is an
  assumption, not a measurement.
- **Reasoned, not quoted:** two claims are inference rather than a sentence in
  a vendor document. Cilium's GKE prerequisites (the
  `node.cilium.io/agent-not-ready` taint, the node-init DaemonSet that
  reconfigures kubelet and mounts the eBPF filesystem) are from Cilium's own
  install page, but "the cluster must not be running Dataplane V2" is from a
  secondary source. And the anycast weakness in the FQDN allow-list follows
  from the documented DNS-proxy mechanism — Cilium admits the addresses it saw
  in the response — rather than from a Cilium warning about Cloudflare
  specifically. Both should be tested on the cluster, not argued about.
- **Not checked:** whether Hetzner Singapore's kernel and virtualisation
  settings suit Cilium's eBPF requirements — this should be confirmed before
  ordering, and Helsinki is the fallback if not. Whether the existing Seoul
  facility can take a second machine. Whether NUFI has a data-residency
  commitment that requires agent execution to stay in Korea; if it does, this
  decision reverses to GKE Standard in asia-northeast3 or a Korean provider,
  and the architecture above is unchanged.
