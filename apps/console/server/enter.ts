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
// CHAT_BASE_URL (used by chat-identity.ts's fetch()) only needs to be
// reachable from the console -- on a deploy with private networking that can
// be an internal-only host like chat.railway.internal. A redirect sends the
// member's own browser to chat instead, which needs a host the browser can
// resolve, so it is not always the same address. CHAT_PUBLIC_URL is that
// address; it defaults to CHAT_BASE_URL so a deployment with one public chat
// host needs to set nothing new.
const CHAT_URL = (
  process.env.CHAT_PUBLIC_URL ??
  process.env.CHAT_BASE_URL ??
  'https://chat.nufi.me'
).replace(/\/+$/, '');
const CHOOSER_HOST = process.env.CHOOSER_HOST ?? 'agents.nufi.me';

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
 * A browser navigation gets sent somewhere it can act on; a script gets a
 * status code. The split is on Accept, because `verify-agents.sh` asserts a
 * status code and a browser must never be shown raw JSON as an answer to a
 * click. Shared by both ways `/studio` can refuse a member: no session at
 * all, and a session that isn't entitled to Studio.
 */
function refuse(
  c: Context<Env>,
  redirectTo: string,
  body: Record<string, string>,
  status: 401 | 403,
) {
  if ((c.req.header('accept') ?? '').includes('text/html')) {
    return c.redirect(redirectTo, 302);
  }
  return c.json(body, status);
}

/** A member whose chat session is gone gets sent to sign back in. */
function noSession(c: Context<Env>) {
  return refuse(
    c,
    `${CHAT_URL}/login`,
    { error: 'unauthorized', detail: 'could not resolve NUFI identity' },
    401,
  );
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
  //
  // A browser gets here whenever redirectToNufiEntry() bounces an expired
  // Studio session back through this route -- not just from a deliberate
  // click on the chooser -- so a member whose entitlement was revoked
  // mid-session must land on the chooser's own explanation, not raw JSON.
  if (!isEntitled(identity, 'studio')) {
    return refuse(
      c,
      `https://${CHOOSER_HOST}/choose`,
      { error: 'forbidden', detail: 'not entitled to NUFI Studio' },
      403,
    );
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
