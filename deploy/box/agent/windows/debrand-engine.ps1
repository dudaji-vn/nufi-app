# debrand-engine.ps1 -- patch a COPY of the pinned tailscale source so the Windows
# engine runs under NufiBox names.
#
# Why a source patch (Windows only): on Linux/macOS the daemon's names come from
# flags/the launchd plist, so renaming the binaries is enough. On Windows they do
# not. Running as a service, tailscaled re-execs itself as `/subproc <logid>` and
# that child -- the one doing the work -- never sees the service's flags, so
# --tun/--statedir/--socket on an sc.exe binPath are silently dropped. The
# defaults it falls back to are hardcoded "Tailscale" names: the service, the
# wintun adapter (name, tunnel type and a FIXED adapter GUID), the CLI pipe, the
# state/log dirs and two Windows Firewall rules. Left alone they are both
# visible to the member and identical to an official Tailscale install, so the
# two would fight over one adapter, pipe, state file and firewall rules.
#
# Every replacement must match EXACTLY the expected number of times, or this
# fails -- a TS_VERSION bump that moves any of these lines is caught at build
# time, not on a member's machine. Only Windows code paths are touched.
#
#   debrand-engine.ps1 -Src <writable copy of tailscale.com@vX.Y.Z>

param([Parameter(Mandatory)][string]$Src)
$ErrorActionPreference = "Stop"

# Stable forever: changing it orphans the adapter on every installed member.
$AdapterGuid = "{c9878163-6f55-41ea-94dc-91da8a676e55}"

# file, regex, replacement, expected match count
$patches = @(
  # Service name (also the event-log source) and its SCM metadata.
  @("cmd/tailscaled/tailscaled_windows.go", 'const serviceName = "Tailscale"', 'const serviceName = "NufiBox"', 1),
  @("cmd/tailscaled/install_windows.go", 'DisplayName:(\s+)serviceName,', 'DisplayName:$1"NufiBox Mesh",', 1),
  @("cmd/tailscaled/install_windows.go", '"Connects this computer to others on the Tailscale network\."', '"Connects this computer to the NufiBox mesh."', 1),
  # Wintun adapter: default name, tunnel type, and the fixed GUID official
  # Tailscale also uses (sharing it would hijack/remove the other's adapter).
  @("cmd/tailscaled/tailscaled.go", '(case "windows":\s+return )"Tailscale"', '$1"NufiBox"', 1),
  @("net/tstun/tun_windows.go", 'tun\.WintunTunnelType = "Tailscale"', 'tun.WintunTunnelType = "NufiBox"', 1),
  @("net/tstun/tun_windows.go", '\{37217669-42da-4657-a55b-0d995d328250\}', $AdapterGuid, 1),
  # CLI <-> daemon named pipe (the CLI is built from the same patched source).
  @("paths/paths.go", '\\Administrators\\Tailscale\\tailscaled', '\Administrators\NufiBox\tailscaled', 1),
  # State, legacy state, logs, syspolicy file: %ProgramData%\NufiBox.
  @("paths/paths.go", '(os\.Getenv\("ProgramData"\), )"Tailscale"(, "server-state\.conf")', '$1"NufiBox"$2', 1),
  @("paths/paths.go", '(os\.Getenv\("LocalAppData"\), )"Tailscale"(, "server-state\.conf")', '$1"NufiBox"$2', 1),
  @("logpolicy/logpolicy.go", '(?m)^(\s+dir := filepath\.Join\(os\.Getenv\("(ProgramData|LocalAppData)"\), )"Tailscale"\)', '$1"NufiBox")', 2),
  @("cmd/tailscaled/syspolicy.go", '(filepath\.Join\(pd, )"Tailscale"(, "syspolicy\.json"\))', '$1"NufiBox"$2', 1),
  # The state-dir ACL lockdown (LocalSystem + Administrators only) keys off the
  # dir's base name. Without this the renamed dir -- holding the machine key --
  # would keep %ProgramData%'s default ACL (readable by Users).
  @("paths/paths_windows.go", '!= "tailscale" \{', '!= "nufibox" {', 1),
  # Windows Firewall rules: each daemon deletes these by name on start.
  @("wgengine/router/osrouter/router_windows.go", '"name=Tailscale-In"', '"name=NufiBox-In"', 2),
  @("wgengine/router/osrouter/router_windows.go", '"name=Tailscale-Process"', '"name=NufiBox-Process"', 2)
)

foreach ($p in $patches) {
  $file, $re, $rep, $want = $p
  $path = Join-Path $Src $file
  if (-not (Test-Path $path)) { throw "debrand: missing $file (upstream layout changed?)" }
  $text = [IO.File]::ReadAllText($path)
  $got = ([regex]::Matches($text, $re)).Count
  if ($got -ne $want) { throw "debrand: $file expected $want match(es) of /$re/, found $got -- re-check this patch for the new TS_VERSION" }
  [IO.File]::WriteAllText($path, [regex]::Replace($text, $re, $rep))
  Write-Host "  patched $file ($got)"
}
Write-Host "==> engine de-branded ($($patches.Count) patches)"
