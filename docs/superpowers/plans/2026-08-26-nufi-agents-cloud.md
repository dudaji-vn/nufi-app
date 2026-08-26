# NUFI Studio and NUFI Works on Railway — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put both agent products on the public internet behind one door, so a
member who clicks through from `chat.nufi.me` lands in either product already
signed in, with their own gateway key.

**Architecture:** Two Railway services built from GHCR images. The console
becomes the single identity issuer: it signs a short-lived JWT that NUFI Studio
validates natively over JWKS, and it speaks OAuth authorization-code to NUFI
Works, which consumes it through better-auth's `generic-oauth` plugin. The
chooser at `agents.nufi.me` is a route on the console service, not a service of
its own.

**Tech Stack:** Railway, GHCR, GitHub Actions, Docker; Bun + Hono + TanStack
Router (console); `jose` for JWKS; Langflow (Python/FastAPI) and Paperclip
(Node/Express + better-auth 1.6.23 + Drizzle/Postgres).

**Spec:** `docs/superpowers/specs/2026-08-26-nufi-agents-cloud-design.md`

## Global Constraints

- Fork discipline: every file touched under `apps/agents/` and
  `apps/nufi-agent/` must be in that fork's `nufi/check-fork-diff.sh`
  allowlist. Adding a path to the allowlist is a deliberate act, and this
  plan adds exactly one: `apps/agents/server/src/auth/better-auth.ts`.
- Product names: **NUFI Studio** (`apps/nufi-agent`) and **NUFI Works**
  (`apps/agents`). Brand casing is `NUFI`, never `NuFi` or `Nufi`.
- Hosts: `agents.nufi.me` (chooser), `studio.nufi.me`, `works.nufi.me`,
  `console.nufi.me` (issuer), `chat.nufi.me` (identity source).
- Every model call egresses to `https://api.codechi.me/v1` and nowhere else.
  `apps/agents/nufi/verify-adapters.mjs` asserts this; it must stay passing
  and must not be relaxed.
- Railway project `nufi` = `06c8dad0-f74c-412e-b9cf-f563676520d5`,
  environment `production` = `57cf6b17-ab70-466c-a7d8-fcbbe8b01d49`.
  Changing a service's source needs `serviceInstanceUpdate` followed by
  `serviceInstanceDeployV2`; `railway redeploy` re-runs the old deployment.
- JWT audiences: `nufi-studio` and `nufi-works`. Never one token for both.
- These guards must pass before every commit that touches a fork:
  `apps/nufi-agent/nufi/check-fork-diff.sh`, `check-backend-brand.sh`,
  `check-locale-parity.sh`, `apps/agents/nufi/check-fork-diff.sh`,
  `apps/agents/nufi/verify-adapters.mjs`.

---

### Task 1: NUFI Studio container image

The Langflow fork has no image. Upstream's `docker/build_and_push.Dockerfile`
is not in the allowlist, so the NuFi image is defined under `nufi/`.

**Files:**
- Create: `apps/nufi-agent/nufi/Dockerfile`
- Create: `.github/workflows/nufi-agent-image.yml`

**Interfaces:**
- Produces: image `ghcr.io/dudaji-vn/nufi-studio:<tag>`, listening on
  `$PORT` (default 7860), entrypoint `langflow run --host 0.0.0.0`.

- [ ] **Step 1: Write the Dockerfile**

The frontend build applies the rebrand through the allowlisted
`src/frontend/vite.config.mts`, so no post-build rename step is needed on this
side — unlike NUFI Works (Task 3).

```dockerfile
# syntax=docker/dockerfile:1.7
# ---- Stage 1: build the rebranded frontend ---------------------------------
FROM node:22-slim AS frontend
WORKDIR /app/src/frontend
COPY src/frontend/package.json src/frontend/package-lock.json ./
RUN npm ci
COPY src/frontend ./
COPY nufi /app/nufi
RUN npm run build

# ---- Stage 2: python runtime ------------------------------------------------
FROM python:3.12-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    LANGFLOW_HOST=0.0.0.0 \
    PORT=7860
WORKDIR /app
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential curl git \
 && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock* README.md ./
COPY src ./src
RUN uv pip install --system --no-cache .
COPY --from=frontend /app/src/frontend/build \
                     /usr/local/lib/python3.12/site-packages/langflow/frontend
EXPOSE 7860
CMD ["sh","-c","langflow run --host 0.0.0.0 --port ${PORT}"]
```

- [ ] **Step 2: Build it locally and watch it fail or pass on its own terms**

Run: `docker build -f apps/nufi-agent/nufi/Dockerfile -t nufi-studio:dev apps/nufi-agent`
Expected: a built image. If the frontend stage cannot find `nufi/brand.css`,
the `COPY nufi /app/nufi` line is at the wrong depth — fix the path rather
than removing the brand import.

- [ ] **Step 3: Assert the brand survived the build, before trusting it**

```bash
docker run --rm nufi-studio:dev \
  sh -c 'grep -c "NUFI Studio" /usr/local/lib/python3.12/site-packages/langflow/frontend/index.html'
```
Expected: at least `1`. A `0` means the rebrand plugin did not run in the
image build even though it runs locally — stop and fix that, because every
later task assumes the image is branded.

- [ ] **Step 4: Write the image workflow**

