# File Manager (Cycle 2 — Plan 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the File Sharing MVP into the full Figma file manager — folders, breadcrumb, rename, cascade delete, new folder, per-column sort/filter, a multi-file upload progress panel, and per-file/folder **Accessibility (Public/Private)** that the ingest daemon enforces into chat/RAG access.

**Architecture:** owner-console adds folder-aware filesystem CRUD over `/drives/<dept>` plus a per-dept access-state file `.nufi-access.json`; the React tab is reworked for folders/breadcrumb/context-menu/modals; `nufi-ingest` reads the access-state and keeps Public files on the dept agent while keeping Private files off it (owner-only). Specific-Users is deferred (UI disabled).

**Tech Stack:** Bun + Hono (owner-console api), React 19 + Vite + Zustand + TanStack Query (web), stdlib Python 3 (ingest). No new deps.

**Spec:** `docs/superpowers/specs/2026-10-05-owner-console-deferred-design.md`

## Global Constraints

- No new dependencies anywhere. Kebab-case component files, PascalCase exports; reuse `web/src/ui/` + `var(--…)` tokens, no raw hex.
- Backend tests in `deploy/box/owner-console/tests/` (`bun:test`, `makeApp()`/`ownerCookie()` from `tests/helpers.ts`); web tests `vitest` (`vi.spyOn(api,…)` pattern); ingest tests stdlib `unittest`.
- Drives root is `env.NUFI_DRIVES_DIR ?? '/drives'`. All path handling reuses `deptDir`/`safeName`/`filePath`/`entry` (lstat) and keeps the Cycle-1 traversal + symlink guards on every segment.
- `FileRow.kind` stays `'file' | 'dir'` (Cycle-1 type); the UI labels `'dir'` as "Folder".
- `.nufi-access.json` (and any dotfile) is never listed, downloaded, or deletable through the API. Ingest already skips dotfiles (`IGNORED_PREFIXES` includes `"."`, `nufi_ingest.py:41`) — do not break that.
- PR bodies + commits in English; no AI-authorship tells in committed docs.

## Review Focus

- **Dotfile integrity:** `.nufi-access.json` must never appear in a listing, be downloadable, or be clobbered by an upload named `.nufi-access.json` (reject dot-leading upload names) — Task 3/4 tests.
- **Effective-access inheritance:** a file with no own entry inherits the **nearest ancestor folder's** access, not the dept default when an ancestor is set — Task 2 tests.
- **Transition enforcement:** public→private **removes** the file from the dept agent (and clears any FILE ACL grants); private→public **re-adds** it — Task 9 tests.
- **Cascade delete hygiene:** deleting a folder removes the access-state entries for it and all descendants (no orphan entries left to mislead ingest) — Task 4 tests.
- **Path traversal with folders:** the new `path` param on list/upload/download/mkdir/rename/delete is validated segment-by-segment; `..`, absolute, backslash, encoded traversal, and symlinked intermediate dirs are all refused — Task 3 tests.

---

### Task 1: Design-system additions (`web/src/ui/`)

**Files:**
- Create: `web/src/ui/context-menu.tsx`, `input.tsx`, `select.tsx`, `checkbox.tsx`, `radio.tsx`, `avatar.tsx`
- Test: `web/src/ui/ui.test.tsx` (extend)

**Interfaces — Produces:**
- `ContextMenu({ items: {label, icon?, danger?, disabled?, onSelect}[], children })` — `children` is the trigger; opens a positioned menu; closes on select/outside-click/Escape.
- `Input(props: JSX.IntrinsicElements['input'])`, `Select({value,onChange,options:{value,label}[]})`, `Checkbox({checked,onChange,label?})`, `Radio({name,value,checked,onChange,label,hint?})`, `Avatar({name,size?})` (initial + token color).

- [ ] **Step 1: Failing tests** — each renders + behaves: ContextMenu opens on trigger click and calls `onSelect`; a `disabled` item does not; Radio reflects `checked`; Avatar shows the initial. (vitest + @testing-library, the `ui.test.tsx` pattern.)
- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement** the six components with `var(--…)` tokens only (match the Figma "Design STM" states; ContextMenu uses the Modal/portal pattern for outside-click + Escape).
- [ ] **Step 4: Run → PASS** + `bun run build` clean.
- [ ] **Step 5: Commit** — `feat(owner-console): design-system context-menu/input/select/checkbox/radio/avatar`.

---

### Task 2: Access-state module (`src/access.ts`)

**Files:**
- Create: `deploy/box/owner-console/src/access.ts`
- Test: `tests/access.test.ts`

