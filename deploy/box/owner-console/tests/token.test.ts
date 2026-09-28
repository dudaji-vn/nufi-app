import { describe, expect, test } from 'bun:test';
import { signToken, verifyToken } from '../src/token';

const SECRET = 'x'.repeat(64);

describe('signed token', () => {
  test('round-trips claims and adds an exp', () => {
    const t = signToken(SECRET, { key: 'abc', serverUrl: 'https://c' }, 3600);
    const p = verifyToken(SECRET, t);
    expect(p?.key).toBe('abc');
    expect(p?.serverUrl).toBe('https://c');
    expect(typeof p?.exp).toBe('number');
  });

  test('rejects a tampered signature', () => {
    const t = signToken(SECRET, { a: 1 }, 3600);
    const bad = t.slice(0, -1) + (t.endsWith('a') ? 'b' : 'a');
    expect(verifyToken(SECRET, bad)).toBeNull();
  });

  test('rejects another secret, a missing token, and a missing secret', () => {
    expect(verifyToken(SECRET, signToken('y'.repeat(64), {}, 3600))).toBeNull();
    expect(verifyToken(SECRET, undefined)).toBeNull();
    expect(verifyToken('', signToken(SECRET, {}, 3600))).toBeNull();
  });

  test('rejects an expired token and a malformed one', () => {
    expect(verifyToken(SECRET, signToken(SECRET, {}, -1, Date.now() - 10_000))).toBeNull();
    expect(verifyToken(SECRET, 'nodot')).toBeNull();
    expect(verifyToken(SECRET, 'body.')).toBeNull();
  });
});
