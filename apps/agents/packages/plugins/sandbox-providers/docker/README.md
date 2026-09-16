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
| limits | memory, CPUs, pids from the config; defaults 2 GB / 2 / 512. Memory has a floor of `6m`, Docker's own minimum: `"0"` is valid Docker syntax and means *unlimited*, so it is refused |
| filesystem | read-only root, a per-run `/workspace` volume, a `noexec` tmpfs `/tmp` |
| privilege | none: all capabilities dropped, `no-new-privileges`, no Docker socket |

The provider only requests `works-sandbox` by name; the box compose that
declares it (`internal: true`) is piece C and has not landed yet, so until
it does, a sandbox started on a box without that network simply fails —
Docker refuses to attach a container to a network it does not know, which
is the safe direction to fail in.

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
grant gets is `DockerClient.assertOurs`: every path that touches a
container — exec (and so realize's `mkdir` and the deadline's kill),
resume's `start`, release, destroy and the unknown-state removal —
inspects its target first and refuses one missing the `me.nufi.works.run`
label, so a mislabeled or foreign container — another plugin's, a
co-located service's — cannot be run in or torn down through this
provider. The verdict is cached per container id for the client's
lifetime: the host's run-log tail execs about four times a second, and a
label set at create never changes. A 404 is not cached; there is nothing
there to remember.

## The deadline

The Engine API has no handle on a running exec, so the deadline is
enforced where the process is: every exec with a `timeoutMs` runs as
`timeout -s KILL <seconds> <command>` inside the sandbox (the image is
ours; busybox and coreutils both ship `timeout`), and the caller's
deadline — or the environment's own `timeoutMs` when the caller sets none
— is always there. The provider's own timer is still the arbiter of
`timedOut: true`: when it fires, the result says so and the exit code is
`null`, whatever `timeout(1)` reports a moment later. The **command** is
what gets killed. Killing the container instead — the earlier design —
destroyed the agent's sandbox on any single slow command, and the host's
run-log tail execs every 250 ms with a 15 s deadline, tolerating a few
timeouts but not the sandbox vanishing under it.

The container is killed only as a fallback. If the provider's timer fires
and the stream has still not ended five seconds later
(`DEFAULT_KILL_GRACE_MS`), the command has outlived the one thing that was
supposed to stop it — it escaped `timeout(1)`, or the daemon never
answered the exec at all — and the provider tears down its own end and
SIGKILLs the container rather than walk away from a process still running,
which is the failure this whole design exists to avoid. It is a kill, not
a graceful stop: PID 1 is `sleep infinity`, which has nothing to shut down
for, so a `stop()` would just be five more seconds of the daemon waiting
on a SIGTERM nobody is going to honour. `docker.test.ts` pins both halves:
an ordinary timeout reaches no `/kill`; a stream that never ends does,
after the grace.

`HostConfig.Init: true` is for something else: a real init (`tini`) at
PID 1 in place of `sleep`, reaping the zombie processes left behind across
the many `exec()` calls a single run makes. There is no graceful-stop path
for it to keep prompt — release and destroy force-remove.

A rejection from `exec()` after the exec was created leaves the
container's state unknown — the daemon connection dropped mid-command —
and is typed as `SandboxStateUnknownError`; the execute hook force-removes
the container (and its volume) through the same `assertOurs` guard and
returns `exitCode: null`, rather than claim to know what is still running
in there. A rejection *before* that point — `assertOurs` refused, or the
daemon refused the exec itself — is a known state: nothing ran, and the
hook returns `exitCode: 1` with the message and removes nothing.

## Tests

```sh
# from apps/agents — the typecheck compiles the SDK with the workspace's tsc
pnpm install --frozen-lockfile --filter @paperclipai/plugin-sdk
# from this directory
pnpm install --frozen-lockfile --ignore-workspace
pnpm typecheck
pnpm test
```

No Docker. `fake-docker.ts` is an Engine API over a unix socket that records
every call with its body, so the tests assert what was asked of Docker —
the runtime, the network, the mounts — rather than that a mock was called.
It answers a hijacked exec (`Upgrade: tcp`, which is what an exec with
stdin sends) with a real `101` and records what arrived on the socket, so
the stdin test asserts the bytes delivered, not the flag that asked for
them.
The one live proof is the box's own: `.github/workflows/gvisor-probe.yml`,
which showed `uname -r` inside `--runtime=runsc` reporting `4.19.0-gvisor`
on Ubuntu x86-64.

This package sits outside the pnpm workspace, like every provider upstream
ships, and installs on its own — the eighth sandbox provider beside
upstream's seven (cloudflare, daytona, e2b, exe-dev, kubernetes, modal,
novita). `agents-ci.yml` runs its tests; no provider's tests ran there
before this one.
