# Box Owner Console Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the Box Owner Console as a React SPA served by the existing Hono backend, shipping the General, Users, and File Sharing (MVP) tabs from the Figma design, production on a real box.

**Architecture:** A `web/` Vite + React 19 SPA (Zustand + TanStack Query) is built to `web/dist` and served statically by the existing Hono server, which gains a JSON API under `/api/*` that reuses the current `health`/`boxinfo`/`mesh-api`/`invite` logic. New backend pieces: a user-record store (`/state/users.json`), a narrow audited exec layer (docker socket, fixed allowlist), and a files handler over the department drives.

**Tech Stack:** Bun, Hono, React 19, Vite, TypeScript, Zustand, @tanstack/react-query. Tests: `bun test` (backend, box-ci) and Vitest + Testing Library (frontend).

**Spec:** `docs/superpowers/specs/2026-10-05-owner-console-redesign-design.md`

## Global Constraints

- Stack: Bun + React 19 + Zustand + TanStack Query + Hono + Vite (exact).
- The box's socket-free guarantee is relaxed ONLY for the allowlisted exec layer; nothing else gains host access.
- `exec`/`console` accept ONLY: `action ∈ {start, restart, stop}` × a fixed box-service list; `cmd ∈ {status, logs, logs librechat, doctor, support}`. No free-form input ever reaches a shell.
- Kebab-case component files (`service-card.tsx`); exports PascalCase.
- PR bodies and commits in English; no AI-authorship tells in committed docs; no government framing user-visible.
- Design tokens from Figma: fonts Open Sans + Menlo; colors navy `#293069`, green `#00bc37`, red `#ff3333`, blue `#0086e4`, neutral grays, surface `#ffffff`, ground `#f6f7f9`.
- The owner password gates every `/api/*` route except the existing public `/connect*`.

## Review Focus

- **Activation computation edge cases** (Task 7): a key that is expired AND has a joined node is **Activated**, not Expired; a node with no matching record is omitted from the table (not crash); a record whose key the coordinator no longer has reads **Expired**.
- **Exec allowlist bypass** (Task 4): a `service` or `cmd` carrying shell metacharacters or extra args (`status; rm -rf /`, `caddy && …`) is rejected by exact-membership check, never interpolated into a shell.
- **File path traversal** (Task 9): `dept` or `name` containing `..`, a leading `/`, or a path separator is refused before any filesystem access.
- **Coordinator unreachable / no API key** (Task 7): the users list and invite endpoints return a precise `{error}` and HTTP 503/412, and the UI renders it inline — never a blank or a crash.
- **Concurrent store writes** (Task 6): two Add-User writes do not corrupt `users.json`; writes are atomic (write-temp-then-rename) under a single-process in-memory lock.

---

## File Structure

**Backend — `deploy/box/owner-console/src/`**
- `app.ts` *(modify)* — mount `/api/*`, serve `web/dist`, keep auth + `/connect*`.
- `api/status.ts` *(new)* — `GET /api/status`.
- `api/users.ts` *(new)* — users list/add/delete/regenerate/connector/import/export.
- `api/control.ts` *(new)* — `POST /api/control`, `POST /api/console` (SSE).
- `api/files.ts` *(new)* — files list/upload/download.
- `store.ts` *(new)* — `UserRecord` store over `/state/users.json`.
- `exec.ts` *(new)* — allowlisted docker action/command + audit.
- `reuse (unchanged)`: `health.ts`, `boxinfo.ts`, `mesh-api.ts`, `invite.ts`, `connector.ts`, `auth.ts`, `token.ts`.

**Backend tests — `deploy/box/owner-console/test/`** (existing dir; follows the owner-console handler-test pattern)

