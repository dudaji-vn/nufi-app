import { Hono } from 'hono';
import { serveStatic } from 'hono/bun';
import { resolve, sep } from 'node:path';
import { rangeResponse } from './range';

// Serves the built SPA from ./dist. Static files are served directly; any
// other path falls back to index.html so client-side routes (/blog, /blog/...)
// resolve on a hard refresh or a shared deep link.
const app = new Hono();

const DIST = resolve('./dist');

// Videos need byte ranges (Safari/iOS won't play them otherwise); everything else goes to serveStatic.
app.get('*', async (c, next) => {
  const range = c.req.header('range');
  if (!range || !/\.(mp4|webm)$/i.test(c.req.path)) return next();
  const path = resolve(DIST, '.' + decodeURIComponent(c.req.path));
  if (!path.startsWith(DIST + sep)) return next();
  return (await rangeResponse(path, range)) ?? next();
});
app.use('/*', serveStatic({ root: './dist' }));
app.get('*', serveStatic({ path: './dist/index.html' }));

const port = Number(process.env.PORT ?? 3000);
console.log(`nufi-landing listening on :${port}`);

export default { port, fetch: app.fetch };
