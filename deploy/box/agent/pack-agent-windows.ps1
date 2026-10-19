# pack-agent-windows.ps1 -- build the NufiBox Agent for Windows as a SIGNED .msi:
# the member installs one thing, sees no "Tailscale", and SmartScreen raises no
# "unknown publisher" warning. The Windows analog of build-agent-macos.sh.
#
# The tailscale engine (BSD-3) is built HERE from a de-branded copy of the pinned
# source (windows/debrand-engine.ps1 -- see README-windows.md for why Windows
# needs a source patch, not just a rename). Runs on the Windows signing host with
# Go, WiX v4 and the Windows SDK's signtool; nothing here runs on the box or the
# member's machine.
#
#   .\pack-agent-windows.ps1                       # -> dist\nufibox-agent-windows-amd64.msi (+ .sha256)
#   .\pack-agent-windows.ps1 -TsVersion 1.102.3 -Arch amd64
#
# Signing: the Dudaji code-signing certificate in CurrentUser\My, picked by
# -CertThumbprint (or $env:NUFIBOX_SIGN_THUMBPRINT), else the newest valid one
# whose subject is $CertSubject. The key never leaves this machine.

param(
  [string]$TsVersion = $(if ($env:TS_VERSION) { $env:TS_VERSION } else { "1.102.3" }),
  [ValidateSet("amd64", "arm64")][string]$Arch = "amd64",
  [string]$CertThumbprint = $env:NUFIBOX_SIGN_THUMBPRINT,
  [string]$CertSubject = "DUDAJI VIETNAM COMPANY LIMITED",
  [string]$Out = (Join-Path $PSScriptRoot "dist")
)
$ErrorActionPreference = "Stop"

# Pinned third-party inputs (bump deliberately, with the new hash).
$WintunUrl    = "https://www.wintun.net/builds/wintun-0.14.1.zip"
$WintunSha256 = "07c256185d6ee3652e09fa55c0b673e2624b565e02c4b9091c79ca7d2f24ef51"
$WixVersion   = "4.0.6"
$WixUtilUrl   = "https://api.nuget.org/v3-flatcontainer/wixtoolset.util.wixext/$WixVersion/wixtoolset.util.wixext.$WixVersion.nupkg"
$WixUtilSha256 = "541168d58c299dd8d62e92ea1877489756cfa73a27fd6ec855cd6341c8447562"
$Timestamp    = "http://timestamp.digicert.com"

function Step([string]$msg) { Write-Host "==> $msg" }
function Need([string]$name, [string[]]$fallbacks) {
  $c = Get-Command $name -ErrorAction SilentlyContinue
  if ($c) { return $c.Source }
  foreach ($f in $fallbacks) { if ($f -and (Test-Path $f)) { return $f } }
  throw "$name is required (see windows-agent-plan.md prerequisites)"
}
function Run([string]$exe) {
  & $exe @args
  if ($LASTEXITCODE -ne 0) { throw "$(Split-Path -Leaf $exe) $($args[0]) failed (exit $LASTEXITCODE)" }
}
function Fetch([string]$url, [string]$sha, [string]$dest) {
  Invoke-WebRequest -UseBasicParsing $url -OutFile $dest
  $got = (Get-FileHash $dest -Algorithm SHA256).Hash.ToLower()
  if ($got -ne $sha) { throw "sha256 mismatch for $url (got $got, want $sha)" }
}

# --- pre-checks: tools + signing identity (fail before building anything) ----
$go   = Need "go" @("$env:LOCALAPPDATA\Programs\go\bin\go.exe", "$env:ProgramFiles\Go\bin\go.exe")
$wix  = Need "wix" @("$env:USERPROFILE\.dotnet\tools\wix.exe")
$sign = Need "signtool" @(Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kits\10\bin\*\x64\signtool.exe" -ErrorAction SilentlyContinue |
                          Sort-Object FullName -Descending | Select-Object -ExpandProperty FullName)
if (-not $env:DOTNET_ROOT -and (Test-Path "$env:LOCALAPPDATA\Microsoft\dotnet")) { $env:DOTNET_ROOT = "$env:LOCALAPPDATA\Microsoft\dotnet" }

$now = Get-Date
$cert = Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert |
  Where-Object { $_.NotAfter -gt $now -and $_.HasPrivateKey -and
                 ($(if ($CertThumbprint) { $_.Thumbprint -eq $CertThumbprint } else { $_.Subject -like "*CN=$CertSubject*" })) } |
  Sort-Object NotAfter -Descending | Select-Object -First 1
if (-not $cert) { throw "missing signing certificate: $(if ($CertThumbprint) { $CertThumbprint } else { "CN=$CertSubject" }) (valid, with private key, in CurrentUser\My)" }
Step "signing as $($cert.Subject.Split(',')[0]) ($($cert.Thumbprint)), expires $($cert.NotAfter.ToString('yyyy-MM-dd'))"
if ($cert.NotAfter -lt $now.AddDays(30)) { Write-Warning "the signing certificate expires within 30 days -- renew it" }