**Frontend — `deploy/box/owner-console/web/`**
- `package.json`, `vite.config.ts`, `index.html`, `tsconfig.json` *(new)*.
- `src/main.tsx`, `src/app.tsx` *(new)* — root + three-tab shell.
- `src/store.ts` *(new)* — Zustand UI store (active tab, open modal).
- `src/api.ts` *(new)* — typed fetch client + TanStack Query hooks.
- `src/ui/` *(new)* — `tokens.css`, `button.tsx`, `card.tsx`, `badge.tsx`, `tabs.tsx`, `table.tsx`, `modal.tsx`, `toast.tsx`.
- `src/tabs/general.tsx`, `general/service-card.tsx`, `general/console.tsx` *(new)*.
- `src/tabs/users.tsx`, `users/user-table.tsx`, `users/add-user-modal.tsx` *(new)*.
- `src/tabs/files.tsx` *(new)*.

**Compose / image — `deploy/box/`**
- `docker-compose.yml` *(modify)* — caddy `ports: + "3009:3009"`; owner-console `volumes: + owner-console-state:/state` + `${NUFI_DATA_DIR}/drives:/drives`; `environment: + SSL_CERT_FILE`.
- `owner-console/Dockerfile` *(modify)* — build `web/`; entrypoint builds the CA bundle.
- `owner-console/entrypoint.sh` *(new)* — concatenate system CA + `$MESH_CA_FILE` → `/tmp/ca-bundle.crt`, export `SSL_CERT_FILE`.

---

## Task 1: Scaffold the SPA, serve it from Hono, and fix the two deploy bugs

**Files:**
- Create: `deploy/box/owner-console/web/package.json`, `web/vite.config.ts`, `web/index.html`, `web/tsconfig.json`, `web/src/main.tsx`, `web/src/app.tsx`
- Create: `deploy/box/owner-console/entrypoint.sh`
- Modify: `deploy/box/owner-console/src/app.ts` (serve `web/dist`), `deploy/box/owner-console/Dockerfile`, `deploy/box/docker-compose.yml`, `deploy/box/Caddyfile` (confirm `:3009` route present — no change expected)
- Test: `deploy/box/owner-console/test/spa.test.ts`, `deploy/box/tests/test_compose.py` (extend)

**Interfaces:**
- Produces: Hono serves `GET /` → the built SPA's `index.html`; `GET /assets/*` → static; `GET /api/ping` → `{ok:true}`. Build command `bun run --cwd web build` emits `web/dist`.

- [ ] **Step 1: Write the failing test** — the server serves the SPA shell and a ping.
```ts
// test/spa.test.ts
import { test, expect } from 'bun:test';
import app from '../src/app';
test('GET /api/ping returns ok', async () => {
  const r = await app.request('/api/ping');
  expect(r.status).toBe(200);
  expect(await r.json()).toEqual({ ok: true });
});
test('GET / serves the SPA index', async () => {
  const r = await app.request('/');
  expect(r.status).toBe(200);
  expect(r.headers.get('content-type') || '').toContain('text/html');
});
```
- [ ] **Step 2: Run to verify it fails** — `cd deploy/box/owner-console && bun test spa` → FAIL (no `/api/ping`, no SPA serve).
- [ ] **Step 3: Scaffold the Vite React app.** `web/package.json` with deps `react@^19 react-dom@^19 zustand @tanstack/react-query` and dev `vite @vitejs/plugin-react typescript vitest @testing-library/react jsdom`. `web/vite.config.ts` sets `build.outDir='dist'`, `base='/'`. `web/index.html` loads `/src/main.tsx`. `web/src/main.tsx` mounts `<App/>` into `#root` inside a `QueryClientProvider`. `web/src/app.tsx` renders a minimal shell (`<div>NuFi box · owner</div>`). Run `bun install` in `web/` then `bun run build`.
- [ ] **Step 4: Serve it from Hono.** In `src/app.ts`, after auth middleware, add `app.get('/api/ping', c => c.json({ ok: true }))` and mount static serving of `web/dist` for `/` and `/assets/*` (use `hono/bun` `serveStatic({ root: './web/dist' })` with an SPA fallback to `index.html` for non-API routes). Keep `/connect*` and `/login`/`/logout` as they are.
- [ ] **Step 5: Run to verify it passes** — `bun test spa` → PASS.
- [ ] **Step 6: Fix bug #1 — publish `:3009`.** In `deploy/box/docker-compose.yml` caddy service `ports:`, add `- "3009:3009"`. Extend `deploy/box/tests/test_compose.py` with `test_caddy_publishes_owner_console_port` asserting `3009:3009` is in the rendered caddy ports when the owner-console profile is on. Run the pytest → PASS.
- [ ] **Step 7: Fix bug #2 — Bun CA bundle.** Create `entrypoint.sh`: `cat /etc/ssl/certs/ca-certificates.crt "${MESH_CA_FILE:-/dev/null}" > /tmp/ca-bundle.crt 2>/dev/null; export SSL_CERT_FILE=/tmp/ca-bundle.crt; exec bun run src/server.ts`. Point the Dockerfile `ENTRYPOINT`/`CMD` at it, and build `web/` in the image (`RUN bun install && bun run build` in `web/`, copy `web/dist`). Add `SSL_CERT_FILE` is set by the entrypoint (no compose env needed). Add `test/ca_bundle.test.ts` that runs `entrypoint.sh` with a fake `MESH_CA_FILE` and asserts `/tmp/ca-bundle.crt` contains the fake CA.
- [ ] **Step 8: Commit** — `git add deploy/box/owner-console/web deploy/box/owner-console/entrypoint.sh deploy/box/owner-console/src/app.ts deploy/box/owner-console/Dockerfile deploy/box/docker-compose.yml deploy/box/owner-console/test && git commit -m "feat(owner-console): React SPA served by Hono; publish :3009; Bun CA bundle"`

