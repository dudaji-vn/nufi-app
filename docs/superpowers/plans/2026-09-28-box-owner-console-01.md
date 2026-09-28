# Box Owner Console — Sub-task 01 (scaffold + owner login) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a Bun + Hono web service in the box that an owner logs into with a local password, laying the foundation the status dashboard, invites, and /connect page build on.

**Architecture:** A new profile-gated container `owner-console` (built from `deploy/box/owner-console/`), fronted by Caddy on a new TLS port `:3009`, reverse-proxied to its internal `:8890`. Server-rendered HTML, no SPA. Owner auth is a locally generated password checked in constant time; the session is an HMAC-signed cookie. Socket-free: no Docker socket, no host shell. Opt-in via `install-box.sh --owner-console` (`NUFI_OWNER_CONSOLE=1`); a box without the flag is byte-for-byte unchanged.

**Tech Stack:** Bun (`oven/bun:1.4.2-alpine`), Hono `4.13.9`, `node:crypto` (HMAC + timingSafeEqual). Tests: `bun test` for handlers; daemon-free `pytest` for compose/Caddy/install. CI: box-ci `Box suites` + a new Bun step.

**Spec:** `docs/superpowers/specs/2026-09-28-box-owner-console-design.md`

## Global Constraints

- **Opt-in / additive:** the service is `profiles: [owner-console]`; the profile is added to the compose command only when `NUFI_OWNER_CONSOLE=1`. A box without the flag runs an identical compose plan (no `owner-console` service) and prints no owner-console banner line. Following the box's existing pattern (`ADMIN_PASSWORD`, `WORKS_AUTH_SECRET` are generated on *every* box regardless of whether the feature is on), the owner secrets and the tag/flag vars ARE written to every box's `.env` — "off by default" means the profile is absent, the service does not run, and the banner is silent; it does NOT mean the vars are absent.
- **Socket-free:** the `owner-console` service mounts **no** Docker socket and never shells the host. (01 reaches nothing outbound; 02+ use HTTP + headscale REST.)
- **Pin every image exact, never `:latest`:** Bun base is `oven/bun:1.4.2-alpine`; Hono is `4.13.9`.
- **Secrets only via `.env`:** `BOX_OWNER_PASSWORD` and `BOX_OWNER_SESSION_SECRET` are generated unconditionally by `install-box.sh` (exactly like `ADMIN_PASSWORD` / `ADMIN_SESSION_SECRET` / `WORKS_AUTH_SECRET`) and injected via compose env interpolation. Plaintext in `.env` is consistent with every other box secret; the console verifies with `crypto.timingSafeEqual` (a constant-time compare is the right primitive here — argon2 over a plaintext-`.env` generated-random secret buys nothing, so the spec's "argon2" wording is deliberately implemented as constant-time compare + HMAC-signed cookie).
- **bash 3.2 compatible** for `install-box.sh` / `nufi-box` edits.
- **Ports:** Caddy TLS site `:3009`; container internal `:8890`.
- **Commits:** English messages, end every commit with:
  ```
  Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01P36BNm3JLmSMieHEdaBtsm
  ```
- **Branch:** `feat/box-owner-console` (already created; the spec is committed there).

---

## File Structure

**New — the service (`deploy/box/owner-console/`):**
- `package.json` — pins `hono@4.13.9`; `type: module`.
- `tsconfig.json` — Bun/ESNext, so `bun test` and the editor agree.
- `src/auth.ts` — `verifyPassword`, `signSession`, `verifySession` (pure, no I/O).
- `src/views.ts` — `loginPage(error?)`, `dashboardShell()` server-rendered HTML.
- `src/app.ts` — `createApp(env)` returns a Hono app wiring routes + the session guard.
- `src/server.ts` — Bun entrypoint (`export default { port, fetch }`).
- `tests/auth.test.ts` — unit tests for `src/auth.ts`.
- `tests/app.test.ts` — route/flow tests for `src/app.ts`.
- `Dockerfile` — build the image from `oven/bun:1.4.2-alpine`.
- `.dockerignore` — keep `node_modules`, `tests` out of the image.

**Modified:**
- `deploy/box/docker-compose.yml` — add the `owner-console` service (profile `owner-console`).
- `deploy/box/Caddyfile` — add the `:3009` site.
- `deploy/box/nufi-box` — add the profile to its COMPOSE assembly.
- `deploy/box/install-box.sh` — `--owner-console` flag, `NUFI_OWNER_CONSOLE`, the two secrets, the `NUFI_OWNER_CONSOLE_TAG` default, `render_env`, the banner line, `REUSE_VARS`, help text, and its COMPOSE assembly.
- `deploy/box/Makefile` — publish the image in `save` (offline bundle) and `registry-push` (LAN mirror).
- `deploy/box/tests/test_compose.py` — assert the profiled, socket-free service.
- `deploy/box/tests/test_caddyfile.py` — assert the `:3009` site.
- `deploy/box/tests/test_install.py` — assert the flag/secrets/banner in `--dry-run`.
- `deploy/box/tests/test_makefile.py` — cover the new image in the bundle/mirror.
- `.github/workflows/box-ci.yml` — a `bun test` step for the console.
- `.github/workflows/box-images.yml` — build + push `nufi-owner-console`.

---

### Task 1: Scaffold the service and the auth module

**Files:**
- Create: `deploy/box/owner-console/package.json`
- Create: `deploy/box/owner-console/tsconfig.json`
- Create: `deploy/box/owner-console/src/auth.ts`
- Test: `deploy/box/owner-console/tests/auth.test.ts`

**Interfaces:**
- Produces:
  - `verifyPassword(input: string, expected: string): boolean` — constant-time; `false` when `expected` is empty (fail-closed).
  - `signSession(secret: string, ttlSeconds?: number, now?: number): string` — returns `"<body>.<sig>"`.
  - `verifySession(secret: string, token: string | undefined, now?: number): { exp: number } | null` — `null` on bad signature, malformed token, or expiry.

- [ ] **Step 1: Create `package.json`**

```json
{
  "name": "nufi-owner-console",
  "private": true,
  "type": "module",
  "dependencies": {
    "hono": "4.13.9"
  }
}
```

- [ ] **Step 2: Create `tsconfig.json`**

```json
{
  "compilerOptions": {
    "lib": ["ESNext"],
    "module": "ESNext",
    "target": "ESNext",
    "moduleResolution": "bundler",
    "types": ["bun-types"],
    "strict": true,
    "skipLibCheck": true,
    "noEmit": true
  }
}
```

- [ ] **Step 3: Install deps (creates `bun.lock`)**

Run: `cd deploy/box/owner-console && bun install`
Expected: `hono@4.13.9` installed, `bun.lock` written.

- [ ] **Step 4: Write the failing test `tests/auth.test.ts`**

```ts
import { describe, expect, test } from 'bun:test';
import { signSession, verifyPassword, verifySession } from '../src/auth';

const SECRET = 'x'.repeat(64);

describe('verifyPassword', () => {
  test('accepts the right password', () => {
    expect(verifyPassword('hunter2', 'hunter2')).toBe(true);
  });
  test('rejects the wrong password', () => {
    expect(verifyPassword('nope', 'hunter2')).toBe(false);
  });
  test('fails closed when no password is configured', () => {
    expect(verifyPassword('anything', '')).toBe(false);
  });
});

describe('session token', () => {
  test('round-trips a signed token', () => {
    const t = signSession(SECRET);
    expect(verifySession(SECRET, t)).not.toBeNull();
  });
  test('rejects a tampered signature', () => {
    const t = signSession(SECRET);
    const bad = t.slice(0, -1) + (t.endsWith('a') ? 'b' : 'a');
    expect(verifySession(SECRET, bad)).toBeNull();
  });
  test('rejects a token signed with another secret', () => {
    expect(verifySession(SECRET, signSession('y'.repeat(64)))).toBeNull();
  });
  test('rejects an expired token', () => {
    const past = Date.now() - 10_000;
    const t = signSession(SECRET, -1, past);      // exp already behind `now`
    expect(verifySession(SECRET, t)).toBeNull();
  });
  test('rejects a missing token and a missing secret', () => {
    expect(verifySession(SECRET, undefined)).toBeNull();
    expect(verifySession('', signSession(SECRET))).toBeNull();
  });
});
```

- [ ] **Step 5: Run it to verify it fails**

Run: `cd deploy/box/owner-console && bun test tests/auth.test.ts`
Expected: FAIL — cannot resolve `../src/auth`.

- [ ] **Step 6: Write `src/auth.ts`**

```ts
import { createHash, createHmac, timingSafeEqual } from 'node:crypto';

// Constant-time password check. Hash both sides to a fixed 32 bytes first, so
// timingSafeEqual never sees unequal lengths (it throws on those) and the
// comparison leaks neither length nor content. Empty `expected` (no owner
// password configured on this box) always fails: the console is fail-closed.
export function verifyPassword(input: string, expected: string): boolean {
  if (!expected) return false;
  const a = createHash('sha256').update(input).digest();
  const b = createHash('sha256').update(expected).digest();
  return timingSafeEqual(a, b);
}

const b64url = (b: Buffer) => b.toString('base64url');

// A session token is `<body>.<sig>` where body is base64url({exp}) and sig is
// the HMAC-SHA256 of body under the box's session secret. No server-side store.
export function signSession(secret: string, ttlSeconds = 8 * 3600, now = Date.now()): string {
  const exp = Math.floor(now / 1000) + ttlSeconds;
  const body = b64url(Buffer.from(JSON.stringify({ exp })));
  const sig = b64url(createHmac('sha256', secret).update(body).digest());
  return `${body}.${sig}`;
}

export function verifySession(
  secret: string,
  token: string | undefined,
  now = Date.now(),
): { exp: number } | null {
  if (!secret || !token) return null;
  const dot = token.lastIndexOf('.');
  if (dot < 0) return null;
  const body = token.slice(0, dot);
  const sig = token.slice(dot + 1);
  const expected = b64url(createHmac('sha256', secret).update(body).digest());
  const s = Buffer.from(sig);
  const e = Buffer.from(expected);
  if (s.length !== e.length || !timingSafeEqual(s, e)) return null;
  try {
    const payload = JSON.parse(Buffer.from(body, 'base64url').toString());
    if (typeof payload.exp !== 'number' || payload.exp < Math.floor(now / 1000)) return null;
    return payload as { exp: number };
  } catch {
    return null;
  }
}
```

- [ ] **Step 7: Run the test to verify it passes**

Run: `cd deploy/box/owner-console && bun test tests/auth.test.ts`
Expected: PASS (all cases).

- [ ] **Step 8: Commit**

```bash
git add deploy/box/owner-console/package.json deploy/box/owner-console/tsconfig.json \
  deploy/box/owner-console/bun.lock deploy/box/owner-console/src/auth.ts \
  deploy/box/owner-console/tests/auth.test.ts
git commit -m "feat(box): owner-console auth module (constant-time password + signed session)"
```

---

### Task 2: The Hono app — login, logout, session guard, dashboard shell

**Files:**
- Create: `deploy/box/owner-console/src/views.ts`
- Create: `deploy/box/owner-console/src/app.ts`
- Create: `deploy/box/owner-console/src/server.ts`
- Test: `deploy/box/owner-console/tests/app.test.ts`

**Interfaces:**
- Consumes: `verifyPassword`, `signSession`, `verifySession` from `src/auth.ts` (Task 1).
- Produces:
  - `createApp(env?: { BOX_OWNER_PASSWORD?: string; BOX_OWNER_SESSION_SECRET?: string }): Hono` — routes `GET /healthz`, `GET /login`, `POST /login`, `POST /logout`, `GET /`.
  - `loginPage(error?: string): string`, `dashboardShell(): string`.
  - `src/server.ts` default export `{ port: number, fetch: app.fetch }` for `bun run`.

- [ ] **Step 1: Write `src/views.ts`**

```ts
const shell = (title: string, body: string) => `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>${title}</title>
<style>
  :root{color-scheme:light dark}
  body{font:16px/1.5 system-ui,sans-serif;max-width:24rem;margin:4rem auto;padding:0 1rem}
  h1{font-weight:600;font-size:1.4rem}
  form{display:flex;flex-direction:column;gap:.75rem;margin-top:1.5rem}
  input,button{font:inherit;padding:.6rem .7rem;border-radius:8px;border:1px solid #8886}
  button{cursor:pointer;font-weight:600}
  .err{color:#c0392b;margin-top:1rem}
</style></head><body>${body}</body></html>`;

export function loginPage(error?: string): string {
  return shell('NuFi box · owner', `
  <h1>NuFi box owner</h1>
  <form method="post" action="/login">
    <label>Owner password<input type="password" name="password" autofocus required></label>
    <button type="submit">Sign in</button>
  </form>
  ${error ? `<p class="err">${error}</p>` : ''}`);
}

export function dashboardShell(): string {
  return shell('NuFi box · owner', `
  <h1>NuFi box owner</h1>
  <p>Signed in. Status, invites and drives arrive here next.</p>
  <form method="post" action="/logout"><button type="submit">Sign out</button></form>`);
}
```

- [ ] **Step 2: Write the failing test `tests/app.test.ts`**

```ts
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
    expect(r.headers.get('set-cookie')).toContain('nufi_owner=');
  });

  test('GET / with a valid cookie renders the dashboard', async () => {
    const app = createApp(ENV);
    const login = await app.request(form('hunter2'));
    const cookie = (login.headers.get('set-cookie') ?? '').split(';')[0];
    const r = await app.request('/', { headers: { cookie } });
    expect(r.status).toBe(200);
    expect(await r.text()).toContain('Signed in');
  });

  test('fails closed when no owner password is configured', async () => {
    const app = createApp({ BOX_OWNER_PASSWORD: '', BOX_OWNER_SESSION_SECRET: '' });
    expect((await app.request(form('anything'))).status).toBe(401);
    const r = await app.request('/');
    expect(r.status).toBe(303);                 // still bounced to /login, never in
  });
});
```

- [ ] **Step 3: Run it to verify it fails**

Run: `cd deploy/box/owner-console && bun test tests/app.test.ts`
Expected: FAIL — cannot resolve `../src/app`.

- [ ] **Step 4: Write `src/app.ts`**

```ts
import { Hono } from 'hono';
import { deleteCookie, getCookie, setCookie } from 'hono/cookie';
import { signSession, verifyPassword, verifySession } from './auth';
import { dashboardShell, loginPage } from './views';

const COOKIE = 'nufi_owner';
const NOT_CONFIGURED = 'The owner password is not configured on this box.';

export function createApp(
  env: { BOX_OWNER_PASSWORD?: string; BOX_OWNER_SESSION_SECRET?: string } = process.env,
): Hono {
  const password = env.BOX_OWNER_PASSWORD ?? '';
  const secret = env.BOX_OWNER_SESSION_SECRET ?? '';
  const configured = Boolean(password && secret);
  const app = new Hono();

  app.get('/healthz', (c) => c.text('ok'));

  app.get('/login', (c) => c.html(loginPage(configured ? undefined : NOT_CONFIGURED)));

  app.post('/login', async (c) => {
    if (!configured) return c.html(loginPage(NOT_CONFIGURED), 401);
    const body = await c.req.parseBody();
    const pw = typeof body.password === 'string' ? body.password : '';
    if (!verifyPassword(pw, password)) return c.html(loginPage('Wrong password.'), 401);
    setCookie(c, COOKIE, signSession(secret), {
      httpOnly: true, secure: true, sameSite: 'Lax', path: '/',
    });
    return c.redirect('/', 303);
  });

  app.post('/logout', (c) => {
    deleteCookie(c, COOKIE, { path: '/' });
    return c.redirect('/login', 303);
  });

  app.get('/', (c) => {
    if (!configured || !verifySession(secret, getCookie(c, COOKIE))) return c.redirect('/login', 303);
    return c.html(dashboardShell());
  });

  return app;
}
```

- [ ] **Step 5: Write `src/server.ts`**

```ts
import { createApp } from './app';

const app = createApp();
export default { port: Number(process.env.PORT ?? 8890), fetch: app.fetch };
```

- [ ] **Step 6: Run the whole suite to verify it passes**

Run: `cd deploy/box/owner-console && bun test`
Expected: PASS (auth + app).

- [ ] **Step 7: Commit**

```bash
git add deploy/box/owner-console/src/views.ts deploy/box/owner-console/src/app.ts \
  deploy/box/owner-console/src/server.ts deploy/box/owner-console/tests/app.test.ts
git commit -m "feat(box): owner-console login/logout, session guard, dashboard shell"
```

---

### Task 3: Dockerfile + the profiled, socket-free compose service

**Files:**
- Create: `deploy/box/owner-console/Dockerfile`
- Create: `deploy/box/owner-console/.dockerignore`
- Modify: `deploy/box/docker-compose.yml` (add the `owner-console` service)
- Modify: `deploy/box/.env.example` (declare the new vars — required by test_compose's env-coverage test, which this task runs)
- Modify: `deploy/box/nufi-box` (add the profile to its COMPOSE assembly)
- Test: `deploy/box/tests/test_compose.py`

**Interfaces:**
- Consumes: the app from Tasks 1–2 (`src/server.ts` is the container entrypoint).
- Produces: a compose service named `owner-console`, only present under `--profile owner-console`, on network `box`, publishing no ports, mounting no Docker socket, reading `BOX_OWNER_PASSWORD` / `BOX_OWNER_SESSION_SECRET` / `PORT` from the environment.

**Ruling (pre-flight):** adding this service's `${NUFI_REGISTRY:-ghcr.io/dudaji-vn}/nufi-owner-console:` ref makes `tests/test_makefile.py` derive `nufi-owner-console` into `NUFI_IMAGES`, so that file goes RED until Task 6 adds its `TAG_KEY` entry and Makefile lines. That is expected: no task between here and Task 6 uses test_makefile as its gate; the controller runs the full suite after Task 6. This task's gate is `test_compose.py` only.

- [ ] **Step 1: Write `.dockerignore`**

```
node_modules
tests
bun.lock
```
(Keep `bun.lock` out of the layer used for the copy step below — it is used only at install time, which happens before the source copy.)

- [ ] **Step 2: Write `Dockerfile`**

```dockerfile
FROM oven/bun:1.4.2-alpine
WORKDIR /app
COPY package.json bun.lock ./
RUN bun install --frozen-lockfile --production
COPY src ./src
ENV PORT=8890
EXPOSE 8890
USER bun
CMD ["bun", "run", "src/server.ts"]
```

Note: adjust `.dockerignore` so `bun.lock` IS available to the `COPY package.json bun.lock` line — remove `bun.lock` from `.dockerignore` (it must ship for `--frozen-lockfile`). Final `.dockerignore` is:
```
node_modules
tests
```

- [ ] **Step 3: Add the service to `docker-compose.yml`**

Add after the `admin-panel` service block (mirror its shape: `logging: *box-logging`, `restart`, `networks: [box]`, a `bun -e` healthcheck). No `depends_on` (01 talks to nothing):

```yaml
  owner-console:
    logging: *box-logging
    image: ${NUFI_REGISTRY:-ghcr.io/dudaji-vn}/nufi-owner-console:${NUFI_OWNER_CONSOLE_TAG:-main}
    profiles: [owner-console]
    restart: unless-stopped
    environment:
      PORT: 8890
      BOX_OWNER_PASSWORD: ${BOX_OWNER_PASSWORD:-}
      BOX_OWNER_SESSION_SECRET: ${BOX_OWNER_SESSION_SECRET:-}
    healthcheck:
      test: ["CMD-SHELL", "bun -e \"fetch('http://127.0.0.1:8890/healthz').then(r=>{if(!r.ok)throw 1}).catch(()=>process.exit(1))\""]
      interval: 15s
      timeout: 5s
      retries: 5
      start_period: 10s
    networks: [box]
```

- [ ] **Step 3b: Declare the new vars in `.env.example`**

`tests/test_compose.py::test_env_example_covers_every_variable` fails unless every `${VAR}` a compose file references is declared in `.env.example`. The service above adds `${NUFI_OWNER_CONSOLE_TAG}`, `${BOX_OWNER_PASSWORD}`, `${BOX_OWNER_SESSION_SECRET}`. Add these lines to `.env.example` (near the other `NUFI_*_TAG` and secret entries, mirroring the `WORKS_AUTH_SECRET=replace-me` style):

```
NUFI_OWNER_CONSOLE=0                # 1 = the owner-console profile is part of this box's stack
NUFI_OWNER_CONSOLE_TAG=main
BOX_OWNER_PASSWORD=replace-me       # owner console login; generated by the installer on every box
BOX_OWNER_SESSION_SECRET=replace-me # owner console cookie signing; generated by the installer
```

- [ ] **Step 4: Add the profile to `nufi-box`'s COMPOSE assembly**

In `deploy/box/nufi-box`, after the `--profile works` line (~line 73), add (OS-agnostic — the console runs on mac and linux):

```bash
[ "${NUFI_OWNER_CONSOLE:-0}" = "1" ] && COMPOSE="$COMPOSE --profile owner-console"
```

- [ ] **Step 5: Write the failing test in `deploy/box/tests/test_compose.py`**

```python
def test_owner_console_is_off_by_default_and_socket_free_when_on():
    # Off by default: no flag, no service — the plain box is unchanged.
    assert "owner-console" not in render()["services"]
    # On with the profile: present, on the box network, no published ports,
    # and never mounting the Docker socket (the appliance security boundary).
    svc = render(profiles=("owner-console",),
                 BOX_OWNER_PASSWORD="pw", BOX_OWNER_SESSION_SECRET="s" * 40)["services"]
    assert "owner-console" in svc
    oc = svc["owner-console"]
    assert set(oc.get("networks", {})) == {"box"}
    assert not oc.get("ports")
    assert all("docker.sock" not in str(v) for v in oc.get("volumes", []))
```

- [ ] **Step 6: Run it to verify it fails**

Run: `cd deploy/box && python3 -m pytest tests/test_compose.py::test_owner_console_is_off_by_default_and_socket_free_when_on -q`
Expected: FAIL — service not found under the profile (before the compose edit) or a KeyError.

- [ ] **Step 7: Run it to verify it passes (after Steps 3–4)**

Run: `cd deploy/box && python3 -m pytest tests/test_compose.py -q`
Expected: PASS (new test + the existing compose suite unchanged).

- [ ] **Step 8: Commit**

```bash
git add deploy/box/owner-console/Dockerfile deploy/box/owner-console/.dockerignore \
  deploy/box/docker-compose.yml deploy/box/.env.example deploy/box/nufi-box \
  deploy/box/tests/test_compose.py
git commit -m "feat(box): owner-console compose service (profile owner-console, socket-free)"
```

---

### Task 4: Caddy TLS site on :3009

**Files:**
- Modify: `deploy/box/Caddyfile`
- Test: `deploy/box/tests/test_caddyfile.py`

**Interfaces:**
- Consumes: the `owner-console` service (Task 3) at `owner-console:8890`.
- Produces: a Caddy site `{$BOX_HOST}:3009, {$BOX_IP}:3009, localhost:3009` importing `box_tls`.

- [ ] **Step 1: Add the site to `Caddyfile`**

Add after the gateway (`:4000`) site, before the `import caddy/mesh*.caddy` line:

```
# The box owner console (status, invites, drives). Opt-in: the service only
# runs under the owner-console profile, so on a box without it this site has no
# upstream and simply 502s — the port is never advertised.
{$BOX_HOST}:3009, {$BOX_IP}:3009, localhost:3009 {
	import box_tls
	reverse_proxy owner-console:8890
}
```

- [ ] **Step 2: Extend the failing test in `deploy/box/tests/test_caddyfile.py`**

In `test_every_product_port_is_served`, add `3009` to the port tuple:

```python
def test_every_product_port_is_served():
    for port in (3080, 3001, 3002, 3003, 7860, 4000, 3009):
        assert re.search(rf"^\{{\$BOX_HOST\}}:{port}, ", CADDYFILE, re.M), port
    assert ":80 {" in CADDYFILE
```

And add a focused test:

```python
def test_the_owner_console_site_uses_box_tls_and_the_console_upstream():
    site = re.search(r"^\{\$BOX_HOST\}:3009, .*?\n\}", CADDYFILE, re.S | re.M).group(0)
    assert "import box_tls" in site
    assert "reverse_proxy owner-console:8890" in site
```

- [ ] **Step 3: Run to verify it fails (before Step 1), then passes (after)**

Run: `cd deploy/box && python3 -m pytest tests/test_caddyfile.py -q`
Expected: PASS after the Caddyfile edit.

- [ ] **Step 4: Commit**

```bash
git add deploy/box/Caddyfile deploy/box/tests/test_caddyfile.py
git commit -m "feat(box): serve the owner console on Caddy TLS :3009"
```

---

### Task 5: install-box.sh — flag, secrets, tag, banner

**Files:**
- Modify: `deploy/box/install-box.sh`
- Test: `deploy/box/tests/test_install.py`

**Interfaces:**
- Consumes: the compose profile (Task 3), the Caddy site (Task 4).
- Produces (in a box `.env` and the dry-run plan): `NUFI_OWNER_CONSOLE=1`, `BOX_OWNER_PASSWORD=<hex>`, `BOX_OWNER_SESSION_SECRET=<hex>`, `NUFI_OWNER_CONSOLE_TAG=main`, and `--profile owner-console` in the compose plan; the banner prints the console URL and password.

- [ ] **Step 1: Parse the flag**

In the flag `case` block (~line 61+), add:
```bash
    --owner-console) NUFI_OWNER_CONSOLE=1 ;;
```
And initialise it with the other defaults near the top of the file (where `WITH_WORKS=0` etc. are set / where env-derived vars default):
```bash
NUFI_OWNER_CONSOLE="${NUFI_OWNER_CONSOLE:-0}"
```

- [ ] **Step 2: Generate the secrets (unconditionally, like every other box secret)**

Near the `sec ADMIN_SESSION_SECRET ...` line (~467), add — NOT gated on the flag, exactly like `sec ADMIN_PASSWORD` and `sec WORKS_AUTH_SECRET`, which the box generates on every install regardless of whether the feature is enabled (so a later `.env` flip-on already has them, and the box's secret-generation stays uniform):
```bash
sec BOX_OWNER_PASSWORD "gen_hex 8"
sec BOX_OWNER_SESSION_SECRET "gen_hex 32"
```

- [ ] **Step 3: Default the image tag**

Where the other `NUFI_*_TAG` defaults live (search `NUFI_ADMIN_TAG`), add:
```bash
NUFI_OWNER_CONSOLE_TAG="${NUFI_OWNER_CONSOLE_TAG:-main}"
```

- [ ] **Step 4: Write them in `render_env`**

In the `render_env` heredoc, alongside `ADMIN_SESSION_SECRET=...` and the `NUFI_*_TAG` lines, add:
```bash
NUFI_OWNER_CONSOLE=$NUFI_OWNER_CONSOLE
NUFI_OWNER_CONSOLE_TAG=$NUFI_OWNER_CONSOLE_TAG
BOX_OWNER_PASSWORD=$BOX_OWNER_PASSWORD
BOX_OWNER_SESSION_SECRET=$BOX_OWNER_SESSION_SECRET
```

- [ ] **Step 5: Add the profile to the installer's COMPOSE assembly**

After the Linux-only block closes (after line 856 `fi`, before the `NUFI_BOX_COMPOSE_EXTRA` loop), add (OS-agnostic):
```bash
# The owner console is a plain web service (no host networking), so it runs on
# any box, unlike the Linux-only layers above.
[ "$NUFI_OWNER_CONSOLE" = 1 ] && COMPOSE="$COMPOSE --profile owner-console"
```

- [ ] **Step 6: Add the banner line**

In the "is up." banner heredoc, after the `Admin panel:` line, add a conditional block (like the Works one):
```bash
$( [ "$NUFI_OWNER_CONSOLE" = 1 ] && printf '\n  Owner console: https://%s:3009   (owner password below)\n' "$BOX_HOST" )
```
And after the `Admin login:` line:
```bash
$( [ "$NUFI_OWNER_CONSOLE" = 1 ] && printf '  Owner login:   password %s  (owner console at :3009)\n' "$BOX_OWNER_PASSWORD" )
```

- [ ] **Step 7: Keep the secrets across re-installs**

Add to `REUSE_VARS` (~line 252) so a re-install never blanks them:
```bash
REUSE_VARS="$REUSE_VARS NUFI_OWNER_CONSOLE BOX_OWNER_PASSWORD BOX_OWNER_SESSION_SECRET"
```

- [ ] **Step 8: Update the help text**

Add `--owner-console` to the usage comment and the `--help` sed range (the summary of flags at the top of the file); bump the sed line range if the help block grew.

- [ ] **Step 9: Write the tests in `deploy/box/tests/test_install.py`**

```python
def test_owner_console_flag_enables_the_profile_and_a_password():
    out = run("--owner-console").stdout
    assert "--profile owner-console" in out
    assert "NUFI_OWNER_CONSOLE=1" in out
    assert re.search(r"^BOX_OWNER_PASSWORD=\S+", out, re.M)
    assert re.search(r"^BOX_OWNER_SESSION_SECRET=\S+", out, re.M)
    assert "Owner console:" in out and ":3009" in out

def test_without_the_flag_there_is_no_owner_console():
    # "Off by default" = the profile is not added, NUFI_OWNER_CONSOLE stays 0, and
    # the banner is silent. The secrets ARE still generated (every box gets them,
    # like ADMIN_PASSWORD / WORKS_AUTH_SECRET), so do NOT assert their absence.
    out = run().stdout
    assert "--profile owner-console" not in out
    assert "NUFI_OWNER_CONSOLE=1" not in out
    assert "NUFI_OWNER_CONSOLE=0" in out
    assert "Owner console:" not in out
```
(Add `import re` at the top of the file if it is not already imported.)

- [ ] **Step 10: Run to verify**

Run: `cd deploy/box && python3 -m pytest tests/test_install.py -q`
Expected: PASS (new tests + existing dry-run suite unchanged).

- [ ] **Step 11: Commit**

```bash
git add deploy/box/install-box.sh deploy/box/tests/test_install.py
git commit -m "feat(box): install --owner-console (flag, generated owner password, banner)"
```

---

### Task 6: Publish and bundle the image (box-images, Makefile, mirror)

**Files:**
- Modify: `.github/workflows/box-images.yml`
- Modify: `deploy/box/Makefile`
- Test: `deploy/box/tests/test_makefile.py`

**Interfaces:**
- Consumes: the `owner-console` Dockerfile (Task 3) and the compose image ref `ghcr.io/dudaji-vn/nufi-owner-console:main`.
- Produces: the image built by box-images, carried by `make save`, and mirrored by `registry-push`, so an air-gapped / LAN-registry box has it (the same coverage every other box image gets).

- [ ] **Step 1: Add the build to `box-images.yml`**

Bring the workflow into the sparse checkout, then edit:
```bash
git sparse-checkout add .github/workflows
```
Add to the `paths:` filter (push): `- 'deploy/box/owner-console/**'`.
Add to the `matrix.include` list:
```yaml
          - name: nufi-owner-console
            context: deploy/box/owner-console
            file: deploy/box/owner-console/Dockerfile
```

- [ ] **Step 2: Add the image to `NUFI_IMAGES`/`TAG_KEY` expectations in `test_makefile.py`**

`NUFI_IMAGES` is derived from `docker-compose.yml`'s `${NUFI_REGISTRY:-...}/<img>:` refs, so once Task 3 added the `owner-console` service the regex already includes `nufi-owner-console`. Add its tag key so `test_the_compose_file_names_every_image_the_mirror_knows` still passes:
```python
TAG_KEY = { ...,
    "nufi-owner-console": "NUFI_OWNER_CONSOLE_TAG" }
```

- [ ] **Step 3: Write the failing test — the bundle carries it**

Add to `test_makefile.py`:
```python
def test_save_and_mirror_carry_the_owner_console_image():
    out = make_n("save")
    save_cmd = out[out.index("docker save"):]
    assert "ghcr.io/dudaji-vn/nufi-owner-console:" in save_cmd
    push = make_n("registry-push", REGISTRY="172.10.10.30:5001")
    assert "docker push localhost:5001/nufi-owner-console:" in push
```

- [ ] **Step 4: Run to verify it fails**

Run: `cd deploy/box && python3 -m pytest tests/test_makefile.py -q`
Expected: FAIL — the image is not yet in `save`/`registry-push` (and `TAG_KEY` vs `NUFI_IMAGES` may mismatch until Step 2).

- [ ] **Step 5: Add the image to the Makefile**

`registry-push` and `save` iterate the NuFi images; `nufi-owner-console` must be in whatever list they build from. Follow the exact shape the sibling NuFi images use in `Makefile` (a `docker tag`/retag line in `save`, a `docker push` line in `registry-push`, tagged `main` on the way out). Add `nufi-owner-console` there so both cover it.

- [ ] **Step 6: Run to verify it passes**

Run: `cd deploy/box && python3 -m pytest tests/test_makefile.py -q`
Expected: PASS (the full Makefile suite, incl. the new test and `test_the_compose_file_names_every_image_the_mirror_knows`).

- [ ] **Step 7: Commit**

```bash
git add .github/workflows/box-images.yml deploy/box/Makefile deploy/box/tests/test_makefile.py
git commit -m "build(box): build, bundle and mirror the nufi-owner-console image"
```

---

### Task 7: Run the console's handler tests in box-ci

**Files:**
- Modify: `.github/workflows/box-ci.yml`

**Interfaces:**
- Consumes: `deploy/box/owner-console` `bun test` (Tasks 1–2).
- Produces: a CI step that fails the `Box suites` job if the console handlers regress.

- [ ] **Step 1: Add a Bun step to the `Box suites` job**

After the Python setup steps and before/after the pytest steps, add:
```yaml
      - uses: oven-sh/setup-bun@v2
        with:
          bun-version: "1.4.2"
      - name: Owner console handlers
        run: bun install --frozen-lockfile && bun test
        working-directory: deploy/box/owner-console
```

- [ ] **Step 2: Verify the workflow parses**

Run: `python3 -c "import yaml,sys; yaml.safe_load(open('.github/workflows/box-ci.yml'))"`
Expected: no error (valid YAML).

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/box-ci.yml
git commit -m "ci(box): run the owner-console handler tests in box-ci"
```

---

## Self-Review

**Spec coverage:**
- New service, `deploy/box/owner-console/`, Bun+Hono, container `owner-console` → Tasks 1–3. ✓
- Caddy TLS `:3009` → Task 4. ✓
- Socket-free (no Docker socket, no host shell; 01 mounts nothing) → Task 3 test asserts it. ✓
- Owner auth: generated `BOX_OWNER_PASSWORD`, printed once, constant-time verify, HMAC-signed cookie, fail-closed → Tasks 1, 2, 5. ✓ (constant-time compare implements the spec's "argon2" intent — see Global Constraints.)
- Opt-in / plain box unchanged → profile-gated service + gated secrets; Tasks 3 & 5 tests assert "off by default". ✓
- Sub-task 01 scope (scaffold + login + shell + /healthz) → Tasks 1–2. ✓
- Testing: pytest (compose/Caddy/install/makefile) + `bun test` + a Bun CI step → Tasks 3–7. ✓
- Image-size risk (bundle the new image like the tailscale fix) → Task 6. ✓

02–05 (status dashboard, invite=link, /connect, drives) are out of scope for this plan by design; each gets its own.

**Placeholder scan:** No TBD/TODO. Task 6 Step 5 says "follow the exact shape the sibling NuFi images use" rather than pasting the Makefile's generated lines, because those lines are templated over `$(OWNER)/$(TAG)` and the sibling pattern is the source of truth; the test in Step 3 pins the observable outcome (the image appears in `save` and `registry-push`), so the step is verifiable, not vague.

**Type consistency:** `verifyPassword`/`signSession`/`verifySession` signatures match between `auth.ts` (Task 1), its tests, and `app.ts` (Task 2). `createApp(env)`, `loginPage(error?)`, `dashboardShell()` match between `app.ts`/`views.ts` and `app.test.ts`. Env var names `BOX_OWNER_PASSWORD` / `BOX_OWNER_SESSION_SECRET` / `NUFI_OWNER_CONSOLE` / `NUFI_OWNER_CONSOLE_TAG` are identical across the app, compose, install, and tests. Port `8890` (internal) and `3009` (Caddy) are consistent across compose, Caddyfile, healthcheck, and server.

**Open item carried to execution:** Task 6 Step 5 edits the Makefile by pattern; the executor reads the current `save`/`registry-push` recipes first and mirrors the sibling lines exactly.
