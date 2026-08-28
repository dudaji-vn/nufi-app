import { randomBytes, timingSafeEqual } from 'node:crypto';
import { Hono } from 'hono';
import { getCookie } from 'hono/cookie';
import { createLocalJWKSet, jwtVerify } from 'jose';
import { resolveChatIdentity } from './lib/chat-identity.ts';
import { getJwks, ISSUER, signIdentity } from './lib/oidc-keys.ts';
import type { AuthedUser } from './middleware/auth.ts';

type Env = { Variables: { user: AuthedUser } };
type Client = {
  clientId: string;
  clientSecret: string;
  redirectUris: string[];
  // A federation client is a trusted upstream identity provider (e.g. the
  // MeshBox portal, first-party and on-box) that has ALREADY authenticated a
  // user through its own SSO and asks this console to mint the federated
  // identity for that user. Only clients that carry this flag may call
  // /federated-token; a plain authorization-code client never can. The minted
  // token is scoped to `audience` (the resource that will consume it, e.g. the
  // meshbox-chat adapter) so it cannot be replayed at the console itself.
  federation?: boolean;
  audience?: string;
};
type Code = { user: AuthedUser; clientId: string; redirectUri: string; expires: number };

type Access = 'viewer' | 'editor' | 'admin';
const ACCESS_LEVELS: readonly Access[] = ['viewer', 'editor', 'admin'];

const CODE_TTL_MS = 60_000;
const TOKEN_TTL_SECONDS = Number(process.env.IDENTITY_TTL_SECONDS ?? 8 * 60 * 60);

/**
 * Authorization codes live in memory.
 *
 * That is a stated limit, not an oversight: a code issued by one replica will
 * not be found by another, so this console runs as a single instance until
 * these move to a shared store. The alternative -- a signed, stateless code --
 * cannot be revoked on first use, and single use is the property that matters
 * most here.
 */
const codes = new Map<string, Code>();

function clients(): Client[] {
  try {
    const raw: unknown = JSON.parse(process.env.OIDC_CLIENTS ?? '[]');
    return Array.isArray(raw) ? (raw as Client[]) : [];
  } catch {
    // A malformed variable disables the flow rather than defaulting to
    // something permissive. Nobody gets in, which is the safe direction.
    return [];
  }
}

function findClient(id: string | undefined | null): Client | undefined {
  if (!id) return undefined;
  return clients().find((c) => c.clientId === id);
}

function secretMatches(expected: string, given: string): boolean {
  const a = Buffer.from(expected);
  const b = Buffer.from(given);
  // Length is compared first because timingSafeEqual throws on a mismatch.
  // The length of a secret is not the secret.
  return a.length === b.length && timingSafeEqual(a, b);
}

function accessFor(user: AuthedUser): 'admin' | 'editor' {
  return user.role === 'ADMIN' ? 'admin' : 'editor';
}

export const oidc = new Hono<Env>();

oidc.get('/authorize', async (c) => {
  const client = findClient(c.req.query('client_id'));
  const redirectUri = c.req.query('redirect_uri');
  const state = c.req.query('state') ?? '';

  // Checked before anything is issued and before any redirect happens. An
  // unregistered redirect_uri must never receive a code, and must not be
  // reachable by talking a signed-in member through a screen. Comparison is
  // exact string equality: no trailing slash, no prefix, no scheme coercion.
  if (!client || !redirectUri || !client.redirectUris.includes(redirectUri)) {
    return c.json({ error: 'invalid_request' }, 400);
  }

  // Same reason as /enter/studio: the session cookie carries an id and nothing
  // else, and an authorization code that resolves to an identity with no email
  // is rejected at the far end (`email_is_missing`) after a round trip that
  // looks, from the member's side, like the sign-in simply failed.
  const refreshToken = getCookie(c, 'refreshToken');
  const identity = refreshToken ? await resolveChatIdentity(refreshToken) : null;
  if (!identity) {
    return c.json({ error: 'unauthorized', detail: 'could not resolve NUFI identity' }, 401);
  }

  for (const cookie of identity.setCookies) c.header('set-cookie', cookie, { append: true });

  const code = randomBytes(32).toString('base64url');
  codes.set(code, {
    user: { id: identity.id, email: identity.email, name: identity.name, role: identity.role },
    clientId: client.clientId,
    redirectUri,
    expires: Date.now() + CODE_TTL_MS,
  });

  const target = new URL(redirectUri);
  target.searchParams.set('code', code);
  target.searchParams.set('state', state);
  return c.redirect(target.toString(), 302);
});