```yaml
name: nufi-agent-image

on:
  push:
    branches: [main]
    paths: ['apps/nufi-agent/**']
    tags: ['nufi-studio-v*']
  workflow_dispatch:

permissions:
  contents: read
  packages: write

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository_owner }}/nufi-studio

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - id: meta
        uses: docker/metadata-action@v5
        with:
          images: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}
          tags: |
            type=ref,event=branch
            type=match,pattern=nufi-studio-(v.+),group=1
            type=raw,value=latest,enable=${{ startsWith(github.ref, 'refs/tags/nufi-studio-v') }}
            type=sha,prefix=sha-,format=short
      - uses: docker/build-push-action@v6
        with:
          context: apps/nufi-agent
          file: apps/nufi-agent/nufi/Dockerfile
          platforms: linux/amd64
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

- [ ] **Step 5: Commit**

```bash
git add apps/nufi-agent/nufi/Dockerfile .github/workflows/nufi-agent-image.yml
git commit -m "build(studio): container image for the Langflow fork"
```

---

### Task 2: NUFI Studio on Railway at studio.nufi.me

**Files:** none in the repo. This task is Railway state, recorded here so the
next person can reproduce it.

**Interfaces:**
- Consumes: `ghcr.io/dudaji-vn/nufi-studio:<tag>` from Task 1.
- Produces: service `nufi-studio`, a Postgres database, and the hostname
  `studio.nufi.me`.

- [ ] **Step 1: Create the shared Postgres service**

One Postgres instance carries both products' databases; a second idle instance
would be a recurring cost for no isolation we actually need at this stage.

Create service `nufi-agents-db` from the Postgres template in project `nufi`,
environment `production`. Then create two databases on it:

```sql
CREATE DATABASE nufi_studio;
CREATE DATABASE nufi_works;
```

- [ ] **Step 2: Create the service and set variables**

Service `nufi-studio`, source = the GHCR image.

```
PORT=7860
LANGFLOW_DATABASE_URL=postgresql://<user>:<pw>@<host>:<port>/nufi_studio
LANGFLOW_AUTO_LOGIN=false
LANGFLOW_SUPERUSER=<admin email>
LANGFLOW_SUPERUSER_PASSWORD=<generated, stored in the team vault>
LANGFLOW_SECRET_KEY=<openssl rand -hex 32>
```

Leave every `LANGFLOW_EXTERNAL_AUTH_*` variable unset for now. Task 6 turns
external identity on, and turning it on before the issuer exists locks
everyone out.

- [ ] **Step 3: Deploy and verify it serves**

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://<service>.up.railway.app/
```
Expected: `200`.

- [ ] **Step 4: Verify the brand and the egress, on the deployed instance**

```bash
curl -s https://<service>.up.railway.app/ | grep -c "NUFI Studio"     # >= 1
curl -s https://<service>.up.railway.app/ | grep -ci "langflow"        # 0
```
Expected: a positive count then `0`. A non-zero second number means the
deployed image is not the branded one.

- [ ] **Step 5: Add the custom domain**

Add custom domain `studio.nufi.me` to the service, target port 7860. Railway
returns a CNAME target; the DNS record has to be created at the registrar.
Record the CNAME target in the deploy notes — this is the one step that
cannot be done from here.

- [ ] **Step 6: Commit the deploy notes**

```bash
git add deploy/railway/README.md
git commit -m "docs(deploy): NUFI Studio service, variables and DNS target"
```

---

### Task 3: NUFI Works container image

Upstream's `apps/agents/Dockerfile` builds the app but does not rename
`server/dist`; `nufi/README.md` records that `nufi/rebrand-server-dist.mjs`
**must be run after every `tsc`**. Upstream's Dockerfile is not in the
allowlist, so the rename is applied by a thin wrapper on top of the image it
produces — the same shape the chat app already uses on Railway.

**Files:**
- Create: `apps/agents/nufi/Dockerfile`
- Create: `.github/workflows/agents-image.yml`

**Interfaces:**
- Produces: image `ghcr.io/dudaji-vn/nufi-works:<tag>`, listening on 3100.

- [ ] **Step 1: Write the wrapper Dockerfile**

```dockerfile
# syntax=docker/dockerfile:1.7
# The upstream image, with the NuFi rename applied to server/dist.
#
# ui/dist is already branded: the rebrand runs as a Vite plugin through the
# allowlisted ui/vite.config.ts. server/dist is not, because tsc has no such
# hook -- see nufi/README.md, "The rename covers both bundles".
ARG BASE
FROM ${BASE} AS branded
WORKDIR /app
RUN node nufi/rebrand-server-dist.mjs server/dist \
 && node nufi/rebrand-server-dist.mjs --check server/dist
```

- [ ] **Step 2: Prove the wrapper actually changes something**

Build the upstream image, then assert the unbranded state before wrapping —
otherwise a no-op wrapper would look identical to a working one.

```bash
docker build -f apps/agents/Dockerfile -t nufi-works-base:dev apps/agents
docker run --rm nufi-works-base:dev sh -c 'grep -rc "Paperclip" server/dist | head -1'
```
Expected: greater than `0`. That number is what the wrapper has to erase.

- [ ] **Step 3: Build the wrapper and assert the number is now zero**

```bash
docker build --build-arg BASE=nufi-works-base:dev \
  -f apps/agents/nufi/Dockerfile -t nufi-works:dev apps/agents
docker run --rm nufi-works:dev sh -c 'grep -rc "Paperclip" server/dist | head -1'
```
Expected: `0`.

- [ ] **Step 4: Write the image workflow**

```yaml
name: agents-image

on:
  push:
    branches: [main]
    paths: ['apps/agents/**']
    tags: ['nufi-works-v*']
  workflow_dispatch:

permissions:
  contents: read
  packages: write

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository_owner }}/nufi-works

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - id: meta
        uses: docker/metadata-action@v5
        with:
          images: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}
          tags: |
            type=ref,event=branch
            type=match,pattern=nufi-works-(v.+),group=1
            type=raw,value=latest,enable=${{ startsWith(github.ref, 'refs/tags/nufi-works-v') }}
            type=sha,prefix=sha-,format=short
      - name: Build the upstream image
        uses: docker/build-push-action@v6
        with:
          context: apps/agents
          file: apps/agents/Dockerfile
          platforms: linux/amd64
          push: false
          load: true
          tags: nufi-works-base:ci
          cache-from: type=gha
          cache-to: type=gha,mode=max
      - name: Apply the NuFi rename and push
        uses: docker/build-push-action@v6
        with:
          context: apps/agents
          file: apps/agents/nufi/Dockerfile
          platforms: linux/amd64
          push: true
          build-args: BASE=nufi-works-base:ci
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
```

