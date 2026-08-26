import { Hono } from 'hono';
import { setCookie } from 'hono/cookie';
import { signIdentity } from './lib/oidc-keys.ts';
import type { AuthedUser } from './middleware/auth.ts';

type Env = { Variables: { user: AuthedUser } };

const STUDIO_URL = (process.env.STUDIO_URL ?? 'https://studio.nufi.me').replace(/\/+$/, '');
const COOKIE_DOMAIN = process.env.IDENTITY_COOKIE_DOMAIN ?? '.nufi.me';
const TTL_SECONDS = Number(process.env.IDENTITY_TTL_SECONDS ?? 8 * 60 * 60);

/**
 * NUFI Studio is not an OAuth client. It validates a JWT it finds in a cookie
 * (LANGFLOW_EXTERNAL_AUTH_TOKEN_COOKIE) against this console's JWKS, and
 * provisions the local user on first sight. So the whole handoff is: check the
 * chat session, mint a token for Studio alone, set it, redirect.
 *
 * The cookie is scoped to the parent domain because a response from
 * console.nufi.me cannot set a cookie that only studio.nufi.me sees. That
 * means every NUFI subdomain receives it. It is audience-scoped and
 * short-lived, so another subdomain can do nothing with it except replay it to
 * Studio -- which is where it was going. If a subdomain ever stops being ours,
 * this needs a per-host proxy instead.
 */
export const enter = new Hono<Env>();

enter.get('/studio', async (c) => {
  const user = c.get('user');
  const token = await signIdentity(
    {
      sub: user.id,
      email: user.email,
      access: user.role === 'ADMIN' ? 'admin' : 'editor',
    },
    'nufi-studio',
    TTL_SECONDS,
  );

  setCookie(c, 'nufi_id', token, {
    domain: COOKIE_DOMAIN,
    path: '/',
    httpOnly: true,
    secure: true,
    sameSite: 'Lax',
    maxAge: TTL_SECONDS,
  });

  return c.redirect(`${STUDIO_URL}/`, 302);
});
