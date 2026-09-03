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

  // How ops "clears" a Railway variable: the name stays, the value goes. It
  // reads as an empty rule set, and an empty rule set that failed CLOSED would
  // lock every member out of both products with nothing in the logs. It fails
  // open, like an unset variable -- asserted here because the two branches are
  // one `||` apart and only one of them was covered.
  it('lets everyone in when the variable is present but empty', () => {
    process.env.AGENT_ENTITLEMENTS = '';
    expect(isEntitled(member, 'studio')).toBe(true);
    expect(isEntitled(member, 'works')).toBe(true);
  });

  it('lets everyone in when the variable holds only whitespace', () => {
    process.env.AGENT_ENTITLEMENTS = '   \n ';
    expect(isEntitled(member, 'studio')).toBe(true);
    expect(isEntitled(member, 'works')).toBe(true);
  });

  it('lets nobody but an admin in when the variable is malformed', () => {
    process.env.AGENT_ENTITLEMENTS = '{not json';
    expect(isEntitled(member, 'studio')).toBe(false);
    // Admitting an admin here does not mean trusting the unparseable
    // variable: role comes from the chat identity, verified independently of
    // this list. A typo in one Railway variable must not lock ops out of the
    // whole agent surface, including whoever has to diagnose it.
    expect(isEntitled(admin, 'studio')).toBe(true);
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