- [ ] **Step 5: Verify the fork guard still passes, then commit**

```bash
./apps/agents/nufi/check-fork-diff.sh
git add apps/agents/nufi/Dockerfile .github/workflows/agents-image.yml
git commit -m "build(works): container image with the server-dist rename applied"
```

---

### Task 4: NUFI Works on Railway at works.nufi.me

**Interfaces:**
- Consumes: `ghcr.io/dudaji-vn/nufi-works:<tag>`, the `nufi_works` database
  from Task 2 Step 1.
- Produces: service `nufi-works` and the hostname `works.nufi.me`.

- [ ] **Step 1: Create the service with a volume**

Service `nufi-works`, source = the GHCR image, volume mounted at `/paperclip`.
The volume is not optional: agent workspaces, uploads and instance config live
there, and without it every redeploy starts empty.

- [ ] **Step 2: Set variables**

```
PORT=3100
DATABASE_URL=postgresql://<user>:<pw>@<host>:<port>/nufi_works
BETTER_AUTH_SECRET=<openssl rand -hex 32>
PAPERCLIP_DEPLOYMENT_MODE=authenticated
PAPERCLIP_DEPLOYMENT_EXPOSURE=public
PAPERCLIP_PUBLIC_URL=https://works.nufi.me
PAPERCLIP_HOME=/paperclip
```

`PAPERCLIP_AUTH_DISABLE_SIGN_UP` stays unset until Task 8. Setting it before
the OAuth client works would leave no way in at all.

- [ ] **Step 3: Deploy and verify**

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://<service>.up.railway.app/
curl -s https://<service>.up.railway.app/ | grep -ci "paperclip"
```
Expected: `200`, then `0`.

- [ ] **Step 4: Add the custom domain**

Add `works.nufi.me`, target port 3100. Record the CNAME target.

- [ ] **Step 5: Add the origin to the existing connect allow-list**

On the `nufi-console` service, append to `AGENTS_ALLOWED_ORIGINS`:
`https://works.nufi.me`. Exact string equality is the whole security boundary
of the connect flow — no trailing slash, no wildcard.

- [ ] **Step 6: Commit the deploy notes**

```bash
git add deploy/railway/README.md
git commit -m "docs(deploy): NUFI Works service, volume, variables and DNS target"
```

---

### Task 5: Console signs identity tokens and publishes JWKS

**Files:**
- Create: `apps/console/server/lib/oidc-keys.ts`
- Create: `apps/console/server/lib/oidc-keys.test.ts`
- Modify: `apps/console/server/index.ts`
- Modify: `apps/console/package.json` (add `jose`)

**Interfaces:**
- Produces:
  - `getSigningKey(): Promise<{ privateKey: CryptoKey; kid: string }>`
  - `getJwks(): Promise<{ keys: JsonWebKey[] }>`
  - `signIdentity(claims: IdentityClaims, audience: string, ttlSeconds: number): Promise<string>`
  - `type IdentityClaims = { sub: string; email?: string; access: 'viewer' | 'editor' | 'admin' }`
  - `GET /.well-known/jwks.json`

- [ ] **Step 1: Write the failing test**

```ts
import { describe, expect, it } from 'bun:test';
import { createLocalJWKSet, jwtVerify } from 'jose';
import { getJwks, signIdentity } from './oidc-keys.ts';

process.env.OIDC_PRIVATE_KEY_PEM ??= '';

describe('identity tokens', () => {
  it('verifies against the published JWKS', async () => {
    const token = await signIdentity(
      { sub: 'user-1', email: 'a@b.c', access: 'editor' },
      'nufi-studio',
      300,
    );
    const jwks = createLocalJWKSet(await getJwks());
    const { payload } = await jwtVerify(token, jwks, {
      issuer: 'https://console.nufi.me',
      audience: 'nufi-studio',
    });
    expect(payload.sub).toBe('user-1');
    expect(payload.access).toBe('editor');
  });

  it('refuses a token minted for another audience', async () => {
    const token = await signIdentity({ sub: 'u', access: 'viewer' }, 'nufi-works', 300);
    const jwks = createLocalJWKSet(await getJwks());
    await expect(
      jwtVerify(token, jwks, { issuer: 'https://console.nufi.me', audience: 'nufi-studio' }),
    ).rejects.toThrow();
  });

  it('never publishes private key material', async () => {
    const jwks = await getJwks();
    for (const k of jwks.keys) {
      expect(k).not.toHaveProperty('d');
    }
  });
});
```

- [ ] **Step 2: Run it and watch it fail**

Run: `cd apps/console && bun test server/lib/oidc-keys.test.ts`
Expected: FAIL — `Cannot find module './oidc-keys.ts'`.

- [ ] **Step 3: Add the dependency**

Run: `cd apps/console && bun add jose`

- [ ] **Step 4: Implement**

