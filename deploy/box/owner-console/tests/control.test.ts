import { expect, test } from 'bun:test';
import { BadRequest } from '../src/exec';
import { makeApp, ownerCookie } from './helpers';

const calls: unknown[][] = [];
const exec = {
  controlService: (async (a: string, s: string) => {
    if (s === 'boom') throw new Error('docker: not found');
    if (s !== 'caddy') throw new BadRequest('invalid service');
    calls.push([a, s]);
    return { ok: true, audit: 'x' };
  }) as never,
  runReadCommand: (async function* (cmd: string) {
    if (cmd === 'bad') throw new BadRequest('invalid command');
    if (cmd === 'fail') { yield 'one'; throw new Error('spawn failed'); }
    yield 'line1';
    yield 'line2';
  }) as never,
};
const app = makeApp({}, { exec });
const post = (path: string, body: unknown, auth = true) =>
  app.request(path, {
    method: 'POST',
    headers: { 'content-type': 'application/json', ...(auth ? { cookie: ownerCookie() } : {}) },
    body: JSON.stringify(body),
  });

test('control requires owner auth', async () => {
  expect((await post('/api/control', { action: 'restart', service: 'caddy' }, false)).status).toBe(401);
  expect((await post('/api/console', { cmd: 'status' }, false)).status).toBe(401);
});

test('control: allowlisted restart calls exec and returns ok', async () => {
  const r = await post('/api/control', { action: 'restart', service: 'caddy' });
  expect(r.status).toBe(200);
  expect((await r.json()).ok).toBe(true);
  expect(calls).toEqual([['restart', 'caddy']]);
});

test('control: bad service -> 400, exec failure -> 500', async () => {
  const bad = await post('/api/control', { action: 'restart', service: 'evil; rm' });
  expect(bad.status).toBe(400);
  expect((await bad.json()).error).toBeTruthy();
  const boom = await post('/api/control', { action: 'restart', service: 'boom' });
  expect(boom.status).toBe(500);
  expect((await boom.json()).error).toContain('docker');
});

test('control: real exec layer rejects a bad service with 400 (no mock)', async () => {
  const r = await makeApp().request('/api/control', {
    method: 'POST',
    headers: { 'content-type': 'application/json', cookie: ownerCookie() },
    body: JSON.stringify({ action: 'restart', service: 'evil; rm' }),
  });
  expect(r.status).toBe(400);
});

test('console: streams lines as SSE', async () => {
  const r = await post('/api/console', { cmd: 'status' });
  expect(r.status).toBe(200);
  expect(r.headers.get('content-type')).toContain('text/event-stream');
  const t = await r.text();
  expect(t).toContain('data: line1');
  expect(t).toContain('data: line2');
});

test('console: bad cmd -> 400; mid-stream failure -> error event', async () => {
  expect((await post('/api/console', { cmd: 'bad' })).status).toBe(400);
  const t = await (await post('/api/console', { cmd: 'fail' })).text();
  expect(t).toContain('data: one');
  expect(t).toContain('event: error');
});

test('whole-box control is accepted via service __box__ and scope box', async () => {
  const seen: string[] = [];
  const a = makeApp({}, { exec: { controlService: (async (_a: string, s: string) => { seen.push(s); return { ok: true, audit: 'x' }; }) as never, runReadCommand: exec.runReadCommand } });
  const p = (b: unknown) => a.request('/api/control', { method: 'POST', headers: { 'content-type': 'application/json', cookie: ownerCookie() }, body: JSON.stringify(b) });
  expect((await p({ action: 'restart', service: '__box__' })).status).toBe(200);
  expect((await p({ action: 'restart', scope: 'box' })).status).toBe(200);
  expect(seen).toEqual(['__box__', '__box__']);
});