$work = Join-Path ([IO.Path]::GetTempPath()) "nufibox-pack-$([guid]::NewGuid().ToString('N').Substring(0,8))"
New-Item -ItemType Directory -Force $work | Out-Null
try {
  # --- de-branded engine ------------------------------------------------------
  # A throwaway module pins the tailscale version (go get the COMMAND packages so
  # every transitive go.sum entry is recorded), then a writable copy of that
  # exact source is patched and swapped in with a replace directive.
  $mod = Join-Path $work "mod"; New-Item -ItemType Directory $mod | Out-Null
  Push-Location $mod
  try {
    $env:CGO_ENABLED = "0"; $env:GOOS = "windows"; $env:GOARCH = $Arch
    Run $go mod init nufibox-agent-win
    Step "pinning tailscale.com@v$TsVersion"
    Run $go get "tailscale.com/cmd/tailscaled@v$TsVersion" "tailscale.com/cmd/tailscale@v$TsVersion"
    $srcDir = (& $go mod download -json "tailscale.com@v$TsVersion" | Out-String | ConvertFrom-Json).Dir
    if (-not $srcDir) { throw "could not locate the tailscale.com@v$TsVersion source" }
    Copy-Item $srcDir (Join-Path $mod "tailscale-src") -Recurse
    Get-ChildItem (Join-Path $mod "tailscale-src") -Recurse -File | ForEach-Object { $_.IsReadOnly = $false }
    Step "de-branding the engine source"
    & (Join-Path $PSScriptRoot "windows\debrand-engine.ps1") -Src (Join-Path $mod "tailscale-src")
    Run $go mod edit -replace "tailscale.com=./tailscale-src"

    $stage = Join-Path $work "stage"; New-Item -ItemType Directory -Force (Join-Path $stage "bin") | Out-Null
    $ld = "-X tailscale.com/version.longStamp=$TsVersion-nufibox -X tailscale.com/version.shortStamp=$TsVersion"
    Step "building the engine for windows/$Arch (CGO off)"
    Run $go build -trimpath -ldflags $ld -o (Join-Path $stage "nufibox-tailscaled.exe") tailscale.com/cmd/tailscaled
    Run $go build -trimpath -ldflags $ld -o (Join-Path $stage "nufibox-tailscale.exe")  tailscale.com/cmd/tailscale
    Copy-Item (Join-Path $mod "tailscale-src\LICENSE") (Join-Path $stage "LICENSE-tailscale.txt")
  } finally {
    Pop-Location
    Remove-Item Env:GOOS, Env:GOARCH, Env:CGO_ENABLED -ErrorAction SilentlyContinue
  }

  # --- wintun: the official signed DLL, unmodified, + its license ------------
  Step "fetching wintun (pinned)"
  $wt = Join-Path $work "wintun"; New-Item -ItemType Directory $wt | Out-Null
  Fetch $WintunUrl $WintunSha256 (Join-Path $wt "wintun.zip")
  Expand-Archive (Join-Path $wt "wintun.zip") (Join-Path $wt "x")
  Copy-Item (Join-Path $wt "x\wintun\bin\$Arch\wintun.dll") $stage
  Copy-Item (Join-Path $wt "x\wintun\LICENSE.txt") (Join-Path $stage "LICENSE-wintun.txt")

  Copy-Item (Join-Path $PSScriptRoot "nufibox-agent.ps1") $stage
  Copy-Item (Join-Path $PSScriptRoot "windows\nufibox-agent.cmd") (Join-Path $stage "bin")

  # --- sign the engine (wintun.dll already carries WireGuard's signature) ----
  Step "signing the engine binaries"
  $exes = @((Join-Path $stage "nufibox-tailscaled.exe"), (Join-Path $stage "nufibox-tailscale.exe"))
  Run $sign sign /sha1 $cert.Thumbprint /fd SHA256 /tr $Timestamp /td SHA256 /d "NufiBox Mesh" @exes
  Run $sign verify /pa /q @exes (Join-Path $stage "wintun.dll")

  # --- build + sign the .msi --------------------------------------------------
  Step "fetching the WiX util extension (pinned)"
  $wu = Join-Path $work "wixutil"; New-Item -ItemType Directory $wu | Out-Null
  Fetch $WixUtilUrl $WixUtilSha256 (Join-Path $wu "util.zip")
  Expand-Archive (Join-Path $wu "util.zip") (Join-Path $wu "x")

  New-Item -ItemType Directory -Force $Out | Out-Null
  $msi = Join-Path $Out "nufibox-agent-windows-$Arch.msi"
  $wixArch = @{ amd64 = "x64"; arm64 = "arm64" }[$Arch]
  Step "wix build -> $msi"
  Run $wix build (Join-Path $PSScriptRoot "windows\nufibox-agent.wxs") -arch $wixArch `
    -ext (Join-Path $wu "x\wixext4\WixToolset.Util.wixext.dll") `
    -d "PayloadDir=$stage" -d "Version=$TsVersion" -o $msi
  Remove-Item ([IO.Path]::ChangeExtension($msi, ".wixpdb")) -ErrorAction SilentlyContinue
  Step "signing the .msi"
  Run $sign sign /sha1 $cert.Thumbprint /fd SHA256 /tr $Timestamp /td SHA256 /d "NufiBox Mesh" $msi
  Run $sign verify /pa $msi

  # Plain lowercase hex, no newline: the shape app.ts shaOfFile expects.
  $sha = (Get-FileHash $msi -Algorithm SHA256).Hash.ToLower()
  [IO.File]::WriteAllText("$msi.sha256", $sha)
  Step "done: $msi ($([math]::Round((Get-Item $msi).Length / 1MB, 1)) MB, sha256 $sha)"
} finally {
  Remove-Item $work -Recurse -Force -ErrorAction SilentlyContinue
}
