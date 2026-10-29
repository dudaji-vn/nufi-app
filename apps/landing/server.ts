import { Hono } from 'hono';
import { serveStatic } from 'hono/bun';

// Serves the built SPA from ./dist. Static files are served directly; any
// other path falls back to index.html so client-side routes (/blog, /blog/...)
// resolve on a hard refresh or a shared deep link.
const app = new Hono();

app.use('/*', serveStatic({ root: './dist' }));
app.get('*', serveStatic({ path: './dist/index.html' }));

const port = Number(process.env.PORT ?? 3000);
console.log(`nufi-landing listening on :${port}`);

export default { port, fetch: app.fetch };
