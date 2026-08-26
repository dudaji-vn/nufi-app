import { RPCHandler } from '@orpc/server/fetch';
import { Hono } from 'hono';
import { logger } from 'hono/logger';
import { enter } from './enter.ts';
import { getJwks } from './lib/oidc-keys.ts';
import { servePublic } from './lib/serve-public.ts';
import { type AuthedUser, auth } from './middleware/auth.ts';
import { oidc } from './oidc.ts';
import { router } from './router/index.ts';

const PORT = Number(process.env.PORT ?? 3000);
const SERVE_DIST = process.env.SERVE_DIST !== 'false';

type Env = { Variables: { user: AuthedUser } };
const app = new Hono<Env>();
app.use('*', logger());

app.get('/_health', (c) => c.json({ ok: true }));

// The public half of the identity signing key. NUFI Studio fetches this to
// verify the token in its cookie; NUFI Works uses it for the id_token from the
// authorization-code exchange. Cached briefly so a key rotation propagates in
// minutes rather than on a restart.
app.get('/.well-known/jwks.json', async (c) => {
  c.header('Cache-Control', 'public, max-age=300');
  return c.json(await getJwks());
});

// Handing a member into another product. Behind the same session check as
// everything else: without a valid chat cookie this must 401 rather than mint
// an identity for whoever asked.
app.use('/enter/*', auth());
app.route('/enter', enter);

// The authorization-code flow NUFI Works signs in through. Only /authorize
// sits behind the session check: /token and /userinfo are called by the Works
// server, which carries no browser cookie, so requiring one there would break
// the exchange rather than secure it. They authenticate by client secret and
// bearer token instead.
app.use('/oidc/authorize', auth());
app.route('/oidc', oidc);

// agents.nufi.me and console.nufi.me are the same service. The hostname is
// what decides which front page a visitor gets, so the root path is redirected
// on the chooser host and left alone everywhere else. Scoped to '/' on
// purpose: every other path, including /rpc, /enter and /oidc, has to keep
// working on both hostnames.
const CHOOSER_HOST = process.env.CHOOSER_HOST ?? 'agents.nufi.me';

app.use('*', async (c, next) => {
  const host = c.req.header('host')?.split(':')[0];
  if (host === CHOOSER_HOST && new URL(c.req.url).pathname === '/') {
    return c.redirect('/choose', 302);
  }
  return next();
});

const rpc = new RPCHandler(router);

app.use('/rpc/*', auth(), async (c, next) => {
  const { matched, response } = await rpc.handle(c.req.raw, {
    prefix: '/rpc',
    context: { user: c.get('user') },
  });
  if (matched) return response;
  return next();
});

if (SERVE_DIST) {
  // In production: Hono serves the Vite-built SPA at every other path.
  // In dev: Vite's dev server handles the SPA; this branch is skipped.
  app.use('*', servePublic());
}

console.log(`[console] listening on http://localhost:${PORT}`);

export default {
  port: PORT,
  fetch: app.fetch,
};
