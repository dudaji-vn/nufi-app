import { Hono } from 'hono';
import { logger } from 'hono/logger';
import { RPCHandler } from '@orpc/server/fetch';
import { router } from './router/index.ts';
import { servePublic } from './lib/serve-public.ts';

const PORT = Number(process.env.PORT ?? 3000);
const SERVE_DIST = process.env.SERVE_DIST !== 'false';

const app = new Hono();
app.use('*', logger());

app.get('/_health', (c) => c.json({ ok: true }));

const rpc = new RPCHandler(router);

app.use('/rpc/*', async (c, next) => {
  const { matched, response } = await rpc.handle(c.req.raw, {
    prefix: '/rpc',
    context: {},
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
