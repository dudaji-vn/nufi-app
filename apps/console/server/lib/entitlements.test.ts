import { afterEach, describe, expect, it } from 'bun:test';
import { isEntitled } from './entitlements.ts';

const member = { email: 'a@dudaji.vn', role: 'USER' as const };
const admin = { email: 'ops@dudaji.vn', role: 'ADMIN' as const };

afterEach(() => {
  delete process.env.AGENT_ENTITLEMENTS;
});

describe('isEntitled', () => {
  it('lets everyone in when the variable is unset', () => {
    expect(isEntitled(member, 'studio')).toBe(true);
    expect(isEntitled(member, 'works')).toBe(true);
  });

  it('lets nobody in when the variable is malformed', () => {
    process.env.AGENT_ENTITLEMENTS = '{not json';
    expect(isEntitled(member, 'studio')).toBe(false);
    // Not even an admin: a config nobody can read is a config nobody trusts.
    expect(isEntitled(admin, 'studio')).toBe(false);
  });

  it('matches a listed address exactly, case-insensitively', () => {
    process.env.AGENT_ENTITLEMENTS = JSON.stringify({ studio: ['A@Dudaji.VN'] });
    expect(isEntitled(member, 'studio')).toBe(true);
    expect(isEntitled({ email: 'b@dudaji.vn', role: 'USER' }, 'studio')).toBe(false);
  });

  it('matches a domain entry by suffix', () => {
    process.env.AGENT_ENTITLEMENTS = JSON.stringify({ works: ['@dudaji.vn'] });
    expect(isEntitled(member, 'works')).toBe(true);
    expect(isEntitled({ email: 'x@example.com', role: 'USER' }, 'works')).toBe(false);
  });

  it('does not let a lookalike domain through', () => {
    process.env.AGENT_ENTITLEMENTS = JSON.stringify({ works: ['@dudaji.vn'] });
    expect(isEntitled({ email: 'x@notdudaji.vn', role: 'USER' }, 'works')).toBe(false);
  });

  it('leaves a product open when its list is absent', () => {
    process.env.AGENT_ENTITLEMENTS = JSON.stringify({ studio: ['a@dudaji.vn'] });
    expect(isEntitled({ email: 'x@example.com', role: 'USER' }, 'works')).toBe(true);
  });

  it('always admits an admin against a well-formed list', () => {
    process.env.AGENT_ENTITLEMENTS = JSON.stringify({ studio: [] });
    expect(isEntitled(admin, 'studio')).toBe(true);
    expect(isEntitled(member, 'studio')).toBe(false);
  });

  it('treats "*" as everyone', () => {
    process.env.AGENT_ENTITLEMENTS = JSON.stringify({ studio: ['*'] });
    expect(isEntitled({ email: 'x@example.com', role: 'USER' }, 'studio')).toBe(true);
  });
});