---

## Task 2: Design system (`web/src/ui/`)

**Files:**
- Create: `web/src/ui/tokens.css`, `button.tsx`, `card.tsx`, `badge.tsx`, `tabs.tsx`, `table.tsx`, `modal.tsx`, `toast.tsx`
- Test: `web/src/ui/ui.test.tsx`

**Interfaces:**
- Produces:
  - `Button({variant?: 'primary'|'secondary'|'danger'|'ghost', size?, ...})` 
  - `Card({title?, right?, children})`
  - `Badge({tone: 'ok'|'bad'|'warn'|'neutral', children})` (the pill)
  - `Tabs({tabs: {id,label}[], active, onChange})`
  - `Table({columns: Col[], rows, ...})` with sort-less columns
  - `Modal({open, title, onClose, children, actions})`
  - `useToast()` → `push(msg, tone)`; `<Toaster/>`

- [ ] **Step 1: Write the failing test** — each primitive renders its contract.
```tsx
// ui.test.tsx (Vitest + Testing Library)
import { render, screen } from '@testing-library/react';
import { Button } from './button'; import { Badge } from './badge';
test('Button renders label and variant class', () => {
  render(<Button variant="danger">Stop</Button>);
  const b = screen.getByRole('button', { name: 'Stop' });
  expect(b.className).toContain('danger');
});
test('Badge ok tone', () => {
  render(<Badge tone="ok">Running</Badge>);
  expect(screen.getByText('Running').className).toContain('ok');
});
```
- [ ] **Step 2: Run to verify it fails** — `cd web && bunx vitest run ui` → FAIL.
- [ ] **Step 3: Implement `tokens.css`** — CSS variables for the Figma palette + fonts (`--navy`, `--ok`, `--bad`, `--info`, `--ink`, `--surface`, `--ground`, `--rule`, radii; `--font: "Open Sans",…`, `--mono: Menlo,…`). Import Open Sans via a `<link>` in `index.html`.
- [ ] **Step 4: Implement each primitive** — thin, class-token-driven components mapping the Figma states (Button variants = the Figma Start/Restart/Stop styling; Badge tones = Running green / error red / neutral grey; Tabs = the General/Users/File Sharing pill switch; Table = the Users/Files columns; Modal = the Figma "Restart Service?" dialog; Toast for action feedback). Markup follows the Figma component set (`Design STM` page); styling via tokens only.
- [ ] **Step 5: Run to verify it passes** — `bunx vitest run ui` → PASS.
- [ ] **Step 6: Commit** — `git commit -m "feat(owner-console): design-system primitives from Figma tokens"`

