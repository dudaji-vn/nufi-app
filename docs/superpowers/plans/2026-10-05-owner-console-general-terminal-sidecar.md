# General + Terminal + Exec Sidecar (Cycle 2 — Plan 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the General tab to the full Figma (whole-box Start/Restart/Stop, richer status cards, and a `nufi-box` command console) AND move the docker-socket exec out of the web-facing owner-console into a minimal privileged **sidecar**, so the web surface holds no root-equivalent access.

**Architecture:** A new tiny `owner-exec` container holds `/var/run/docker.sock` and owns the allowlist + argv-only + audit logic (moved from `owner-console/src/exec.ts`). It serves a local HTTP API over a **shared unix socket** (`owner-exec-sock` volume): `POST /control`, `POST /run` (streaming). `owner-console` becomes a thin client (its `exec.ts` calls the sidecar; `control.ts` is unchanged) and **drops the docker.sock mount + group_add**. The command console expands the allowlist to read-safe `nufi-box` subcommands (never a raw shell, never destructive commands).

**Tech Stack:** Bun + Hono (owner-console + the sidecar, Bun unix-socket serve/fetch), React 19 + Vite (web). No new deps.

**Spec:** `docs/superpowers/specs/2026-10-05-owner-console-deferred-design.md` (Plan 2 sections)

## Global Constraints

- No new dependencies. Kebab-case files, PascalCase exports; reuse `web/src/ui/` + `var(--…)` tokens, no raw hex.
- Backend tests in the owner-console + sidecar `tests/` (`bun:test`); web tests `vitest`.
- **The exec allowlist is argv-only (never a shell), exact-membership-checked before building argv, and audited to `/state/audit.log` BEFORE spawning.** Moving it to the sidecar must preserve all of this verbatim.
- **After this plan, `owner-console` must NOT mount `/var/run/docker.sock` and must NOT have `group_add` for the docker GID** — only `owner-exec` does. (Restores + strengthens the socket-free-web guarantee.)
- The command console accepts only an allowlisted `nufi-box` subcommand as the first token; **destructive subcommands (`down`, `restore`, `remove`, `uninstall`, `mesh down`, `coordinator down`) and any shell metacharacter are rejected.**
- PR bodies + commits in English; no AI-authorship tells in committed docs.

## Review Focus

