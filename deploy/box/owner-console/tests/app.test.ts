import { describe, expect, test } from 'bun:test';
import { mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createApp } from '../src/app';
import { signInvite } from '../src/invite';

const spaDist = mkdtempSync(join(tmpdir(), 'appspa-'));
writeFileSync(join(spaDist, 'index.html'), '<!doctype html><div id="root"></div>');

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

  test('GET / with a valid cookie serves the SPA (or falls back to /app)', async () => {
    const app = createApp({ ...dashEnv, WEB_DIST_DIR: spaDist }, { checkHealth: async () => health });
    const cookie = (await app.request(form('hunter2'))).headers.get('set-cookie')!.split(';')[0];
    const r = await app.request('/', { headers: { cookie } });
    expect(r.status).toBe(200);
    expect(await r.text()).toContain('id="root"');
    const bare = createApp({ ...dashEnv, WEB_DIST_DIR: join(spaDist, 'missing') });
    const cookie2 = (await bare.request(form('hunter2'))).headers.get('set-cookie')!.split(';')[0];
    const r2 = await bare.request('/', { headers: { cookie: cookie2 } });
    expect(r2.status).toBe(303);
    expect(r2.headers.get('location')).toBe('/app');
  });

  test('the legacy dashboard routes are gone', async () => {
    const app = createApp(dashEnv, { checkHealth: async () => health });
    expect((await app.request('/invite', { method: 'POST' })).status).toBe(404);
    expect((await app.request('/revoke', { method: 'POST' })).status).toBe(404);
  });

  test('fails closed when no owner password is configured', async () => {
    const app = createApp({ BOX_OWNER_PASSWORD: '', BOX_OWNER_SESSION_SECRET: '' });
    expect((await app.request(form('anything'))).status).toBe(401);
    const r = await app.request('/');
    expect(r.status).toBe(303);                 // still bounced to /login, never in
  });

  // --- member-facing /connect (no login) -----------------------------------
  const connectDeps = {
    checkHealth: async () => health,
    templatesDir: TEMPLATES,
    boxCaB64: async () => 'Ym94Y2E=',
    coordCaB64: () => 'Y29vcmRjYQ==',
    agentSha256: () => ({ amd64: 'a'.repeat(64), arm64: 'b'.repeat(64) }),
  };

  test('GET /agent serves an allow-listed bundle (linux tarball + macOS pkg), 404s anything else', async () => {
    const dir = mkdtempSync(join(tmpdir(), 'agentdist-'));
    writeFileSync(join(dir, 'nufibox-agent-linux-amd64.tar.gz'), 'FAKE-TARBALL');
    writeFileSync(join(dir, 'nufibox-agent-macos.pkg'), 'FAKE-PKG');
    const app = createApp(dashEnv, { checkHealth: async () => health, agentDistDir: dir });
    const ok = await app.request('/agent/nufibox-agent-linux-amd64.tar.gz');   // public, no cookie
    expect(ok.status).toBe(200);
    expect(ok.headers.get('content-disposition')).toContain('nufibox-agent-linux-amd64.tar.gz');
    expect(await ok.text()).toBe('FAKE-TARBALL');
    const pkg = await app.request('/agent/nufibox-agent-macos.pkg');
    expect(pkg.status).toBe(200);
    expect(pkg.headers.get('content-type')).toBe('application/octet-stream');
    expect(await pkg.text()).toBe('FAKE-PKG');
    expect((await app.request('/agent/nufibox-agent-linux-arm64.tar.gz')).status).toBe(404); // allow-listed but absent
    expect((await app.request('/agent/nufibox-agent-linux-x86.tar.gz')).status).toBe(404);   // bad arch
    expect((await app.request('/agent/nufibox-agent-macos.pkg.sha256')).status).toBe(404);   // sha not served here
    expect((await app.request('/agent/evil.sh')).status).toBe(404);                          // not allow-listed
  });

  test('GET /agent/mesh-ca.crt serves the coordinator CA when self-hosted, 404s otherwise', async () => {
    const withCa = createApp(dashEnv, { checkHealth: async () => health, coordCaB64: () => Buffer.from('-----BEGIN CERTIFICATE-----\nX\n-----END CERTIFICATE-----').toString('base64') });
    const r = await withCa.request('/agent/mesh-ca.crt');
    expect(r.status).toBe(200);
    expect(await r.text()).toContain('BEGIN CERTIFICATE');
    const noCa = createApp(dashEnv, { checkHealth: async () => health, coordCaB64: () => '' });
    expect((await noCa.request('/agent/mesh-ca.crt')).status).toBe(404);        // public coordinator: nothing to serve
  });

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

  test('POST /connect/connector returns the Linux agent installer for a valid token', async () => {
    const app = createApp(dashEnv, connectDeps);
    const token = signInvite(dashEnv.BOX_OWNER_SESSION_SECRET, { key: 'k-join-xyz', serverUrl: 'https://coordinator.internal' });
    const r = await app.request('/connect/connector', {
      method: 'POST',
      headers: {
        'content-type': 'application/x-www-form-urlencoded',   // NO cookie: this is public
        host: 'nufi.local', 'x-forwarded-proto': 'http',       // the box origin the member reached
      },
      body: new URLSearchParams({ token, os: 'linux', member: 'Ivy Nguyen' }),
    });
    expect(r.status).toBe(200);
    expect(r.headers.get('content-disposition')).toContain('filename="nufi-join-ivy-nguyen.sh"');
    const body = await r.text();
    expect(body).toContain('k-join-xyz');                          // the key the laptop joins with
    expect(body).toContain('http://nufi.local/agent/nufibox-agent-linux-$ARCH.tar.gz'); // agent from the box
    expect(body).toContain('nufibox-agent/install.sh');
    expect(body).not.toContain('tailscale.com');                  // no external Tailscale download
    expect(body).toContain(`amd64) WANT_SHA="${'a'.repeat(64)}"`); // baked digest flows into the connector
  });

  test('POST /connect/connector returns a JSON plan (pkg + enrol command) for macOS', async () => {
    const app = createApp(dashEnv, connectDeps);
    const token = signInvite(dashEnv.BOX_OWNER_SESSION_SECRET, { key: 'k-join-xyz', serverUrl: 'https://coordinator.internal' });
    const r = await app.request('/connect/connector', {
      method: 'POST',
      headers: {
        'content-type': 'application/x-www-form-urlencoded',
        host: 'nufi.local', 'x-forwarded-proto': 'http',
      },
      body: new URLSearchParams({ token, os: 'macos', member: 'Ivy Nguyen' }),
    });
    expect(r.status).toBe(200);
    expect(r.headers.get('content-type')).toContain('application/json');   // a plan, not a file download
    const plan = await r.json();
    expect(plan.pkgUrl).toBe('http://nufi.local/agent/nufibox-agent-macos.pkg');
    expect(plan.enroll).toContain('nufibox-agent enroll');
    expect(plan.enroll).toContain("--auth-key 'k-join-xyz'");
    expect(plan.enroll).toContain("--hostname 'ivy-nguyen'");
    expect(plan.enroll).toContain('security add-trusted-cert');             // trusts the box CA too
    expect(plan.enroll).toContain("curl -fsS 'http://nufi.local/agent/mesh-ca.crt'"); // connectDeps has a coord CA
    expect(plan.chatUrl).toContain('/register');
  });

  test('reads the baked .sha256 files from the dist dir; a garbled digest is dropped', async () => {
    const dir = mkdtempSync(join(tmpdir(), 'agentsha-'));
    const good = 'a'.repeat(64);
    writeFileSync(join(dir, 'nufibox-agent-linux-amd64.tar.gz.sha256'), `${good}  nufibox-agent-linux-amd64.tar.gz\n`);
    writeFileSync(join(dir, 'nufibox-agent-linux-arm64.tar.gz.sha256'), 'not-a-valid-hex-digest\n');
    // no injected agentSha256 -> exercises the real file reader + hex guard
    const app = createApp(dashEnv, { checkHealth: async () => health, templatesDir: TEMPLATES, agentDistDir: dir });
    const token = signInvite(dashEnv.BOX_OWNER_SESSION_SECRET, { key: 'k', serverUrl: 'https://coordinator.internal' });
    const r = await app.request('/connect/connector', {
      method: 'POST',
      headers: { 'content-type': 'application/x-www-form-urlencoded', host: 'nufi.local', 'x-forwarded-proto': 'http' },
      body: new URLSearchParams({ token, os: 'linux', member: 'x' }),
    });
    const body = await r.text();
    expect(body).toContain(`amd64) WANT_SHA="${good}"`);          // valid hex read from file
    expect(body).toContain('arm64) WANT_SHA="";;');               // garbled -> dropped, check skipped
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
});
