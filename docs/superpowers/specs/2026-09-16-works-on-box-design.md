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
| **C** — the box registers the environment | `deploy/box/` (one script, run by the installer) | **no** — see the revision below |

**Revision, 2026-09-16, before any code.** The first draft of C added a third
value to `PAPERCLIP_EXECUTION_MODE` in `execution-policy-bootstrap.ts`. Writing
the plan for it found what the spec had missed: `apps/agents` is a vendored
upstream (`nufi/upstream.json`, `paperclipai/paperclip` at `v2026.722.0`)
guarded by `nufi/check-fork-diff.sh`, and none of the three files that change
would touch is on the allowlist. The forced-mode machinery is upstream's, built
for upstream's Kubernetes; widening the fork to generalise it is exactly the
drift the guard exists to stop. So C does not touch the host at all.

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

## C — the box registers the Docker environment

Upstream already has the seam: `POST /environments` accepts `driver: "sandbox"`
with a free-form `config`, and a sandbox environment resolves to whichever
provider `config.provider` names. That is how an operator adds the E2B or
Daytona provider to a cloud instance today, with no forced mode. The box does
the same for `docker`:

- `nufi-box works install` (called by `install-box.sh --with-works`) signs in
  with the box's Works credentials, installs the provider plugin from its local
  path, creates — idempotently, by name — one environment
  `{ driver: "sandbox", config: { provider: "docker", image, memory, cpus,
  egressAllow } }`, and sets it as the instance default. Every company's runs
  land on it.
- The same command sets the upstream `Local` environment's `status` to
  `archived` (the only inactive status upstream defines). Upstream creates that row on first boot (`ensureLocalEnvironment`)
  and it would run agent code inside the `works` container under plain Docker,
  with no gVisor. Disabling it is the box's equivalent of the cloud's forced
  mode.
- `nufi-box doctor` checks both: the default environment's provider is `docker`,
  and `Local` is archived.

What this gives up, stated plainly: the cloud's forced mode is enforced **per
run** in the heartbeat and cannot be undone from the product UI; the box's
arrangement is enforced **at install** and could be undone by an administrator
un-archiving `Local` in the Environments page. On a single-department appliance
whose administrator already holds `.env`, that is an acceptable trade for not
forking the host. If a hard per-run gate is ever wanted, the shape it should
take is a `forcedProviderKey()` in upstream's `execution-allowlist.ts` — a
patch to send **upstream**, not to carry in the fork.

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
- **C**: the register script's tests, in the shape of `test_nufi_box.py` — dry-run
  asserts the calls it plans (create environment with `provider: "docker"`, set
  default, disable `Local`), and a fake Works API asserts idempotency: a second
  run creates nothing.
- **Box**: `verify-ubuntu-box.sh` gains a Works step on `--with-works` boxes —
  a run that executes `uname -r` in a sandbox and asserts `gvisor` in the
  output, which is the probe's own test performed through the product.

Every one of these is written to fail first, as the rest of the box's suites
are. The class of bug this project has met most often is a check that cannot
fail, and a security boundary is the worst place to meet it again.

## Order

A first (a week; nothing can be registered until there is a provider to
register), then B (two or three days), then C with the box wiring (two or three
days — C is now a box script, so it lands together with the compose changes),
then docs. A is testable without B — a provider on a network with no proxy
simply has no egress, which is the safe default — so the pieces land as
separate pull requests and the box is never left half-wired.

## Addendum, 2026-09-16 — what C found when it read the host

Written before C's plan, after A (#119) and B (#120) merged. Six things the
section above leaves open, each settled by reading `apps/agents` rather than
by preference.

1. **How the box gets an instance admin without a human step.** Works in
   `authenticated` mode grants instance admin only to the first browser
   session that claims it (`POST /api/bootstrap/claim`, private exposure), and
   a board API key carries whatever rights its user has. So `nufi-box works
   install` signs in **as the box admin, through the same SSO path a browser
   takes**: the chat login (`ADMIN_EMAIL`/`ADMIN_PASSWORD`, which the box
   already holds for the ingest daemon) → the console's `/oidc/authorize` →
   Works' `/api/auth/oauth2/callback/nufi`. That session claims first admin
   and mints one board key (`WORKS_BOX_KEY` in `.env`) for every later call.
   No service account, no direct database write, no host change — and the
   admin's own browser lands on the same account, because it is the same
   OIDC identity. A separate password account for the admin was rejected:
   better-auth refuses to link an OAuth sign-in to an existing local user
   unless the provider asserts `email_verified`, which the console does not,
   so the admin would have had two accounts and the automation would have
   owned the wrong one.
2. **Environments are instance-wide.** The route is
   `/companies/:companyId/environments`, but the table has no company column,
   `instance_settings.default_environment_id` is the instance default the
   heartbeat resolves first, and upstream's `Local` row is one per instance.
   The register step therefore needs one company to exist and creates the
   box's (`BOX_NAME`) when there is none — the admin lands in it as owner.
3. **The sandbox image is the box's own.** Piece A defaults to
   `ghcr.io/dudaji-vn/nufi-sandbox:main`, which did not exist; upstream's
   per-adapter runtime images are published only under `git-<sha>` tags. C
   builds `deploy/box/sandbox/Dockerfile` in `box-images` — Ubuntu (GNU
   coreutils `timeout`, A's hard requirement), Node, git, the coding harnesses
   the box's adapter file enables — and registers it **by digest**, resolved
   after the installer pulls it.
4. **The model credential in a sandbox is a LiteLLM virtual key, never the
   master key.** The harness env reaches the sandbox, and `litellm-proxy` is on
   the egress allow list, so a master key there is a key to the gateway's
   admin API from inside untrusted code. `works install` mints
   `WORKS_MODEL_KEY` and the `works` service exposes it as the three names the
   adapters read.
5. **`works` and `works-egress` sit behind compose profile `works`**
   (`NUFI_WORKS=1` in `.env`, set by `--with-works`). B shipped the proxy on
   every box; the section above says a box without `--with-works` is
   byte-for-byte today's box, and the profile is what makes that true.
   `doctor`'s egress check already skips when the service is not defined.
6. **The socket reaches the provider's worker as uid 1000.** Upstream's
   entrypoint drops privileges with `gosu`, which discards `group_add`; run
   the container as `1000:1000` instead and the entrypoint execs directly,
   keeping the docker group (`DOCKER_GID`, read from the socket at install).
   Works-on-box stays Ubuntu-only: `--with-works` refuses on macOS, where
   Docker Desktop cannot host `runsc`.
