# NufiBox Agent on Windows (scaffold)

The Windows agent is **scaffolded, not finished**. This records exactly what is
proven and what still needs a Windows machine and a certificate, so the work can
be picked up without re-discovering it.

## Proven here (cross-compiled from macOS/Linux)

`build-agent-windows.sh` compiles the de-branded engine for Windows with Go
(`CGO_ENABLED=0 GOOS=windows`), ships it under nufibox names, and zips it with the
wrapper:

```
./build-agent-windows.sh          # -> dist/nufibox-agent-windows-amd64.zip
```

`nufibox-tailscaled.exe` and `nufibox-tailscale.exe` build cleanly (PE32+ x86-64)
— no Windows host is needed to *produce* the binaries. This is the same BSD-3
engine the Linux and macOS agents use.

## Still needed (requires a Windows machine)

- **Runtime check.** Confirm `nufibox-tailscaled.exe` drives a **wintun**
  interface and that wintun ships correctly (embedded in the build vs a
  `wintun.dll` that must travel alongside — and its redistribution terms).
- **Service registration.** Decide how the daemon runs as a Windows service
  (`install-system-daemon` if this build exposes it, or an `sc.exe` service) and
  finish `Daemon-Up` in `nufibox-agent.ps1` (currently a `TODO` that throws).
- **`nufibox-agent.ps1`.** The wrapper is a DRAFT: argument parsing, the
  `certutil -addstore -f Root` CA trust, and `tailscale up` mirror the tested
  Linux/macOS wrappers, but nothing here has run on Windows. Verify end to end.
- **Installer.** Package into a `.msi` (WiX) or a signed installer that lays down
  the binaries + wrapper and registers the service, so the member installs one
  thing.

## Still needed (requires a certificate — from the repo owner)

- **Code signing.** Sign the `.exe`s and the installer so SmartScreen does not
  warn — needs an **EV code-signing certificate** or **Azure Trusted Signing**.
  The Apple Developer ID used for macOS does nothing on Windows. This is the
  Windows equivalent of the macOS notarization step, and the last blocker for a
  warning-free Windows install.

## Where it plugs in

Once a signed Windows installer exists, it slots in exactly like macOS:
`agent-macos.yml` has a sibling that publishes a `agent-windows-v*` release,
box-images bakes the artifact into the owner-console image, and the `/connect`
page's Windows branch installs it instead of today's Tailscale-app connector.
Until then, Windows members keep using the official Tailscale flow.
