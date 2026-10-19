# nufibox-agent.ps1 -- the NuFi box mesh client for Windows.
#
# The Windows counterpart of the bash `nufibox-agent` wrapper: a member installs
# ONE thing (the signed NufiBox .msi) and joins the box's mesh with an invite's
# pre-auth key. No separate Tailscale download and no "Tailscale" shown; the
# engine underneath is tailscale (BSD-3), built with NufiBox names (see
# windows/debrand-engine.ps1) so it never collides with an official Tailscale
# install: service "NufiBox", adapter "NufiBox", state in %ProgramData%\NufiBox,
# pipe \\.\pipe\ProtectedPrefix\Administrators\NufiBox\tailscaled.
#
#   nufibox-agent enroll -Server <url> -AuthKey <key> [-Ca <file>] [-Hostname <name>]
#   nufibox-agent up | down | status | uninstall
#
# The .msi puts bin\nufibox-agent.cmd on PATH (this script stays off PATH, where
# PowerShell's default Restricted policy would refuse it). Every command needs an
# elevated shell: the daemon's pipe only admits Administrators (like sudo on
# Linux/macOS). Keep this file ASCII -- Windows PowerShell 5.1 reads a BOM-less
# script as ANSI.

param(
  [Parameter(Position = 0)][string]$Command = "",
  [string]$Server,
  [string]$AuthKey,
  [string]$Ca,
  [string]$Hostname = $env:COMPUTERNAME.ToLower()
)

$ErrorActionPreference = "Stop"
$Service    = "NufiBox"
$Pipe       = "ProtectedPrefix\Administrators\NufiBox\tailscaled"
$Tailscaled = Join-Path $PSScriptRoot "nufibox-tailscaled.exe"
$Tailscale  = Join-Path $PSScriptRoot "nufibox-tailscale.exe"

function Fail([string]$msg) { [Console]::Error.WriteLine("nufibox-agent: $msg"); exit 1 }

function Assert-Admin {
  $id = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
  if (-not $id.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Fail "run this from PowerShell opened with 'Run as administrator'"
  }
}

function Ts {
  & $Tailscale @args
  if ($LASTEXITCODE -ne 0) { Fail "nufibox-tailscale $($args[0]) failed (exit $LASTEXITCODE)" }
}

# Trust a CA in the machine Root store, like `certutil -addstore -f Root` in the
# join templates. Used for a self-hosted (internal-CA) coordinator, BEFORE the
# join; a public coordinator passes no -Ca and this is skipped.
function Trust-Ca([string]$path) {
  if (-not $path) { return }
  if (-not (Test-Path $path)) { Fail "-Ca file not found: $path" }
  certutil -addstore -f Root $path | Out-Null
  if ($LASTEXITCODE -ne 0) { Fail "could not trust the CA in $path (certutil exit $LASTEXITCODE)" }
}

function Pipe-Ready {
  [IO.Directory]::GetFiles("\\.\pipe\") -contains "\\.\pipe\$Pipe"
}

# The .msi registers and starts the service. For a zip/dev install, register it
# here with the SAME config the .msi uses: --no-logs-no-support on the service
# (the daemon's worker child inherits it via the environment, so nothing phones
# home), auto start, restart on failure.
function Daemon-Up {
  $svc = Get-Service -Name $Service -ErrorAction SilentlyContinue
  if (-not $svc) {
    New-Service -Name $Service -BinaryPathName "`"$Tailscaled`" --no-logs-no-support" `
      -DisplayName "NufiBox Mesh" -Description "Connects this computer to the NufiBox mesh." `
      -StartupType Automatic -DependsOn Dnscache, iphlpsvc, netprofm, WinHttpAutoProxySvc | Out-Null
    sc.exe failure $Service reset= 86400 actions= restart/1000/restart/1000/restart/1000 | Out-Null
    $svc = Get-Service -Name $Service
  }
  if ($svc.Status -ne "Running") { Start-Service $Service }
  for ($i = 0; $i -lt 60 -and -not (Pipe-Ready); $i++) { Start-Sleep -Milliseconds 500 }
  if (-not (Pipe-Ready)) { Fail "the NufiBox service did not come up (see Event Viewer > Windows Logs > Application, source NufiBox)" }
}

Assert-Admin
switch ($Command) {
  "enroll" {
    if (-not $Server)  { Fail "enroll needs -Server <coordinator URL>" }
    if (-not $AuthKey) { Fail "enroll needs -AuthKey <pre-auth key from the invite>" }
    Trust-Ca $Ca
    Daemon-Up
    # --unattended: keep the connection up across logoff/reboot with no tray app
    # (Windows otherwise ties the session to the GUI user that ran `up`).
    # Do NOT pass --advertise-tags: headscale v0.29.3 rejects RequestTags on a
    # pre-auth-key registration; the tag:member tag rides on the key itself.
    Ts up --login-server=$Server --auth-key=$AuthKey --hostname=$Hostname --accept-dns --unattended
    Write-Host "Joined the NuFi mesh as $Hostname."
  }
  "up"        { Daemon-Up; Ts up --unattended }
  "down"      { Ts down }
  "status"    { & $Tailscale status; exit $LASTEXITCODE }
  "uninstall" {
    # For a zip/dev install; the .msi removes its own service on uninstall.
    if (Pipe-Ready) { & $Tailscale down 2>$null }
    if (Get-Service -Name $Service -ErrorAction SilentlyContinue) {
      Stop-Service $Service -ErrorAction SilentlyContinue
      sc.exe delete $Service | Out-Null
    }
    Write-Host "NufiBox service removed (state kept in $env:ProgramData\NufiBox)."
  }
  default {
    Write-Host "usage: nufibox-agent enroll -Server <url> -AuthKey <key> [-Ca <file>] [-Hostname <name>] | up | down | status | uninstall"
    exit 2
  }
}