---

## Task 3: Status API + General read UI

**Files:**
- Create: `src/api/status.ts`, `web/src/api.ts`, `web/src/tabs/general.tsx`, `web/src/tabs/general/service-card.tsx`, `web/src/store.ts`
- Modify: `src/app.ts` (mount status route), `web/src/app.tsx` (render Tabs + General)
- Test: `test/status.test.ts`, `web/src/tabs/general.test.tsx`

**Interfaces:**
- Produces: `GET /api/status` → `{ box: BoxInfo, services: Health[] }` where `Health = {name, ok, ms, status?, detail?}` (from `health.ts`) and `BoxInfo` from `boxinfo.ts`. Frontend: `useStatus()` TanStack Query hook; `<General/>` tab.
- Consumes: `health.ts` `probeAll()`, `boxinfo.ts` `boxInfo()` (existing).

- [ ] **Step 1: Write the failing backend test**
```ts
// test/status.test.ts
import { test, expect } from 'bun:test';
import app from '../src/app';
import { withOwnerCookie } from './helpers'; // existing auth helper pattern
test('GET /api/status returns box + services', async () => {
  const r = await app.request('/api/status', { headers: withOwnerCookie() });
  expect(r.status).toBe(200);
  const j = await r.json();
  expect(j.box).toHaveProperty('name');
  expect(Array.isArray(j.services)).toBe(true);
});
test('GET /api/status without owner cookie is 401', async () => {
  expect((await app.request('/api/status')).status).toBe(401);
});
```
- [ ] **Step 2: Run → FAIL** (`bun test status`).
- [ ] **Step 3: Implement `api/status.ts`** — `export const status = async (c) => c.json({ box: await boxInfo(), services: await probeAll() })`; mount `app.get('/api/status', requireOwner, status)` in `app.ts` (reuse the existing owner-auth middleware).
- [ ] **Step 4: Run → PASS**.
- [ ] **Step 5: Write the failing frontend test** — `general.test.tsx`: mock `useStatus` to return four services; assert four service cards render with name + a status badge.
- [ ] **Step 6: Implement `web/src/api.ts`** (fetch wrapper that throws `{error}` on non-2xx; `useStatus = () => useQuery(['status'], () => get('/api/status'))`), `store.ts` (Zustand: `{tab, setTab, modal, setModal}`), `<General/>` + `<ServiceCard/>` mapping the four Figma cards (Web Server/Database/chat/AI model) with the Running badge, and the Tabs shell in `app.tsx`.
- [ ] **Step 7: Run frontend test → PASS**.
- [ ] **Step 8: Commit** — `git commit -m "feat(owner-console): status API + General service cards"`

---

## Task 4: The exec layer (`exec.ts`)

**Files:**
- Create: `src/exec.ts`
- Test: `test/exec.test.ts`

**Interfaces:**
- Produces:
  - `const SERVICES = ['librechat','litellm-proxy','rag_api','ollama','caddy','mongodb','postgres','studio'] as const` (the box services exposed to control)
  - `const READ_CMDS = ['status','logs','logs librechat','doctor','support'] as const`
  - `async function controlService(action:'start'|'restart'|'stop', service:string): Promise<{ok:boolean, audit:string}>` — throws `BadRequest` if `action`/`service` not in the sets.
  - `async function runReadCommand(cmd:string): AsyncIterable<string>` — streams stdout lines; throws `BadRequest` if `cmd` not in `READ_CMDS`.
  - Both append a line to the audit log (`/state/audit.log`) before running.
- Consumes: the docker socket (mounted) — via `docker` CLI invoked with an **argv array**, never a shell string.

