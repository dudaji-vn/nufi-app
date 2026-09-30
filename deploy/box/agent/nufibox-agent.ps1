# nufibox-agent.ps1 — the NuFi box mesh client for Windows (DRAFT).
#
# The Windows counterpart of the bash `nufibox-agent` wrapper: a member installs
# ONE thing (this, with a de-branded tailscaled.exe bundled alongside — see
# build-agent-windows.sh) and joins the box's mesh with an invite's pre-auth key.
# No separate Tailscale download and no "Tailscale" shown; the engine underneath
# is tailscale (BSD-3), shipped under nufibox names.
#
#   nufibox-agent.ps1 enroll -Server <url> -AuthKey <key> [-Ca <file>] [-Hostname <name>]
#   nufibox-agent.ps1 up | down | status
#
# STATUS: DRAFT — cross-compiled binaries build (build-agent-windows.sh), but this
# wrapper has NOT been run on Windows yet. The certificate-trust and `tailscale
# up` lines mirror the Linux/macOS wrappers and are safe; the daemon/service
# registration (marked TODO) must be confirmed on a real Windows host before this
# ships. Do not treat it as verified. See README-windows.md.

param(
  [Parameter(Position = 0)][string]$Command = "",
  [string]$Server,
  [string]$AuthKey,
  [string]$Ca,
  [string]$Hostname = $env:COMPUTERNAME
)

$ErrorActionPreference = "Stop"
$InstallDir = Join-Path $env:ProgramFiles "NufiBox"
$Tailscaled = Join-Path $PSScriptRoot "nufibox-tailscaled.exe"
$Tailscale  = Join-Path $PSScriptRoot "nufibox-tailscale.exe"

function Trust-Ca([string]$path) {
  if (-not $path) { return }
  if (-not (Test-Path $path)) { throw "--ca file not found: $path" }
  # System root store, like `certutil -addstore -f Root` in the join templates.
  certutil -addstore -f Root $path | Out-Null
}

function Daemon-Up {
  # TODO(windows): confirm on a real host. tailscaled on Windows runs as a
  # service; the MSI normally registers it. From this stand-alone .exe the
  # intended path is `nufibox-tailscaled.exe install-system-daemon` (verify the
  # subcommand exists in this build) or an sc.exe service pointing at the .exe
  # with its own state dir. wintun: confirm the .exe drives a wintun interface
  # (embedded vs a wintun.dll that must ship alongside).
  throw "Daemon-Up is not implemented for Windows yet — see README-windows.md"
}

switch ($Command) {
  "enroll" {
    if (-not $Server)  { throw "enroll needs -Server <coordinator URL>" }
    if (-not $AuthKey) { throw "enroll needs -AuthKey <pre-auth key from the invite>" }
    Trust-Ca $Ca
    Daemon-Up
    # Do NOT pass --advertise-tags: headscale v0.29.3 rejects RequestTags on a
    # pre-auth-key registration; the tag:member tag rides on the key itself.
    & $Tailscale up --login-server=$Server --auth-key=$AuthKey --hostname=$Hostname --accept-dns
    Write-Host "Joined the NuFi mesh as $Hostname."
  }
  "up"     { Daemon-Up; & $Tailscale up }
  "down"   { & $Tailscale down }
  "status" { & $Tailscale status }
  default  { Write-Host "usage: nufibox-agent.ps1 enroll -Server <url> -AuthKey <key> [-Ca <file>] [-Hostname <name>] | up | down | status" }
}
