import { afterEach, beforeEach, describe, expect, it } from 'bun:test';
import { Hono } from 'hono';
import { enter } from './enter.ts';
import type { AuthedUser } from './middleware/auth.ts';

/**
 * This route turns a chat session into a signed-in session in another product.
 * The cookie it sets is the whole credential, so its attributes are the
 * security properties worth asserting: host-wide but not readable by script,
 * never sent over plaintext, and carrying an audience only Studio accepts.
 */
const member: AuthedUser = { id: 'u-1', email: 'a@b.c', role: 'USER' };

// c.get('user') comes from middleware. Hono's third request() argument carries
// Env bindings, not Variables, so a stub middleware is the only way to put a
// user on the context in a test.
/**
 * The chat identity lookup, stubbed at the network boundary. The session cookie
 * names the member but does not describe them, so this route has to fetch the
 * record; without it the token carries no email and Studio provisions an
 * `external-<hash>` account for a real person.
 */
const realFetch = globalThis.fetch;
let chatReply: { status: number; body: unknown; setCookie?: string } = { status: 200, body: null };

function stubChat(user: AuthedUser | null) {
  chatReply = user
    ? {
        status: 200,
        body: { user: { id: user.id, email: user.email, name: 'Test Member', role: user.role } },
      }
    : { status: 401, body: {} };
}

beforeEach(() => {
  stubChat(member);
  globalThis.fetch = (async (input: RequestInfo | URL) => {
    if (!String(input).includes('/api/auth/refresh')) throw new Error('unexpected fetch');
    const headers = new Headers({ 'content-type': 'application/json' });
    if (chatReply.setCookie) headers.append('set-cookie', chatReply.setCookie);
    return new Response(JSON.stringify(chatReply.body), { status: chatReply.status, headers });
  }) as typeof fetch;
});

afterEach(() => {
  globalThis.fetch = realFetch;
});

function as(user: AuthedUser) {
  stubChat(user);
  const app = new Hono<{ Variables: { user: AuthedUser } }>();
  app.use('*', async (c, next) => {
    c.set('user', user);
    await next();
  });
  app.route('/', enter);
  return app;
}

const WITH_SESSION = { headers: { cookie: 'refreshToken=rt-test' } };

function payloadOf(setCookie: string) {
  const token = /nufi_id=([^;]+)/.exec(setCookie)?.[1];
  if (!token) throw new Error('no nufi_id cookie');
  return JSON.parse(Buffer.from(token.split('.')[1], 'base64url').toString());
}

describe('GET /enter/studio', () => {
  it('redirects to Studio and sets a host-wide identity cookie', async () => {
    const res = await as(member).request('/studio', WITH_SESSION);
    expect(res.status).toBe(302);
    expect(res.headers.get('location')).toBe('https://studio.nufi.me/');

    const cookie = res.headers.get('set-cookie') ?? '';
    expect(cookie).toContain('nufi_id=');
    expect(cookie).toContain('Domain=.nufi.me');
    expect(cookie).toContain('HttpOnly');
    expect(cookie).toContain('Secure');
    expect(cookie).toContain('SameSite=Lax');
  });

  it('scopes the token to Studio alone', async () => {
    const res = await as(member).request('/studio', WITH_SESSION);
    const claims = payloadOf(res.headers.get('set-cookie') ?? '');
    expect(claims.aud).toBe('nufi-studio');
    expect(claims.sub).toBe('u-1');
    expect(claims.email).toBe('a@b.c');
  });

  it('gives an admin the admin ceiling and everyone else editor', async () => {
    const asMember = payloadOf(
      (await as(member).request('/studio', WITH_SESSION)).headers.get('set-cookie') ?? '',
    );
    expect(asMember.access).toBe('editor');

    const asAdmin = payloadOf(
      (await as({ ...member, role: 'ADMIN' }).request('/studio', WITH_SESSION)).headers.get(
        'set-cookie',
      ) ?? '',
    );
    expect(asAdmin.access).toBe('admin');
  });

  it('expires the cookie and the token together', async () => {
    const res = await as(member).request('/studio', WITH_SESSION);
    const cookie = res.headers.get('set-cookie') ?? '';
    const maxAge = Number(/Max-Age=(\d+)/.exec(cookie)?.[1]);
    const claims = payloadOf(cookie);
    // A cookie outliving its token leaves the member holding a credential that
    // is silently rejected, which reads as a broken product rather than a
    // finished session.
    expect(claims.exp - claims.iat).toBe(maxAge);
  });

  // The defect this route shipped with: the chat session cookie carries
  // `{ id, sessionId }` and no email, so a token minted from it alone made
  // Studio invent a user called `external-<hash>` for a real person. If the
  // email cannot be resolved, no cookie is set and nobody is sent anywhere.
  it('refuses when the identity has no email', async () => {
    const app = as(member);
    // after as(), which re-stubs from `member` and would restore the email
    chatReply = { status: 200, body: { user: { id: 'u-1', role: 'USER' } } };
    const res = await app.request('/studio', WITH_SESSION);
    expect(res.status).toBe(401);
    expect(res.headers.get('set-cookie')).toBeNull();
    expect(res.headers.get('location')).toBeNull();
  });

  it('refuses without a chat session cookie', async () => {
    const res = await as(member).request('/studio');
    expect(res.status).toBe(401);
    expect(res.headers.get('set-cookie')).toBeNull();
  });

  it('carries the role through as the access ceiling', async () => {
    const res = await as({ id: 'u-2', email: 'boss@nufi.me', role: 'ADMIN' }).request(
      '/studio',
      WITH_SESSION,
    );
    expect(payloadOf(res.headers.get('set-cookie') ?? '').access).toBe('admin');
  });

  // Rotating the chat token and dropping the replacement would sign the member
  // out of chat as a side effect of opening Studio.
  it('passes the rotated session cookie back to the browser', async () => {
    const app = as(member);
    // after as(), which re-stubs and would otherwise clear this
    chatReply.setCookie = 'refreshToken=rotated; Path=/';
    const res = await app.request('/studio', WITH_SESSION);
    expect(res.status).toBe(302);
    const cookies = res.headers.getSetCookie().join(' | ');
    expect(cookies).toContain('rotated');
    expect(cookies).toContain('nufi_id=');
  });

  // better-auth refuses a profile with no name the same way it refuses one
  // with no email, and the failure looks identical from the outside: a
  // redirect that appears to work, then an error page.
  it('refuses when the identity has no usable name', async () => {
    const app = as(member);
    chatReply = { status: 200, body: { user: { id: 'u-1', email: '', role: 'USER' } } };
    const res = await app.request('/studio', WITH_SESSION);
    expect(res.status).toBe(401);
  });

  it('falls back to the email local part when chat has no display name', async () => {
    const app = as(member);
    chatReply = {
      status: 200,
      body: { user: { id: 'u-1', email: 'nobody@nufi.me', role: 'USER' } },
    };
    const res = await app.request('/studio', WITH_SESSION);
    expect(payloadOf(res.headers.get('set-cookie') ?? '').name).toBe('nobody');
  });

  it('carries the display name chat holds', async () => {
    const res = await as(member).request('/studio', WITH_SESSION);
    expect(payloadOf(res.headers.get('set-cookie') ?? '').name).toBe('Test Member');
  });
});