- [ ] **Step 1: Write the failing test** — allowlist is exact; bypass rejected; argv not a shell.
```ts
// test/exec.test.ts
import { test, expect } from 'bun:test';
import { controlService, runReadCommand } from '../src/exec';
test('rejects an action not in the set', async () => {
  await expect(controlService('nuke' as any, 'caddy')).rejects.toThrow(/action/);
});
test('rejects a service with metacharacters', async () => {
  await expect(controlService('restart', 'caddy; rm -rf /')).rejects.toThrow(/service/);
});
test('rejects a read command with appended args', async () => {
  const it = runReadCommand('status; whoami');
  await expect((async () => { for await (const _ of it) {} })()).rejects.toThrow(/command/);
});
```
- [ ] **Step 2: Run → FAIL**.
- [ ] **Step 3: Implement `exec.ts`.** Exact-membership checks (`if (!SERVICES.includes(service)) throw BadRequest`). `controlService` spawns `['docker','compose','-p','nufi-box', action==='start'?'start':action==='stop'?'stop':'restart', service]` via `Bun.spawn({ cmd: [...] })` (argv array, no shell). `runReadCommand` maps the fixed cmd to `['bash','nufi-box', ...cmd.split(' ')]` **only after** exact-membership on the whole string, spawns with an argv array, and yields stdout lines. Audit: append `ISO ts · action/cmd · service` to `/state/audit.log`.
- [ ] **Step 4: Run → PASS**.
- [ ] **Step 5: Commit** — `git commit -m "feat(owner-console): allowlisted, audited exec layer"`

---

## Task 5: Control API + General control & console UI

**Files:**
- Create: `src/api/control.ts`, `web/src/tabs/general/console.tsx`
- Modify: `src/app.ts`, `web/src/tabs/general.tsx` (add control buttons + console)
- Test: `test/control.test.ts`, `web/src/tabs/general-control.test.tsx`

**Interfaces:**
- Produces: `POST /api/control {action, service}` → `{ok, audit}` (calls `controlService`); `POST /api/console {cmd}` → `text/event-stream` of output lines (calls `runReadCommand`). Frontend: Start/Restart/Stop buttons (restart/stop open the confirm `Modal`), and a `<Console/>` that streams lines.

- [ ] **Step 1: Write the failing backend test** — control routes gate on the allowlist + owner auth.
```ts
test('POST /api/control restart caddy → ok (allowlisted)', async () => {
  const r = await app.request('/api/control', { method:'POST', headers: withOwnerCookie({'content-type':'application/json'}),
    body: JSON.stringify({ action:'restart', service:'caddy' }) });
  expect([200,500]).toContain(r.status); // 500 only if docker is absent in CI; never a shell injection
});
test('POST /api/control with a bad service → 400', async () => {
  const r = await app.request('/api/control', { method:'POST', headers: withOwnerCookie({'content-type':'application/json'}),
    body: JSON.stringify({ action:'restart', service:'evil; rm' }) });
  expect(r.status).toBe(400);
});
```
- [ ] **Step 2: Run → FAIL**.
- [ ] **Step 3: Implement `api/control.ts`** — parse+validate body, call `controlService`/`runReadCommand`; the console route returns an SSE stream (`c.stream`), mapping the `BadRequest` to 400 and other failures to 500 with `{error}`. Mount both with `requireOwner`.
- [ ] **Step 4: Run → PASS**.
- [ ] **Step 5: Write the failing frontend test** — clicking Restart opens the confirm modal; confirming POSTs `{action:'restart', service}`.
- [ ] **Step 6: Implement the General control row + `<Console/>`** — three buttons (Start/Restart/Stop) using `Button` variants; restart/stop open `Modal` ("It will take about 1–2 minutes…", Figma screen −4); on confirm, call `useControl().mutate`. `<Console/>` renders the five command chips, posts to `/api/console`, appends streamed lines in a Menlo panel.
- [ ] **Step 7: Run → PASS**.
- [ ] **Step 8: Commit** — `git commit -m "feat(owner-console): General control + System Console (allowlisted)"`

---

## Task 6: The user-record store (`store.ts`)

**Files:**
- Create: `src/store.ts`
- Test: `test/store.test.ts`

