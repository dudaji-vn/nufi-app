# Windows de-branded NufiBox Agent — executable plan

This is the runbook for finishing the **Windows** de-branded agent so it reaches
parity with macOS: a member installs **one signed thing** (no "Tailscale" shown,
no SmartScreen warning), then pastes **one enrol command**, and joins the box's
mesh without the box being reachable at install time.

It is written to be executed by an agent (or a person) working **on the Windows
machine** that holds the code-signing credential — the DigitalOcean Windows host.
Everything that does *not* need Windows (the box-side wiring in steps 6–8) can be
done from any machine and is called out as such.

**Mirror of the macOS pipeline — read these first, they are the reference:**

| Concern | macOS (done, copy its shape) | Windows (this plan) |
|---|---|---|
| Build + de-brand engine | `build-agent-macos.sh` | `build-agent-windows.sh` (scaffold) + new `pack-agent-windows.ps1` |
| Wrapper CLI | `nufibox-agent` (bash) | `nufibox-agent.ps1` (draft) |
| Installer | signed `.pkg` (pkgbuild + Developer ID Installer) | signed `.msi` (WiX) |
| "no warning" step | notarize + staple (`notarytool`/`stapler`) | Authenticode sign (Azure Trusted Signing / EV cert) |
| CI | `agent-macos.yml` (self-hosted mac runner, dispatch/tag only) | `agent-windows.yml` (self-hosted Windows runner, dispatch/tag only) |
| Signing doc | `README-signing.md` | add a Windows section there |
| Bake into box | box-images fetches `agent-macos-v*` `.pkg` → Dockerfile `cp` | fetch `agent-windows-v*` `.msi` → Dockerfile `cp` |
| Served at | `/agent/nufibox-agent-macos.pkg` | `/agent/nufibox-agent-windows-<arch>.msi` |
| `/connect` branch | `macosPlan` (download + enrol) | new `windowsPlan` (download + enrol) |

**The design this implements:** `onboarding-separation.md` (same directory). The
decisions there are settled — §"Decisions to confirm": keep the single-file join
alongside `/connect`; air-gap fallback is **automatic** (public release first,
box `/agent/` as fallback); the Windows target is the **de-branded signed `.msi`**
with official Tailscale as the interim. This plan does not reopen them.

---

## What is already proven (do not redo)

`build-agent-windows.sh` cross-compiles the de-branded engine from macOS/Linux
with `CGO_ENABLED=0 GOOS=windows` and ships `nufibox-tailscaled.exe` +
`nufibox-tailscale.exe` under nufibox names (PE32+ x86-64), zipped with the
wrapper. **The binaries build cleanly.** What is unproven is everything that
needs a Windows host: wintun at runtime, the service, the `.msi`, and signing.

## Global constraints (apply to every step)

- **De-branded:** the member never sees the word "Tailscale", and the installed
  product, service, and tray (if any) are named **NufiBox**. The engine is
  tailscale (BSD-3) under nufibox names — license notice ships in the `.msi`.
- **Version pin:** bundle **tailscale 1.102.3** (`TS_VERSION`), the same engine
  version as Linux/macOS and the box's `tailscale` image
  (`docker-compose.mesh.yml`). Keep all four in step.
- **Box-independent install (the whole point):** nothing in the download or the
  enrol command may require the box's LAN address. The coordinator (public) is
  the only thing that must be reachable to join; the box CA is trusted **after**
  the join, over the **mesh name**, best-effort — exactly as the macOS/Linux
  connectors now do (`macosPlan` / `renderConnector`). Do not reintroduce a
  box-LAN fetch.
- **Signing key never leaves the machine / never becomes a CI secret.** Same
  rule as the macOS Developer ID (`README-signing.md`): the Windows runner is
  self-hosted and signs in place.
- **Never add a `pull_request:` trigger** to `agent-windows.yml`. Untrusted PR
  code must not run on a self-hosted runner that can reach signing material.
  Dispatch + `agent-windows-v*` tag only (copy `agent-macos.yml`).

## Prerequisites on the Windows machine

