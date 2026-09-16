# NUFI Works on the box — design

2026-09-16. Follows the spike (`docs/2026-09-16-works-on-box-spike.md`), whose
runtime probe passed on Ubuntu x86-64 on 2026-09-16 (run 35048384818). The
decision it implements is option B: Works runs on the box, its agent code runs
under Docker with gVisor as the runtime, and the box keeps its compose shape.
The constraint from the requester is that this must not disturb the rest of the
box much; every section below says what it touches.

## What Works needs that the box does not have

Works runs code its agents write. That is untrusted code, and two properties of
the cloud cluster are what make it safe there:

1. **a kernel boundary** — `runtimeClassName: gvisor`, so a sandbox does not
   share the host kernel as its only defence;
2. **egress restricted by hostname** — Cilium network policy with `toFQDNs`,
   because ordinary network policy cannot express a hostname.

Docker gives neither on its own. This design supplies both without Kubernetes:
gVisor as a Docker *runtime* (proved), and a forward proxy on a network with no
other route out (the property the probe's last step proved).

## Three pieces

```
                 ┌──────────────── the box (docker compose) ────────────────┐
                 │                                                          │
   member ──────▶│  caddy :3003 ──▶ works (apps/agents server)              │
                 │                     │ docker socket                      │
                 │                     ▼                                    │
                 │   ┌── network: works-sandbox (--internal) ─────────┐     │
                 │   │  sandbox  sandbox  sandbox   (runtime: runsc)  │     │
                 │   │     │        │        │                        │     │
                 │   │     └────────┴────────┴──▶ works-egress :3128  │     │
                 │   └────────────────────────────────┬───────────────┘     │
                 │                                    │ allow-list only     │
                 └────────────────────────────────────┼─────────────────────┘
                                                      ▼
                                    litellm :4000 · works :3100 · (nothing else)
```

| Piece | Lives in | Touches existing code? |
|---|---|---|
| **A** — the sandbox provider | `apps/agents/packages/plugins/sandbox-providers/docker/` | no — a new package beside the six that exist |
| **B** — the egress proxy | `deploy/box/` (a service, a rendered config, a test) | no existing service |
| **C** — execution mode `docker` | `apps/agents/server/src/services/execution-policy-bootstrap.ts` | **yes**: one accepted value added, ~30 lines plus tests |

C is the only line of host code, and it is the same file the cloud deployment
runs. It is kept to the smallest change that lets a box refuse every provider
but this one, which is what `kubernetes` mode does for the cluster today.

## A — the Docker provider

A plugin with the same ten hooks as the six existing providers, read from the
SDK's `protocol.ts` and matched one-for-one to Docker operations:

| Hook | Does |
|---|---|
| `setup` | log |
| `onHealth` | `docker info` reachable **and** `runsc` in its runtimes; otherwise `status: "error"` naming which |
| `onEnvironmentValidateConfig` | image is a pinned reference (tag or digest, never bare); memory and CPU limits parse; every allow-listed host is a hostname, not a URL |
| `onEnvironmentProbe` | daemon reachable |
| `onEnvironmentAcquireLease` | `docker create` with `--runtime=runsc`, on the `works-sandbox` network, with the proxy in its environment, then `start`; `providerLeaseId` is the container id |
| `onEnvironmentResumeLease` | `inspect`; `start` if stopped; fail if gone |
| `onEnvironmentReleaseLease` | `stop` |
| `onEnvironmentDestroyLease` | `rm -f` |
| `onEnvironmentRealizeWorkspace` | `exec mkdir -p <cwd>` |
| `onEnvironmentExecute` | `exec` with `cwd`, `env`, `stdin`; the caller's `timeoutMs` is a hard deadline after which the exec is killed and `timedOut: true` returned |

**What every sandbox gets, and cannot change:**

- `--runtime=runsc`. Not configurable; a provider that could be told to use
  `runc` is a provider that is one config line away from no kernel boundary.
  `onHealth` refuses to report healthy without it.
- `--network works-sandbox`, a compose network declared `internal: true`. No
  route out except to other members of that network.
- `HTTP_PROXY`, `HTTPS_PROXY`, `NO_PROXY` pointing at the egress proxy. Code
  that ignores them has no route and fails closed — the probe's last step.
- `--memory`, `--cpus`, `--pids-limit` from the environment config, with
  defaults (2 GB, 2 CPUs, 512 pids). A sandbox that cannot be bounded is a
  sandbox that can take the box's one model down.
- `--read-only` root with a writable `/workspace` volume and `/tmp` tmpfs.
- No Docker socket. The **provider** has it; the sandbox does not.

**The socket.** The provider talks to the daemon over `/var/run/docker.sock`
mounted into the `works` container. That is a real grant: a process that can
reach the daemon can start any container on the box, as root. It is the same
grant `nufi-cron` explicitly avoids (its comment explains why). It is accepted
here because there is no other way for a container to create sibling
containers, and it is stated in the box README rather than left to be
discovered. The mitigation is that only the `works` service — not any sandbox
— has the mount.

**Talking to Docker.** `dockerode`, a new dependency of this package only. The
tests use a fake daemon over an HTTP server, in the shape of `test_ingest.py`
and `test_nufi_cron.py`: the calls the provider makes are asserted, not mocked.

## B — the egress proxy

A `works-egress` service in the box compose: tinyproxy, on both the
`works-sandbox` network and the box's own, with a config rendered at start from
an allow list. It is the only member of the sandbox network that also has a
route out.

**The allow list** is what the cloud's `PAPERCLIP_K8S_EGRESS_ALLOW_FQDNS`
carries, plus what the k8s network policy already grants without saying so:

| Always | Why |
|---|---|
| `works:3100` | the sandbox reports back to the Works server; the k8s policy names this as `paperclip-egress-allow` |
| `litellm-proxy:4000` | the model, through the gateway, so a sandbox is bound by the same limits and guardrails as a chat |
| *operator list* | `WORKS_EGRESS_ALLOW` in `.env`, hostnames, comma-separated, empty by default |

Everything else is refused with 403 and **logged by hostname**, which is the
one thing this design has that the Cilium path does not: an answer to "what did
that agent try to reach".

**No proxy for the model host directly.** A sandbox reaches the model through
LiteLLM or not at all; Ollama's own port is not on the list. That keeps every
model call metered and guarded the same way, and it is the reason the gateway
is on the list at all.

**Fail closed is structural, not configured.** The sandbox network is
`internal: true`; the proxy is the only exit. If the proxy is down, sandboxes
have no network rather than an unfiltered one. The test for this is the same
as the probe's: a sandbox on the network with the proxy stopped cannot reach a
public host within five seconds.

## C — execution mode `docker`

`execution-policy-bootstrap.ts` accepts `PAPERCLIP_EXECUTION_MODE` of
`kubernetes` or `any`. It gains `docker`, which does for the box what
`kubernetes` does for the cluster: forces every company onto the named
provider and denies local execution. The config it carries is small —
`PAPERCLIP_DOCKER_IMAGE`, `_MEMORY`, `_CPUS`, `_EGRESS_ALLOW` — and mirrors the
`PAPERCLIP_K8S_*` shape so the two read the same way.

The change is additive: a deployment that never sets `docker` cannot observe
it. The existing tests for the `kubernetes` branch stay; the new ones are the
same tests with the other value.

## On the box

- **compose** gains three things: the `works` service (image
  `nufi-works:main`, the socket mount, port 3003 behind Caddy), the
  `works-egress` service, and the `works-sandbox` internal network.
- **`install-box.sh`** gains one step, off by default: `--with-works` installs
  `runsc` (one binary, one `daemon.json` stanza, one daemon restart — exactly
  the probe's install step) and enables the two services. A box without
  `--with-works` is byte-for-byte the box that ships today.
- **`nufi-box doctor`** gains a check: on a box with Works, `runsc` is among
  Docker's runtimes, and the egress proxy answers.
- **Caddy** gains a fifth product port, 3003, in the same shape as the other
  four — and in the mesh sites, which import the same snippet.
- **Console** gains Works as a product on `/choose` on a box that has it. The
  entitlement gate that already exists for Works in the cloud applies unchanged.

## What it does not do

- **Persist sandboxes across box restarts.** A lease that was running when the
  box went down is gone; `onEnvironmentResumeLease` reports it and the host
  starts a new one. Same as the cloud provider's behaviour on a pod eviction.
- **Run on Docker Desktop.** The provider refuses to report healthy without
  `runsc`, and Docker Desktop does not let an operator add one. Works-on-box is
  an Ubuntu feature; a Mac developing it uses the Ubuntu VM the box tests
  already use.
- **Share the sandbox network with anything but sandboxes and the proxy.** The
  Works server itself is on the box network and reaches sandboxes through the
  daemon, not through their network.

## Testing

Each piece has its own suite, and the box gets one end-to-end check.

- **A**: stdlib-shaped vitest against a fake Docker daemon. The cases that
  matter: `runsc` is always requested and `runc` never is; every sandbox lands
  on the internal network with the proxy in its environment; a timed-out exec
  is killed rather than abandoned; `onHealth` is red without `runsc`.
- **B**: a rendered config is asserted from an allow list (the same
  parser-in-CLI rule `schedule list` follows: one renderer, no second copy);
  and on a box, a sandbox reaching a listed host gets through, an unlisted one
  gets 403, and with the proxy stopped nothing gets out.
- **C**: the bootstrap tests, duplicated for the new value.
- **Box**: `verify-ubuntu-box.sh` gains a Works step on `--with-works` boxes —
  a run that executes `uname -r` in a sandbox and asserts `gvisor` in the
  output, which is the probe's own test performed through the product.

Every one of these is written to fail first, as the rest of the box's suites
are. The class of bug this project has met most often is a check that cannot
fail, and a security boundary is the worst place to meet it again.

## Order

C first (a day; it is what lets the box run in `docker` mode at all), then A
(a week), then B (two or three days), then the box wiring (two or three days),
then docs. A is testable without B — a provider on a network with no proxy
simply has no egress, which is the safe default — so the pieces land as
separate pull requests and the box is never left half-wired.
