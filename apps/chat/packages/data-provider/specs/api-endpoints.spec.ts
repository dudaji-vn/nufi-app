/**
 * @jest-environment jsdom
 */
import { buildLoginRedirectUrl, teamMember, teamMemberRole } from '../src/api-endpoints';

describe('buildLoginRedirectUrl', () => {
  afterEach(() => {
    window.history.replaceState({}, '', '/');
  });

  it('builds a login URL from explicit args', () => {
    const result = buildLoginRedirectUrl('/c/new', '?q=hello', '');
    expect(result).toBe('/login?redirect_to=%2Fc%2Fnew%3Fq%3Dhello');
  });

  it('encodes complex paths with query and hash', () => {
    const result = buildLoginRedirectUrl('/c/new', '?q=hello&submit=true', '#section');
    expect(result).toContain('redirect_to=');
    const encoded = result.split('redirect_to=')[1];
    expect(decodeURIComponent(encoded)).toBe('/c/new?q=hello&submit=true#section');
  });

  it('falls back to window.location when no args provided', () => {
    window.history.replaceState({}, '', '/c/abc123?model=gpt-4#msg-5');
    const result = buildLoginRedirectUrl();
    const encoded = result.split('redirect_to=')[1];
    expect(decodeURIComponent(encoded)).toBe('/c/abc123?model=gpt-4#msg-5');
  });

  it('returns plain /login when all location parts are empty (root)', () => {
    window.history.replaceState({}, '', '/');
    const result = buildLoginRedirectUrl();
    expect(result).toBe('/login');
  });

  it('returns plain /login when pathname is /login (prevents recursive redirect)', () => {
    const result = buildLoginRedirectUrl('/login', '?redirect_to=%2Fc%2Fnew', '');
    expect(result).toBe('/login');
  });

  it('returns plain /login when window.location is already /login', () => {
    window.history.replaceState({}, '', '/login?redirect_to=%2Fc%2Fabc');
    const result = buildLoginRedirectUrl();
    expect(result).toBe('/login');
  });

  it('returns plain /login for /login sub-paths', () => {
    const result = buildLoginRedirectUrl('/login/2fa', '', '');
    expect(result).toBe('/login');
  });

  it('returns plain /login for basename-prefixed /login (e.g. /librechat/login)', () => {
    window.history.replaceState({}, '', '/librechat/login?redirect_to=%2Fc%2Fabc');
    const result = buildLoginRedirectUrl();
    expect(result).toBe('/login');
  });

  it('returns plain /login for basename-prefixed /login sub-paths', () => {
    const result = buildLoginRedirectUrl('/librechat/login/2fa', '', '');
    expect(result).toBe('/login');
  });

  it('returns plain /login for root path (no pointless redirect_to=/)', () => {
    const result = buildLoginRedirectUrl('/', '', '');
    expect(result).toBe('/login');
    expect(result).not.toContain('redirect_to');
  });

  it('does NOT match paths where "login" is a substring of a segment', () => {
    const result = buildLoginRedirectUrl('/c/loginhistory', '', '');
    expect(result).toContain('redirect_to=');
    expect(decodeURIComponent(result.split('redirect_to=')[1])).toBe('/c/loginhistory');
  });
});

describe('teams member endpoints', () => {
  // Regression for BUG_TEAM_002: the change-role client URL must match the
  // server route `PATCH /api/teams/:id/members/:userId` — a stray `/role`
  // suffix made every role change 404.
  it('teamMemberRole targets the member route with no /role suffix', () => {
    expect(teamMemberRole('t1', 'u1')).toBe('/api/teams/t1/members/u1');
    expect(teamMemberRole('t1', 'u1')).not.toContain('/role');
  });

  it('teamMemberRole matches teamMember (same URL, PATCH vs DELETE distinguishes them)', () => {
    expect(teamMemberRole('t1', 'u1')).toBe(teamMember('t1', 'u1'));
  });

  it('encodes ids', () => {
    expect(teamMemberRole('t/1', 'u 1')).toBe('/api/teams/t%2F1/members/u%201');
  });
});