**Interfaces — Produces:**
```ts
export type Access = 'public' | 'private';
export type AccessFile = { version: 1; entries: Record<string, { access: Access }> };
// path of the dept's .nufi-access.json
export function accessPath(driveDir: string): string;               // `${driveDir}/.nufi-access.json`
export async function readAccess(driveDir: string): Promise<AccessFile>;   // {version:1,entries:{}} if absent/corrupt
export async function writeAccess(driveDir: string, a: AccessFile): Promise<void>; // atomic temp+rename, 0600
export function effectiveAccess(a: AccessFile, relPath: string): Access;    // own → nearest ancestor folder → 'public'
export async function setEntry(driveDir: string, relPath: string, access: Access): Promise<void>;
export async function removeSubtree(driveDir: string, relPath: string): Promise<void>; // relPath + all descendants
```

- [ ] **Step 1: Failing tests** — `effectiveAccess`: own entry wins; else nearest ancestor folder (`a/b/c.pdf` inherits `a/b` over `a`); else `'public'`. `setEntry`/`readAccess` round-trip; absent file → empty; corrupt JSON → empty (no throw). `removeSubtree('a')` drops `a`, `a/x`, `a/y/z` but not `ab`. Atomic write leaves no `.tmp`.
- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement** — reuse the user-store atomic write (temp+rename, 0600) + a serialize queue; path keys use `/` separators; `effectiveAccess` walks ancestors by trimming the last `/`-segment.
- [ ] **Step 4: Run → PASS.**
- [ ] **Step 5: Commit** — `feat(owner-console): per-dept access-state module`.

---

### Task 3: files.ts — folders, path, mkdir, rename, cascade delete

**Files:**
- Modify: `deploy/box/owner-console/src/api/files.ts`
- Test: `tests/files.test.ts` (extend)

**Interfaces — Produces (all under the existing `/api/*` 401 gate):**
- `GET /api/files?dept=&path=<rel>` → `FileRow[]` for that folder (`path` empty = root). `FileRow` gains `access: Access` (from Task 2, effective).
- `POST /api/files?dept=&path=<rel>` (multipart `file`) → upload into `path` (auto-mkdir). Reject a dot-leading upload name.
- `GET /api/files/:dept/*` → download; the `*` is the rel path (folders allowed), validated segment-by-segment.
- `POST /api/files/folder {dept, path, name}` → mkdir.
- `POST /api/files/rename {dept, path, newName}` → rename a file/folder (same parent).
- `DELETE /api/files?dept=&path=<rel>` → delete file, or folder + contents (recursive); then `removeSubtree(path)`.

**Interfaces — Consumes:** Task 2 `readAccess`/`effectiveAccess`/`removeSubtree`; existing `deptDir`/`safeName`/`filePath`/`entry`.

- [ ] **Step 1: Failing tests** — add `resolveRel(dir, path)` that validates each segment with `safeName` + the `startsWith(dir+sep)` recheck + rejects a symlinked intermediate dir. Tests: list a subfolder; upload into `sub/`; download `sub/a.pdf`; mkdir; rename; delete a folder removes its files on disk AND its access entries; `path=../x`, `path=a/../../etc`, `%2e%2e`, a dot-leading upload name, a symlinked intermediate dir → 400 and nothing written; `.nufi-access.json` never appears in a listing.
- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement** — add `resolveRel`; thread `path` through the routes; `mkdir -p` on upload; `rm -rf` (recursive) on folder delete then `removeSubtree`; filter dotfiles out of every listing; attach `access` to each row via `effectiveAccess(await readAccess(dir), relOf(entry))`.
- [ ] **Step 4: Run → PASS.**
- [ ] **Step 5: Commit** — `feat(owner-console): folders, mkdir, rename, cascade delete in the files API`.

---

### Task 4: files.ts — the Accessibility endpoint

**Files:**
- Modify: `deploy/box/owner-console/src/api/files.ts`
- Test: `tests/files.test.ts` (extend)

**Interfaces — Produces:** `PUT /api/files/access {dept, path, access:'public'|'private'}` → `setEntry` after validating `path` resolves to an existing file/folder; 400 on a bad dept/path/access value; rejects `path` that is a dotfile.

- [ ] **Step 1: Failing tests** — set a file private then GET list shows `access:'private'`; set a folder private then a child with no own entry lists as `'private'` (inherited); an invalid `access` value → 400; `path` pointing at `.nufi-access.json` → 400; setting then deleting the item leaves no stale entry (ties to Task 3 cascade).
- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement** the route; reuse `resolveRel` to confirm the target exists; call `setEntry`.
- [ ] **Step 4: Run → PASS.**
- [ ] **Step 5: Commit** — `feat(owner-console): set file/folder accessibility (public/private)`.

