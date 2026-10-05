# Box Owner Console Redesign — Design Spec

**Date:** 2026-10-05
**Status:** For review
**Area:** `deploy/box/owner-console`

## Goal

Rebuild the Box Owner Console UI to the new Figma "Administrator Dashboard"
design, as a React app served by the existing Hono backend, shipping three
tabs this cycle: **General** (service status + control), **Users** (member /
invite management), and **File Sharing (MVP)** (browse + upload over the
department drives). Production, running on a real box.

## Scope

**In scope (this cycle):**
- **General** — service status cards; Start / Restart / Stop on known services
  (confirm dialog); a System Console limited to five read-only commands.
- **Users** — member table with activation states, invite links with expiry,
  Add User, CSV bulk, copy / regenerate / download join file / revoke, bulk
  export.
- **File Sharing (MVP)** — per-department file browser (name / kind / size /
  dates), drag-and-drop upload, download, over the existing `/drives/<dept>`
  volumes.
- **Two in-repo bug fixes** found taking the console live (below).

**Deferred (Next):**
- Per-file access control (Public / Private / shared-with-N-users), folders,
  move / rename — the full Figma file manager.
- A free-form in-browser terminal (arbitrary commands).
- Hardening the exec layer into a separate privileged sidecar (see Security).

## Non-goals

- Changing chat, the admin panel, Studio, or the coordinator.
- The member-facing `/connect` page beyond what already ships (it stays; the
  redesign is the owner-facing console).

---

## Current state (what we build on)

`deploy/box/owner-console/` is a small Bun + Hono app, server-rendering HTML:

- `src/app.ts` — routes (login, dashboard, invite, revoke, logout, `/connect*`).
- `src/views.ts` — all HTML (login, dashboard, connect) with one inline `<style>`.
- `src/auth.ts` / `src/token.ts` — owner-password auth, HMAC-signed cookie.
- `src/health.ts` — probes box services over HTTP, returns `{name, ok, ms, status}`.
- `src/boxinfo.ts` — non-secret box facts (name, host, ip, mesh, departments).
- `src/mesh-api.ts` — headscale REST: list nodes, mint pre-auth keys, revoke.
- `src/invite.ts` — mint an invite link / fleet link / connector.
- `src/connector.ts` — the per-OS join connector the member downloads.

The backend logic for **read status, list members, mint invites, revoke**
already exists and is reused. The redesign replaces `views.ts` (server HTML)
with a React SPA, and turns the routes into a JSON API.

**Two bugs to fix in-repo (found taking the console live on a self-host box):**
1. **Caddy does not publish `:3009`.** The Caddyfile serves the console on
   `:3009` but the `caddy` service's `ports:` list omits `3009`, so the console
   is unreachable on the LAN. Fix: add `"3009:3009"` to the caddy ports.
2. **Bun does not honour `NODE_EXTRA_CA_CERTS` for `fetch()`.** On a self-host
   coordinator (internal CA) the console's calls to the coordinator fail with
   "unable to get local issuer certificate". Bun honours `SSL_CERT_FILE`. Fix:
   have the owner-console entrypoint build a CA bundle (system + the mounted
   coordinator CA) and set `SSL_CERT_FILE` to it — verification stays on.

---

## Architecture

```
Browser (owner)
   │  HTTPS :3009  (Caddy TLS → owner-console:8890)
   ▼
owner-console (Bun + Hono)
   ├── serves the built React SPA (static assets)            [web/dist]
   ├── JSON API  (/api/*)                                    [src/api/*]
   │     ├── status/box   → health.ts, boxinfo.ts   (read)
   │     ├── users        → mesh-api.ts + user store (read/write)
   │     ├── control      → exec.ts (allowlist)     (service control, console)
   │     └── files        → files.ts (over /drives) (browse/upload/download)
   ├── user store         → /state/users.json       (new volume)
   ├── exec layer         → docker socket, fixed allowlist, audit  (new)
   └── drives (ro+rw)     → /drives/<dept>           (mounted, new)
```

