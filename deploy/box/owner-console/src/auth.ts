import { createHash, createHmac, timingSafeEqual } from 'node:crypto';

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

const b64url = (b: Buffer) => b.toString('base64url');

// A session token is `<body>.<sig>` where body is base64url({exp}) and sig is
// the HMAC-SHA256 of body under the box's session secret. No server-side store.
export function signSession(secret: string, ttlSeconds = 8 * 3600, now = Date.now()): string {
  const exp = Math.floor(now / 1000) + ttlSeconds;
  const body = b64url(Buffer.from(JSON.stringify({ exp })));
  const sig = b64url(createHmac('sha256', secret).update(body).digest());
  return `${body}.${sig}`;
}

export function verifySession(
  secret: string,
  token: string | undefined,
  now = Date.now(),
): { exp: number } | null {
  if (!secret || !token) return null;
  const dot = token.lastIndexOf('.');
  if (dot < 0) return null;
  const body = token.slice(0, dot);
  const sig = token.slice(dot + 1);
  const expected = b64url(createHmac('sha256', secret).update(body).digest());
  const s = Buffer.from(sig);
  const e = Buffer.from(expected);
  if (s.length !== e.length || !timingSafeEqual(s, e)) return null;
  try {
    const payload = JSON.parse(Buffer.from(body, 'base64url').toString());
    if (typeof payload.exp !== 'number' || payload.exp < Math.floor(now / 1000)) return null;
    return payload as { exp: number };
  } catch {
    return null;
  }
}