- **No exec path bypasses the sidecar allowlist:** after the move, trace every way `owner-console` can run a host command — all must go through the sidecar, and the sidecar must re-validate (never trust the console's input) — Task 2/3 tests.
- **The sidecar socket is the only docker access:** compose must show `owner-console` with no docker.sock + no group_add, and `owner-exec` with both — Task 6 `test_compose`.
- **Terminal allowlist can't reach a destructive or shell command:** `down`, `restore`, `remove`, `; rm -rf`, `$(…)`, `&&`, a service name with metacharacters, `logs; cat /etc/shadow` — all rejected before spawn — Task 3 tests.
- **Whole-box Stop needs a confirm and can't be triggered accidentally** (it disconnects all users) — Task 5 test (the confirm dialog gates the mutation).
- **Richer-card probes fail gracefully** (Postgres connection count, chat version, model) — a probe that can't read returns a card without the extra detail, never crashes `/api/status` — Task 4 tests.

---

### Task 1: Extract the exec allowlist into a shared module

**Files:**
- Create: `deploy/box/owner-console/src/exec-core.ts` (the pure allowlist + argv + audit, no I/O binding)
- Modify: `deploy/box/owner-console/src/exec.ts`
- Test: `tests/exec-core.test.ts`

**Interfaces — Produces:** move the pure logic out of `exec.ts` into `exec-core.ts` so BOTH the sidecar and (for tests) the console use one allowlist: `SERVICES`, `ACTIONS`, `READ_CMDS` (unchanged for now), `BadRequest`, `buildControlArgv(action, service)`, `buildReadArgv(cmd)`, `auditLine(now, what, service?)`. No behavior change — this is a refactor so Task 2's sidecar imports the same validation.

- [ ] **Step 1: Failing test** — `exec-core.test.ts` re-asserts the existing allowlist behavior from `exec.ts` against the new module (invalid action/service/cmd → BadRequest; exact argv for a valid control + read; shell metachars in a service → BadRequest).
- [ ] **Step 2: Run → FAIL** (module missing).
- [ ] **Step 3: Implement** — move the pure functions to `exec-core.ts`; `exec.ts` re-exports from it + keeps its `Bun.spawn`/`appendFileSync` bindings. Keep `src/api/control.ts` working unchanged.
- [ ] **Step 4: Run → PASS** (full owner-console suite still green).
- [ ] **Step 5: Commit** — `refactor(owner-console): extract exec allowlist into exec-core`.

---

### Task 2: The `owner-exec` sidecar

**Files:**
- Create: `deploy/box/owner-exec/` — `src/server.ts`, `src/handler.ts`, `package.json`, `bun.lock`, `Dockerfile`, `entrypoint.sh`, `tests/handler.test.ts`
- Test: `deploy/box/owner-exec/tests/handler.test.ts`

**Interfaces — Produces:** a Bun server listening on a unix socket (`Bun.serve({ unix: process.env.EXEC_SOCK || '/sock/exec.sock', fetch })`) exposing:
- `POST /control` `{action, service}` → runs `docker compose -p nufi-box <action> <service>` via `Bun.spawn` (argv), audited; `{ok, audit}` or 400 (BadRequest) / 500.
- `POST /run` `{cmd}` → validates `cmd` against the allowlist, audits, streams stdout lines back (chunked response). 400 off-list.
It imports the allowlist from a copy of `exec-core` (the sidecar is its own image; vendor `exec-core.ts` into `owner-exec/src/` OR share via the build — simplest: copy the file in the Dockerfile build so the one source of truth is `owner-console/src/exec-core.ts`). The sidecar is the ONLY place `Bun.spawn('docker', …)` runs. Audit to `/state/audit.log` (a mounted state volume) before spawn.

- [ ] **Step 1: Failing test** — `handler.test.ts` tests the request handler (injecting a fake spawn): `POST /control {restart, caddy}` → spawns `docker compose -p nufi-box restart caddy`, audited; an off-list service/action → 400; `POST /run {status}` → streams; `POST /run {down}` or a metachar cmd → 400 before spawn; audit-write failure → no spawn.
- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement** the handler + server; the Dockerfile = `oven/bun:1.4.2-alpine` + `apk add docker-cli docker-cli-compose`, copies `owner-console/src/exec-core.ts` + the sidecar src, runs as root OR a user in the docker group (the sidecar is tiny + privileged by design). Audit before spawn.
- [ ] **Step 4: Run → PASS** (`cd deploy/box/owner-exec && bun test`).
- [ ] **Step 5: Commit** — `feat(owner-exec): privileged exec sidecar over a unix socket`.

---

### Task 3: owner-console → thin exec client + expanded `nufi-box` terminal allowlist

**Files:**
- Modify: `deploy/box/owner-console/src/exec.ts`, `src/exec-core.ts`
- Test: `tests/exec.test.ts`, `tests/exec-core.test.ts`

**Interfaces — Produces:**
- `exec.ts` no longer spawns docker; `controlService`/`runReadCommand` call the sidecar over the unix socket (`fetch('http://exec/control', { unix: EXEC_SOCK, … })` / `/run`, streaming the response). The `control.ts` route interface is unchanged (still `controlService` / `runReadCommand`).
- **Expand `READ_CMDS`** in `exec-core.ts` to the read-safe `nufi-box` subcommands: `status`, `logs`, `logs <service>`, `doctor`, `support`, `members`, `mesh status`, `coordinator status`, `works status`, `flows list`, `user list`, `ps`. Parsing is by exact first-token (and the fixed two-word forms) membership; anything else → BadRequest. **Explicitly reject** the destructive set (`down`, `restore`, `remove`, `uninstall`, `mesh down`, `coordinator down`) and any shell metacharacter. The sidecar builds the argv (`nufi-box <sub>` or `docker compose … ps`) from the validated command.

- [ ] **Step 1: Failing tests** — exec-core: each new read cmd → valid argv; `down`/`restore`/`remove`/`mesh down` → BadRequest; `logs; rm -rf` / `status && x` / `$(…)` → BadRequest; `logs badservice` → BadRequest. exec.ts: `controlService`/`runReadCommand` call the sidecar (inject a fake unix-fetch) with the right body and stream the result; a sidecar 400 → BadRequest, a 500 → error.
- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement** the thin client + the expanded allowlist (shared with the sidecar via exec-core).
- [ ] **Step 4: Run → PASS.**
- [ ] **Step 5: Commit** — `feat(owner-console): call the exec sidecar; expand the console to nufi-box read commands`.

---

### Task 4: General — richer status cards + whole-box control API

**Files:**
- Modify: `deploy/box/owner-console/src/health.ts`, `src/api/status.ts`, `src/api/control.ts`
- Test: `tests/health.test.ts`, `tests/control.test.ts`

**Interfaces — Produces:**
- Richer card data on `GET /api/status`: Database → a Postgres **connection count** (a lightweight read; e.g. the sidecar runs `docker compose exec -T postgres psql -tAc 'select count(*) from pg_stat_activity'`, or a TCP+simple query — keep it graceful-fail, returning the base card if it can't read); chat → a **version** (from `/api/config` or the image tag); AI model → the **model name + size** (from the existing litellm/ollama probe's payload). Each stays `{name, ok, ms, …, detail?}` so a failed detail-read never breaks the card.
- `POST /api/control` gains a **whole-box** action: `{action:'start'|'restart'|'stop', service:'__box__'}` (or a dedicated `{scope:'box'}`) → the sidecar runs `docker compose -p nufi-box <action>` across the box. Audited; confirm is a client-side gate (Task 5).

- [ ] **Step 1: Failing tests** — status returns the extra detail when the probe succeeds and the base card when it fails (inject a failing detail-fetch) with `/api/status` still 200; the whole-box control action is accepted and calls the sidecar with the box-wide argv; an unknown service still 400.
- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement** the probes (graceful) + the whole-box control path (through exec.ts → sidecar).
- [ ] **Step 4: Run → PASS.**
- [ ] **Step 5: Commit** — `feat(owner-console): richer status cards + whole-box service control`.

---

### Task 5: General tab UI — whole-box controls, richer cards, command console input

**Files:**
- Modify: `web/src/tabs/general.tsx`, `web/src/tabs/general/controls.tsx`, `web/src/tabs/general/service-card.tsx`, `web/src/tabs/general/console.tsx`, `web/src/api.ts`
- Test: `web/src/tabs/general.test.tsx`, `general-control.test.tsx`

**Interfaces — Produces:**
- A **Status pill** + whole-box **Start / Restart / Stop Service** buttons (the Figma top bar), each with a confirm dialog (Stop: "This will disconnect all users and stop all running processes"). Wired to the whole-box control action.
- The 4 cards show the richer detail from Task 4 (Caddy·port, Postgres·N connections, chat·version, model·size).
- The **System Console** gains a command **input** (`root@nufi-box:~# ___`, Enter to run) that POSTs to `/api/console` and streams output, in addition to the existing quick chips. Reject-on-server (a 400) shows the error inline.

- [ ] **Step 1: Failing tests** — the Stop button opens a confirm and only on confirm calls the whole-box control mutate; a card renders its detail (e.g. "12 connections"); typing a command + Enter calls `streamConsole` with that command; a server 400 ("invalid command") shows inline.
- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement** using `ui/` (Button/Modal/Badge) + tokens; reuse the existing `streamConsole`.
- [ ] **Step 4: Run → PASS** + `bun run build` clean.
- [ ] **Step 5: Commit** — `feat(owner-console): General whole-box controls, richer cards, command console`.

---

### Task 6: Compose, image, CI wiring

**Files:**
- Modify: `deploy/box/docker-compose.yml`, `deploy/box/owner-console/Dockerfile` (drop nothing — it stays), `.github/workflows/box-images.yml`
- Test: `deploy/box/tests/test_compose.py`

**Interfaces — Produces:**
- Add the `owner-exec` service (image `nufi-owner-exec`, profile `owner-console`, mounts `/var/run/docker.sock` + `group_add: ["${DOCKER_GID:-999}"]` + the shared `owner-exec-sock` volume + the `/state` volume for the audit log + a read-only mount of the box dir so `nufi-box` is runnable, as needed).
- **Remove** the `docker.sock` mount + `group_add` from the `owner-console` service; add it the `owner-exec-sock` volume (ro or rw as the client needs) + `EXEC_SOCK` env.
- Register `owner-exec-sock` in the top-level volumes; add `owner-exec` to `box-images.yml` build matrix (its context `deploy/box/owner-exec`).

- [ ] **Step 1** — `test_compose.py`: assert owner-console has NO docker.sock + NO group_add; owner-exec HAS both + the shared socket volume; `owner-exec-sock` declared; both share it.
- [ ] **Step 2: Run → FAIL** (assertions not yet true).
- [ ] **Step 3: Implement** the compose + CI changes.
- [ ] **Step 4: Run → PASS** (`python3 -m pytest tests/test_compose.py`).
- [ ] **Step 5: Commit** — `feat(box): wire the owner-exec sidecar; drop the socket from owner-console`.

---

### Task 7: Image build, deploy + live verify

- [ ] **Step 1** — full suites green: owner-console `bun test`, owner-exec `bun test`, web `vitest` + build, `test_compose.py`.
- [ ] **Step 2** — build the `nufi-owner-console` + `nufi-owner-exec` images; confirm the console image has no docker-cli need (the sidecar does).
- [ ] **Step 3** — deploy to the box (load images, add the owner-exec service + volume, recreate owner-console + owner-exec); verify: a service restart from the UI works THROUGH the sidecar; the command console runs `nufi-box status`/`members`; a destructive command (`down`) is rejected; the owner-console container has NO docker socket (`docker exec … ls /var/run/docker.sock` fails); the audit log records via the sidecar.
- [ ] **Step 4** — Playwright e2e: whole-box restart (confirm), a console command, the richer cards.
- [ ] **Step 5: Commit + open PR** — `feat(owner-console): General + terminal + exec sidecar — build + deploy`.

---

## Self-Review

**Spec coverage:** whole-box control + Status pill (T4,5) ✅; richer cards (T4,5) ✅; command console with the nufi-box allowlist (T3,5) ✅; exec sidecar isolating docker access (T1,2,3,6) ✅; socket-free web restored (T6) ✅. Switch/Drawer DS components — not required by these screens; skip unless a card/console needs one.

**Placeholder scan:** no TBDs; each task names files, signatures, and test cases. The exact Postgres-connection-count mechanism (psql-via-sidecar vs a probe) is the one open implementation choice — Task 4 picks the simplest graceful one and the review checks it fails gracefully.

**Type consistency:** `exec-core` (T1) is the single allowlist consumed by the sidecar (T2) and the console client (T3); `controlService`/`runReadCommand` keep their signatures so `control.ts` is untouched; the whole-box action threads T4→T5.

**Review Focus:** no-bypass-of-sidecar (T2,3), sidecar-is-only-docker-access (T6), terminal-can't-reach-destructive/shell (T3), whole-box-Stop-needs-confirm (T5), richer-probes-fail-gracefully (T4) — each pinned to a task.
