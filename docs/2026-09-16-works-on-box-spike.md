# NUFI Works on the box — spike findings

2026-09-16. The question was whether option B — a seventh sandbox provider that
runs untrusted agent code under Docker with gVisor as the runtime — is a
two-week job or a two-month one, and whether it can be done without disturbing
the rest of the box. Two probes: the runtime, and the provider contract.

## Verdict

**About three weeks, in three separable pieces, and the box's shape survives.**
One of the two probes could not be finished on the development machine and has
to be run on Ubuntu before any code is written. Everything below says which
claims come from reading and which from running.

## Probe 1 — can `runsc` be a Docker runtime on the box? *(not finished)*

What is established:

- gVisor publishes `runsc` and its containerd shim for both `x86_64` and
  `aarch64` (checked: both return 200 from the release bucket). Docker
  documents `runsc` as a runtime installed by dropping the two binaries on the
  host and adding one stanza to `daemon.json`. No Kubernetes is involved in
  that path.
- The development machine is **Docker Desktop** (kernel `6.12.76-linuxkit`,
  `aarch64`). Its daemon runs inside a VM, so installing a runtime means writing
  binaries *into that VM*, which this session was not permitted to do. Not
  attempted a second time: it is the wrong target anyway.

What is not established, and blocks writing code:

- **That `runsc` starts a container on the box's actual target, Ubuntu 24.04 on
  x86-64, with Docker Engine.** This is the platform gVisor is built for and
  documented on, so the expectation is that it works — but "documented" is not
  "seen", and the difference has cost this project before. The check is ten
  minutes on any Ubuntu machine:

  ```sh
  curl -fsSL -o /usr/local/bin/runsc https://storage.googleapis.com/gvisor/releases/release/latest/x86_64/runsc
  curl -fsSL -o /usr/local/bin/containerd-shim-runsc-v1 https://storage.googleapis.com/gvisor/releases/release/latest/x86_64/containerd-shim-runsc-v1
  chmod +x /usr/local/bin/runsc /usr/local/bin/containerd-shim-runsc-v1
  # daemon.json: {"runtimes": {"runsc": {"path": "/usr/local/bin/runsc"}}}
  systemctl restart docker
  docker run --rm --runtime=runsc alpine:3.20 dmesg | head -3   # prints gVisor's own kernel banner
  ```

  The last line is the whole test: under gVisor, `dmesg` inside the container
  shows gVisor's synthetic boot messages rather than the host kernel's.

- **Apple Silicon.** gVisor ships `aarch64` binaries, but Docker Desktop is the
  only Docker most Macs have, and it does not let an operator add a runtime
  without going through its VM. Works-on-box on a Mac is a separate question
  and should be answered "not on Docker Desktop" until someone shows otherwise.
  This matters only because the demo machine is a Mac; the product target is
  not.

## Probe 2 — how wide is the provider contract? *(finished, by reading)*

A sandbox provider is a plugin that implements **ten hooks**. Read from the E2B
provider, which is the leanest complete one (1,266 lines including its config
parsing and tests); the Kubernetes provider is 3,237 lines because most of it
is Kubernetes.

| Hook | What it must do | Docker equivalent |
|---|---|---|
| `setup` | log readiness | — |
| `onHealth` | say whether the provider can work | `docker info` reachable, `runsc` listed in runtimes |
| `onEnvironmentValidateConfig` | reject a bad config before use | check image name, limits, allowed hosts parse |
| `onEnvironmentProbe` | can a lease be acquired right now? | daemon reachable |
| `onEnvironmentAcquireLease` | create a sandbox, return an id | `docker create --runtime=runsc …`, return the container id |
| `onEnvironmentResumeLease` | reattach to an existing sandbox | `docker inspect <id>`, start if stopped |
| `onEnvironmentReleaseLease` | stop but keep | `docker stop` |
| `onEnvironmentDestroyLease` | remove | `docker rm -f` |
| `onEnvironmentRealizeWorkspace` | make the working directory exist | `mkdir -p` inside the container |
| `onEnvironmentExecute` | run a command, return exit/stdout/stderr, honour a timeout | `docker exec` with the deadline |

