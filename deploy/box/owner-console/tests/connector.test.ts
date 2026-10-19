import { describe, expect, test } from 'bun:test';
import { join } from 'node:path';
import { macosPlan, renderConnector, safeMember, windowsPlan, type ConnectorInput } from '../src/connector';

// The real CLI templates — the point is that the console fills THESE, not a copy.
const TEMPLATES = join(import.meta.dir, '../../lib/join-templates');

const base = (os: ConnectorInput['os']): ConnectorInput => ({
  os,
  member: 'Ivy Nguyen',
  key: 'k-member-secret',
  serverUrl: 'https://coordinator.internal',
  boxMeshHost: 'nufi.box.internal',
  departments: ['legal', 'hr'],
  boxCaB64: 'Ym94Y2E=',
  coordCaB64: 'Y29vcmRjYQ==',
  boxUrl: 'http://nufi.local',
  agentSha256: {
    amd64: 'a'.repeat(64),
    arm64: 'b'.repeat(64),
  },
});

describe('safeMember', () => {
  test('reduces a display name to a safe label', () => {
    expect(safeMember('Ivy Nguyen')).toBe('ivy-nguyen');
    expect(safeMember('  @@@  ')).toBe('member');
    expect(safeMember('')).toBe('member');
  });
});

describe('renderConnector — Windows (template flow)', () => {
  test('fills every placeholder and embeds the key, URL, host, CAs', () => {
    const c = renderConnector(base('windows'), TEMPLATES);
    expect(c.body).not.toMatch(/@[A-Z_]+@/);           // no placeholder left
    expect(c.body).toContain('k-member-secret');
    expect(c.body).toContain('https://coordinator.internal');
    expect(c.body).toContain('nufi.box.internal');
    expect(c.body).toContain('ivy-nguyen');
    expect(c.body).toContain('Ym94Y2E=');              // box CA
    expect(c.body).toContain('Y29vcmRjYQ==');          // coordinator CA
    expect(c.filename).toBe('nufi-join-ivy-nguyen.cmd');
  });

  test('maps drives with net use from Z down, UNC path quoted', () => {
    const c = renderConnector(base('windows'), TEMPLATES);
    expect(c.body).toContain('net use Z: "\\\\nufi.box.internal\\legal" /persistent:yes');
    expect(c.body).toContain('net use Y: "\\\\nufi.box.internal\\hr" /persistent:yes');
  });

  test('lands the member on the sign-up page', () => {
    expect(renderConnector(base('windows'), TEMPLATES).body).toContain('https://nufi.box.internal:3080/register');
  });

  test('a public coordinator (empty coord CA) leaves no literal placeholder', () => {
    const c = renderConnector({ ...base('windows'), coordCaB64: '' }, TEMPLATES);
    expect(c.body).not.toContain('@COORD_CA_B64@');
  });
});

