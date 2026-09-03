import { afterEach, beforeEach, describe, expect, it } from 'bun:test';
import { Hono } from 'hono';
import { sign } from 'hono/jwt';
import { enter } from './enter.ts';
import { type AuthedUser, auth } from './middleware/auth.ts';

// auth() answers 500 without these, so they are set before the middleware is
// ever built rather than inside a hook.
process.env.JWT_SECRET ??= 'test-access-secret';
process.env.JWT_REFRESH_SECRET ??= 'test-refresh-secret';

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

describe('entitlement', () => {
  afterEach(() => {
    delete process.env.AGENT_ENTITLEMENTS;
  });

  it('refuses a member who is not on the Studio list', async () => {
    process.env.AGENT_ENTITLEMENTS = JSON.stringify({ studio: ['someone@else.com'] });
    const res = await as(member).request('/studio', WITH_SESSION);
    expect(res.status).toBe(403);
    // The door closes without minting anything.
    expect(res.headers.get('set-cookie') ?? '').not.toContain('nufi_id=');
  });

  it('still hands back the rotated chat session when it refuses', async () => {
    // Refusing entry must not sign the member out of chat as a side effect.
    process.env.AGENT_ENTITLEMENTS = JSON.stringify({ studio: [] });
    const app = as(member);
    // after as(), which re-stubs and would otherwise clear this
    chatReply.setCookie = 'refreshToken=rotated; Path=/';
    const res = await app.request('/studio', WITH_SESSION);
    expect(res.status).toBe(403);
    expect(res.headers.get('set-cookie') ?? '').toContain('refreshToken=rotated');
  });

  // redirectToNufiEntry() now reaches this branch by itself whenever a
  // Studio session expires, not only via a deliberate click on the chooser --
  // so a member whose entitlement was pulled mid-session must land on the
  // chooser's own explanation instead of a raw JSON error page.
  it('bounces a browser navigation to the chooser when not entitled', async () => {
    process.env.AGENT_ENTITLEMENTS = JSON.stringify({ studio: [] });
    const res = await as(member).request('/studio', {
      headers: { cookie: 'refreshToken=rt-test', accept: 'text/html,application/xhtml+xml' },
    });
    expect(res.status).toBe(302);
    expect(res.headers.get('location')).toBe('https://agents.nufi.me/choose');
  });

  it('still answers 403 with JSON to a scripted caller when not entitled', async () => {
    process.env.AGENT_ENTITLEMENTS = JSON.stringify({ studio: [] });
    const res = await as(member).request('/studio', {
      headers: { cookie: 'refreshToken=rt-test', accept: '*/*' },
    });
    expect(res.status).toBe(403);
    expect(await res.json()).toEqual({ error: 'forbidden', detail: 'not entitled to NUFI Studio' });
  });

  it('reports per-product entitlement to the chooser', async () => {
    process.env.AGENT_ENTITLEMENTS = JSON.stringify({ studio: ['a@b.c'], works: [] });
    const res = await as(member).request('/products', WITH_SESSION);
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ studio: true, works: false });
  });

  it('refuses to report entitlement without a session', async () => {
    const app = as(member);
    stubChat(null); // after as(), which re-stubs a valid member
    const res = await app.request('/products');
    expect(res.status).toBe(401);
  });
});

describe('returning to where the member was', () => {
  it('sends the member back to the path they came from', async () => {
    const res = await as(member).request('/studio?next=%2Fflow%2Fabc', WITH_SESSION);
    expect(res.status).toBe(302);
    expect(res.headers.get('location')).toBe('https://studio.nufi.me/flow/abc');
  });

  it('ignores a next that leaves the site', async () => {
    // "//evil.com" is a protocol-relative URL: it starts with '/' and is
    // still off-site. Rejected outright rather than sanitised.
    const res = await as(member).request('/studio?next=%2F%2Fevil.com', WITH_SESSION);
    expect(res.headers.get('location')).toBe('https://studio.nufi.me/');
  });

  it('ignores an absolute next', async () => {
    const res = await as(member).request('/studio?next=https%3A%2F%2Fevil.com', WITH_SESSION);
    expect(res.headers.get('location')).toBe('https://studio.nufi.me/');
  });

  it('bounces a browser navigation to chat instead of answering JSON', async () => {
    const app = as(member);
    stubChat(null); // after as(), which re-stubs a valid member
    const res = await app.request('/studio', {
      headers: { accept: 'text/html,application/xhtml+xml' },
    });
    expect(res.status).toBe(302);
    expect(res.headers.get('location')).toBe('https://chat.nufi.me/login');
  });

  it('still answers 401 to a scripted caller', async () => {
    // verify-agents.sh asserts exactly this. curl sends Accept: */*.
    const app = as(member);
    stubChat(null); // after as(), which re-stubs a valid member
    const res = await app.request('/studio', { headers: { accept: '*/*' } });
    expect(res.status).toBe(401);
  });
});

