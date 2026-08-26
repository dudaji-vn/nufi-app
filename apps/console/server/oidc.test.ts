import { beforeEach, describe, expect, it } from 'bun:test';
import { Hono } from 'hono';
import type { AuthedUser } from './middleware/auth.ts';
import { oidc } from './oidc.ts';

/**
 * The authorization-code half of the identity issuer, used by NUFI Works.
 *
 * Everything here is about what must NOT happen. An unregistered redirect_uri
 * must never receive a code, because that is how a page on the internet walks
 * away with a member's identity. A code must work exactly once. A wrong client
 * secret must fail even when the code is genuine. The happy path is one test;
 * the rest are the reason this file exists.
 */
const CALLBACK = 'https://works.nufi.me/api/auth/oauth2/callback/nufi';
const member: AuthedUser = { id: 'u-9', email: 'm@nufi.me', role: 'USER' };

function as(user: AuthedUser) {
  const app = new Hono<{ Variables: { user: AuthedUser } }>();
  app.use('*', async (c, next) => {
    c.set('user', user);
    await next();
  });
  app.route('/', oidc);
  return app;
}

async function codeFor(user: AuthedUser = member): Promise<string> {
  const res = await as(user).request(
    `/authorize?client_id=nufi-works&redirect_uri=${encodeURIComponent(CALLBACK)}&state=s`,
  );
  const code = new URL(res.headers.get('location') ?? '').searchParams.get('code');
  if (!code) throw new Error('no code issued');
  return code;
}

function tokenBody(code: string, over: Record<string, string> = {}) {
  return new URLSearchParams({
    grant_type: 'authorization_code',
    code,
    client_id: 'nufi-works',
    client_secret: 's3cret',
    redirect_uri: CALLBACK,
    ...over,
  });
}

beforeEach(() => {
  process.env.OIDC_CLIENTS = JSON.stringify([
    { clientId: 'nufi-works', clientSecret: 's3cret', redirectUris: [CALLBACK] },
  ]);
});

describe('authorize', () => {
  it('redirects back with a code and the exact state', async () => {
    const res = await as(member).request(
      `/authorize?client_id=nufi-works&redirect_uri=${encodeURIComponent(CALLBACK)}&state=abc`,
    );
    expect(res.status).toBe(302);
    const url = new URL(res.headers.get('location') ?? '');
    expect(url.origin + url.pathname).toBe(CALLBACK);
    expect(url.searchParams.get('state')).toBe('abc');
    expect(url.searchParams.get('code')).toBeTruthy();
  });

  it('refuses a redirect_uri that is not registered, without redirecting', async () => {
    const res = await as(member).request(
      '/authorize?client_id=nufi-works&redirect_uri=https%3A%2F%2Fevil.example%2Fcb&state=x',
    );
    expect(res.status).toBe(400);
    expect(res.headers.get('location')).toBeNull();
  });

  it('refuses a redirect_uri that only looks registered', async () => {
    for (const near of [`${CALLBACK}/`, `${CALLBACK}?x=1`, CALLBACK.replace('https', 'http')]) {
      const res = await as(member).request(
        `/authorize?client_id=nufi-works&redirect_uri=${encodeURIComponent(near)}&state=x`,
      );
      expect(res.status).toBe(400);
    }
  });

  it('refuses an unknown client', async () => {
    const res = await as(member).request(
      `/authorize?client_id=nobody&redirect_uri=${encodeURIComponent(CALLBACK)}&state=x`,
    );
    expect(res.status).toBe(400);
  });
});

describe('token', () => {
  it('exchanges a code for an id_token scoped to the client', async () => {
    const res = await oidc.request('/token', { method: 'POST', body: tokenBody(await codeFor()) });
    expect(res.status).toBe(200);
    const json = (await res.json()) as { id_token: string; token_type: string };
    expect(json.token_type).toBe('Bearer');
    const claims = JSON.parse(Buffer.from(json.id_token.split('.')[1], 'base64url').toString());
    expect(claims.aud).toBe('nufi-works');
    expect(claims.sub).toBe('u-9');
    expect(claims.email).toBe('m@nufi.me');
  });

  it('refuses the replay of a code it already spent', async () => {
    const body = tokenBody(await codeFor());
    expect((await oidc.request('/token', { method: 'POST', body })).status).toBe(200);
    expect((await oidc.request('/token', { method: 'POST', body })).status).toBe(400);
  });

  it('refuses a wrong client secret', async () => {
    const res = await oidc.request('/token', {
      method: 'POST',
      body: tokenBody(await codeFor(), { client_secret: 'wrong' }),
    });
    expect(res.status).toBe(401);
  });

  it('burns the code even when the secret was wrong', async () => {
    const code = await codeFor();
    await oidc.request('/token', {
      method: 'POST',
      body: tokenBody(code, { client_secret: 'wrong' }),
    });
    // Leaving a code alive after a failed attempt lets a caller keep guessing
    // the secret against a genuine code.
    const retry = await oidc.request('/token', { method: 'POST', body: tokenBody(code) });
    expect(retry.status).toBe(400);
  });

  it('refuses a code redeemed against a different redirect_uri', async () => {
    const res = await oidc.request('/token', {
      method: 'POST',
      body: tokenBody(await codeFor(), { redirect_uri: 'https://works.nufi.me/elsewhere' }),
    });
    expect(res.status).toBe(400);
  });
});

describe('userinfo', () => {
  it('returns the member behind a valid token', async () => {
    const exchange = await oidc.request('/token', {
      method: 'POST',
      body: tokenBody(await codeFor()),
    });
    const { id_token } = (await exchange.json()) as { id_token: string };
    const res = await oidc.request('/userinfo', {
      headers: { authorization: `Bearer ${id_token}` },
    });
    expect(res.status).toBe(200);
    expect(await res.json()).toMatchObject({ sub: 'u-9', email: 'm@nufi.me' });
  });

  it('refuses a missing or forged token', async () => {
    expect((await oidc.request('/userinfo')).status).toBe(401);
    expect(
      (await oidc.request('/userinfo', { headers: { authorization: 'Bearer not.a.jwt' } })).status,
    ).toBe(401);
  });
});
