import { describe, expect, test } from 'bun:test';
import { join } from 'node:path';
import { renderConnector, safeMember, type ConnectorInput } from '../src/connector';

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
});

describe('safeMember', () => {
  test('reduces a display name to a safe label', () => {
    expect(safeMember('Ivy Nguyen')).toBe('ivy-nguyen');
    expect(safeMember('  @@@  ')).toBe('member');
    expect(safeMember('')).toBe('member');
  });
});

describe('renderConnector — macOS/Windows (template flow, requires Tailscale)', () => {
  for (const os of ['macos', 'windows'] as const) {
    test(`${os}: fills every placeholder and embeds the key, URL, host, CAs`, () => {
      const c = renderConnector(base(os), TEMPLATES);
      expect(c.body).not.toMatch(/@[A-Z_]+@/);           // no placeholder left
      expect(c.body).toContain('k-member-secret');
      expect(c.body).toContain('https://coordinator.internal');
      expect(c.body).toContain('nufi.box.internal');
      expect(c.body).toContain('ivy-nguyen');
      expect(c.body).toContain('Ym94Y2E=');              // box CA
      expect(c.body).toContain('Y29vcmRjYQ==');          // coordinator CA
      expect(c.filename).toBe(`nufi-join-ivy-nguyen.${os === 'macos' ? 'command' : 'cmd'}`);
    });
  }

  test('windows maps drives with net use from Z down, UNC path quoted', () => {
    const c = renderConnector(base('windows'), TEMPLATES);
    expect(c.body).toContain('net use Z: "\\\\nufi.box.internal\\legal" /persistent:yes');
    expect(c.body).toContain('net use Y: "\\\\nufi.box.internal\\hr" /persistent:yes');
  });

  test('macos maps drives with open smb://, single-quoted; a space/metachar is quoted', () => {
    expect(renderConnector(base('macos'), TEMPLATES).body).toContain("open 'smb://nufi.box.internal/legal'");
    const hr = renderConnector({ ...base('macos'), departments: ['Human Resources'] }, TEMPLATES);
    expect(hr.body).toContain("open 'smb://nufi.box.internal/Human Resources'");
  });

  test('both land the member on the sign-up page', () => {
    for (const os of ['macos', 'windows'] as const) {
      expect(renderConnector(base(os), TEMPLATES).body).toContain('https://nufi.box.internal:3080/register');
    }
  });

  test('a public coordinator (empty coord CA) leaves the placeholder empty, not literal', () => {
    const c = renderConnector({ ...base('macos'), coordCaB64: '' }, TEMPLATES);
    expect(c.body).not.toContain('@COORD_CA_B64@');
    expect(c.body).toContain('COORD_CA_B64=""');
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