oidc.post('/token', async (c) => {
  const form = await c.req.parseBody();
  const clientId = String(form.client_id ?? '');
  const code = String(form.code ?? '');

  // Spent on read, before the client is even authenticated. Leaving a code
  // alive after a failed attempt would let a caller keep guessing the secret
  // against a code that is known to be genuine.
  const entry = codes.get(code);
  codes.delete(code);

  const client = findClient(clientId);
  if (!client || !secretMatches(client.clientSecret, String(form.client_secret ?? ''))) {
    return c.json({ error: 'invalid_client' }, 401);
  }

  if (
    !entry ||
    entry.expires < Date.now() ||
    entry.clientId !== clientId ||
    entry.redirectUri !== String(form.redirect_uri ?? '')
  ) {
    return c.json({ error: 'invalid_grant' }, 400);
  }

  const idToken = await signIdentity(
    {
      sub: entry.user.id,
      email: entry.user.email,
      name: entry.user.name,
      access: accessFor(entry.user),
    },
    clientId,
    TOKEN_TTL_SECONDS,
  );

  return c.json({
    access_token: idToken,
    id_token: idToken,
    token_type: 'Bearer',
    expires_in: TOKEN_TTL_SECONDS,
  });
});

/**
 * Federated identity grant (RFC 8693-style token exchange for a trusted IdP).
 *
 * The MeshBox portal authenticates a member through its own SSO, then asks here
 * for a console-signed identity so the member's requests to the on-box AI carry
 * a verifiable subject and stay attributable in the audit trail. There is no
 * browser or authorization code in this path: the portal is a server, so it
 * authenticates by client credentials and asserts the subject directly. This is
 * deliberately privileged, which is why it is gated on the `federation` flag --
 * a client that can name any subject can impersonate anyone, so only a
 * first-party upstream may hold it.
 */
oidc.post('/federated-token', async (c) => {
  const form = await c.req.parseBody();
  const clientId = String(form.client_id ?? '');
  const client = findClient(clientId);

  // Authenticate the federation client AND require the flag. A normal
  // authorization-code client, even with a correct secret, must not reach the
  // subject-assertion path.
  if (
    !client ||
    !client.federation ||
    !secretMatches(client.clientSecret, String(form.client_secret ?? ''))
  ) {
    return c.json({ error: 'invalid_client' }, 401);
  }

  const sub = String(form.sub ?? '').trim();
  if (!sub) {
    return c.json({ error: 'invalid_request', error_description: 'sub is required' }, 400);
  }
  const email = form.email ? String(form.email) : undefined;
  const asked = String(form.access ?? 'viewer') as Access;
  // An unrecognised access value falls to the least privilege rather than
  // failing open: a typo must not grant admin.
  const access: Access = ACCESS_LEVELS.includes(asked) ? asked : 'viewer';

  // The consumer of this token is the resource named by `audience`, never the
  // console. A token minted here cannot be presented back to /authorize.
  const audience = client.audience ?? clientId;
  const token = await signIdentity({ sub, email, access }, audience, TOKEN_TTL_SECONDS);

  return c.json({
    access_token: token,
    id_token: token,
    token_type: 'Bearer',
    expires_in: TOKEN_TTL_SECONDS,
    aud: audience,
  });
});

oidc.get('/userinfo', async (c) => {
  const token = /^Bearer\s+(.+)$/i.exec(c.req.header('authorization') ?? '')?.[1];
  if (!token) return c.json({ error: 'invalid_token' }, 401);

  try {
    const { payload } = await jwtVerify(token, createLocalJWKSet(await getJwks()), {
      issuer: ISSUER,
    });
    return c.json({
      sub: payload.sub,
      email: payload.email,
      name: payload.name,
      access: payload.access,
    });
  } catch {
    return c.json({ error: 'invalid_token' }, 401);
  }
});