- **Frontend:** `deploy/box/owner-console/web/` — **React 19 + Vite +
  TypeScript**, **Zustand** (UI state) + **TanStack Query** (server state).
  Tabs, no router needed (three tabs in one page; a tiny state switch). Built to
  `web/dist`, baked into the owner-console image.
- **Backend:** the existing **Hono** server. `src/app.ts` keeps auth + serves
  the SPA; new `src/api/*` handlers return JSON. Existing `health/boxinfo/
  mesh-api/invite/connector` are reused by the API handlers unchanged where
  possible.
- **Design system:** from Figma — tokens (Open Sans + Menlo; navy `#293069`,
  green `#00bc37`, red `#ff3333`, blue `#0086e4`, grays; radii) and the reused
  components (Button, Card, Pill/Badge, Tabs, Table, Modal, Toast). Built once,
  used by all tabs.

### Module boundaries (each one thing, testable alone)

| Module | Does | Depends on |
|---|---|---|
| `web/` React SPA | the three-tab UI | the JSON API |
| `web/ui/` | design-system components (Button/Card/Table/Modal/…) | tokens only |
| `src/api/status.ts` | `GET /api/status` → services + box + mesh | `health.ts`, `boxinfo.ts` |
| `src/api/users.ts` | `GET/POST/DELETE /api/users*` → the member table + invites | `mesh-api.ts`, `invite.ts`, `store.ts` |
| `src/store.ts` | the user record store (`/state/users.json`) | fs |
| `src/exec.ts` | run an allowlisted action / read-command; audit | docker socket |
| `src/api/control.ts` | `POST /api/control` (service action), `POST /api/console` (read cmd, SSE) | `exec.ts` |
| `src/api/files.ts` | `GET/POST /api/files*` over `/drives/<dept>` | fs |

---

## Data model — the user store

The Figma Users table shows per-user **Name**, **OS**, **Activation**
(Pending / Activated / Expired), and an **Access Key** (invite link + expiry).
headscale alone cannot hold this (pre-auth keys carry no name/OS). So the
console keeps a small store, joined with live headscale data at read time.

**`/state/users.json`** — `UserRecord[]`:
```ts
type UserRecord = {
  id: string;            // stable local id
  name: string;          // "Sun Nguyen"
  os: 'macos' | 'windows' | 'linux';
  keyId: string;         // the headscale pre-auth key id this invite minted
  token: string;         // the /connect invite token (the Access Key link)
  createdAt: string;     // ISO
};
```

**Activation is computed** (not stored), by joining a record with headscale:
- **Activated** — a headscale node exists whose pre-auth key is `keyId` (joined).
- **Expired** — the key is expired/used and no node joined.
- **Pending** — the key is unused and unexpired; show the expiry countdown.

Writes: Add User / CSV append records (after minting the invite); regenerate
mints a new key and updates `keyId`/`token`; delete removes the record and
revokes the node/key. A small state **volume** (`owner-console-state` → `/state`)
is added to the compose service.

---

## Security — the exec layer (the one real posture change)

The current console is **socket-free** by design (no docker socket, no host
shell). General's **Start / Restart / Stop** and the **System Console** require
running something on the host, so this cycle the console gains a **narrow,
audited exec layer** — approved as the deliberate trade-off.

- **One endpoint, a hard allowlist.** `POST /api/control` takes
  `{action, service}` where `action ∈ {start, restart, stop}` and `service ∈`
  a fixed list of box service names. `POST /api/console` takes `{cmd}` where
  `cmd ∈ {status, logs, logs librechat, doctor, support}` only — the five
  read-only commands in the design. **No free-form command input.** Anything
  off the list is rejected before execution.
- **Execution.** Via the **docker socket** mounted into the container (the
  lightest path this cycle) — the allowlist is enforced in the handler, and
  **every call is written to an audit log**. Owner-password auth gates it.
- **Console output streams** back over SSE; restart/stop show a confirm dialog
  (Figma screen −4).
