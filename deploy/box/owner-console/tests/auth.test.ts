import { describe, expect, test } from 'bun:test';
import { signSession, verifyPassword, verifySession } from '../src/auth';

const SECRET = 'x'.repeat(64);

describe('verifyPassword', () => {
  test('accepts the right password', () => {
    expect(verifyPassword('hunter2', 'hunter2')).toBe(true);
  });
  test('rejects the wrong password', () => {
    expect(verifyPassword('nope', 'hunter2')).toBe(false);
  });
  test('fails closed when no password is configured', () => {
    expect(verifyPassword('anything', '')).toBe(false);
  });
});

describe('session token', () => {
  test('round-trips a signed token', () => {
    const t = signSession(SECRET);
    expect(verifySession(SECRET, t)).not.toBeNull();
  });
  test('rejects a tampered signature', () => {
    const t = signSession(SECRET);
    const bad = t.slice(0, -1) + (t.endsWith('a') ? 'b' : 'a');
    expect(verifySession(SECRET, bad)).toBeNull();
  });
  test('rejects a token signed with another secret', () => {
    expect(verifySession(SECRET, signSession('y'.repeat(64)))).toBeNull();
  });
  test('rejects an expired token', () => {
    const past = Date.now() - 10_000;
    const t = signSession(SECRET, -1, past);      // exp already behind `now`
    expect(verifySession(SECRET, t)).toBeNull();
  });
  test('rejects a missing token and a missing secret', () => {
    expect(verifySession(SECRET, undefined)).toBeNull();
    expect(verifySession('', signSession(SECRET))).toBeNull();
  });
  test('does not throw for a dot-less token', () => {
    expect(() => verifySession(SECRET, 'nodot')).not.toThrow();
    expect(verifySession(SECRET, 'nodot')).toBeNull();
  });
  test('does not throw for an empty string token', () => {
    expect(() => verifySession(SECRET, '')).not.toThrow();
    expect(verifySession(SECRET, '')).toBeNull();
  });
  test('does not throw for a token with empty signature segment', () => {
    expect(() => verifySession(SECRET, 'body.')).not.toThrow();
    expect(verifySession(SECRET, 'body.')).toBeNull();
  });
  test('does not throw for a token with wrong-length signature', () => {
    const validToken = signSession(SECRET);
    const parts = validToken.split('.');
    const badToken = parts[0] + '.' + 'abc'; // Replace signature with short string
    expect(() => verifySession(SECRET, badToken)).not.toThrow();
    expect(verifySession(SECRET, badToken)).toBeNull();
  });
});
