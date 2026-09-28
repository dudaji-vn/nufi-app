import { describe, expect, test } from 'bun:test';
import { connectLink, signInvite, verifyInvite } from '../src/invite';
import { signSession } from '../src/auth';

const SECRET = 'x'.repeat(64);

describe('invite token', () => {
  test('round-trips the key and coordinator URL', () => {
    const t = signInvite(SECRET, { key: 'k-abc', serverUrl: 'https://coordinator.internal' });
    const p = verifyInvite(SECRET, t);
    expect(p?.key).toBe('k-abc');
    expect(p?.serverUrl).toBe('https://coordinator.internal');
  });

  test('rejects a tampered or wrong-secret token', () => {
    const t = signInvite(SECRET, { key: 'k', serverUrl: 'https://c' });
    expect(verifyInvite(SECRET, t.slice(0, -1) + 'z')).toBeNull();
    expect(verifyInvite('y'.repeat(64), t)).toBeNull();
  });

  test('rejects an expired token', () => {
    const t = signInvite(SECRET, { key: 'k', serverUrl: 'https://c' }, -1, Date.now() - 10_000);
    expect(verifyInvite(SECRET, t)).toBeNull();
  });

  test('does NOT accept an owner session token as an invite (audience split)', () => {
    // Same secret, different audience: a session cookie must never verify as an
    // invite, and vice versa (see the session-side check in auth.test.ts).
    const session = signSession(SECRET);
    expect(verifyInvite(SECRET, session)).toBeNull();
  });
});

describe('connectLink', () => {
  test('builds a /connect?token= link on the given origin', () => {
    expect(connectLink('https://nufi.local:3009', 'tok en')).toBe('https://nufi.local:3009/connect?token=tok%20en');
    expect(connectLink('https://nufi.local:3009/', 'abc')).toBe('https://nufi.local:3009/connect?token=abc');
  });
});