---

### Task 5: Web data layer + folder navigation + breadcrumb

**Files:**
- Modify: `web/src/api.ts`, `web/src/tabs/files.tsx`
- Create: `web/src/tabs/files/breadcrumb.tsx`
- Test: `web/src/tabs/files.test.tsx` (extend)

**Interfaces — Produces (api.ts):**
```ts
export type FileRow = { name:string; kind:'file'|'dir'; size:number; uploadedAt:string; modifiedAt:string; access:'public'|'private' };
export const useFiles = (dept?:string, path?:string) => useQuery({ queryKey:['files',dept,path], queryFn:()=>get<FileRow[]>(`/api/files?dept=${enc(dept!)}&path=${enc(path??'')}`), enabled:!!dept, retry:false });
export const useMkdir/ useRename / useDeleteFile / useSetAccess = useMutation(...) // each invalidates ['files',dept,path]
```
State: a Zustand `path` per dept (current folder) in `web/src/store.ts`.

- [ ] **Step 1: Failing tests** — clicking a `dir` row navigates (path grows, `useFiles` called with the new path); the breadcrumb renders `Files › a › b` and clicking a crumb navigates up; mutations invalidate `['files',dept,path]`.
- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement** the hooks (+ a `del`/`putJson` helper as needed, reusing `fail(r)`), the `path` state, a `<Breadcrumb/>`, and row-click navigation for `dir` rows.
- [ ] **Step 4: Run → PASS** + build clean.
- [ ] **Step 5: Commit** — `feat(owner-console): file manager folder navigation + breadcrumb`.

---

### Task 6: The table — columns, sort, filter, context menu

**Files:**
- Modify: `web/src/tabs/files.tsx`
- Create: `web/src/tabs/files/file-table.tsx`
- Test: `web/src/tabs/files.test.tsx` (extend)

**Interfaces — Produces:** `<FileTable rows onOpen onAction search />` with columns Name · Owner(`Admin`) · Accessibility(Badge: Public/Private) · Kind · Size · Date uploaded · Date modified; client-side **sort** (Name/Size/dates) and **filter** (Owner/Accessibility/Kind) per the Figma header affordances; each row a `<ContextMenu>` (Accessibility / Create Agent *(disabled)* / Rename / Download / Delete); `dir` rows open on click.

- [ ] **Step 1: Failing tests** — a private row shows a "Private" badge, a public row "Public"; sorting by Name reorders; filtering Accessibility=Private hides public rows; the context menu lists the five items with Create-Agent disabled; selecting Rename/Delete/Accessibility fires the right callback with the row.
- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement** using `ui/table`, `ui/badge`, `ui/context-menu`, `ui/avatar`; pure helpers `sortRows`/`filterRows` (testable).
- [ ] **Step 4: Run → PASS** + build clean.
- [ ] **Step 5: Commit** — `feat(owner-console): file table with sort, filter, and row context menu`.

---

### Task 7: Modals — Accessibility, Rename, Delete-confirm, New Folder

**Files:**
- Create: `web/src/tabs/files/access-modal.tsx`, `rename-modal.tsx`, `delete-dialog.tsx`, `new-folder-modal.tsx`
- Modify: `web/src/tabs/files.tsx`
- Test: `web/src/tabs/files.test.tsx` (extend)

**Interfaces — Produces:** `<AccessModal>` (radios **Public** / **Private** enabled with the Figma hints, **Specific Users** radio **disabled** "coming soon") → `useSetAccess`; `<RenameModal>` → `useRename`; `<DeleteDialog>` (folder → the cascade-warning copy; file → simple) → `useDeleteFile`; `<NewFolderModal>` → `useMkdir`.

- [ ] **Step 1: Failing tests** — AccessModal: Specific-Users radio is disabled; choosing Private + Save calls `useSetAccess` with `access:'private'`. RenameModal submits `newName`. DeleteDialog for a folder shows the permanent-delete copy and calls `useDeleteFile`. NewFolder calls `useMkdir`.
- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement** with `ui/modal` + `ui/radio`/`ui/input`/`ui/button`; wire a "New Folder" button into the tab header.
- [ ] **Step 4: Run → PASS** + build clean.
- [ ] **Step 5: Commit** — `feat(owner-console): file manager modals (accessibility, rename, delete, new folder)`.

---

### Task 8: Multi-file upload progress panel

**Files:**
- Create: `web/src/tabs/files/upload-panel.tsx`
- Modify: `web/src/tabs/files.tsx`
- Test: `web/src/tabs/files.test.tsx` (extend)

