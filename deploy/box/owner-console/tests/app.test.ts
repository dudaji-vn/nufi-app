import { describe, expect, test } from 'bun:test';
import { join } from 'node:path';
import { createApp } from '../src/app';
import { signInvite } from '../src/invite';

const TEMPLATES = join(import.meta.dir, '../../lib/join-templates');

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
    MESH_API_KEY: 'k-api',
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

  test('the dashboard offers no invite button when the console lacks the coordinator API key', async () => {
    // serverUrl set but no MESH_API_KEY: minting is impossible, so show the
    // precise reason, not a button that only fails.
    const env = { ...ENV, BOX_NAME: 'nufi', MESH_SERVER_URL: 'https://coordinator.internal' };
    const { app, cookie } = await loggedIn(env, { checkHealth: async () => health });
    const html = await (await app.request('/', { headers: { cookie } })).text();
    expect(html).toContain('no coordinator API key');
    expect(html).not.toContain('Generate an invite link');
  });

  // --- members list + revoke + drives (sub-task 05) -------------------------
  const members = [
    { id: '1', name: 'nufi', ips: ['100.64.0.1'], online: true, lastSeen: '', tags: ['tag:box'] },
    { id: '2', name: 'ivy', ips: ['100.64.0.5'], online: false, lastSeen: '', tags: ['tag:member'] },
  ];

  test('the dashboard lists members and drive paths; the box node has no Revoke', async () => {
    const { app, cookie } = await loggedIn(dashEnv, { checkHealth: async () => health, listMembers: async () => members });
    const html = await (await app.request('/', { headers: { cookie } })).text();
    expect(html).toContain('ivy');
    expect(html).toContain('100.64.0.5');
    expect(html).toContain('this box');                          // the box node, not revocable
    expect(html).toContain('value="2"');                         // a Revoke form targets the member by id
    expect(html).not.toContain('value="1"');                     // never a Revoke form for the box node
    expect(html).toContain('smb://nufi.box.internal/legal');     // a department drive path
  });

  test('the dashboard shows a clear notice when the member list is unavailable', async () => {
    const { app, cookie } = await loggedIn(dashEnv, {
      checkHealth: async () => health,
      listMembers: async () => ({ error: 'coordinator unreachable' }),
    });
    const html = await (await app.request('/', { headers: { cookie } })).text();
    expect(html).toContain('Member list unavailable');
  });

  test('POST /revoke without a session redirects to /login', async () => {
    const app = createApp(dashEnv, { checkHealth: async () => health });
    const r = await app.request('/revoke', { method: 'POST' });
    expect(r.status).toBe(303);
    expect(r.headers.get('location')).toBe('/login');
  });

  test('POST /revoke removes the node by id and reloads the dashboard', async () => {
    let revoked = '';
    const { app, cookie } = await loggedIn(dashEnv, {
      checkHealth: async () => health,
      revoke: async (_cfg, id) => { revoked = id; },
    });
    const r = await app.request('/revoke', {
      method: 'POST',
      headers: { cookie, 'content-type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({ id: '2' }),
    });
    expect(revoked).toBe('2');
    expect(r.status).toBe(303);
    expect(r.headers.get('location')).toBe('/');
  });

  test('POST /invite without a session redirects to /login', async () => {
    const app = createApp(dashEnv, { checkHealth: async () => health, mint: async () => 'k' });
    const r = await app.request('/invite', { method: 'POST' });
    expect(r.status).toBe(303);
    expect(r.headers.get('location')).toBe('/login');
  });

  test('POST /invite mints a key and returns a /connect share link on the request origin', async () => {
    const app = createApp(dashEnv, { checkHealth: async () => health, mint: async () => 'k-member-xyz' });
    const login = await app.request(form('hunter2'));
    const cookie = (login.headers.get('set-cookie') ?? '').split(';')[0];
    const r = await app.request('/invite', {
      method: 'POST',
      headers: { cookie, host: 'nufi.local:3009', 'x-forwarded-proto': 'https' },
    });
    expect(r.status).toBe(200);
    const html = await r.text();
    expect(html).toContain('https://nufi.local:3009/connect#token=');
    expect(html).toContain('works once and expires');
    expect(html).not.toContain('k-member-xyz');    // the raw key is inside the token, never shown
  });

  test('POST /invite on a LAN-only box explains it must join a mesh first', async () => {
    const app = createApp({ ...ENV, BOX_NAME: 'nufi' }, { checkHealth: async () => health, mint: async () => 'k' });
    const login = await app.request(form('hunter2'));
    const cookie = (login.headers.get('set-cookie') ?? '').split(';')[0];
    const r = await app.request('/invite', { method: 'POST', headers: { cookie } });
    expect(r.status).toBe(200);
    expect(await r.text()).toContain('not on a mesh yet');
  });

  // --- member-facing /connect (no login) -----------------------------------
  const connectDeps = {
    checkHealth: async () => health,
    templatesDir: TEMPLATES,
    boxCaB64: async () => 'Ym94Y2E=',
    coordCaB64: () => 'Y29vcmRjYQ==',
  };

  test('GET /connect is public, shows the OS picker, and carries no token', async () => {
    const app = createApp(dashEnv, connectDeps);
    const r = await app.request('/connect');       // no cookie
    expect(r.status).toBe(200);
    const html = await r.text();
    expect(html).toContain('data-os="macos"');
    expect(html).toContain('data-os="windows"');
    expect(html).toContain('data-os="linux"');
    expect(html).not.toContain('token=');           // token lives in the fragment, read client-side
  });

  test('POST /connect/connector returns a downloadable per-OS join file for a valid token', async () => {
    const app = createApp(dashEnv, connectDeps);
    const token = signInvite(dashEnv.BOX_OWNER_SESSION_SECRET, { key: 'k-join-xyz', serverUrl: 'https://coordinator.internal' });
    const r = await app.request('/connect/connector', {
      method: 'POST',
      headers: { 'content-type': 'application/x-www-form-urlencoded' },   // NO cookie: this is public
      body: new URLSearchParams({ token, os: 'linux', member: 'Ivy Nguyen' }),
    });
    expect(r.status).toBe(200);
    expect(r.headers.get('content-disposition')).toContain('filename="nufi-join-ivy-nguyen.sh"');
    const body = await r.text();
    expect(body).toContain('k-join-xyz');           // the key the laptop joins with
    expect(body).toContain('https://coordinator.internal');
    expect(body).toContain('gio mount');            // a department drive line
    expect(body).not.toMatch(/@[A-Z_]+@/);          // every placeholder filled
  });

  test('POST /connect/connector rejects an invalid/expired token', async () => {
    const app = createApp(dashEnv, connectDeps);
    const r = await app.request('/connect/connector', {
      method: 'POST',
      headers: { 'content-type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({ token: 'not-a-real-token', os: 'linux', member: 'x' }),
    });
    expect(r.status).toBe(400);
  });

  test('POST /connect/connector rejects an unknown OS', async () => {
    const app = createApp(dashEnv, connectDeps);
    const token = signInvite(dashEnv.BOX_OWNER_SESSION_SECRET, { key: 'k', serverUrl: 'https://c' });
    const r = await app.request('/connect/connector', {
      method: 'POST',
      headers: { 'content-type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({ token, os: 'beos', member: 'x' }),
    });
    expect(r.status).toBe(400);
  });

  test('a session token cannot be used as an invite at /connect/connector (audience split)', async () => {
    const { signSession } = await import('../src/auth');
    const app = createApp(dashEnv, connectDeps);
    const sessionToken = signSession(dashEnv.BOX_OWNER_SESSION_SECRET);
    const r = await app.request('/connect/connector', {
      method: 'POST',
      headers: { 'content-type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({ token: sessionToken, os: 'linux', member: 'x' }),
    });
    expect(r.status).toBe(400);                     // rejected: not an invite-aud token
  });

  test('POST /invite surfaces an unreachable coordinator with the egress hint', async () => {
    const { MeshError } = await import('../src/mesh-api');
    const app = createApp(dashEnv, {
      checkHealth: async () => health,
      mint: async () => { throw new MeshError('coordinator unreachable: ECONNREFUSED'); },
    });
    const login = await app.request(form('hunter2'));
    const cookie = (login.headers.get('set-cookie') ?? '').split(';')[0];
    const r = await app.request('/invite', { method: 'POST', headers: { cookie } });
    const html = await r.text();
    expect(html).toContain('Invite failed');
    expect(html).toContain('egress allow-list');
  });
});
