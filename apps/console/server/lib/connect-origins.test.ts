import { describe, expect, it } from 'bun:test';

import { matchAllowedOrigin, parseAllowedOrigins } from './connect-origins.ts';

describe('parseAllowedOrigins', () => {
  it('reads a comma-separated list and canonicalises each entry', () => {
    expect(parseAllowedOrigins('https://agents.nufi.me, http://localhost:5174')).toEqual([
      'https://agents.nufi.me',
      'http://localhost:5174',
    ]);
  });

  it('tolerates trailing slashes, paths, and mixed case in configuration', () => {
    expect(parseAllowedOrigins('https://Agents.NUFI.me/some/path')).toEqual([
      'https://agents.nufi.me',
    ]);
  });

  it('drops the default port so the two spellings of one origin agree', () => {
    expect(parseAllowedOrigins('https://agents.nufi.me:443')).toEqual(['https://agents.nufi.me']);
  });

  /** Unset must disable the feature, never open it. */
  it('returns nothing for unset, empty, or whitespace-only configuration', () => {
    expect(parseAllowedOrigins(undefined)).toEqual([]);
    expect(parseAllowedOrigins('')).toEqual([]);
    expect(parseAllowedOrigins('  ,  ')).toEqual([]);
  });

  it('discards entries that are not valid http(s) origins rather than failing to boot', () => {
    expect(parseAllowedOrigins('not-a-url, ftp://x.example, https://ok.example')).toEqual([
      'https://ok.example',
    ]);
  });

  /**
   * A wildcard in configuration is an operator asking for the exact hole this
   * allow-list exists to close. Refuse it rather than matching it literally and
   * letting someone believe it worked.
   */
  it('discards wildcard entries', () => {
    expect(parseAllowedOrigins('*, https://*.nufi.me, https://ok.example')).toEqual([
      'https://ok.example',
    ]);
  });
});

describe('matchAllowedOrigin', () => {
  const allowed = parseAllowedOrigins('https://agents.nufi.me, http://localhost:5174');

  it('returns the canonical origin on an exact match', () => {
    expect(matchAllowedOrigin('https://agents.nufi.me', allowed)).toBe('https://agents.nufi.me');
  });

  it('matches a spelling that canonicalises to an allowed origin', () => {
    expect(matchAllowedOrigin('https://agents.nufi.me/', allowed)).toBe('https://agents.nufi.me');
    expect(matchAllowedOrigin('https://AGENTS.nufi.me', allowed)).toBe('https://agents.nufi.me');
  });

  /**
   * The attacks this function exists to stop. Each of these is a hostname an
   * attacker can register or a scheme they can serve, and each would pass a
   * naive `includes`, `startsWith`, or `endsWith` check.
   */
  it.each([
    ['a suffix lookalike', 'https://evil-agents.nufi.me'],
    ['a subdomain of an attacker domain', 'https://agents.nufi.me.evil.com'],
    ['a prefix lookalike', 'https://agents.nufi.mevil.com'],
    ['a downgraded scheme', 'http://agents.nufi.me'],
    ['an unexpected port', 'https://agents.nufi.me:8443'],
    ['a different localhost port', 'http://localhost:9999'],
    ['the opaque origin of a sandboxed frame', 'null'],
    ['an unparseable value', 'javascript:alert(1)'],
    ['nothing at all', undefined],
    ['an empty string', ''],
  ])('refuses %s', (_label, candidate) => {
    expect(matchAllowedOrigin(candidate, allowed)).toBeNull();
  });

  it('refuses everything when nothing is configured', () => {
    expect(matchAllowedOrigin('https://agents.nufi.me', [])).toBeNull();
  });
});