- **Named boundary + hardening path.** Mounting the docker socket is
  root-equivalent; the allowlist is an app-level control, not a kernel one. The
  **deferred hardening** is a separate minimal sidecar that holds the docker
  access and accepts only the allowlisted actions over a local socket, shrinking
  the attack surface. This is written down, not hidden.

---

## Screens → API

### General
- **Service cards** (Caddy / Postgres / chat / AI model): `GET /api/status`.
- **Start / Restart / Stop**: `POST /api/control` (+ confirm modal).
- **System Console**: `POST /api/console` (SSE stream of the five read commands).

### Users
- **Table** (name / OS / activation / access-key + countdown): `GET /api/users`
  (joins store × headscale keys × nodes).
- **Add User** (name + OS → invite link): `POST /api/users`.
- **Upload CSV** (many at once): `POST /api/users/import`.
- **Copy / regenerate / download join file**: `GET /api/users/:id/connector`,
  `POST /api/users/:id/regenerate`.
- **Revoke / delete**: `DELETE /api/users/:id`.
- **Bulk export** (CSV / zip of invite links): `POST /api/users/export`.

### File Sharing (MVP)
- **List** per department: `GET /api/files?dept=<d>` (reads `/drives/<d>`).
- **Upload** (drag-and-drop): `POST /api/files?dept=<d>` (writes the file;
  ingestion into the department agent happens as it does today).
- **Download**: `GET /api/files/:dept/:name`.
- *Deferred:* the Owner / Accessibility (Public/Private/N-users) columns and
  folders — shown as placeholders or omitted this cycle.

---

## Error handling

- Every API handler returns `{error}` + an HTTP status on failure; the SPA shows
  it inline (a toast or a field error), never a blank state.
- Coordinator-unreachable (the self-host CA case, once fixed) and
  no-API-key states are shown precisely, as the current console already does.
- `exec`/`control` failures surface the command's stderr tail + the audit id.
- Uploads validate size/type; the files handler refuses paths outside the
  department folder.

## Testing

- **Backend (Bun test, run in box-ci):** each API handler — status shape, the
  users join (pending/activated/expired computed correctly against a fake
  headscale), the exec allowlist (off-list rejected; on-list runs; audited),
  files (list/upload/download within the department, traversal refused).
  Follows the existing owner-console handler-test pattern.
- **Frontend:** component tests for the design-system pieces + the three tabs'
  key states (loading / error / empty / filled), using a mocked API.
- **Live:** the console is taken onto a real box at the end — login, each tab,
  invite, control, upload — the way this week's demo was verified.

## Deployment

- The React build is baked into the `nufi-owner-console` image (box-images).
- The two bug fixes (caddy `:3009`, Bun `SSL_CERT_FILE`) land with it so a
  self-host box reaches the console and trusts its coordinator out of the box.
- The `owner-console-state` volume and the `/drives` mount are added to the
  compose service.

## Rough shape (for the plan — not the plan itself)

- **D1** — scaffold React + Vite + Zustand + TanStack Query; design system
  (tokens + core components); Hono serves the SPA + `GET /api/status`; General
  read parts.
- **D2** — General control + console (the exec layer + allowlist + audit + SSE
  + confirm modal); the two bug fixes.
- **D3** — Users: store + the joined table (states + countdown) + Add User +
  copy / regenerate / revoke / download.
- **D4** — Users CSV bulk + export + bulk select; File Sharing MVP (list /
  upload / download over the drives).
- **D5 (buffer)** — pixel polish, tests, build into the image, deploy + verify
  on a real box; record the real-product demo video of the new console.

## Global Constraints

- The box's **socket-free** guarantee is deliberately relaxed only for the
  allowlisted exec layer; nothing else gains host access.
- PR bodies and commits in English; no AI-authorship tells in committed docs.
- Kebab-case component files (`service-card.tsx`), PascalCase exports.
- Stack: Bun + React 19 + Zustand + TanStack Query + Hono + Vite.
- No government framing anywhere user-visible.
