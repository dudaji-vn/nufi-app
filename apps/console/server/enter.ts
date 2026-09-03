import { type Context, Hono } from 'hono';
import { getCookie, setCookie } from 'hono/cookie';
import { resolveChatIdentity } from './lib/chat-identity.ts';
import { isEntitled } from './lib/entitlements.ts';
import { signIdentity } from './lib/oidc-keys.ts';
import type { AuthedUser } from './middleware/auth.ts';

type Env = { Variables: { user: AuthedUser } };

const STUDIO_URL = (process.env.STUDIO_URL ?? 'https://studio.nufi.me').replace(/\/+$/, '');
const COOKIE_DOMAIN = process.env.IDENTITY_COOKIE_DOMAIN ?? '.nufi.me';
const TTL_SECONDS = Number(process.env.IDENTITY_TTL_SECONDS ?? 8 * 60 * 60);
const CHAT_URL = (process.env.CHAT_BASE_URL ?? 'https://chat.nufi.me').replace(/\/+$/, '');

/**
 * Where inside Studio to land. Only a site-relative path is honoured: a
 * protocol-relative "//host" and an absolute URL both start a redirect off
 * this site, so they are dropped rather than repaired -- a half-fixed
 * redirect target is how open redirects get shipped.
 */
function safeNext(next: string | undefined): string {
  if (!next || !next.startsWith('/')) return '/';
  if (next.startsWith('//') || next.startsWith('/\\')) return '/';
  return next;
}

/**
 * A member whose chat session is gone gets sent to sign in; a script gets a
 * status code. The split is on Accept, because `verify-agents.sh` asserts the
 * 401 and a browser must never be shown raw JSON as an answer to a click.
 */
function noSession(c: Context<Env>) {
  if ((c.req.header('accept') ?? '').includes('text/html')) {
    return c.redirect(`${CHAT_URL}/login`, 302);
  }
  return c.json({ error: 'unauthorized', detail: 'could not resolve NUFI identity' }, 401);
}

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
  // The session cookie names the member but does not describe them, so the
  // record is fetched rather than inferred. Without this the token carries no
  // email and Studio provisions an `external-<hash>` account for a real person.
  const refreshToken = getCookie(c, 'refreshToken');
  const identity = refreshToken ? await resolveChatIdentity(refreshToken) : null;
  if (!identity) {
    return noSession(c);
  }

  // The lookup rotated the session token; hand the replacement to the browser
  // or the member is signed out of chat by having visited this route.
  for (const cookie of identity.setCookies) c.header('set-cookie', cookie, { append: true });

  // Checked after the rotated session is handed back and before anything is
  // minted: a member who may not enter must still leave with a working chat
  // session, and must never receive an identity token.
  if (!isEntitled(identity, 'studio')) {
    return c.json({ error: 'forbidden', detail: 'not entitled to NUFI Studio' }, 403);
  }

  const token = await signIdentity(
    {
      sub: identity.id,
      email: identity.email,
      name: identity.name,
      access: identity.role === 'ADMIN' ? 'admin' : 'editor',
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

  return c.redirect(`${STUDIO_URL}${safeNext(c.req.query('next'))}`, 302);
});

/**
 * What this member may open. The chooser at agents.nufi.me asks before it
 * renders, so a member sees a disabled card with a reason rather than
 * discovering the refusal by clicking into it.
 */
enter.get('/products', async (c) => {
  const refreshToken = getCookie(c, 'refreshToken');
  const identity = refreshToken ? await resolveChatIdentity(refreshToken) : null;
  if (!identity) {
    return c.json({ error: 'unauthorized', detail: 'could not resolve NUFI identity' }, 401);
  }
  for (const cookie of identity.setCookies) c.header('set-cookie', cookie, { append: true });

  return c.json({
    studio: isEntitled(identity, 'studio'),
    works: isEntitled(identity, 'works'),
  });
});
