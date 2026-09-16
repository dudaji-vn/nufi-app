# @nufi/plugin-docker-sandbox

The sandbox provider that lets NUFI Works run on a NuFi box without
Kubernetes. Each run gets a container under **gVisor** on an **internal
network** whose only way out is the box's egress proxy.

Design and the decisions behind it:
[`docs/superpowers/specs/2026-09-16-works-on-box-design.md`](../../../../../../docs/superpowers/specs/2026-09-16-works-on-box-design.md).

## What every sandbox gets, and cannot change

| | |
|---|---|
| runtime | `runsc` — the provider refuses to report healthy without it |
| network | `works-sandbox`, declared `internal: true` in the box compose |
| egress | `HTTP_PROXY` / `HTTPS_PROXY` → `works-egress:3128`; a client that ignores them has no route |
| limits | memory, CPUs, pids from the config; defaults 2 GB / 2 / 512 |
| filesystem | read-only root, a per-run `/workspace` volume, a `noexec` tmpfs `/tmp` |
| privilege | none: all capabilities dropped, `no-new-privileges`, no Docker socket |

The config schema exposes the image, the limits, the proxy address and a
lifetime. It does not expose the runtime, the network or privilege, and
`manifest.test.ts` pins that: a provider that can be told to use `runc` is
one config line away from having no kernel boundary. A stored config that
says `runtime: runc` changes nothing — `container-spec.ts` never reads the
raw config — and `plugin.test.ts` proves it on the real acquire path.

## Lifetime

The manifest declares no `reuse_by_environment` lease, and the host only
ever calls destroy for a lease the manifest marks reusable — never for an
ordinary run. So release, not destroy, is the only cleanup call a normal
run gets, and `onEnvironmentReleaseLease` force-removes the container and
its named `/workspace` volume exactly as `onEnvironmentDestroyLease` does;
the e2b sibling does the same when it isn't asked to keep a lease alive.
A release is therefore final: `plugin.test.ts` also proves that resuming a
lease after it has been released throws — by design, not by omission —
rather than quietly standing up a fresh container in its place.

## The socket

The **provider** talks to the Engine over `/var/run/docker.sock`, mounted
into the `works` container. A process that can reach the daemon can start
any container on the box, as root — and, with nothing else in the way,
stop or remove any container on the box too. It is the same grant
`nufi-cron` deliberately avoids. It is accepted here because sibling
containers cannot be created any other way, and it is confined to the
`works` service — no sandbox has the mount. The cheapest confinement this
grant gets is `DockerClient.assertOurs`: every destructive call inspects
its target first and refuses to stop or remove a container missing the
`me.nufi.works.run` label, so a mislabeled or foreign container — another
plugin's, a co-located service's — cannot be torn down through this
provider.

## The deadline

The Engine API has no handle on a running exec. When a command outstays
`timeoutMs`, the provider **kills the container** (`SIGKILL`) rather than
merely stopping to listen: a client that walks away from a process still
running is the failure this whole design exists to avoid. It is a kill,
not a graceful stop — PID 1 is `sleep infinity`, which has nothing to shut
down for, so a `stop()` here would just be five more seconds of the daemon
waiting on a SIGTERM nobody is going to honour before it SIGKILLs anyway.
`HostConfig.Init: true` is set for the other stop path instead, so that a
graceful `stop()` on release stays prompt: `sleep infinity` ignores
SIGTERM on its own, and the init reaps and forwards the signal for it.
`docker.test.ts` asserts the kill call arrives on timeout.

A rejection from `exec()` itself leaves the container's state unknown —
the daemon connection may have dropped mid-command, or the post-timeout
kill may itself have failed — so the execute hook force-removes the
container through the same `assertOurs` guard and returns `exitCode:
null`, rather than claim to know what is still running in there.

## Tests

```sh
pnpm install
pnpm test
```

No Docker. `fake-docker.ts` is an Engine API over a unix socket that records
every call with its body, so the tests assert what was asked of Docker —
the runtime, the network, the mounts — rather than that a mock was called.
The one live proof is the box's own: `.github/workflows/gvisor-probe.yml`,
which showed `uname -r` inside `--runtime=runsc` reporting `4.19.0-gvisor`
on Ubuntu x86-64.

This package sits outside the pnpm workspace, like every provider upstream
ships, and installs on its own — the eighth sandbox provider beside
upstream's seven (cloudflare, daytona, e2b, exe-dev, kubernetes, modal,
novita). `agents-ci.yml` runs its tests; no provider's tests ran there
before this one.
