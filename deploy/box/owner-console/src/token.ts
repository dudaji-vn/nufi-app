import { createHmac, timingSafeEqual } from 'node:crypto';

// A signed, expiring token: base64url(json).base64url(hmac-sha256). Used for
// both the owner session and member invites — each is "a signed JSON blob with
// an exp". No server-side store; the signature is the whole check.

const b64url = (b: Buffer) => b.toString('base64url');

export function signToken(
  secret: string,
  claims: Record<string, unknown>,
  ttlSeconds: number,
  now = Date.now(),
): string {
  const payload = { ...claims, exp: Math.floor(now / 1000) + ttlSeconds };
  const body = b64url(Buffer.from(JSON.stringify(payload)));
  const sig = b64url(createHmac('sha256', secret).update(body).digest());
  return `${body}.${sig}`;
}

// Returns the decoded claims, or null on: missing secret/token, malformed
// token, a bad/forged/wrong-length signature, or an expired exp. Constant-time
// signature comparison, length-guarded so timingSafeEqual never throws.
export function verifyToken(
  secret: string,
  token: string | undefined,
  now = Date.now(),
): Record<string, unknown> | null {
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
    return payload;
  } catch {
    return null;
  }
}
