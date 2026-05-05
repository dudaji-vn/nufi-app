import type { MiddlewareHandler } from 'hono';
import { file } from 'bun';
import path from 'node:path';

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

/**
 * Serve the Vite-built SPA from ./dist. Static assets are returned with
 * appropriate Content-Type; everything else falls through to index.html so
 * client-side routing works (TanStack Router handles unknown paths).
 */
export function servePublic(): MiddlewareHandler {
  return async (c) => {
    const url = new URL(c.req.url);
    const requested = path.join(DIST, url.pathname);
    const safe = requested.startsWith(DIST) ? requested : path.join(DIST, 'index.html');
    const ext = path.extname(safe);

    if (ext) {
      const f = file(safe);
      if (await f.exists()) {
        const type = MIME[ext] ?? 'application/octet-stream';
        return new Response(f, {
          headers: {
            'Content-Type': type,
            'Cache-Control': ext === '.html' ? 'no-cache' : 'public, max-age=31536000, immutable',
          },
        });
      }
    }

    const indexHtml = file(path.join(DIST, 'index.html'));
    if (!(await indexHtml.exists())) {
      return c.text('SPA build missing — run `bun run build`.', 500);
    }
    return new Response(indexHtml, {
      headers: { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-cache' },
    });
  };
}
