import { RPCHandler } from '@orpc/server/fetch';
import { Hono } from 'hono';
import { logger } from 'hono/logger';
import { enter } from './enter.ts';
import { getJwks } from './lib/oidc-keys.ts';
import { servePublic } from './lib/serve-public.ts';
import { type AuthedUser, auth } from './middleware/auth.ts';
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