```ts
import { createHash } from 'node:crypto';
import { SignJWT, exportJWK, generateKeyPair, importPKCS8 } from 'jose';

export type IdentityClaims = {
  sub: string;
  email?: string;
  access: 'viewer' | 'editor' | 'admin';
};

export const ISSUER = process.env.OIDC_ISSUER ?? 'https://console.nufi.me';
const ALG = 'RS256';

let cached: Promise<{ privateKey: CryptoKey; publicJwk: JsonWebKey; kid: string }> | undefined;

/**
 * The signing key comes from OIDC_PRIVATE_KEY_PEM in production. A generated
 * ephemeral key is a development convenience only: it changes on every boot,
 * so tokens minted by one instance would fail on another. Two instances of
 * this service must therefore share the variable.
 */
async function load() {
  const pem = process.env.OIDC_PRIVATE_KEY_PEM?.trim();
  const privateKey = pem
    ? await importPKCS8(pem, ALG)
    : (await generateKeyPair(ALG, { extractable: true })).privateKey;

  const jwk = await exportJWK(privateKey);
  const publicJwk: JsonWebKey = { kty: jwk.kty, n: jwk.n, e: jwk.e, alg: ALG, use: 'sig' };
  const kid = createHash('sha256').update(`${jwk.n}.${jwk.e}`).digest('base64url').slice(0, 16);
  return { privateKey, publicJwk: { ...publicJwk, kid }, kid };
}

export function getSigningKey() {
  cached ??= load();
  return cached;
}

export async function getJwks(): Promise<{ keys: JsonWebKey[] }> {
  const { publicJwk } = await getSigningKey();
  return { keys: [publicJwk] };
}

export async function signIdentity(
  claims: IdentityClaims,
  audience: string,
  ttlSeconds: number,
): Promise<string> {
  const { privateKey, kid } = await getSigningKey();
  return new SignJWT({ email: claims.email, access: claims.access })
    .setProtectedHeader({ alg: ALG, kid })
    .setSubject(claims.sub)
    .setIssuer(ISSUER)
    .setAudience(audience)
    .setIssuedAt()
    .setExpirationTime(`${ttlSeconds}s`)
    .sign(privateKey);
}
```

- [ ] **Step 5: Mount the endpoint**

In `apps/console/server/index.ts`, directly after the `/_health` route:

```ts
import { getJwks } from './lib/oidc-keys.ts';

app.get('/.well-known/jwks.json', async (c) => {
  c.header('Cache-Control', 'public, max-age=300');
  return c.json(await getJwks());
});
```

- [ ] **Step 6: Run the tests and make sure they pass**

Run: `cd apps/console && bun test server/lib/oidc-keys.test.ts`
Expected: 3 pass.

- [ ] **Step 7: Commit**

```bash
git add apps/console/server/lib/oidc-keys.ts apps/console/server/lib/oidc-keys.test.ts \
        apps/console/server/index.ts apps/console/package.json apps/console/bun.lock
git commit -m "feat(console): sign identity tokens and publish JWKS"
```

---

### Task 6: The Studio handoff

NUFI Studio is not an OAuth client. It validates a JWT it finds in a cookie.
The console mints that cookie after checking the chat session, then redirects.

**Files:**
- Create: `apps/console/server/enter.ts`
- Create: `apps/console/server/enter.test.ts`
- Modify: `apps/console/server/index.ts`

**Interfaces:**
- Consumes: `signIdentity` from Task 5; `auth()` from
  `apps/console/server/middleware/auth.ts`, which yields `{ id, email, role }`.
- Produces: `GET /enter/studio` — 302 to `https://studio.nufi.me/`, setting
  cookie `nufi_id` on `.nufi.me`.

- [ ] **Step 1: Write the failing test**

```ts
import { describe, expect, it } from 'bun:test';
import { Hono } from 'hono';
import { enter } from './enter.ts';

const asUser = { id: 'u-1', email: 'a@b.c', role: 'USER' as const };

// c.set('user') comes from middleware, so a test has to mount one. Hono's
// third request() argument is Env bindings and cannot carry Variables.
function as(user: typeof asUser) {
  const app = new Hono();
  app.use('*', async (c, next) => {
    c.set('user', user);
    await next();
  });
  app.route('/', enter);
  return app;
}

describe('GET /enter/studio', () => {
  it('redirects to Studio and sets a host-wide identity cookie', async () => {
    const res = await as(asUser).request('/studio');
    expect(res.status).toBe(302);
    expect(res.headers.get('location')).toBe('https://studio.nufi.me/');
    const cookie = res.headers.get('set-cookie') ?? '';
    expect(cookie).toContain('nufi_id=');
    expect(cookie).toContain('Domain=.nufi.me');
    expect(cookie).toContain('HttpOnly');
    expect(cookie).toContain('Secure');
    expect(cookie).toContain('SameSite=Lax');
  });

  it('gives an admin the admin ceiling and everyone else editor', async () => {
    const res = await as({ ...asUser, role: 'ADMIN' }).request('/studio');
    const token = /nufi_id=([^;]+)/.exec(res.headers.get('set-cookie') ?? '')?.[1];
    const claims = JSON.parse(Buffer.from(token!.split('.')[1], 'base64url').toString());
    expect(claims.access).toBe('admin');
    expect(claims.aud).toBe('nufi-studio');
  });
});
```

- [ ] **Step 2: Run it and watch it fail**

Run: `cd apps/console && bun test server/enter.test.ts`
Expected: FAIL — `Cannot find module './enter.ts'`.

- [ ] **Step 3: Implement**