Every one of those maps onto a single Docker operation. There is no hook that
needs Kubernetes concepts. The provider talks to the daemon over the socket
(`dockerode` is the usual library), which means **the Works container needs the
Docker socket mounted** — the same trust the box already extends to nothing
else, and worth a line in the design. `dockerode` would be a new dependency;
nothing in `apps/agents` uses it today.

**Plugins are loaded from a local path.** `plugin-dev-watcher.ts` documents
"plugins installed from a local path", so the seventh provider can live in the
monorepo next to the other six and be installed on the box without an npm
publish.

## The two things that are not "just Docker"

### Egress by hostname

This is the reason the cloud cluster needs Cilium: the execution policy
restricts a sandbox's outbound traffic to a list of hostnames, and ordinary
network policy cannot express a hostname. Under Docker there is no Cilium, so
the same guarantee has to come from somewhere else. Two options, and the
first is the one to take:

- **A forward proxy the sandbox cannot bypass.** Put each sandbox on an
  internal Docker network with no route out, and give it exactly one way to
  the world: an HTTP CONNECT proxy on that network which consults the allow
  list. Squid or tinyproxy does this in a dozen lines of config. The sandbox
  sees `HTTP_PROXY`/`HTTPS_PROXY`; anything that ignores those variables has no
  route and fails closed. The proxy also gives you a log of every hostname a
  sandbox tried, which the Cilium path has to work for.
- gVisor's own network stack can also filter, but per-hostname rules there are
  not a documented feature and this is not the place to be first.

### Execution mode

`execution-policy-bootstrap.ts:75` accepts exactly two values for
`PAPERCLIP_EXECUTION_MODE`: `"kubernetes"` or `"any"`. A box provider needs a
third, `"docker"`, or the bootstrap has to be generalised to "the named
provider and nothing else". That is a small change in one file plus its tests,
but it is a change to the host, not to a plugin — the one place this work
touches something the cloud deployment also runs.

## What it costs

| Piece | Size | Touches |
|---|---|---|
| Probe 1 on Ubuntu | one morning | nothing in the repo |
| The provider: ten hooks over `dockerode`, tests against a fake daemon | ~1,200 lines, a week | a new package under `sandbox-providers/` |
| The egress proxy: a container, a config template rendered from the allow list, a test that a disallowed host fails closed | two or three days | `deploy/box/` compose and one Caddy-style template |
| Execution mode `"docker"` | a day | `execution-policy-bootstrap.ts` + tests |
| Works in the box compose: the service, the socket mount, `runsc` in `install-box.sh`, `doctor` checking the runtime is present | two or three days | `deploy/box/` |
| Docs | a day | `apps/docs` |

**Three weeks** if probe 1 passes on Ubuntu. If it does not, option B is dead
and the honest fallback is option A (k3s on the box), which is a different
project.

## What it does not disturb

The user's constraint was that this must not affect the rest of the box much.
Checked against the list above:

- No existing service changes. Works is one more service in compose, like
  `nufi-cron` was.
- No existing image changes. The provider is a new package; the one host change
  is a third accepted value for an environment variable.
- `install-box.sh` gains one optional step (install `runsc`, add the runtime
  stanza) that a box without Works can skip.
- The box stays Docker Compose. Nothing here needs Kubernetes, and the
  installer stays one command.

The only new trust boundary is the Docker socket in the Works container. That
is real and should be stated in the design rather than discovered: a process
that can talk to the daemon can start any container on the box.

## Recommendation

Run probe 1 on an Ubuntu machine first. It is ten minutes, it needs nothing
from the repository, and every other line in this note depends on it. If
`dmesg` under `--runtime=runsc` prints gVisor's banner, proceed to a design
document for the three pieces above; if it does not, stop and reconsider A.

Nothing in this spike is code to keep.
