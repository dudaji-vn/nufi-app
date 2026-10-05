import { expect, test } from 'bun:test';
import { makeApp, ownerCookie } from './helpers';

const health = async () => [{ name: 'Chat', ok: true, ms: 5 }];

test('GET /api/status returns box + services', async () => {
  const r = await makeApp({}, { checkHealth: health }).request('/api/status', { headers: { cookie: ownerCookie() } });
  expect(r.status).toBe(200);
  const j = await r.json();
  expect(j.box).toHaveProperty('name');
  expect(j.services).toEqual([{ name: 'Chat', ok: true, ms: 5 }]);
});

test('GET /api/status without owner cookie is 401', async () => {
  expect((await makeApp({}, { checkHealth: health }).request('/api/status')).status).toBe(401);
});

test('GET /api/ping stays public', async () => {
  expect((await makeApp().request('/api/ping')).status).toBe(200);
});

test('GET /api/status passes detail through and stays 200 without it', async () => {
  const h = async () => [{ name: 'Chat', ok: true, ms: 5, detail: 'v1' }, { name: 'AI model', ok: true, ms: 6 }];
  const r = await makeApp({}, { checkHealth: h }).request('/api/status', { headers: { cookie: ownerCookie() } });
  expect(r.status).toBe(200);
  const j = await r.json();
  expect(j.services[0].detail).toBe('v1');
  expect(j.services[1].detail).toBeUndefined();
});