```ts
import { Hono } from 'hono';
import { setCookie } from 'hono/cookie';
import type { AuthedUser } from './middleware/auth.ts';
import { signIdentity } from './lib/oidc-keys.ts';

type Env = { Variables: { user: AuthedUser } };

const STUDIO_URL = process.env.STUDIO_URL ?? 'https://studio.nufi.me';
const COOKIE_DOMAIN = process.env.IDENTITY_COOKIE_DOMAIN ?? '.nufi.me';
const TTL_SECONDS = 8 * 60 * 60;

export const enter = new Hono<Env>();

enter.get('/studio', async (c) => {
  const user = c.get('user');
  const token = await signIdentity(
    { sub: user.id, email: user.email, access: user.role === 'ADMIN' ? 'admin' : 'editor' },
    'nufi-studio',
    TTL_SECONDS,
  );
  setCookie(c, 'nufi_id', token, {
    domain: COOKIE_DOMAIN,
    path: '/',
    httpOnly: true,
    secure: true,
    sameSite: 'Lax',
    maxAge: TTL_SECONDS,
  });
  return c.redirect(`${STUDIO_URL}/`, 302);
});
```

- [ ] **Step 4: Mount it behind the session check**

In `apps/console/server/index.ts`, before the SPA catch-all:

```ts
import { enter } from './enter.ts';

app.use('/enter/*', auth());
app.route('/enter', enter);
```

- [ ] **Step 5: Run the tests and make sure they pass**

Run: `cd apps/console && bun test server/enter.test.ts`
Expected: 2 pass.

- [ ] **Step 6: Turn external identity on for Studio**

On the `nufi-studio` Railway service:

```
LANGFLOW_EXTERNAL_AUTH_ENABLED=true
LANGFLOW_EXTERNAL_AUTH_TOKEN_COOKIE=nufi_id
LANGFLOW_EXTERNAL_AUTH_JWKS_URL=https://console.nufi.me/.well-known/jwks.json
LANGFLOW_EXTERNAL_AUTH_ISSUER=https://console.nufi.me
LANGFLOW_EXTERNAL_AUTH_AUDIENCE=nufi-studio
LANGFLOW_EXTERNAL_AUTH_SUBJECT_CLAIM=sub
LANGFLOW_EXTERNAL_AUTH_EMAIL_CLAIM=email
LANGFLOW_EXTERNAL_AUTH_ACCESS_CEILING_ENABLED=true
LANGFLOW_EXTERNAL_AUTH_ACCESS_CLAIM=access
LANGFLOW_EXTERNAL_AUTH_DEFAULT_ACCESS_LEVEL=editor
```

`LANGFLOW_EXTERNAL_AUTH_TRUSTED_JWT_DECODE` stays `false`. It skips signature
verification and is only safe behind a proxy that has already validated the
token; there is no such proxy here.

- [ ] **Step 7: Verify end to end in a browser, signed in at chat.nufi.me**

Visit `https://console.nufi.me/enter/studio`. Expected: you land in NUFI Studio
signed in as yourself, and Studio's own login screen never appears.

Then verify the negative case, which matters more: in a private window with no
chat session, the same URL must return 401 and must not set `nufi_id`.

- [ ] **Step 8: Commit**

```bash
git add apps/console/server/enter.ts apps/console/server/enter.test.ts apps/console/server/index.ts
git commit -m "feat(console): hand a member into NUFI Studio already signed in"
```

---

### Task 7: Console speaks OAuth authorization-code to NUFI Works

**Files:**
- Create: `apps/console/server/oidc.ts`
- Create: `apps/console/server/oidc.test.ts`
- Modify: `apps/console/server/index.ts`

**Interfaces:**
- Consumes: `signIdentity`, `ISSUER` from Task 5; `auth()` middleware.
- Produces:
  - `GET /oidc/authorize?client_id&redirect_uri&state&code_challenge&code_challenge_method`
  - `POST /oidc/token` (form-encoded: `grant_type=authorization_code`,
    `code`, `redirect_uri`, `client_id`, `client_secret`, `code_verifier`)
  - `GET /oidc/userinfo` (Bearer)

- [ ] **Step 1: Write the failing test**

```ts
import { beforeEach, describe, expect, it } from 'bun:test';
import { Hono } from 'hono';
import { oidc } from './oidc.ts';

const user = { id: 'u-9', email: 'm@nufi.me', role: 'USER' as const };

// /authorize reads c.get('user'), which only middleware can set. /token and
// /userinfo take no user, so they are exercised through the bare router.
function as(u: typeof user) {
  const app = new Hono();
  app.use('*', async (c, next) => {
    c.set('user', u);
    await next();
  });
  app.route('/', oidc);
  return app;
}

beforeEach(() => {
  process.env.OIDC_CLIENTS = JSON.stringify([
    { clientId: 'nufi-works', clientSecret: 's3cret', redirectUris: ['https://works.nufi.me/api/auth/oauth2/callback/nufi'] },
  ]);
});

describe('authorize', () => {
  it('refuses a redirect_uri that is not registered', async () => {
    const res = await as(user).request(
      '/authorize?client_id=nufi-works&redirect_uri=https://evil.example/cb&state=x',
    );
    expect(res.status).toBe(400);
    expect(res.headers.get('location')).toBeNull();
  });

  it('redirects back with a code and the exact state', async () => {
    const res = await as(user).request(
      '/authorize?client_id=nufi-works&redirect_uri=https%3A%2F%2Fworks.nufi.me%2Fapi%2Fauth%2Foauth2%2Fcallback%2Fnufi&state=abc',
    );
    expect(res.status).toBe(302);
    const url = new URL(res.headers.get('location')!);
    expect(url.origin + url.pathname).toBe('https://works.nufi.me/api/auth/oauth2/callback/nufi');
    expect(url.searchParams.get('state')).toBe('abc');
    expect(url.searchParams.get('code')).toBeTruthy();
  });
});

describe('token', () => {
  it('exchanges a code once and refuses the replay', async () => {
    const auth = await as(user).request(
      '/authorize?client_id=nufi-works&redirect_uri=https%3A%2F%2Fworks.nufi.me%2Fapi%2Fauth%2Foauth2%2Fcallback%2Fnufi&state=s',
    );
    const code = new URL(auth.headers.get('location')!).searchParams.get('code')!;
    const body = new URLSearchParams({
      grant_type: 'authorization_code',
      code,
      client_id: 'nufi-works',
      client_secret: 's3cret',
      redirect_uri: 'https://works.nufi.me/api/auth/oauth2/callback/nufi',
    });
    const first = await oidc.request('/token', { method: 'POST', body });
    expect(first.status).toBe(200);
    expect((await first.json()).id_token).toBeTruthy();

    const replay = await oidc.request('/token', { method: 'POST', body });
    expect(replay.status).toBe(400);
  });

  it('refuses a wrong client secret', async () => {
    const auth = await as(user).request(
      '/authorize?client_id=nufi-works&redirect_uri=https%3A%2F%2Fworks.nufi.me%2Fapi%2Fauth%2Foauth2%2Fcallback%2Fnufi&state=s',
    );
    const code = new URL(auth.headers.get('location')!).searchParams.get('code')!;
    const res = await oidc.request('/token', {
      method: 'POST',
      body: new URLSearchParams({
        grant_type: 'authorization_code', code, client_id: 'nufi-works',
        client_secret: 'wrong',
        redirect_uri: 'https://works.nufi.me/api/auth/oauth2/callback/nufi',
      }),
    });
    expect(res.status).toBe(401);
  });
});
```