/**
 * The stack as `index.ts` actually mounts it.
 *
 * Every test above substitutes a stub middleware for auth(), which is exactly
 * how the defect this describes hid: a member whose chat session ended sends
 * NO cookie (chat's refresh cookie carries `expires`), so they never reach
 * enter.ts's own refusal at all -- they stop at auth(), which answered raw
 * JSON. The session-continuity bounce existed and was unreachable for the one
 * journey it was built for.
 */
function realStack(options?: { bounceHtml?: boolean }) {
  const app = new Hono<{ Variables: { user: AuthedUser } }>();
  app.use('/enter/*', auth(options));
  app.route('/enter', enter);
  return app;
}

const HTML = { accept: 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8' };

async function refreshCookie(overrides: Record<string, unknown> = {}) {
  const token = await sign(
    { id: 'u-1', exp: Math.floor(Date.now() / 1000) + 3600, ...overrides },
    process.env.JWT_REFRESH_SECRET as string,
  );
  return `refreshToken=${token}`;
}

describe('the real middleware stack', () => {
  it('bounces a browser with no session to chat, from the middleware', async () => {
    const res = await realStack({ bounceHtml: true }).request('/enter/studio?next=%2Fflow%2Fabc', {
      headers: HTML,
    });
    expect(res.status).toBe(302);
    expect(res.headers.get('location')).toBe('https://chat.nufi.me/login');
  });

  it('still answers 401 to an anonymous script with no session', async () => {
    // deploy/railway/verify-agents.sh asserts exactly this against production,
    // and curl sends Accept: */*. If this ever becomes a 302 the door still
    // holds, but the standing check that proves it stops proving anything.
    const res = await realStack({ bounceHtml: true }).request('/enter/studio', {
      headers: { accept: '*/*' },
    });
    expect(res.status).toBe(401);
    expect(res.headers.get('location')).toBeNull();
  });

  it('bounces a browser whose session token has expired', async () => {
    const expired = await refreshCookie({ exp: Math.floor(Date.now() / 1000) - 60 });
    const res = await realStack({ bounceHtml: true }).request('/enter/studio', {
      headers: { ...HTML, cookie: expired },
    });
    expect(res.status).toBe(302);
    expect(res.headers.get('location')).toBe('https://chat.nufi.me/login');
  });

  it('bounces a browser whose cookie is valid here but rejected by chat', async () => {
    // The only branch the stubbed suite could reach: past auth(), refused by
    // the identity lookup. It must land in the same place as the others.
    stubChat(null);
    const res = await realStack({ bounceHtml: true }).request('/enter/studio', {
      headers: { ...HTML, cookie: await refreshCookie() },
    });
    expect(res.status).toBe(302);
    expect(res.headers.get('location')).toBe('https://chat.nufi.me/login');
  });

  it('lets a browser with a live session through to Studio', async () => {
    const res = await realStack({ bounceHtml: true }).request('/enter/studio', {
      headers: { ...HTML, cookie: await refreshCookie() },
    });
    expect(res.status).toBe(302);
    expect(res.headers.get('location')).toBe('https://studio.nufi.me/');
  });

  it('never redirects on a mount that did not ask for it', async () => {
    // /rpc/* is called by the SPA with fetch(). A redirect there turns a 401
    // the client knows how to handle into a cross-origin fetch failure, so the
    // bounce is opt-in per mount rather than a property of auth() itself.
    const res = await realStack().request('/enter/studio', { headers: HTML });
    expect(res.status).toBe(401);
    expect(res.headers.get('location')).toBeNull();
  });

  it('marks the products answer uncacheable', async () => {
    const res = await realStack({ bounceHtml: true }).request('/enter/products', {
      headers: { cookie: await refreshCookie(), accept: '*/*' },
    });
    expect(res.status).toBe(200);
    expect(res.headers.get('cache-control')).toBe('no-store');
  });
});

describe('a next that cannot go in a header', () => {
  it('drops a control character rather than answering 500', async () => {
    const res = await as(member).request('/studio?next=%2Fa%0d%0aX%3A%20y', WITH_SESSION);
    expect(res.status).toBe(302);
    expect(res.headers.get('location')).toBe('https://studio.nufi.me/');
  });
});
