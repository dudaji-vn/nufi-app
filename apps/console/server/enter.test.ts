import { describe, expect, it } from 'bun:test';
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
function as(user: AuthedUser) {
  const app = new Hono<{ Variables: { user: AuthedUser } }>();
  app.use('*', async (c, next) => {
    c.set('user', user);
    await next();
  });
  app.route('/', enter);
  return app;
}

function payloadOf(setCookie: string) {
  const token = /nufi_id=([^;]+)/.exec(setCookie)?.[1];
  if (!token) throw new Error('no nufi_id cookie');
  return JSON.parse(Buffer.from(token.split('.')[1], 'base64url').toString());
}

describe('GET /enter/studio', () => {
  it('redirects to Studio and sets a host-wide identity cookie', async () => {
    const res = await as(member).request('/studio');
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
    const res = await as(member).request('/studio');
    const claims = payloadOf(res.headers.get('set-cookie') ?? '');
    expect(claims.aud).toBe('nufi-studio');
    expect(claims.sub).toBe('u-1');
    expect(claims.email).toBe('a@b.c');
  });

  it('gives an admin the admin ceiling and everyone else editor', async () => {
    const asMember = payloadOf((await as(member).request('/studio')).headers.get('set-cookie') ?? '');
    expect(asMember.access).toBe('editor');

    const asAdmin = payloadOf(
      (await as({ ...member, role: 'ADMIN' }).request('/studio')).headers.get('set-cookie') ?? '',
    );
    expect(asAdmin.access).toBe('admin');
  });

  it('expires the cookie and the token together', async () => {
    const res = await as(member).request('/studio');
    const cookie = res.headers.get('set-cookie') ?? '';
    const maxAge = Number(/Max-Age=(\d+)/.exec(cookie)?.[1]);
    const claims = payloadOf(cookie);
    // A cookie outliving its token leaves the member holding a credential that
    // is silently rejected, which reads as a broken product rather than a
    // finished session.
    expect(claims.exp - claims.iat).toBe(maxAge);
  });
});