Confirm (install what's missing) before starting:

- **Go** (`winget install GoLang.Go` or the MSI) — `go version` ≥ 1.22.
- **Git** + **GitHub CLI** (`gh`) authenticated to this repo (`gh auth status`).
- **WiX Toolset v4** (`dotnet tool install --global wix`) — `wix --version`.
- **The signing credential.** One of (decide in step 4 by what this machine
  actually has):
  - **Azure Trusted Signing** — an Azure subscription + a Trusted Signing
    account and certificate profile, and `AzureSignTool` (`dotnet tool install
    --global AzureSignTool`). Preferred: no physical token, CI-friendly, and the
    identity never sits on disk.
  - **A traditional OV/EV code-signing certificate** already importable on this
    host (`.pfx` in the user store, or an EV token). `signtool.exe` (ships with
    the Windows SDK).
- **A unit to test the daemon**: admin PowerShell (service registration needs
  elevation).

---

## Step 1 — Runtime check: wintun + the daemon (resolve the unknowns FIRST)

Everything downstream (the `.msi` payload, the service) depends on these answers.
Build the binaries locally and answer each question before writing the installer.

```powershell
# from a checkout of this repo, on the Windows machine
bash deploy/box/agent/build-agent-windows.sh          # or cross-build elsewhere and copy the zip over
Expand-Archive dist\nufibox-agent-windows-amd64.zip -DestinationPath C:\nufi-agent-test
cd C:\nufi-agent-test\nufibox-agent
```

Answer, writing each answer into `README-windows.md` as you confirm it:

1. **Does the engine embed wintun, or need `wintun.dll` alongside?**
   Run `.\nufibox-tailscaled.exe --help` and bring the daemon up once (step 2).
   If it fails to create an adapter, the build needs `wintun.dll` shipped next to
   the `.exe`. Tailscale's Windows build normally embeds wintun; **verify**, and
   if a DLL is needed, record its source + redistribution terms and add it to the
   `.msi` payload. Do not guess — a missing wintun is a silent "no adapter".
2. **Which service subcommand exists in THIS build?**
   `.\nufibox-tailscaled.exe --help` — look for `install-system-daemon` /
   `uninstall-system-daemon`. If present, that is how the service registers. If
   absent, fall back to an `sc.exe` service pointing at the `.exe` with explicit
   flags (see step 2). Record which path this build supports.
3. **State dir + socket + tun name** for Windows. Mirror the wrapper's
   conventions: a private state dir under `%ProgramData%\NufiBox`, a named pipe
   or local socket the CLI talks to, and the nufibox-named adapter (not
   `Tailscale`). Confirm the exact flags `nufibox-tailscaled.exe` accepts on
   Windows (they differ from Unix; `--state`, `--statedir`, `--tun` spellings).

**Deliverable:** the three answers recorded in `README-windows.md`, replacing its
"Still needed (requires a Windows machine)" bullets with the confirmed facts.

## Step 2 — Finish `nufibox-agent.ps1` `Daemon-Up`

`Daemon-Up` currently throws. Replace it with the path step 1 confirmed. Two
shapes, pick the one that matched:

**If `install-system-daemon` exists:**

```powershell
function Daemon-Up {
  New-Item -ItemType Directory -Force -Path (Join-Path $env:ProgramData 'NufiBox') | Out-Null
  $svc = Get-Service -Name 'nufibox-tailscaled' -ErrorAction SilentlyContinue
  if (-not $svc) {
    & $Tailscaled install-system-daemon    # registers + starts the service under a nufibox name
  } elseif ($svc.Status -ne 'Running') {
    Start-Service 'nufibox-tailscaled'
  }
}
```

**If it does not (sc.exe path):**

```powershell
function Daemon-Up {
  $state = Join-Path $env:ProgramData 'NufiBox'
  New-Item -ItemType Directory -Force -Path $state | Out-Null
  if (-not (Get-Service -Name 'nufibox-tailscaled' -ErrorAction SilentlyContinue)) {
    $bin = "`"$Tailscaled`" --statedir=`"$state`" --no-logs-no-support"   # confirm flag spellings in step 1
    & sc.exe create nufibox-tailscaled binPath= $bin start= auto DisplayName= "NufiBox Mesh" | Out-Null
  }
  Start-Service 'nufibox-tailscaled'
}
```

Keep `Trust-Ca` (System `Root` store via `certutil -addstore -f Root`) and the
`enroll` flow (`& $Tailscale up --login-server=$Server --auth-key=$AuthKey
--hostname=$Hostname --accept-dns`) — they mirror the tested Unix wrapper and the
`windows.cmd` template; the `--advertise-tags` omission is deliberate (headscale
0.29.3 rejects RequestTags on a pre-auth-key login; the `tag:member` tag rides on
the key). Add `uninstall`/`down` to stop+remove the service cleanly.

**Make it box-independent, like macOS/Linux now are:** `enroll` should trust the
**box** CA only AFTER the join, over the **mesh name** (reachable once joined),
best-effort — not before, and not from the box's LAN origin. The **coordinator**
CA (self-hosted box only) is passed with `-Ca` from a file the installer/plan
embeds, never fetched from the box. A public-coordinator box passes no `-Ca`.

**Test end to end** on this Windows host against the KR box's public coordinator
(`mesh.nufi.me`) with a fresh `nufi-box invite … --os windows` key: enrol → the
host appears in `./nufi-box members` → `https://<box>.box.nufi.me:3080/health`
returns 200 over the mesh. Record the result.

