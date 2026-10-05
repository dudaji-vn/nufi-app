import { afterAll, beforeAll, describe, expect, test } from 'bun:test';
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { makeApp, ownerCookie } from './helpers';

let dist = '';
beforeAll(() => {
  dist = mkdtempSync(join(tmpdir(), 'spa-'));
  mkdirSync(join(dist, 'assets'));
  writeFileSync(join(dist, 'index.html'), '<!doctype html><div id="root"></div>');
  writeFileSync(join(dist, 'assets', 'app.js'), 'console.log(1)');
});
afterAll(() => rmSync(dist, { recursive: true, force: true }));

describe('SPA serving', () => {
  test('GET /api/ping returns ok', async () => {
    const r = await makeApp({ WEB_DIST_DIR: dist }).request('/api/ping');
    expect(r.status).toBe(200);
    expect(await r.json()).toEqual({ ok: true });
  });

  test('GET /app serves the SPA index', async () => {
    const r = await makeApp({ WEB_DIST_DIR: dist }).request('/app');
    expect(r.status).toBe(200);
    expect(r.headers.get('content-type') || '').toContain('text/html');
    expect(await r.text()).toContain('id="root"');
  });

  test('GET /assets/* serves static files', async () => {
    const r = await makeApp({ WEB_DIST_DIR: dist }).request('/assets/app.js');
    expect(r.status).toBe(200);
    expect(r.headers.get('content-type') || '').toContain('javascript');
  });

  test('unknown non-api route falls back to the SPA index; unknown /api is 404', async () => {
    const app = makeApp({ WEB_DIST_DIR: dist });
    const spa = await app.request('/app/members/42');
    expect(spa.status).toBe(200);
    expect(await spa.text()).toContain('id="root"');
    expect((await app.request('/api/nope', { headers: { cookie: ownerCookie() } })).status).toBe(404);
    expect((await app.request('/assets/missing.js')).status).toBe(404);
  });

  test('path traversal cannot escape the dist dir', async () => {
    const r = await makeApp({ WEB_DIST_DIR: dist }).request('/assets/..%2f..%2fetc/passwd');
    expect(r.status).toBe(404);
  });

  test('legacy routes still work', async () => {
    const app = makeApp({ WEB_DIST_DIR: dist });
    expect((await app.request('/healthz')).status).toBe(200);
    expect((await app.request('/login')).status).toBe(200);
  });
});
