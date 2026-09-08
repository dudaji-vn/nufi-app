import path from 'node:path';
import { file } from 'bun';
import type { MiddlewareHandler } from 'hono';
import { injectPublicConfig, readPublicConfig } from '../public-config.ts';

const DIST = path.resolve(import.meta.dir, '../../dist');

const MIME: Record<string, string> = {
  '.js': 'application/javascript; charset=utf-8',
  '.mjs': 'application/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.html': 'text/html; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.webp': 'image/webp',
  '.ico': 'image/x-icon',
  '.json': 'application/json; charset=utf-8',
  '.map': 'application/json; charset=utf-8',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
};

// A box does not know its own hostname at image-build time, so the chat,
// gateway and Works URLs are read from PUBLIC_* env at serve time rather than
// baked in by Vite. index.html is read and injected once per process --
// there is exactly one build to serve for the life of this process, and the
// env it reads from does not change underneath it.
let cachedIndexHtml: string | null | undefined;

async function getIndexHtml(): Promise<string | null> {
  if (cachedIndexHtml !== undefined) return cachedIndexHtml;
  const indexFile = file(path.join(DIST, 'index.html'));
  if (!(await indexFile.exists())) {
    cachedIndexHtml = null;
    return cachedIndexHtml;
  }
  cachedIndexHtml = injectPublicConfig(await indexFile.text(), readPublicConfig());
  return cachedIndexHtml;
}

/**
 * Serve the Vite-built SPA from ./dist. Static assets are returned with
 * appropriate Content-Type; everything else falls through to index.html so
 * client-side routing works (TanStack Router handles unknown paths). Every
 * response carrying index.html -- the fallback below and a direct request for
 * it -- gets the injected runtime config, since both serve the same file.
 */
export function servePublic(): MiddlewareHandler {
  return async (c) => {
    const url = new URL(c.req.url);
    const requested = path.join(DIST, url.pathname);
    const safe = requested.startsWith(DIST) ? requested : path.join(DIST, 'index.html');
    const ext = path.extname(safe);

    if (ext && ext !== '.html') {
      const f = file(safe);
      if (await f.exists()) {
        const type = MIME[ext] ?? 'application/octet-stream';
        return new Response(f, {
          headers: { 'Content-Type': type, 'Cache-Control': 'public, max-age=31536000, immutable' },
        });
      }
    }

    const indexHtml = await getIndexHtml();
    if (indexHtml === null) {
      return c.text('SPA build missing — run `bun run build`.', 500);
    }
    return new Response(indexHtml, {
      headers: { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-cache' },
    });
  };
}