## Step 3 — Package the `.msi` (WiX v4)

Author `deploy/box/agent/windows/nufibox-agent.wxs` (new). The `.msi` lays down
the payload and registers the service so the member installs one thing:

- **Payload** into `%ProgramFiles%\NufiBox\`: `nufibox-tailscaled.exe`,
  `nufibox-tailscale.exe`, `nufibox-agent.ps1`, the BSD-3 license notice, and
  `wintun.dll` **only if** step 1 found it is not embedded.
- **Service:** register `nufibox-tailscaled` (ServiceInstall/ServiceControl in
  WiX, or a custom action running the confirmed `install-system-daemon`), started
  automatically, under the NufiBox display name.
- **PATH / shim (optional):** a `nufibox-agent` command on PATH so the enrol
  command the member pastes is literally `nufibox-agent enroll …` rather than a
  full `.ps1` path. If you keep the `.ps1`, the enrol command uses
  `powershell -ExecutionPolicy Bypass -File "...\nufibox-agent.ps1" enroll …`.
  Decide and make the `/connect` command (step 7) match exactly.
- **Enrolment is NOT in the installer.** The per-member key is always a separate
  step (same rule as the macOS `postinstall`, which only sets up the daemon).
- **Product metadata:** publisher "Dudaji", product "NufiBox Mesh", a stable
  UpgradeCode GUID (so a new version upgrades, not double-installs), version =
  `TS_VERSION`.

Build:

```powershell
wix build deploy\box\agent\windows\nufibox-agent.wxs `
  -d PayloadDir=C:\nufi-agent-test\nufibox-agent `
  -arch x64 -o dist\nufibox-agent-windows-amd64.msi
```

## Step 4 — Sign the binaries and the `.msi` (the "no SmartScreen warning" step)

This is the Windows equivalent of macOS notarization, and the last blocker for a
warning-free install. Apple Developer ID does nothing here. Sign **both** the
`.exe`s (before packaging) and the final `.msi`.

**Preferred — Azure Trusted Signing** (no token, reproducible in CI):

```powershell
AzureSignTool sign -kvu https://<region>.codesigning.azure.net `
  -kvc <cert-profile> -kvi <account> `
  -tr http://timestamp.acs.microsoft.com -td sha256 -fd sha256 `
  dist\nufibox-agent-windows-amd64.msi
```

**Alternative — EV / OV certificate already on this host:**

```powershell
signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 /a `
  dist\nufibox-agent-windows-amd64.msi
```

Always timestamp (so the signature outlives the cert). Verify:
`signtool verify /pa /v dist\nufibox-agent-windows-amd64.msi`. Then write the
digest: `(Get-FileHash dist\nufibox-agent-windows-amd64.msi -Algorithm SHA256).Hash.ToLower()
> dist\nufibox-agent-windows-amd64.msi.sha256` (plain-hex, the shape `app.ts`
`shaOfFile` expects).

**Decision for the Windows agent to make here:** report which credential this
machine actually has (Trusted Signing vs an EV cert) and sign with that one;
record it in `README-signing.md`'s new Windows section so CI (step 5) matches.

## Step 5 — `pack-agent-windows.ps1` + `.github/workflows/agent-windows.yml`

