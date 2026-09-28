import { describe, expect, test } from 'bun:test';
import { createApp } from '../src/app';

const ENV = { BOX_OWNER_PASSWORD: 'hunter2', BOX_OWNER_SESSION_SECRET: 'x'.repeat(64) };
const form = (password: string) =>
  new Request('http://x/login', {
    method: 'POST',
    headers: { 'content-type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({ password }),
  });

describe('owner-console app', () => {
  test('GET /healthz is public and returns ok', async () => {
    const r = await createApp(ENV).request('/healthz');
    expect(r.status).toBe(200);
    expect(await r.text()).toBe('ok');
  });

  test('GET / without a session redirects to /login', async () => {
    const r = await createApp(ENV).request('/');
    expect(r.status).toBe(303);
    expect(r.headers.get('location')).toBe('/login');
  });

  test('POST /login with the wrong password is 401', async () => {
    const r = await createApp(ENV).request(form('nope'));
    expect(r.status).toBe(401);
  });

  test('POST /login with the right password sets a cookie and redirects', async () => {
    const r = await createApp(ENV).request(form('hunter2'));
    expect(r.status).toBe(303);
    expect(r.headers.get('location')).toBe('/');
    const setCookie = r.headers.get('set-cookie');
    expect(setCookie).toContain('nufi_owner=');
    expect(setCookie).toMatch(/HttpOnly/i);
    expect(setCookie).toMatch(/Secure/i);
    expect(setCookie).toMatch(/SameSite=Lax/i);
  });

  // A logged-in session for the dashboard tests, with injected health so the
  // route renders deterministically without probing real services.
  const dashEnv = {
    ...ENV,
    BOX_NAME: 'nufi',
    BOX_HOST: 'nufi.local',
    BOX_IP: '192.168.1.10',
    DEPARTMENTS: 'legal,hr',
    MESH_SERVER_URL: 'https://coordinator.internal',
    NUFI_SELF_HOST_COORD: '1',
    BOX_MESH_IP: '100.64.0.1',
    BOX_MESH_HOST: 'nufi.box.internal',
  };
  const health = [
    { name: 'Chat', ok: true, status: 200, ms: 12 },
    { name: 'Gateway', ok: false, error: 'AbortError', ms: 3000 },
  ];
  const loggedIn = async (env = dashEnv, deps = { checkHealth: async () => health }) => {
    const app = createApp(env, deps);
    const login = await app.request(form('hunter2'));
    const cookie = (login.headers.get('set-cookie') ?? '').split(';')[0];
    return { app, cookie };
  };

  test('GET / with a valid cookie renders the status dashboard', async () => {
    const { app, cookie } = await loggedIn();
    const r = await app.request('/', { headers: { cookie } });
    expect(r.status).toBe(200);
    const html = await r.text();
    expect(html).toContain('nufi');                 // box name
    expect(html).toContain('Services');
    expect(html).toContain('Chat');                 // a healthy service
    expect(html).toContain('up · 12ms');
    expect(html).toContain('Gateway');              // an unreachable service
    expect(html).toContain('unreachable');
    expect(html).toContain('100.64.0.1');           // mesh address
    expect(html).toContain('self-hosted on this box');
    expect(html).toContain('legal');                // a department
  });

  test('a LAN-only box shows no mesh address', async () => {
    const { app, cookie } = await loggedIn(
      { ...ENV, BOX_NAME: 'nufi', BOX_HOST: 'nufi.local' },
      { checkHealth: async () => health },
    );
    const r = await app.request('/', { headers: { cookie } });
    const html = await r.text();
    expect(html).toContain('LAN-only');
    expect(html).not.toContain('100.64');
  });

  test('the dashboard route never renders without a valid session', async () => {
    const app = createApp(dashEnv, { checkHealth: async () => health });
    const r = await app.request('/');               // no cookie
    expect(r.status).toBe(303);
    expect(r.headers.get('location')).toBe('/login');
  });

  test('fails closed when no owner password is configured', async () => {
    const app = createApp({ BOX_OWNER_PASSWORD: '', BOX_OWNER_SESSION_SECRET: '' });
    expect((await app.request(form('anything'))).status).toBe(401);
    const r = await app.request('/');
    expect(r.status).toBe(303);                 // still bounced to /login, never in
  });
});
