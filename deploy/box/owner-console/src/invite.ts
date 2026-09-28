import { signToken, verifyToken } from './token';

// An invite is a SHARE LINK, not a file: /connect?token=<t>, where <t> is a
// signed blob carrying the pre-auth key and the coordinator URL a laptop needs
// to join. Signed with the owner session secret so it cannot be forged; short
// TTL so a leaked link stops working. The /connect page (sub-task 04) turns the
// token back into a one-click connector.

export type InvitePayload = { key: string; serverUrl: string; exp: number };

export function signInvite(
  secret: string,
  fields: { key: string; serverUrl: string },
  ttlSeconds = 3600,
  now = Date.now(),
): string {
  // aud:'invite' keeps this token distinct from an owner session signed under
  // the same secret — an invite can never be replayed as a session cookie.
  return signToken(secret, { aud: 'invite', key: fields.key, serverUrl: fields.serverUrl }, ttlSeconds, now);
}

export function verifyInvite(
  secret: string,
  token: string | undefined,
  now = Date.now(),
): InvitePayload | null {
  const p = verifyToken(secret, token, now);
  if (!p || p.aud !== 'invite' || typeof p.key !== 'string' || typeof p.serverUrl !== 'string') return null;
  return { key: p.key, serverUrl: p.serverUrl, exp: p.exp as number };
}

// The shareable link, built from the request's own origin so it is correct on
// the LAN name, the IP, or the mesh name without the box being told which.
export function connectLink(origin: string, token: string): string {
  return `${origin.replace(/\/$/, '')}/connect?token=${encodeURIComponent(token)}`;
}