**`deploy/box/agent/pack-agent-windows.ps1`** (new): the one script that does
build → package → sign, the Windows analog of `build-agent-macos.sh`. It should:
cross-build or local-build the de-branded `.exe`s (reuse `build-agent-windows.sh`
output or call `go build` directly), sign the `.exe`s, `wix build` the `.msi`,
sign the `.msi`, and write the `.sha256`. Accept `-TsVersion` (default 1.102.3)
and `-Arch` (amd64, later arm64). Fail loudly if the signing credential is
missing (mirror `build-agent-macos.sh`'s identity pre-check).

**`.github/workflows/agent-windows.yml`** (new): copy `agent-macos.yml` exactly
and change only platform specifics:

```yaml
name: agent-windows
on:
  workflow_dispatch:
    inputs:
      ts_version: { description: Tailscale engine version to bundle (BSD-3), default: "1.102.3", required: true }
  push:
    tags: ['agent-windows-v*']
permissions:
  contents: write
jobs:
  build:
    runs-on: [self-hosted, windows]      # Dudaji's signing Windows host
    timeout-minutes: 60
    env:
      TS_VERSION: ${{ github.event.inputs.ts_version || '1.102.3' }}
    steps:
      - uses: actions/checkout@v4
      - name: Build, package, sign
        shell: pwsh
        run: deploy/box/agent/pack-agent-windows.ps1 -TsVersion $env:TS_VERSION -Arch amd64
      - uses: actions/upload-artifact@v4
        with:
          name: nufibox-agent-windows
          path: |
            deploy/box/agent/dist/nufibox-agent-windows-*.msi
            deploy/box/agent/dist/nufibox-agent-windows-*.msi.sha256
          if-no-files-found: error
      - name: Publish as a release asset
        env: { GH_TOKEN: ${{ github.token }} }
        shell: pwsh
        run: |
          $tag = "agent-windows-v$env:TS_VERSION"
          Set-Location deploy/box/agent/dist
          $files = Get-ChildItem nufibox-agent-windows-*.msi, nufibox-agent-windows-*.msi.sha256
          if (gh release view $tag 2>$null) { gh release upload $tag $files.Name --clobber }
          else { gh release create $tag --title "NufiBox Agent (Windows) $env:TS_VERSION" --notes "De-branded, signed NufiBox Agent .msi for Windows (amd64). Built on the self-hosted signing Windows host." $files.Name }
```

Register the self-hosted Windows runner scoped to this repo (Settings → Actions →
Runners → New → Windows), running as the signing user. **No `pull_request:`
trigger — ever.** Add a Windows section to `README-signing.md` describing the
runner + the credential, mirroring the macOS section.

## Step 6 — Bake the `.msi` into the box image (any machine)

In `.github/workflows/box-images.yml`, add a sibling to the macOS fetch step
(after it, same `if: matrix.name == 'nufi-owner-console'`):

```yaml
      - name: Fetch the signed Windows agent into the build context
        if: matrix.name == 'nufi-owner-console'
        env: { GH_TOKEN: ${{ secrets.GITHUB_TOKEN }} }
        run: |
          set -euo pipefail
          mkdir -p deploy/box/agent/dist
          TAG=$(gh release list --repo "$GITHUB_REPOSITORY" --limit 50 --json tagName \
                --jq 'map(select(.tagName|startswith("agent-windows-v")))|.[0].tagName // empty')
          if [ -n "$TAG" ]; then
            gh release download "$TAG" --repo "$GITHUB_REPOSITORY" \
              --pattern 'nufibox-agent-windows-*.msi' --dir deploy/box/agent/dist --clobber
          else
            echo "no agent-windows-v* release yet — box will 404 /agent/nufibox-agent-windows-*.msi until one is published"
          fi
```

In `deploy/box/owner-console/Dockerfile` (agentbuild stage, beside the macOS cp):

```dockerfile
RUN cp /agent-src/dist/nufibox-agent-windows-*.msi /dist/ 2>/dev/null || true
```

## Step 7 — Serve + offer it from `/connect` (any machine)

- **`deploy/box/owner-console/src/app.ts`** — extend `AGENT_FILE` so the `.msi`
  is served (and no other path):

  ```ts
  const AGENT_FILE = /^nufibox-agent-(linux-(amd64|arm64)\.tar\.gz|macos\.pkg|windows-(amd64|arm64)\.msi)$/;
  ```

  Set the content-type for `.msi` to `application/x-msi` (or
  `application/octet-stream`) in the `/agent/:file` handler.

- **`deploy/box/owner-console/src/connector.ts`** — add a `windowsPlan`, the
  analog of `macosPlan`: a download step + a one-line enrol command, **public
  release first, box `/agent/` as the fallback**, carrying `agentPublicBase` +
  `agentVersion` (already threaded through `app.ts` for mac/linux). Download URL:
  `${agentPublicBase}/agent-windows-v${agentVersion}/nufibox-agent-windows-amd64.msi`,
  else `${boxUrl}/agent/nufibox-agent-windows-amd64.msi`. Enrol command: the exact
  invocation step 3 settled (`nufibox-agent enroll …` or the `.ps1` form),
  PowerShell-quoted, coordinator CA embedded for a self-hosted box, box CA trusted
  post-join over the mesh. Switch the `/connect` POST handler's Windows branch
  from `renderConnector` (the `windows.cmd` Tailscale template) to `windowsPlan`,
  the way the macOS branch already returns `macosPlan`.

- **Keep the interim path working until the release exists.** Until a signed
  `agent-windows-v*` release is published AND verified end to end,
  `agentPublicBase` resolves the public URL but there is no asset, and the box
  fallback 404s unless the image baked it — so land steps 5–6 (a published,
  baked `.msi`) BEFORE flipping the `/connect` Windows branch off the Tailscale
  template. Order: 1–5 (produce + publish), 6 (bake), then 7 (flip). The
  `windows.cmd` template and `nufi-box invite --os windows` stay as the fallback
  per the settled decision.

- **Tests:** mirror the macOS connector tests in `tests/connector.test.ts` —
  `windowsPlan` with/without a public base (release vs box URL), the enrol command
  shape, post-join box-CA-over-mesh, embedded coord CA for self-host, and
  PowerShell-quoting of injected values. `bun test` green before PR.

## Step 8 — Docs (any machine)

- **`apps/docs/content/docs/box/members.mdx`** — the Windows bullet under "If you
  were sent a link" currently says to install Tailscale from tailscale.com.
  Replace with: download and run the signed NufiBox installer (no "unidentified
  publisher" warning), then paste the one enrol command — matching the Mac flow.
  Drop the Tailscale note for Windows once the de-branded path ships; keep the
  managed-device caveat.
- **`apps/docs/content/docs/box/reaching.mdx`** — the `nufi-box invite --os
  windows` path still uses official Tailscale (the CLI join file is unchanged by
  this plan); leave its Tailscale mention, since that path is the documented
  interim/fallback.

---

## Acceptance

1. **Warning-free install:** on a clean Windows host, the signed `.msi` installs
   with no SmartScreen "unknown publisher" prompt; the product shows as NufiBox,
   not Tailscale.
2. **Box-independent join from a different network:** download the `.msi` from the
   public `agent-windows-v*` release, paste the enrol command → the host joins the
   coordinator → `https://<box>.box.nufi.me:3080/health` returns 200 over the mesh.
   The box was never contacted to install.
3. **Air-gap:** on the box LAN with no internet, the `/connect` Windows plan's box
   `/agent/nufibox-agent-windows-amd64.msi` fallback serves the same `.msi`.
4. **Integrity:** the download is verified against the release's published
   `.sha256`; a tampered `.msi` is refused.
5. **CI:** `agent-windows.yml` on the self-hosted Windows runner publishes the
   signed `.msi` + `.sha256` to `agent-windows-v<version>`; box-images bakes it;
   `/agent/nufibox-agent-windows-amd64.msi` serves it. No `pull_request:` trigger.
6. **Owner-console tests green** (`bun test`), including the new `windowsPlan`
   tests.

## Order of operations (dependency-sorted)

1 (runtime check) → 2 (wrapper `Daemon-Up`, tested) → 3 (`.msi`) → 4 (sign) →
5 (`pack` script + workflow, first published release) → 6 (bake into box) →
7 (serve + flip `/connect`, with tests) → 8 (docs). Steps 1–5 need the Windows
machine; 6–8 do not. Do not flip `/connect` (7) before a real signed release is
published and baked (5–6), or Windows members lose the working Tailscale path.