- [ ] **Step 2: Run it and watch it fail**

Run: `cd apps/console && bun test server/oidc.test.ts`
Expected: FAIL — `Cannot find module './oidc.ts'`.

- [ ] **Step 3: Implement**

```ts
import { randomBytes, timingSafeEqual } from 'node:crypto';
import { Hono } from 'hono';
import type { AuthedUser } from './middleware/auth.ts';
import { ISSUER, signIdentity } from './lib/oidc-keys.ts';

type Env = { Variables: { user: AuthedUser } };
type Client = { clientId: string; clientSecret: string; redirectUris: string[] };

const CODE_TTL_MS = 60_000;
const TOKEN_TTL_SECONDS = 8 * 60 * 60;

/**
 * Codes are held in memory. That is a deliberate limit, not an oversight: it
 * means the console must run as a single instance, or a code issued by one
 * replica fails at the other. Moving to Redis is the price of scaling out.
 */
const codes = new Map<string, { user: AuthedUser; clientId: string; redirectUri: string; expires: number }>();

function clients(): Client[] {
  try {
    const raw = JSON.parse(process.env.OIDC_CLIENTS ?? '[]');
    return Array.isArray(raw) ? raw : [];
  } catch {
    return [];
  }
}

function findClient(id: string | undefined): Client | undefined {
  return clients().find((c) => c.clientId === id);
}

function secretMatches(a: string, b: string): boolean {
  const x = Buffer.from(a);
  const y = Buffer.from(b);
  return x.length === y.length && timingSafeEqual(x, y);
}

export const oidc = new Hono<Env>();

oidc.get('/authorize', (c) => {
  const clientId = c.req.query('client_id');
  const redirectUri = c.req.query('redirect_uri');
  const state = c.req.query('state') ?? '';
  const client = findClient(clientId);

  // Validated before anything is issued and before any redirect: an
  // unregistered redirect_uri must never receive a code, and must never be
  // reachable by talking a signed-in member through a consent screen.
  if (!client || !redirectUri || !client.redirectUris.includes(redirectUri)) {
    return c.json({ error: 'invalid_request' }, 400);
  }

  const code = randomBytes(32).toString('base64url');
  codes.set(code, {
    user: c.get('user'),
    clientId: client.clientId,
    redirectUri,
    expires: Date.now() + CODE_TTL_MS,
  });

  const target = new URL(redirectUri);
  target.searchParams.set('code', code);
  target.searchParams.set('state', state);
  return c.redirect(target.toString(), 302);
});

oidc.post('/token', async (c) => {
  const form = await c.req.parseBody();
  const clientId = String(form.client_id ?? '');
  const clientSecret = String(form.client_secret ?? '');
  const code = String(form.code ?? '');

  const client = findClient(clientId);
  if (!client || !secretMatches(client.clientSecret, clientSecret)) {
    return c.json({ error: 'invalid_client' }, 401);
  }

  const entry = codes.get(code);
  // Deleted on first read, valid or not: a code is single-use, and leaving a
  // failed one in the map lets an attacker retry it against a guessed secret.
  codes.delete(code);
  if (
    !entry ||
    entry.expires < Date.now() ||
    entry.clientId !== clientId ||
    entry.redirectUri !== String(form.redirect_uri ?? '')
  ) {
    return c.json({ error: 'invalid_grant' }, 400);
  }

  const idToken = await signIdentity(
    {
      sub: entry.user.id,
      email: entry.user.email,
      access: entry.user.role === 'ADMIN' ? 'admin' : 'editor',
    },
    clientId,
    TOKEN_TTL_SECONDS,
  );

  return c.json({
    access_token: idToken,
    id_token: idToken,
    token_type: 'Bearer',
    expires_in: TOKEN_TTL_SECONDS,
  });
});

oidc.get('/userinfo', async (c) => {
  const header = c.req.header('authorization') ?? '';
  const token = /^Bearer\s+(.+)$/i.exec(header)?.[1];
  if (!token) return c.json({ error: 'invalid_token' }, 401);

  const { createLocalJWKSet, jwtVerify } = await import('jose');
  const { getJwks } = await import('./lib/oidc-keys.ts');
  try {
    const { payload } = await jwtVerify(token, createLocalJWKSet(await getJwks()), {
      issuer: ISSUER,
    });
    return c.json({ sub: payload.sub, email: payload.email, access: payload.access });
  } catch {
    return c.json({ error: 'invalid_token' }, 401);
  }
});
```

