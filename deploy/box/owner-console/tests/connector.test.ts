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
});

describe('safeMember', () => {
  test('reduces a display name to a safe label', () => {
    expect(safeMember('Ivy Nguyen')).toBe('ivy-nguyen');
    expect(safeMember('  @@@  ')).toBe('member');
    expect(safeMember('')).toBe('member');
  });
});

describe('renderConnector', () => {
  for (const os of ['macos', 'windows', 'linux'] as const) {
    test(`${os}: fills every placeholder and embeds the key, URL, host, CAs`, () => {
      const c = renderConnector(base(os), TEMPLATES);
      // No template placeholder is left unsubstituted.
      expect(c.body).not.toMatch(/@[A-Z_]+@/);
      expect(c.body).toContain('k-member-secret');
      expect(c.body).toContain('https://coordinator.internal');
      expect(c.body).toContain('nufi.box.internal');
      expect(c.body).toContain('ivy-nguyen');       // sanitized member as hostname
      expect(c.body).toContain('Ym94Y2E=');         // box CA
      expect(c.body).toContain('Y29vcmRjYQ==');     // coordinator CA
      expect(c.filename).toBe(`nufi-join-ivy-nguyen.${os === 'macos' ? 'command' : os === 'windows' ? 'cmd' : 'sh'}`);
    });
  }

  test('windows maps drives with net use from Z down', () => {
    const c = renderConnector(base('windows'), TEMPLATES);
    expect(c.body).toContain('net use Z: \\\\nufi.box.internal\\legal /persistent:yes');
    expect(c.body).toContain('net use Y: \\\\nufi.box.internal\\hr /persistent:yes');
  });

  test('macos maps drives with open smb://', () => {
    const c = renderConnector(base('macos'), TEMPLATES);
    expect(c.body).toContain('open "smb://nufi.box.internal/legal"');
  });

  test('linux maps drives with gio mount', () => {
    const c = renderConnector(base('linux'), TEMPLATES);
    expect(c.body).toContain('gio mount "smb://nufi.box.internal/legal"');
  });

  test('no departments -> a clear "no drives" line, not a broken @DRIVES@', () => {
    const c = renderConnector({ ...base('linux'), departments: [] }, TEMPLATES);
    expect(c.body).toContain('No drives were configured');
    expect(c.body).not.toContain('@DRIVES@');
  });

  test('a public coordinator (empty coord CA) leaves the placeholder empty, not literal', () => {
    const c = renderConnector({ ...base('linux'), coordCaB64: '' }, TEMPLATES);
    expect(c.body).not.toContain('@COORD_CA_B64@');
    expect(c.body).toContain('COORD_CA_B64=""');    // the template's empty-guard still holds
  });
});
