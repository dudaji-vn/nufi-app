# NUFI Works on the box — spike findings

2026-09-16. The question was whether option B — a seventh sandbox provider that
runs untrusted agent code under Docker with gVisor as the runtime — is a
two-week job or a two-month one, and whether it can be done without disturbing
the rest of the box. Two probes: the runtime, and the provider contract.

## Verdict

**About three weeks, in three separable pieces, and the box's shape survives.**
Both probes are now finished. The runtime probe could not be run on the
development machine and was run instead on a GitHub Actions `ubuntu-latest`
runner — Ubuntu 24.04, x86-64, Docker Engine, which is the box's actual target
— and passed on the third attempt. The two failed attempts each corrected
something this note had taken from documentation. Everything below says which
claims come from reading and which from running.

## Probe 1 — can `runsc` be a Docker runtime on the box? *(finished: yes)*

Run as `.github/workflows/gvisor-probe.yml` on `ubuntu-latest`
(Ubuntu 24.04.5 LTS, kernel `6.17.0-1022-azure`, Docker Engine 28.0.4),
run 35048384818, all four steps green:

```
runtimes before:  io.containerd.runc.v2 runc
runsc version     release-20260907.0
runtimes after:   io.containerd.runc.v2 runc runsc

host kernel:      6.17.0-1022-azure
inside runc:      6.17.0-1022-azure          ← shares the host kernel
inside runsc:     4.19.0-gvisor              ← gVisor's own
[    0.000000] Starting gVisor...

package install: ok · python under gvisor: ok · file write: ok · outbound https: ok
PASS: on an internal network the sandbox has no route out (fails closed)
```

That last line is the property the egress design leans on: a sandbox placed on
a Docker `--internal` network cannot reach the world at all, so a forward proxy
on that network is the *only* way out rather than the polite one.

Two things the first two runs corrected, both taken from documentation rather
than seen:

- **The containerd shim is not published at `latest`** (404). It is not needed:
  Docker calls the runtime binary directly; the shim is for containerd's own
  path. The install is one binary and one `daemon.json` stanza.
- The "outbound HTTPS" check fetched the root of a GCS bucket, which answers
  400 to everyone. TLS had already succeeded — which was the point — and the
  probe still failed on its own choice of URL.

What was established before the run, and still holds:

- gVisor publishes `runsc` and its containerd shim for both `x86_64` and
  `aarch64` (checked: both return 200 from the release bucket). Docker
  documents `runsc` as a runtime installed by dropping the two binaries on the
  host and adding one stanza to `daemon.json`. No Kubernetes is involved in
  that path.
- The development machine is **Docker Desktop** (kernel `6.12.76-linuxkit`,
  `aarch64`). Its daemon runs inside a VM, so installing a runtime means writing
  binaries *into that VM*, which this session was not permitted to do. Not
  attempted a second time: it is the wrong target anyway.

What remains open:

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
| The provider: ten hooks over `dockerode`, tests against a fake daemon | ~1,200 lines, a week | a new package under `sandbox-providers/` |
| The egress proxy: a container, a config template rendered from the allow list, a test that a disallowed host fails closed | two or three days | `deploy/box/` compose and one Caddy-style template |
| Execution mode `"docker"` | a day | `execution-policy-bootstrap.ts` + tests |
| Works in the box compose: the service, the socket mount, `runsc` in `install-box.sh`, `doctor` checking the runtime is present | two or three days | `deploy/box/` |
| Docs | a day | `apps/docs` |

**Three weeks.** Probe 1 has passed on the target platform, so the conditional
is gone. The install step for the box is smaller than this table first
assumed: one binary, one `daemon.json` stanza, one daemon restart.

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

Proceed to a design document for the three pieces above. The probe workflow
stays in the repository as a manually triggered check, because the box's
installer will one day carry the same three lines and it is worth being able to
re-run the proof against a fresh gVisor release without rediscovering the shim.

Nothing else in this spike is code to keep.