describe('macosPlan (signed .pkg + one-line enrol, no Gatekeeper warning)', () => {
  test('serves the signed pkg from the box and a paste-once enrol command', () => {
    const p = macosPlan(base('macos'));
    expect(p.pkgUrl).toBe('http://nufi.local/agent/nufibox-agent-macos.pkg');   // from the box origin
    expect(p.chatUrl).toBe('https://nufi.box.internal:3080/');   // "Open NuFi" fallback routes either member
    expect(p.enroll).toContain('nufibox-agent enroll');
    expect(p.enroll).toContain("--server 'https://coordinator.internal'");
    expect(p.enroll).toContain("--auth-key 'k-member-secret'");
    expect(p.enroll).toContain("--hostname 'ivy-nguyen'");
    expect(p.enroll).not.toContain('tailscale.com');
    expect(p.enroll).not.toContain('.command');                                  // not a downloadable script
  });

  test('a returning machine lands on sign-in, a fresh one on sign-up (one machine = one node)', () => {
    // Linux: the generated script decides from the agent's state dir and opens
    // the page it chose — sign-in when already set up, sign-up otherwise.
    const sh = renderConnector(base('linux'), TEMPLATES).body;
    expect(sh).toContain('LAND=register');
    expect(sh).toContain('if [ -d /var/lib/nufibox ]; then LAND=login; fi');
    expect(sh).toContain(':3080/$LAND');          // opens whichever it chose
    expect(sh).not.toContain(':3080/register"');  // never a hard-coded sign-up
    // macOS: the enrol command does the same, before enrol creates the state dir.
    const mac = macosPlan(base('macos')).enroll;
    expect(mac).toContain('[ -d /Library/NufiBox ] && P=login');
    expect(mac).toMatch(/open .*:3080\/'\$P/);    // opens the decided page
  });

  test('with a public base the pkg comes from the release; box when empty', () => {
    const pub = macosPlan({ ...base('macos'), agentPublicBase: 'https://github.com/dudaji-vn/nufi-app/releases/download', agentVersion: '1.102.3' });
    expect(pub.pkgUrl).toBe('https://github.com/dudaji-vn/nufi-app/releases/download/agent-macos-v1.102.3/nufibox-agent-macos.pkg');
    expect(macosPlan(base('macos')).pkgUrl).toBe('http://nufi.local/agent/nufibox-agent-macos.pkg'); // no base -> box
  });

  test('trusts the box CA AFTER joining, over the mesh, best effort (box-independent)', () => {
    const p = macosPlan(base('macos'));
    // the box CA is fetched over the MESH name (reachable once joined), not the box LAN origin
    expect(p.enroll).toContain("curl -fsS 'http://nufi.box.internal/nufi-box-ca.crt'");
    expect(p.enroll).toContain('security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain');
    expect(p.enroll).toContain('|| true');                       // best effort -- never blocks the join
    // and it runs AFTER enrol: nothing before enrol touches the box
    expect(p.enroll.indexOf('nufibox-agent enroll')).toBeLessThan(p.enroll.indexOf('add-trusted-cert'));
    expect(p.enroll).not.toContain('http://nufi.local/nufi-box-ca.crt'); // not the box LAN origin
  });

  test('a self-hosted coordinator EMBEDS the coord CA and passes --ca; a public one does not', () => {
    const selfHost = macosPlan(base('macos'));            // base() sets a coord CA
    expect(selfHost.enroll).toContain('base64 --decode > /tmp/nufi-ca.crt'); // embedded, not fetched from the box
    expect(selfHost.enroll).toContain('--ca /tmp/nufi-ca.crt');
    expect(selfHost.enroll).not.toContain('/agent/mesh-ca.crt');            // no box fetch for the coord CA
    const pub = macosPlan({ ...base('macos'), coordCaB64: '' });
    expect(pub.enroll).not.toContain('base64 --decode > /tmp/nufi-ca.crt');
    expect(pub.enroll).not.toContain('--ca ');
  });

  test('shell-quotes owner/coordinator values so a stray char cannot break the paste', () => {
    const evil = macosPlan({ ...base('macos'), serverUrl: "https://x'; rm -rf /; echo '", key: 'k' });
    // the dangerous chars survive only INSIDE single-quotes: the embedded quote is
    // escaped to '\'' and the whole value stays a single quoted --server argument,
    // so ; and rm never execute.
    expect(evil.enroll).toContain("--server 'https://x'\\''; rm -rf /; echo '\\'''");
    expect(evil.enroll).not.toContain("--server https://x");    // never an unquoted, splittable value
  });
});

describe('windowsPlan (signed .msi + one admin-PowerShell enrol)', () => {
  test('serves the signed msi from the box and a paste-once enrol command', () => {
    const p = windowsPlan(base('windows'));
    expect(p.msiUrl).toBe('http://nufi.local/agent/nufibox-agent-windows-amd64.msi');  // from the box origin
    expect(p.chatUrl).toBe('https://nufi.box.internal:3080/');   // "Open NuFi" fallback routes either member
    expect(p.enroll).toContain('$a = "$env:ProgramFiles\\NufiBox\\nufibox-agent.ps1"'); // full path: no stale-PATH miss
    expect(p.enroll).toContain("powershell -NoProfile -ExecutionPolicy Bypass -File $a enroll -Server 'https://coordinator.internal'");
    expect(p.enroll).not.toContain('nufibox-agent.cmd');   // cmd.exe would re-parse & and % in the values
    expect(p.enroll).toContain("-AuthKey 'k-member-secret'");
    expect(p.enroll).toContain("-Hostname 'ivy-nguyen'");
    expect(p.enroll).not.toContain('tailscale');
  });

  test('with a public base the msi comes from the release; box when empty', () => {
    const pub = windowsPlan({ ...base('windows'), agentPublicBase: 'https://github.com/dudaji-vn/nufi-app/releases/download/', agentVersion: '1.102.3' });
    expect(pub.msiUrl).toBe('https://github.com/dudaji-vn/nufi-app/releases/download/agent-windows-v1.102.3/nufibox-agent-windows-amd64.msi');
    expect(windowsPlan(base('windows')).msiUrl).toBe('http://nufi.local/agent/nufibox-agent-windows-amd64.msi'); // no base -> box
  });

  test('a returning machine lands on sign-in, a fresh one on sign-up -- decided before enrol, from the agent', () => {
    const e = windowsPlan(base('windows')).enroll;
    // the .msi's service creates %ProgramData%\NufiBox on a FRESH machine, so the
    // agent's own status (exit 0 only once joined) decides, not the dir
    expect(e).toContain("-File $a status *> $null; $p = if ($LASTEXITCODE -eq 0) { 'login' } else { 'register' }");
    expect(e).not.toContain('Test-Path');
    expect(e.indexOf('$a status')).toBeLessThan(e.indexOf('$a enroll'));
    expect(e).toContain("Start-Process ('https://nufi.box.internal:3080/' + $p)");  // opens the decided page
    expect(e).not.toContain(':3080/register');                                       // never a hard-coded sign-up
  });

  test('trusts the box CA AFTER joining, over the mesh, best effort, only if enrol succeeded', () => {
    const e = windowsPlan(base('windows')).enroll;
    expect(e).toContain("Invoke-WebRequest -UseBasicParsing 'http://nufi.box.internal/nufi-box-ca.crt'"); // mesh name
    expect(e).toContain('certutil -addstore -f Root');
    expect(e).toMatch(/try \{ Invoke-WebRequest .* \} catch \{\}/);   // best effort -- never blocks the join
    expect(e.indexOf('$a enroll')).toBeLessThan(e.indexOf('certutil'));
    expect(e).toMatch(/if \(\$LASTEXITCODE -eq 0\) \{ try \{ Invoke-WebRequest/); // gated on a successful enrol
    expect(e).not.toContain('http://nufi.local/nufi-box-ca.crt');      // not the box LAN origin
  });

  test('a self-hosted coordinator EMBEDS the coord CA and passes -Ca; a public one does not', () => {
    const selfHost = windowsPlan(base('windows'));           // base() sets a coord CA
    expect(selfHost.enroll).toContain("[IO.File]::WriteAllBytes(\"$env:TEMP\\nufi-ca.crt\", [Convert]::FromBase64String('Y29vcmRjYQ=='))");
    expect(selfHost.enroll).toContain('-Ca "$env:TEMP\\nufi-ca.crt"');
    expect(selfHost.enroll).not.toContain('/agent/mesh-ca.crt');      // no box fetch for the coord CA
    const pub = windowsPlan({ ...base('windows'), coordCaB64: '' });
    expect(pub.enroll).not.toContain('nufi-ca.crt');
    expect(pub.enroll).not.toContain('-Ca ');
  });

  test('PowerShell-quotes owner/coordinator values so a stray char cannot break the paste', () => {
    const evil = windowsPlan({ ...base('windows'), serverUrl: "https://x'; Remove-Item C:\\ -Recurse; '", key: 'k$(whoami)' });
    // inside '...' only '' escapes and nothing expands: the value stays ONE argument
    expect(evil.enroll).toContain("-Server 'https://x''; Remove-Item C:\\ -Recurse; '''");
    expect(evil.enroll).toContain("-AuthKey 'k$(whoami)'");          // single-quoted: $() never runs
    expect(evil.enroll).not.toContain('-Server https://x');
  });
});

describe('renderConnector — Linux (agent flow: public release, box as air-gap fallback)', () => {
  test('with no public base it installs from the box (air-gap) and enrols — no tailscale.com', () => {
    const c = renderConnector(base('linux'), TEMPLATES);   // base() sets no agentPublicBase -> box only
    expect(c.filename).toBe('nufi-join-ivy-nguyen.sh');
    expect(c.body).toContain('PUB=""');                                      // public path disabled
    expect(c.body).toContain('TGZ="nufibox-agent-linux-$ARCH.tar.gz"');
    expect(c.body).toContain('http://nufi.local/agent/$TGZ');                // box fallback URL
    expect(c.body).toContain('nufibox-agent/install.sh');
    expect(c.body).toContain('--server "https://coordinator.internal"');
    expect(c.body).toContain('--auth-key "k-member-secret"');
    expect(c.body).toContain('--hostname "ivy-nguyen"');
    expect(c.body).toContain('LAND=register');        // fresh member -> sign-up; a returning one -> sign-in
    expect(c.body).not.toContain('tailscale.com');
  });

  test('with a public base it downloads from the release first, the box as fallback', () => {
    const c = renderConnector(
      { ...base('linux'), agentPublicBase: 'https://github.com/dudaji-vn/nufi-app/releases/download', agentVersion: '1.102.3' },
      TEMPLATES,
    ).body;
    expect(c).toContain('PUB="https://github.com/dudaji-vn/nufi-app/releases/download"');
    expect(c).toContain('"$PUB/agent-linux-v1.102.3/$TGZ"');          // public release, tried first
    expect(c).toContain('"$PUB/agent-linux-v1.102.3/$TGZ.sha256"');   // verified against its own digest
    expect(c).toContain('http://nufi.local/agent/$TGZ');              // box still there as the fallback
    expect(c.indexOf('$PUB/agent-linux')).toBeLessThan(c.indexOf('/agent/$TGZ')); // public before box
  });

  test('trusts the box CA so the sign-up page opens without a cert warning (parity with mac/Win)', () => {
    const c = renderConnector(base('linux'), TEMPLATES).body;
    expect(c).toContain('BOX_CA_B64="Ym94Y2E="');           // the box CA IS embedded and installed
    expect(c).toContain('/usr/local/share/ca-certificates/nufi-box.crt');
    expect(c).toContain('update-ca-certificates');
    // absent box CA (public/edge case) leaves the guard empty, not a literal
    const noBoxCa = renderConnector({ ...base('linux'), boxCaB64: '' }, TEMPLATES).body;
    expect(noBoxCa).toContain('BOX_CA_B64=""');
  });

  test('verifies the downloaded tarball sha256 before running it as root', () => {
    const c = renderConnector(base('linux'), TEMPLATES).body;
    // both arches' expected digests are embedded, chosen by detected $ARCH
    expect(c).toContain(`amd64) WANT_SHA="${'a'.repeat(64)}"`);
    expect(c).toContain(`arm64) WANT_SHA="${'b'.repeat(64)}"`);
    expect(c).toContain('sha256sum "$TMP/agent.tgz"');
    // the check runs BEFORE the tarball is extracted/installed
    expect(c.indexOf('WANT_SHA')).toBeLessThan(c.indexOf('tar -xzf'));
    expect(c.indexOf('GOT_SHA" != "$WANT_SHA')).toBeLessThan(c.indexOf('install.sh'));
    expect(c).toContain('exit 3');                    // refuse on mismatch
  });

  test('an arch with no baked digest skips the check (graceful), not a literal', () => {
    const c = renderConnector({ ...base('linux'), agentSha256: { amd64: '', arm64: '' } }, TEMPLATES).body;
    expect(c).toContain('amd64) WANT_SHA="";;');      // empty -> `if [ -n "$WANT_SHA" ]` skips
    expect(c).toContain('arm64) WANT_SHA="";;');
  });

  test('maps the department drives after joining (best effort)', () => {
    const c = renderConnector(base('linux'), TEMPLATES).body;
    expect(c).toContain("gio mount 'smb://nufi.box.internal/legal'");
    expect(c).toContain("gio mount 'smb://nufi.box.internal/hr'");
  });

  test('detects the client architecture', () => {
    const b = renderConnector(base('linux'), TEMPLATES).body;
    expect(b).toContain('dpkg --print-architecture');
    expect(b).toMatch(/amd64/);
    expect(b).toMatch(/arm64/);
  });

  test('with a coordinator CA it writes it and passes --ca; without, it does not', () => {
    const withCa = renderConnector(base('linux'), TEMPLATES).body;
    expect(withCa).toContain('CA_B64="Y29vcmRjYQ=="');
    expect(withCa).toContain('CA_ARG="--ca');
    const noCa = renderConnector({ ...base('linux'), coordCaB64: '' }, TEMPLATES).body;
    expect(noCa).toContain('CA_B64=""');              // guarded: no --ca when empty
  });

  test('shell-escapes owner/coordinator values landing in a double-quoted context', () => {
    const evil = renderConnector(
      { ...base('linux'), serverUrl: 'https://x"; touch /tmp/pwned; echo "', key: 'k$(id)' },
      TEMPLATES,
    ).body;
    // the injected quote/`$(` must be neutralised, not left live before sudo
    expect(evil).not.toContain('"; touch /tmp/pwned; echo "');
    expect(evil).toContain('\\"');                    // the embedded " was escaped
    expect(evil).toContain('k\\$(id)');               // the $ was escaped, not expanded
  });
});
