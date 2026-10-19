# NufiBox Agent on Windows

A member installs **one signed `.msi`** ("NufiBox Mesh", publisher Dudaji, with
no "Tailscale" shown anywhere). It runs the `NufiBox` service, and then the
member runs one elevated `nufibox-agent enroll …` command. The engine is
tailscale (BSD-3), the same version as Linux/macOS, de-branded at the source.
The remaining box-side steps (bake, `/connect`, docs) are in
[`windows-agent-plan.md`](./windows-agent-plan.md).

## Build

On the Windows signing host (see the Windows section of
[`README-signing.md`](./README-signing.md)):

```powershell
deploy\box\agent\pack-agent-windows.ps1     # -> dist\nufibox-agent-windows-amd64.msi (+ .sha256)
```

It pins tailscale, de-brands a copy of its source (`windows/debrand-engine.ps1`),
builds and signs the `.exe`s, fetches the pinned `wintun.dll`, builds the `.msi`
from `windows/nufibox-agent.wxs`, and signs it. CI runs the same script
(`.github/workflows/agent-windows.yml`).

The `.msi` installs to `%ProgramFiles%\NufiBox`: the engine, `wintun.dll`, the
wrapper, the license notices, and `bin\nufibox-agent.cmd`, which is on PATH. It
registers and starts the `NufiBox` service. Enrolment is never part of it.
Uninstall stops the service and removes the adapter, routes and firewall rules
(`--cleanup` plus deleting the rules by name), but keeps `%ProgramData%\NufiBox`.
An upgrade replaces in place (stable UpgradeCode).

`build-agent-windows.sh` is the original cross-compile scaffold. It does **not**
de-brand, so its binaries collide with an official Tailscale install. Do not
ship them.

## Confirmed on Windows 11 (tailscale 1.102.3, Go 1.27.0)

- **The engine must be de-branded at the source, not just renamed.** As a
  service, tailscaled re-execs itself as `/subproc <logid>` and that child never
  sees the service's flags, so `--tun`/`--statedir`/`--socket` on the binPath
  are dropped. Its defaults are hardcoded "Tailscale" (service, adapter name +
  tunnel type + a fixed adapter GUID, CLI pipe, state/log dirs, firewall rules),
  which are both visible to the member and identical to an official Tailscale
  install. `windows/debrand-engine.ps1` patches a copy of the pinned source
  before `go build`. Every patch must match an exact count, so a `TS_VERSION`
  bump that moves a line fails the build.
- **wintun is a DLL shipped alongside, not embedded.** Ship the official signed
  `wintun.dll` 0.14.1 (from wintun.net, amd64 build) unmodified next to the
  `.exe`s, with its LICENSE. Its terms allow redistributing the signed DLL
  unmodified. With it in place the daemon creates the adapter **`NufiBox`**
  ("NufiBox Tunnel", GUID `{c9878163-6f55-41ea-94dc-91da8a676e55}`, which must
  never change). No Tailscale-named adapter is created.
- **Service registration: a plain SCM service, no `install-system-daemon`.**
  The service is `NufiBox` (display "NufiBox Mesh"), binPath `"<dir>\nufibox-tailscaled.exe"
  --no-logs-no-support`, auto start, depends on Dnscache/iphlpsvc/netprofm/WinHttpAutoProxySvc,
  restart on failure. This is what `Daemon-Up` does and what the `.msi` must
  replicate.
- **Paths (patched defaults, no flags needed):** state
  `%ProgramData%\NufiBox\server-state.conf`, locked to SYSTEM + Administrators
  by the daemon on start. The CLI pipe is
  `\\.\pipe\ProtectedPrefix\Administrators\NufiBox\tailscaled`, so the CLI needs
  an elevated shell. Firewall rules are `NufiBox-Process` / `NufiBox-In`.

## Still needed

- **End-to-end enrol** of an installed `.msi` against the public coordinator with
  a fresh `nufi-box invite … --os windows` key: the host shows in
  `nufi-box members`, and the box's `/health` returns 200 over the mesh.
- **SmartScreen on a clean machine.** The publisher is now signed. An OV
  certificate (unlike EV) can still show a "not commonly downloaded" prompt
  until the file builds download reputation.
- **Box side** (plan steps 6–8): bake the `.msi` into the owner-console image,
  serve it at `/agent/`, flip the `/connect` Windows branch to `windowsPlan`, and
  update the docs. Until then, Windows members keep the official Tailscale flow.