**Interfaces — Produces:** a floating panel (bottom-right, Figma) listing each in-flight upload with a progress bar + ✓/✕ + "Cancel all"; driven by an upload queue that POSTs each file to `/api/files?dept=&path=` (into the current folder), reports progress (XHR `upload.onprogress`), and invalidates `['files',dept,path]` as each completes. Drag-and-drop into the folder uses the same queue.

- [ ] **Step 1: Failing tests** — dropping two files shows two rows; a completed one shows ✓; "Cancel all" aborts in-flight; on success the list query is invalidated. (Mock the uploader.)
- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement** the queue (XHR for progress) + the panel; gate the drop zone on an active dept.
- [ ] **Step 4: Run → PASS** + build clean.
- [ ] **Step 5: Commit** — `feat(owner-console): multi-file upload progress panel`.

---

### Task 9: nufi-ingest — read access-state, enforce Public/Private

**Files:**
- Modify: `deploy/platform/adapters/nufi-ingest/nufi_ingest.py`
- Test: `deploy/platform/adapters/nufi-ingest/test_nufi_ingest.py` (create if absent)

**Interfaces — Produces:** per dept, load `<drives>/<dept>/.nufi-access.json`; compute each file's effective access (own → nearest ancestor folder → `public`, mirroring Task 2). **Public** → attach to the dept agent `file_ids` (current behavior). **Private** → embed but **do not attach to the agent**; if a grant exists, clear it (`PUT /api/permissions/file/:id` to owner-only). On a public→private change, detach from the agent; private→public, attach. The access map is part of the per-file diff so an accessibility-only change re-runs sharing without re-embedding.

- [ ] **Step 1: Failing tests** — with a fake chat API (inject the HTTP fn): a public file is attached to the agent; a private file is embedded but not attached; flipping public→private detaches it; flipping back attaches; effective access inherits from a folder entry; a dotfile (`.nufi-access.json`) is never embedded (already true — assert it).
- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement** — a `load_access(dept_dir)` + `effective_access(access, rel)`; thread access through `scan`/`upload`/`share`; store the last-seen access in `state.json` per file so transitions are detected.
- [ ] **Step 4: Run → PASS.**
- [ ] **Step 5: Commit** — `feat(nufi-ingest): enforce per-file/folder Public/Private accessibility`.

---

### Task 10: Image build, deploy + live verify

**Files:**
- Modify: (only if needed) `deploy/box/docker-compose.yml` (owner-console already mounts `/drives` RW; ingest already mounts `/drives` + has `JWT_SECRET`/app access — confirm no change needed)
- Test: live on the box

- [ ] **Step 1** — full suites green: `cd deploy/box/owner-console && bun test`; `cd web && bun run test && bun run build`; the ingest unittest; `deploy/box/tests/test_compose.py`.
- [ ] **Step 2** — build the owner-console image (`docker build --build-context templates=../lib/join-templates --build-context agent=../agent …`) + the ingest image; confirm clean.
- [ ] **Step 3** — deploy to the box (the Cycle-1 mechanism: load images, recreate `owner-console` + `nufi-ingest`); Playwright e2e: create a folder, upload into it, rename, set a file Private, set Public, delete a folder (cascade), navigate the breadcrumb — all green.
- [ ] **Step 4** — RAG check: set a file **Private** on the box and confirm a dept member no longer gets it in NuFi Chat; set **Public** and confirm they do. Capture evidence.
- [ ] **Step 5: Commit + (end of plan) open PR** — `feat(owner-console): file manager — build + deploy wiring`.

---

## Self-Review

**Spec coverage:** folders/breadcrumb/rename/delete/new-folder (T3,5,7) ✅; sort/filter/columns/context-menu (T6) ✅; upload panel (T8) ✅; Accessibility Public/Private UI (T7) + backend (T2,4) + enforcement (T9) ✅; DS additions (T1) ✅; deferred Specific-Users + Create-Agent are UI-disabled (T6,7) ✅; Move deferred (not built) ✅.

**Placeholder scan:** no TBDs; each task names exact files, signatures, and test cases.

**Type consistency:** `Access`/`AccessFile`/`effectiveAccess` (T2) consumed by files.ts (T3,4) and mirrored in ingest (T9); `FileRow` gains `access` (T3) consumed by the web hooks (T5) and table (T6); `useMkdir/useRename/useDeleteFile/useSetAccess` (T5) consumed by the modals (T7).

**Review Focus:** dotfile integrity (T3,4), inheritance (T2), transition enforcement (T9), cascade hygiene (T4), path traversal with folders (T3) — each pinned to a task's tests above.
