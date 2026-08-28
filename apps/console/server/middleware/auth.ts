import type { Context, MiddlewareHandler } from 'hono';
import { getCookie } from 'hono/cookie';
import { verify } from 'hono/jwt';
import type { JWTPayload } from 'hono/utils/jwt/types';

export type AuthedUser = {
  id: string;
  email?: string;
  name?: string;
  role: 'USER' | 'ADMIN';
};

type Env = { Variables: { user: AuthedUser } };

/**
 * Verify a LibreChat-issued JWT and attach the user to Hono context.
 *
 * Two accepted mechanisms (in order):
 *   1. `Authorization: Bearer <access_token>` — verified with JWT_SECRET
 *      (used by service clients like the e2e script).
 *   2. `refreshToken` cookie — verified with JWT_REFRESH_SECRET (the
 *      browser path; LibreChat sets this on login. We treat a valid
 *      refresh token as proof of session for our internal console.
 *      Long-term: proxy through LibreChat's /api/auth/refresh to honour
 *      session revocation.)
 *
 * On any failure, returns 401 with a structured body.
 */
export function auth(): MiddlewareHandler<Env> {
  return async (c, next) => {
    const accessSecret = process.env.JWT_SECRET;
    const refreshSecret = process.env.JWT_REFRESH_SECRET;
    if (!accessSecret || !refreshSecret) {
      return c.json({ error: 'server_misconfigured', detail: 'JWT secrets missing' }, 500);
    }

    const fromHeader = readBearer(c);
    const fromCookie = getCookie(c, 'refreshToken');

    let payload: JWTPayload | undefined;
    let source: 'access' | 'refresh' | undefined;

    if (fromHeader) {
      payload = await safeVerify(fromHeader, accessSecret);
      if (payload) source = 'access';
    }
    if (!payload && fromCookie) {
      payload = await safeVerify(fromCookie, refreshSecret);
      if (payload) source = 'refresh';
    }

    if (!payload || !source) {
      return c.json({ error: 'unauthorized' }, 401);
    }

    const id = pickString(payload, ['id', 'userId', '_id', 'sub']);
    if (!id) {
      return c.json({ error: 'unauthorized', detail: 'token missing user id' }, 401);
    }

    const role = pickString(payload, ['role']);
    const email = pickString(payload, ['email']);

    c.set('user', {
      id,
      email,
      role: role === 'ADMIN' ? 'ADMIN' : 'USER',
    });

    await next();
  };
}

function readBearer(c: Context): string | undefined {
  const header = c.req.header('Authorization') ?? c.req.header('authorization');
  if (!header) return;
  const m = /^Bearer\s+(.+)$/i.exec(header);
  return m?.[1];
}

async function safeVerify(token: string, secret: string): Promise<JWTPayload | undefined> {
  try {
    return await verify(token, secret, 'HS256');
  } catch {
    return undefined;
  }
}

function pickString(payload: JWTPayload, keys: string[]): string | undefined {
  for (const k of keys) {
    const v = payload[k];
    if (typeof v === 'string' && v.length > 0) return v;
  }
  return undefined;
}
