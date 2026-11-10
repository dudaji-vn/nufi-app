import { afterAll, beforeAll, describe, expect, test } from 'bun:test';
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createApp } from './app';

let dist: string;
let app: ReturnType<typeof createApp>;

beforeAll(() => {
  dist = mkdtempSync(join(tmpdir(), 'landing-dist-'));
  const put = (p: string, body: string) => {
    mkdirSync(join(dist, p, '..'), { recursive: true });
    writeFileSync(join(dist, p), body);
  };
  put('index.html', '<h1>home prerendered</h1>');
  put('blog/index.html', '<h1>blog prerendered</h1>');
  put('blog/a-post/index.html', '<h1>a post prerendered</h1>');
  put('blog/a-post.md', '# A post');
  put('llms.txt', '# NuFi');
  put('robots.txt', 'User-agent: *');
  put('sitemap.xml', '<urlset/>');
  put('404.html', '<div id="root"></div>');
  put('assets/app.js', 'console.log(1)');
  app = createApp(dist);
});

afterAll(() => rmSync(dist, { recursive: true, force: true }));

const get = (path: string) => app.fetch(new Request(`http://x${path}`));

describe('prerendered routes', () => {
  test.each([
    ['/', 'home prerendered'],
    ['/blog', 'blog prerendered'],
    ['/blog/', 'blog prerendered'],
    ['/blog/a-post', 'a post prerendered'],
  ])('%s serves its own HTML', async (path, text) => {
    const r = await get(path);
    expect(r.status).toBe(200);
    expect(r.headers.get('content-type')).toContain('text/html');
    expect(await r.text()).toContain(text);
  });
});

describe('files for crawlers and LLMs', () => {
  test.each([
    ['/blog/a-post.md', 'text/markdown', '# A post'],
    ['/llms.txt', 'text/plain', '# NuFi'],
    ['/robots.txt', 'text/plain', 'User-agent'],
    ['/sitemap.xml', 'xml', '<urlset/>'],
  ])('%s is served as %s', async (path, type, text) => {
    const r = await get(path);
    expect(r.status).toBe(200);
    expect(r.headers.get('content-type')).toContain(type);
    expect(await r.text()).toContain(text);
  });

  test('static assets still work', async () => {
    expect((await get('/assets/app.js')).status).toBe(200);
  });
});

describe('unknown paths are real 404s', () => {
  test('a page path gets the app shell with 404', async () => {
    const r = await get('/blog/no-such-post');
    expect(r.status).toBe(404);
    expect(await r.text()).toContain('<div id="root"></div>');
  });

  test('a missing file gets a plain 404, not HTML', async () => {
    const r = await get('/missing.txt');
    expect(r.status).toBe(404);
    expect(r.headers.get('content-type') ?? '').not.toContain('text/html');
  });

  test('path traversal does not escape dist', async () => {
    expect((await get('/..%2f..%2fetc%2fpasswd')).status).toBe(404);
  });
});