- [ ] **Step 4: Mount it — authorize behind the session check, token and userinfo not**

`/oidc/token` and `/oidc/userinfo` are called by the NUFI Works server, which
carries no browser cookie. Putting `auth()` in front of them would break the
exchange.

```ts
import { oidc } from './oidc.ts';

app.use('/oidc/authorize', auth());
app.route('/oidc', oidc);
```

- [ ] **Step 5: Run the tests and make sure they pass**

Run: `cd apps/console && bun test server/oidc.test.ts`
Expected: 5 pass.

- [ ] **Step 6: Commit**

```bash
git add apps/console/server/oidc.ts apps/console/server/oidc.test.ts apps/console/server/index.ts
git commit -m "feat(console): authorization-code flow for NUFI Works"
```

---

### Task 8: NUFI Works consumes the console as its identity provider

This is the one file added to the `apps/agents` allowlist.

**Files:**
- Modify: `apps/agents/server/src/auth/better-auth.ts`
- Modify: `apps/agents/nufi/check-fork-diff.sh` (allowlist entry)
- Modify: `apps/agents/nufi/README.md` (record why the entry exists)

**Interfaces:**
- Consumes: `/oidc/authorize`, `/oidc/token`, `/oidc/userinfo` from Task 7.
- Produces: a better-auth session established from a NUFI identity.

- [ ] **Step 1: Add the allowlist entry with its reason**

In `apps/agents/nufi/check-fork-diff.sh`, inside `ALLOWLIST`:

```bash
  # Single-sign-on. Upstream ships better-auth with email+password and no
  # plugins; generic-oauth is already in node_modules, so this turns on a
  # supported extension point rather than patching behaviour. Kept to one
  # file so a subtree pull still applies. Candidate to send upstream.
  "server/src/auth/better-auth.ts"
```

- [ ] **Step 2: Verify the guard fails first, for the right reason**

Run: `./apps/agents/nufi/check-fork-diff.sh`
Expected at this point: PASS with 58 changed files, because the file has not
been edited yet. This step establishes the baseline count so Step 5 can show
the diff grew by exactly one.

- [ ] **Step 3: Turn the plugin on**

In `apps/agents/server/src/auth/better-auth.ts`, add the import and extend
`authConfig`:

```ts
import { genericOAuth } from "better-auth/plugins";

// ... inside the object passed to betterAuth():
    plugins: nufiIssuer()
      ? [
          genericOAuth({
            config: [
              {
                providerId: "nufi",
                clientId: process.env.NUFI_OIDC_CLIENT_ID ?? "",
                clientSecret: process.env.NUFI_OIDC_CLIENT_SECRET ?? "",
                authorizationUrl: `${nufiIssuer()}/oidc/authorize`,
                tokenUrl: `${nufiIssuer()}/oidc/token`,
                userInfoUrl: `${nufiIssuer()}/oidc/userinfo`,
                scopes: ["openid", "email"],
              },
            ],
          }),
        ]
      : [],
```

with, above `createBetterAuthHandler`:

```ts
/**
 * Unset means no NUFI provider at all, rather than a half-configured one: a
 * plugin pointed at an empty issuer would render a sign-in button that fails
 * after the redirect, which is worse than no button.
 */
function nufiIssuer(): string | undefined {
  const raw = process.env.NUFI_OIDC_ISSUER?.trim();
  return raw && process.env.NUFI_OIDC_CLIENT_ID?.trim() ? raw.replace(/\/+$/, "") : undefined;
}
```

- [ ] **Step 4: Set the variables on Railway**

On `nufi-works`:

```
NUFI_OIDC_ISSUER=https://console.nufi.me
NUFI_OIDC_CLIENT_ID=nufi-works
NUFI_OIDC_CLIENT_SECRET=<generated; the same value goes in OIDC_CLIENTS on the console>
PAPERCLIP_AUTH_DISABLE_SIGN_UP=true
```

On `nufi-console`:

```
OIDC_CLIENTS=[{"clientId":"nufi-works","clientSecret":"<same>","redirectUris":["https://works.nufi.me/api/auth/oauth2/callback/nufi"]}]
OIDC_ISSUER=https://console.nufi.me
OIDC_PRIVATE_KEY_PEM=<openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048>
```

- [ ] **Step 5: Verify the fork guard shows exactly one more file**

Run: `./apps/agents/nufi/check-fork-diff.sh`
Expected: PASS, `changed: 59`, `violations: 0`. A larger number means
something else was edited by accident.

- [ ] **Step 6: Verify the flow in a browser**

Signed in at `chat.nufi.me`, visit `https://works.nufi.me` and use the NUFI
sign-in. Expected: no password prompt, and the account created carries your
chat email.

Then the negative case: with no chat session, the same button must end at the
console's 401 and must not create an account.

- [ ] **Step 7: Commit**

```bash
./apps/agents/nufi/verify-adapters.mjs
git add apps/agents/server/src/auth/better-auth.ts apps/agents/nufi/check-fork-diff.sh apps/agents/nufi/README.md
git commit -m "feat(works): sign in with a NUFI account"
```

---

### Task 9: The chooser at agents.nufi.me

**Files:**
- Create: `apps/console/src/routes/choose.tsx`
- Modify: `apps/console/server/index.ts`

**Interfaces:**
- Consumes: `/enter/studio` from Task 6; the NUFI sign-in on
  `https://works.nufi.me` from Task 8.
- Produces: the page served at `agents.nufi.me`.

- [ ] **Step 1: Route the hostname to the chooser**

In `apps/console/server/index.ts`, before the SPA catch-all:

