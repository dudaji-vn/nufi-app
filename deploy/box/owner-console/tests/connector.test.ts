import { describe, expect, test } from 'bun:test';
import { join } from 'node:path';
import { macosPlan, renderConnector, safeMember, type ConnectorInput } from '../src/connector';

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
    expect(p.chatUrl).toBe('https://nufi.box.internal:3080/register');
    expect(p.enroll).toContain('nufibox-agent enroll');
    expect(p.enroll).toContain("--server 'https://coordinator.internal'");
    expect(p.enroll).toContain("--auth-key 'k-member-secret'");
    expect(p.enroll).toContain("--hostname 'ivy-nguyen'");
    expect(p.enroll).not.toContain('tailscale.com');
    expect(p.enroll).not.toContain('.command');                                  // not a downloadable script
  });

  test('trusts the box CA so chat opens without a warning (parity with linux/win)', () => {
    const p = macosPlan(base('macos'));
    expect(p.enroll).toContain("curl -fsS 'http://nufi.local/nufi-box-ca.crt'");
    expect(p.enroll).toContain('security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain');
    // box CA is trusted before the join
    expect(p.enroll.indexOf('add-trusted-cert')).toBeLessThan(p.enroll.indexOf('nufibox-agent enroll'));
  });

  test('a self-hosted coordinator fetches the coord CA and passes --ca; a public one does not', () => {
    const selfHost = macosPlan(base('macos'));
    expect(selfHost.enroll).toContain("curl -fsS 'http://nufi.local/agent/mesh-ca.crt'");
    expect(selfHost.enroll).toContain('--ca /tmp/nufi-ca.crt');
    const pub = macosPlan({ ...base('macos'), coordCaB64: '' });
    expect(pub.enroll).not.toContain('/agent/mesh-ca.crt');
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

describe('renderConnector — Linux (agent flow, installs the NuFi agent from the box)', () => {
  test('downloads the agent from the box and installs+enrols it — no tailscale.com', () => {
    const c = renderConnector(base('linux'), TEMPLATES);
    expect(c.filename).toBe('nufi-join-ivy-nguyen.sh');
    expect(c.body).toContain('http://nufi.local/agent/nufibox-agent-linux-$ARCH.tar.gz'); // from the box origin
    expect(c.body).toContain('nufibox-agent/install.sh');
    expect(c.body).toContain('--server "https://coordinator.internal"');
    expect(c.body).toContain('--auth-key "k-member-secret"');
    expect(c.body).toContain('--hostname "ivy-nguyen"');
    expect(c.body).toContain('/register');            // opens sign-up after joining
    expect(c.body).not.toContain('tailscale.com');
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
