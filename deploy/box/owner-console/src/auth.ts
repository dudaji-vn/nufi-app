import { createHash, timingSafeEqual } from 'node:crypto';
import { signToken, verifyToken } from './token';

// Constant-time password check. Hash both sides to a fixed 32 bytes first, so
// timingSafeEqual never sees unequal lengths (it throws on those) and the
// comparison leaks neither length nor content. Empty `expected` (no owner
// password configured on this box) always fails: the console is fail-closed.
export function verifyPassword(input: string, expected: string): boolean {
  if (!expected) return false;
  const a = createHash('sha256').update(input).digest();
  const b = createHash('sha256').update(expected).digest();
  return timingSafeEqual(a, b);
}

// The owner session is a signed token — the cookie value. It carries an
// audience so it can never be confused with an invite token signed under the
// same secret: a member's invite token, replayed as a session cookie, must NOT
// authenticate as the owner.
export function signSession(secret: string, ttlSeconds = 8 * 3600, now = Date.now()): string {
  return signToken(secret, { aud: 'session' }, ttlSeconds, now);
}

export function verifySession(
  secret: string,
  token: string | undefined,
  now = Date.now(),
): { exp: number } | null {
  const payload = verifyToken(secret, token, now);
  return payload && payload.aud === 'session' ? { exp: payload.exp as number } : null;
}