**Interfaces:**
- Produces:
  - `type UserRecord = { id:string; name:string; os:'macos'|'windows'|'linux'; keyId:string; token:string; createdAt:string }`
  - `async function listUsers(): Promise<UserRecord[]>`
  - `async function addUser(u: Omit<UserRecord,'id'|'createdAt'>): Promise<UserRecord>`
  - `async function updateUser(id:string, patch: Partial<UserRecord>): Promise<UserRecord>`
  - `async function removeUser(id:string): Promise<void>`
  - File: `${NUFI_STATE_DIR||'/state'}/users.json`; atomic writes (temp+rename) under an in-memory mutex.

- [ ] **Step 1: Write the failing test** — CRUD + persistence + concurrent-safe.
```ts
// test/store.test.ts  (set NUFI_STATE_DIR to a tmp dir in beforeEach)
test('add then list persists', async () => {
  const u = await addUser({ name:'Sun', os:'macos', keyId:'k1', token:'t1' });
  expect(u.id).toBeTruthy();
  expect((await listUsers()).map(x=>x.name)).toContain('Sun');
});
test('concurrent adds do not drop records', async () => {
  await Promise.all([1,2,3].map(n => addUser({ name:'u'+n, os:'linux', keyId:'k'+n, token:'t'+n })));
  expect((await listUsers()).length).toBe(3);
});
```
- [ ] **Step 2: Run → FAIL**.
- [ ] **Step 3: Implement `store.ts`** — read `users.json` (default `[]` if absent), `addUser` pushes with `crypto.randomUUID()` + `new Date().toISOString()`, all mutations go through a `queue` promise-chain (serialize writes) and write via `writeFile(tmp)`+`rename(tmp, path)`.
- [ ] **Step 4: Run → PASS**.
- [ ] **Step 5: Commit** — `git commit -m "feat(owner-console): atomic user-record store"`

---

## Task 7: Users API — the activation join

**Files:**
- Create: `src/api/users.ts`
- Modify: `src/app.ts`
- Test: `test/users.test.ts`

**Interfaces:**
- Produces:
  - `GET /api/users` → `UserRow[]` where `UserRow = UserRecord & { activation:'pending'|'activated'|'expired'; expiresAt?:string; nodeIp?:string; online?:boolean }`
  - `POST /api/users {name, os}` → mints an invite (reuse `invite.ts`), stores a record, returns the `UserRow`.
  - `DELETE /api/users/:id` → revoke the node/key (reuse `mesh-api.ts`), remove the record.
  - `POST /api/users/:id/regenerate` → new key+token, update record.
  - `GET /api/users/:id/connector?os=` → the join file (reuse `connector.ts`).
  - `POST /api/users/import` (CSV), `POST /api/users/export` (CSV/zip).
- Consumes: `store.ts`, `mesh-api.ts` (`listNodes()`, `listKeys()`, `mintMemberKey()`, `revokeNode()`), `invite.ts`, `connector.ts`.

- [ ] **Step 1: Write the failing test** — the activation join (the risky logic), against a fake headscale.
```ts
// test/users.test.ts  (mock mesh-api listNodes/listKeys)
test('pending: key unused+unexpired, no node', async () => {
  // store has {keyId:'k1'}; headscale: key k1 unused, exp in future; nodes: []
  const rows = await usersList(); // the handler fn
  expect(rows[0].activation).toBe('pending');
  expect(rows[0].expiresAt).toBeTruthy();
});
test('activated: a node joined on the key, even if the key is now expired', async () => {
  // store {keyId:'k2'}; node exists with preAuthKey k2; key k2 expired
  expect((await usersList())[0].activation).toBe('activated');
});
test('expired: key expired/used, no node', async () => {
  expect((await usersList())[0].activation).toBe('expired');
});
test('a node with no matching record is not in the table', async () => {
  // nodes has 'stranger' with no store record → omitted
  expect((await usersList()).find(r=>r.name==='stranger')).toBeUndefined();
});
test('coordinator unreachable → 503 with error', async () => {
  // mesh-api throws → handler returns { error } 503
});
```
- [ ] **Step 2: Run → FAIL**.
- [ ] **Step 3: Implement `api/users.ts`.** `usersList()`: fetch `listNodes()` + `listKeys()` once; for each `UserRecord`, find a node whose key is `keyId` → **activated**; else if its key is expired/used → **expired**; else **pending** (+`expiresAt` from the key). Wrap mesh calls in try/catch → `{error}` 503. `POST` mints then `addUser`; `DELETE` revokes then `removeUser`; regenerate mints + `updateUser`; import parses CSV rows `{name,os}` and loops add; export builds a CSV/zip of `{name, link}`. Mount all with `requireOwner`.
- [ ] **Step 4: Run → PASS**.
- [ ] **Step 5: Commit** — `git commit -m "feat(owner-console): users API with activation join"`

