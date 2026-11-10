import { Hono } from 'hono';
import { existsSync, statSync } from 'node:fs';
import { extname, join, resolve, sep } from 'node:path';
import { rangeResponse } from './range';

// Serves the built site from dist/. Every route is prerendered at build time (scripts/prerender.ts) to
// dist/<route>/index.html, so crawlers and LLM fetchers get real HTML. Unknown pages get the app shell (404.html)
// with a real 404 status; unknown files get a plain 404.
const TYPES: Record<string, string> = {
  '.html': 'text/html; charset=utf-8',
  '.md': 'text/markdown; charset=utf-8',
  '.txt': 'text/plain; charset=utf-8',
  '.xml': 'application/xml; charset=utf-8',
};

const isFile = (p: string) => existsSync(p) && statSync(p).isFile();

function fileResponse(path: string, status = 200): Response {
  const file = Bun.file(path);
  return new Response(file, { status, headers: { 'content-type': TYPES[extname(path)] ?? file.type } });
}

export function createApp(distDir: string) {
  const DIST = resolve(distDir);
  const app = new Hono();

  // Inside dist/, or null (bad encoding, or a path that climbs out).
  const inDist = (urlPath: string): string | null => {
    let rel: string;
    try {
      rel = decodeURIComponent(urlPath);
    } catch {
      return null;
    }
    const p = resolve(DIST, '.' + rel);
    return p === DIST || p.startsWith(DIST + sep) ? p : null;
  };

  // Videos need byte ranges (Safari/iOS won't play them otherwise).
  app.get('*', async (c, next) => {
    const range = c.req.header('range');
    if (!range || !/\.(mp4|webm)$/i.test(c.req.path)) return next();
    const path = inDist(c.req.path);
    return (path && (await rangeResponse(path, range))) || next();
  });

  app.get('*', (c) => {
    const path = inDist(c.req.path);
    if (path) {
      if (isFile(path)) return fileResponse(path);
      const page = join(path, 'index.html');
      if (isFile(page)) return fileResponse(page);
    }
    if (extname(c.req.path)) return c.text('Not found', 404);
    return fileResponse(join(DIST, '404.html'), 404);
  });

  return app;
}