```ts
const CHOOSER_HOST = process.env.CHOOSER_HOST ?? 'agents.nufi.me';

app.use('*', async (c, next) => {
  const host = c.req.header('host')?.split(':')[0];
  if (host === CHOOSER_HOST && new URL(c.req.url).pathname === '/') {
    return c.redirect('/choose', 302);
  }
  return next();
});
```

- [ ] **Step 2: Write the page**

Two cards, one sentence each saying what the product is for, so a first-time
visitor can tell them apart without opening both.

```tsx
import { createFileRoute } from '@tanstack/react-router';

export const Route = createFileRoute('/choose')({ component: Choose });

const PRODUCTS = [
  {
    name: 'NUFI Studio',
    blurb: 'Build a flow on a canvas: connect a model, a knowledge base and a tool, then run it.',
    href: '/enter/studio',
  },
  {
    name: 'NUFI Works',
    blurb: 'Put agents to work: give a team a goal, approve what matters, and watch the spend.',
    href: 'https://works.nufi.me',
  },
];

function Choose() {
  return (
    <main className="mx-auto max-w-3xl px-6 py-20">
      <h1 className="text-3xl font-semibold">Agents</h1>
      <p className="mt-2 text-muted-foreground">
        Two ways to work with agents on NUFI. You are already signed in.
      </p>
      <div className="mt-10 grid gap-4 sm:grid-cols-2">
        {PRODUCTS.map((p) => (
          <a
            key={p.name}
            href={p.href}
            className="rounded-xl border p-6 transition hover:border-foreground/40"
          >
            <h2 className="text-lg font-medium">{p.name}</h2>
            <p className="mt-2 text-sm text-muted-foreground">{p.blurb}</p>
          </a>
        ))}
      </div>
    </main>
  );
}
```

- [ ] **Step 3: Regenerate the route tree and build**

Run: `cd apps/console && bunx @tanstack/router-cli generate && bun run build`
Expected: build succeeds and `/choose` appears in `src/routeTree.gen.ts`.

- [ ] **Step 4: Add the domain**

Add custom domain `agents.nufi.me` to the existing `nufi-console` service.
Record the CNAME target. No new service, and therefore no new idle cost.

- [ ] **Step 5: Commit**

```bash
git add apps/console/src/routes/choose.tsx apps/console/src/routeTree.gen.ts apps/console/server/index.ts
git commit -m "feat(console): the chooser at agents.nufi.me"
```

---

### Task 10: Prove the whole path, including what should fail

A green deploy is not evidence that access control works. Each negative case
below has to be watched failing.

**Files:**
- Create: `deploy/railway/verify-agents.sh`

- [ ] **Step 1: Write the check script**

```bash
#!/usr/bin/env bash
# Asserts the public surface of both agent products: reachable, branded, and
# closed to anyone without a NUFI session.
set -euo pipefail

fail=0
check() {  # check <label> <actual> <expected>
  if [[ "$2" == "$3" ]]; then printf 'OK    %-52s %s\n' "$1" "$2"
  else printf 'FAIL  %-52s got %s want %s\n' "$1" "$2" "$3"; fail=1; fi
}

code() { curl -s -o /dev/null -w '%{http_code}' "$1"; }
body() { curl -s "$1"; }

check "studio.nufi.me responds"        "$(code https://studio.nufi.me/)" "200"
check "works.nufi.me responds"         "$(code https://works.nufi.me/)"  "200"
check "agents.nufi.me responds"        "$(code https://agents.nufi.me/)" "200"
check "console publishes JWKS"         "$(code https://console.nufi.me/.well-known/jwks.json)" "200"

check "JWKS carries no private key"    "$(body https://console.nufi.me/.well-known/jwks.json | grep -c '"d"' || true)" "0"
check "Studio names no upstream"       "$(body https://studio.nufi.me/ | grep -ci langflow || true)" "0"
check "Works names no upstream"        "$(body https://works.nufi.me/  | grep -ci paperclip || true)" "0"

# The negatives. Without a chat session none of this may hand anything out.
check "entering Studio needs a session" "$(code https://console.nufi.me/enter/studio)" "401"
check "authorize needs a session"       "$(code 'https://console.nufi.me/oidc/authorize?client_id=nufi-works&redirect_uri=https%3A%2F%2Fworks.nufi.me%2Fapi%2Fauth%2Foauth2%2Fcallback%2Fnufi&state=x')" "401"
check "userinfo refuses no token"       "$(code https://console.nufi.me/oidc/userinfo)" "401"

exit "$fail"
```

- [ ] **Step 2: Run it and read every line**

Run: `chmod +x deploy/railway/verify-agents.sh && ./deploy/railway/verify-agents.sh`
Expected: every line `OK`, exit 0. A `401` that reads `200` is the failure
that matters most here — it means the door is open.

- [ ] **Step 3: Verify the human path by hand**

Signed in at `chat.nufi.me`: `agents.nufi.me` → NUFI Studio lands signed in;
back to `agents.nufi.me` → NUFI Works lands signed in; in NUFI Works, Connect
issues a gateway key under your own user.

- [ ] **Step 4: Commit**

```bash
git add deploy/railway/verify-agents.sh
git commit -m "test(deploy): assert both agent products are up, branded and closed"
```

---

## Not in this plan

**The sandbox cluster.** Agents in NUFI Works cannot run until a Kubernetes
cluster with Cilium exists, because that is the only sandbox provider that
enforces the gateway-only egress invariant. That work needs a provider
decision and gets its own plan. Everything above stands without it: both
products are reachable, branded, and entered with a NUFI account.

**Entitlements.** Every `chat.nufi.me` account reaches both products. Adding
an invite list belongs in the console, where the decision is already made.

**Silent token refresh for Studio.** The `nufi_id` cookie lasts eight hours;
after that a member re-enters through `agents.nufi.me`.