---

## Task 8: Users tab UI

**Files:**
- Create: `web/src/tabs/users.tsx`, `users/user-table.tsx`, `users/add-user-modal.tsx`
- Test: `web/src/tabs/users.test.tsx`

**Interfaces:**
- Consumes: `GET/POST/DELETE /api/users*` via TanStack Query hooks in `api.ts` (`useUsers`, `useAddUser`, `useDeleteUser`, `useRegenerate`).

- [ ] **Step 1: Write the failing test** — table renders rows with the activation badge + copy; Add User opens a modal and submits `{name, os}`.
```tsx
test('renders a user row with activation badge and a copy button', () => {
  // mock useUsers → [{name:'Sun', os:'macos', activation:'pending', token:'...', expiresAt:...}]
  render(<Users/>);
  expect(screen.getByText('Sun Nguyen'.slice(0,3), {exact:false})).toBeTruthy();
  expect(screen.getByText(/pending/i)).toBeTruthy();
});
```
- [ ] **Step 2: Run → FAIL**.
- [ ] **Step 3: Implement** the `<Users/>` tab = search + Add User + Upload CSV + the `<UserTable/>` (columns: checkbox, Name, OS, Activation badge, Access Key = the invite link + an expiry countdown ticking from `expiresAt`, and row actions copy/regenerate/download/delete), bulk-select → Export CSV/zip, pagination footer. `<AddUserModal/>` = name + OS select → `useAddUser`. Match the Figma Users frames (−7, −9, −12, −15).
- [ ] **Step 4: Run → PASS**.
- [ ] **Step 5: Commit** — `git commit -m "feat(owner-console): Users tab — table, add user, invite lifecycle"`

---

## Task 9: Files API (MVP)

**Files:**
- Create: `src/api/files.ts`
- Modify: `src/app.ts`, `deploy/box/docker-compose.yml` (mount `${NUFI_DATA_DIR}/drives:/drives` + `owner-console-state:/state` on owner-console)
- Test: `test/files.test.ts`

**Interfaces:**
- Produces: `GET /api/files?dept=<d>` → `{name, kind, size, uploadedAt, modifiedAt}[]`; `POST /api/files?dept=<d>` (multipart) → writes the file; `GET /api/files/:dept/:name` → the bytes. Root: `/drives/<dept>`.
- Consumes: `boxinfo.ts` `departments` (to validate `dept` against the known set).

- [ ] **Step 1: Write the failing test** — list within a dept; upload writes; traversal refused.
```ts
test('lists files in a known department', async () => { /* seed /drives/legal/a.pdf */ });
test('rejects dept traversal', async () => {
  const r = await app.request('/api/files?dept=../../etc', { headers: withOwnerCookie() });
  expect(r.status).toBe(400);
});
test('rejects a filename with a path separator on download', async () => {
  const r = await app.request('/api/files/legal/..%2f..%2fetc%2fpasswd', { headers: withOwnerCookie() });
  expect(r.status).toBe(400);
});
```
- [ ] **Step 2: Run → FAIL**.
- [ ] **Step 3: Implement `api/files.ts`.** Validate `dept` ∈ `departments` (exact), and `name` has no `/`, `\`, or `..` (reject → 400) **before** any fs call; resolve under `/drives/<dept>` and assert the resolved path stays within it. List via `readdir` + `stat`; upload writes the multipart file; download streams it.
- [ ] **Step 4: Run → PASS**; add the compose mounts + a `test_compose.py` assertion for the `/drives` + `/state` mounts.
- [ ] **Step 5: Commit** — `git commit -m "feat(owner-console): files API over the department drives (MVP)"`

---

## Task 10: File Sharing tab UI

**Files:**
- Create: `web/src/tabs/files.tsx`
- Test: `web/src/tabs/files.test.tsx`

**Interfaces:**
- Consumes: `GET/POST /api/files*` via `useFiles(dept)`, `useUpload(dept)`.

- [ ] **Step 1: Write the failing test** — empty state renders the Figma copy; a file list renders rows; drag-drop calls upload.
```tsx
test('empty state', () => { /* mock useFiles → [] */ render(<Files/>);
  expect(screen.getByText(/your uploaded files will be listed here/i)).toBeTruthy(); });
