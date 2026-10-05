# Box Owner Console — Deferred Design (Cycle 2)

**Date:** 2026-10-05
**Status:** For review
**Area:** `deploy/box/owner-console`, `deploy/platform/adapters/nufi-ingest`, `deploy/box/docker-compose.yml`
**Builds on:** `docs/superpowers/specs/2026-10-05-owner-console-redesign-design.md` (Cycle 1, merged PR #185)

## Goal

Finish the Figma "Administrator Dashboard" to full fidelity: the complete **File
Manager** (folders, rename, delete, sort/filter, multi-file upload, and
per-file/folder **Accessibility** that actually governs chat/RAG access), the
full **General** tab (whole-box service control, richer status cards, and a
command console), and the **exec sidecar** that isolates the box's docker access.

## Scope

**In scope (this cycle), as two independent plans:**

- **Plan 1 — File Manager** (`owner-console` + `nufi-ingest`): folders, breadcrumb
  navigation, rename, delete (cascade), create folder, per-column sort + filter,
  the multi-file upload progress panel, the Owner + Accessibility columns, the
  row context menu, and **Accessibility = Public / Private** enforced through the
  ingest daemon into the chat's RAG access.
- **Plan 2 — General + Terminal + Sidecar** (`owner-console` + a new sidecar):
  whole-box Start/Restart/Stop, richer status cards, the `nufi-box` command
  console (allowlisted, not a raw shell), and moving the docker-socket exec into
  a separate privileged sidecar so the web-facing console no longer holds
  root-equivalent access.
- **Design-system additions** (shared, built first in whichever plan needs them):
  Context Menu, Input, Select, Checkbox, Radio, Avatar (Switch/Drawer only if a
  screen needs them).

**Deferred (Next, not this cycle):**

- **Specific Users** accessibility — needs a box-member ↔ chat-user identity
  bridge (mesh members have no chat identity; see "Why deferred" below). The
  Accessibility modal ships the Specific-Users option **disabled** ("coming
  soon").
- **"Create Agent from this item"** (row menu) — chat-side agent creation; shown
  disabled.
- **Move** between folders and drag-to-reorder — not in the Figma row menu.

## Non-goals

- Changing the chat app's RAG retrieval, the agent/ACL model, or the ingest
  team/agent-per-dept structure beyond what Public/Private enforcement needs.
- The member-facing `/connect` flow.

---

## Current state we build on

- **Cycle 1** shipped the SPA (General/Users/File Sharing MVP), the allowlisted
  exec layer (`src/exec.ts`, over the docker socket), the files API
  (`src/api/files.ts`, purely filesystem over `/drives/<dept>`), and the design
  system (`web/src/ui/`: Button/Card/Badge/Tabs/Table/Modal/Toast).
- **Ingest** (`deploy/platform/adapters/nufi-ingest/nufi_ingest.py`): a stdlib
  Python daemon, polls `/drives/<dept>` every 20s, creates **one chat Team + one
  agent per dept**, and uploads every dept file into that agent
  (`file_search`). Granularity is **dept-wide**; there is no per-file metadata or
  ACL today. State in `/state/state.json` (`dept -> {team_id, agent_id,
  agent_oid}` and `"dept/rel/path" -> {file_id,…}`).
- **Chat access control** already exists: a FILE ACL (`resourceType:'file'`,
  principals USER/GROUP/PUBLIC, role `file_viewer`) set via
  `PUT /api/permissions/file/:id`. BUT a dept member who can see the dept agent
  can search ALL of that dept's files via **agent inheritance**
  (`hasAccessToFilesViaAgent`), regardless of the file ACL. So Private must keep
  the file OFF the shared agent.

### Why "Specific Users" is deferred

Owner-console members are **mesh/headscale identities** (`UserRecord{id, name,
os, keyId, token}`) with no email and no chat user id. Chat users are
independent LibreChat accounts (email). There is no mapping. "Specific Users"
would require resolving mesh members to real chat users (via the chat's
`search-principals`) and a per-file agent rework — a separate effort.

---

## Plan 1 — File Manager

### Architecture / data flow

```
owner-console (web)                owner-console (api)            nufi-ingest (20s poll)        chat app
  File Manager tab   ──folders/CRUD──▶  src/api/files.ts  ──writes──▶  reads .nufi-access.json  ──▶ FILE ACL +
  Accessibility modal                   /drives/<dept>/…               computes effective access   agent file_ids
                                        /drives/<dept>/.nufi-access.json
```

### The access-state contract (owner-console writes, ingest reads)

Per department, a single JSON file **`/drives/<dept>/.nufi-access.json`**:

```json
{ "version": 1,
  "entries": {
    "report.pdf":            { "access": "private" },
    "Company Operations":    { "access": "public"  }
  } }
```

- Keys are **paths relative to the dept root** (a file or a folder).
- `access` ∈ `{"public","private"}` this cycle (`"specific"` reserved, not written).
- **Effective access** of a file = its own entry, else the nearest ancestor
  folder's entry, else **`public`** (preserves today's dept-wide default).
- The console writes this file directly (not through the upload path). Both
  `owner-console` and `nufi-ingest` mount `/drives/<dept>` and already can
  read/write it.
- **`nufi-ingest` and the files listing MUST ignore dotfiles** (`.nufi-access.json`
  and any `.*`): ingest must not embed it as a document, and the files API must
  not list it.

### owner-console backend (`src/api/files.ts`, extended)

- `GET /api/files?dept=<d>&path=<rel>` → list a folder: `[{name, kind:'file'|'folder',
  size, uploadedAt, modifiedAt, access:'public'|'private'}]` (access = effective,
  read from `.nufi-access.json`; folders report their own entry or inherited).
  `path` empty = dept root. All the Cycle-1 traversal + symlink guards apply to
  `path` segment-by-segment.
- `POST /api/files?dept=<d>&path=<rel>` (multipart) → upload into the folder at
  `path` (dir auto-created).
- `GET /api/files/:dept/*` → download (path may include folders).
- `POST /api/files/folder {dept, path, name}` → mkdir (name validated).
- `POST /api/files/rename {dept, path, newName}` → rename a file/folder.
- `DELETE /api/files?dept=<d>&path=<rel>` → delete a file, or a folder + contents
  (cascade); also remove its `.nufi-access.json` entry.
- `PUT /api/files/access {dept, path, access}` → set `public|private` in
  `.nufi-access.json` (write via the atomic temp+rename the user store uses).
- Dotfiles are never listed, downloaded, or deletable through the API.

### owner-console frontend (`web/src/tabs/files.tsx`, reworked)

- Table columns Name · Owner (`Admin`) · Accessibility (badge: Public/Private,
  Specific shown only when set, which it won't be) · Kind · Size · Date uploaded ·
  Date modified, with **sort** (Name/Size/dates) and **filter** (Owner/
  Accessibility/Kind) per the Figma headers; client-side (the listing is small).
- **Folders**: a folder row navigates into it; a **breadcrumb** (Files › … ›) at
  the top navigates back; a **New Folder** action (practical necessity; not an
  explicit Figma frame — flagged).
- **Row context menu** (new `ui/context-menu` component): **Accessibility**,
  Create Agent *(disabled)*, **Rename**, **Download**, **Delete**.
- **Modals**: Accessibility (radios **Public** / **Private** enabled, **Specific
  Users** disabled "coming soon"; copy from the Figma); Rename (text input);
  Delete-confirm (cascade warning for folders, exact Figma copy).
- **Upload**: the multi-file progress panel (per-file progress bar + ✓/✕ +
  "Cancel all"), uploading into the current folder.
- Empty / loading / error states as Cycle 1.

### nufi-ingest changes (`nufi_ingest.py`)

- `_listing` skips dotfiles (`.*`), so `.nufi-access.json` is never a document.
- Load `/drives/<dept>/.nufi-access.json`; compute each file's **effective
  access** (own → ancestor folder → `public`).
- **Public** file → add to the dept agent's `file_ids` (current behavior).
- **Private** file → embed as today BUT **do not add to the agent**, and ensure
  no FILE ACL grants (owner-only). On a public→private change, **remove** it from
  the agent's `file_ids` (`PUT /api/permissions/file/:id` to clear grants if any);
  private→public re-adds it.
- The access map is diffed alongside the existing mtime/sha diff, so a pure
  accessibility change re-runs sharing without re-embedding.

### Plan 1 testing

- owner-console: folder CRUD, rename, cascade delete, access read/write,
  dotfile hidden, traversal/symlink still refused — Bun tests over a tmp drives
  dir (Cycle-1 pattern).
- ingest: effective-access computation (own/inherited/default), dotfile skipped,
  public→private removes from agent, private→public re-adds — Python unit tests
  with a fake chat API (the daemon already injects its HTTP calls).
- Live: set a file Private on the box, confirm a dept member no longer gets it
  in chat; set Public, confirm they do.

---

## Plan 2 — General + Terminal + Exec Sidecar

### The exec sidecar (the real posture change)

Cycle 1 mounted the docker socket into `owner-console` itself (the web-facing
container), gated by an app-level allowlist. This cycle moves that to a **minimal
sidecar**:

- A new container **`owner-exec`** (small image) mounts `/var/run/docker.sock`
  and `group_add` the docker GID. It exposes a tiny API over a **shared unix
  socket** (a volume between it and owner-console) — `POST control {action,
  service}`, `POST run {cmd}` (SSE) — enforcing the SAME allowlist (moved from
  `owner-console/src/exec.ts` into the sidecar) and writing the SAME audit log.
- `owner-console` **no longer mounts the docker socket or group_add**; it calls
  the sidecar over the shared socket. The web-facing surface loses
  root-equivalent access; only the ~1-file sidecar has it.
- The allowlist, argv-only execution, and audit-before-run move verbatim; the
  owner-console side becomes a thin client.

### The command console (General)

- The System Console gains a **command input** (`root@nufi-box:~# ___`, "Press
  Enter to execute") in addition to the five quick chips.
- **Allowlist expands to the `nufi-box` CLI surface**: the input's first token
  must be a known `nufi-box` subcommand (a fixed set — e.g. `status`, `logs`,
  `doctor`, `support`, `members`, `ps`, `restart <service>`, …, enumerated from
  the `nufi-box` script) OR one of the existing docker read commands. Anything
  else is rejected before execution. **No raw shell, no shell metacharacters** —
  the input is tokenized and matched, same discipline as Cycle 1.
- Output streams over the existing SSE path, now via the sidecar.

### General status (full cards + whole-box control)

- **Whole-box Start/Restart/Stop Service** (the top buttons): map to
  `docker compose -p nufi-box {start|stop|restart}` across the box's services
  (via the sidecar), with the Figma confirm dialogs ("This will disconnect all
  users…").
- **Richer cards**: Web Server (Caddy · port), Database (Postgres · N active
  connections — a `pg_stat_activity` count via a read probe), NuFi Chat App
  (version — from the librechat image tag or `/api/config`), AI Model (model name
  + size — from ollama `/api/tags` / litellm). Each stays graceful-fail.
- A **Status: Active** pill reflecting overall health.

### Plan 2 testing

- Sidecar: the allowlist + argv + audit tests move with the code; a client↔sidecar
  round-trip test over the unix socket; off-allowlist rejected.
- Console: an allowed `nufi-box` subcommand runs; a raw/shell/off-list input is
  rejected (400) before execution.
- compose test: `owner-console` no longer mounts the docker socket; `owner-exec`
  does; the shared socket volume exists.
- Live: run a console command + a whole-box restart from the UI; confirm the
  web container has no docker socket.

---

## Design-system additions (`web/src/ui/`)

From the Figma "Design STM" page: **context-menu**, **input**, **select**,
**checkbox**, **radio**, **avatar** (and **switch** if a screen needs it). Built
from the existing tokens, kebab-case files, PascalCase exports, consistent with
Cycle 1's components. Each with a component test.

## Error handling

- Every API returns `{error}` + status; the SPA shows it via the (now-mounted)
  toaster, never a blank state.
- Accessibility writes that fail, ingest-unreachable, sidecar-unreachable, a
  folder delete that partially fails — each surfaces precisely.

## Deployment

- `.nufi-access.json` lives on the existing `/drives` mount (no new volume for
  Plan 1). Plan 2 adds the `owner-exec` service + a shared `owner-exec-sock`
  volume, and removes the docker-socket mount + `group_add` from `owner-console`.
- Images build in box-images CI; `nufi-box update` ships them.

## Global Constraints

- Stack: Bun + Hono + React 19 + Vite + Zustand + TanStack Query (owner-console);
  stdlib Python 3 (ingest, no new deps).
- Kebab-case component files, PascalCase exports; reuse `ui/` + `var(--)` tokens,
  no raw hex.
- PR bodies + commits in English; no AI-authorship tells in committed docs.
- The box's socket-free-web guarantee is **restored and strengthened**: after
  Plan 2, the web container holds no docker socket; only the sidecar does.
- No government framing anywhere user-visible.