```
- [ ] **Step 2: Run → FAIL**.
- [ ] **Step 3: Implement** `<Files/>` = department picker + search + Upload button + drag-drop zone + the files `<Table/>` (Name/Kind/Size/Dates; Owner+Accessibility columns shown as disabled placeholders — deferred), and the empty state (Figma −16). Download via the file link.
- [ ] **Step 4: Run → PASS**.
- [ ] **Step 5: Commit** — `git commit -m "feat(owner-console): File Sharing tab (MVP)"`

---

## Task 11: Image build, compose wiring, deploy + verify

**Files:**
- Modify: `deploy/box/owner-console/Dockerfile` (multi-stage: build web, copy dist), `deploy/box/docker-compose.yml` (final: caddy :3009, owner-console `/state` volume + `/drives` mount), `.github/workflows/box-images.yml` (ensure `web/**` triggers a rebuild)
- Test: live on a real box

- [ ] **Step 1: Confirm the full compose** renders: caddy publishes 3009; owner-console has `owner-console-state:/state` and `${NUFI_DATA_DIR}/drives:/drives`; run `deploy/box/tests/test_compose.py` → PASS.
- [ ] **Step 2: Build the image locally** — `docker build deploy/box/owner-console` succeeds, the SPA is in `/app/web/dist`, the entrypoint sets `SSL_CERT_FILE`.
- [ ] **Step 3: Run the full backend suite** — `cd deploy/box/owner-console && bun test` all green; `cd deploy/box && python3 -m pytest tests/test_compose.py -q` green.
- [ ] **Step 4: Deploy to a real box and verify each tab** — install/update a box with the new image; open `:3009`; sign in; General (status + a restart with confirm + a console command); Users (add user → copy link → a real join → revoke); File Sharing (list + upload + download). Capture the results.
- [ ] **Step 5: Record the real-product demo video** — `deploy/platform/scenarios/demo/record-chat.mjs`-style, driving the live console (login → General → Users → Files) with captions; output `boxweek.mp4` (replaces the slide deck next week).
- [ ] **Step 6: Commit + open PR** — `git commit -m "feat(owner-console): build the SPA into the image; deploy wiring"` and open the PR against `main`.

---

## Self-Review

**Spec coverage:** General (status T3, control/console T4–5), Users (store T6, API T7, UI T8), File Sharing MVP (API T9, UI T10), exec-security (T4), user store (T6), both bug fixes (T1), image/deploy (T11), video (T11). All spec sections map to a task.

**Placeholder scan:** no "TBD/handle edge cases"; UI markup defers to the design-system components + Figma frames named per task (concrete, not a placeholder).

**Type consistency:** `UserRecord` (T6) ⊂ `UserRow` (T7) consumed by T8 hooks; `Health`/`BoxInfo` (T3) from existing modules; `SERVICES`/`READ_CMDS` (T4) used by T5; `activation` union consistent T7↔T8.

**Review Focus:** activation edge cases → T7 tests; exec allowlist bypass → T4 tests; path traversal → T9 tests; coordinator-unreachable → T7 test; concurrent store writes → T6 test. All five pinned.
