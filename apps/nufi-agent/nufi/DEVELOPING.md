# Local development — the delta from upstream

**Run [`nufi/init.sh`](./init.sh) to set up this project, not upstream's
`make init`.** `make init`'s last step, `uvx pre-commit install`, would
install a git hook into this monorepo's one shared `.git/hooks/` that can
break commits everywhere in it, not only here — see "`nufi/init.sh`, not
`make init`" below for the full trace and a verified before/after.
`nufi/init.sh` runs the same two dependency-install targets and stops
there.

This is otherwise **only** the delta from
[`../DEVELOPMENT.md`](../DEVELOPMENT.md). Read that first — it covers the
actual walkthrough (installing `uv`/`npm`, hot-reload, adding components,
VS Code debug configs, the Docusaurus docs server) — just substitute
`nufi/init.sh` wherever it says `make init`, for the reason above.
Repeating any more of it here means maintaining two copies that drift on
every `git subtree pull` — the same reasoning `nufi/README.md` gives for
keeping this fork's diff small. This file exists because a handful of
things about running Langflow in *this* monorepo genuinely differ from a
standalone `langflow-ai/langflow` checkout, verified by actually doing
them (see `task-6-report.md` for the full transcript).

## Skip "Set up Git Repository Fork"

Upstream's first section has you fork `langflow-ai/langflow` on GitHub and
clone it standalone. None of that applies — `apps/nufi-agent` is vendored
into this monorepo via `git subtree` (`nufi/upstream.json`). There is no
separate fork to push to; changes land as commits in this repo, on this
branch, following this repo's own PR flow. Resyncing against upstream is
`nufi/upstream.json`'s `resync` field, not a `git remote add upstream`.

## Run every command from `apps/nufi-agent/`, not the repo root

Every path in `Makefile` / `Makefile.frontend` and in
`src/frontend/vite.config.mts` is relative to `apps/nufi-agent/`. This repo
has no root `pyproject.toml` or root `package.json` (deliberately — see
`docs/2026-08-10-nufi-agent-langflow-fork.md` and the `agents-ci.yml`
`package_json_file` comment mirrored below), so running `uv sync` or `make
backend` from the monorepo root fails outright (no project file found)
rather than doing the wrong thing quietly. `cd apps/nufi-agent` first,
always.

One path assumption worth knowing about explicitly:
`src/frontend/vite.config.mts` loads `../../.env` relative to
`src/frontend/`, i.e. it expects a `.env` file at `apps/nufi-agent/.env` —
not at the monorepo root and not inside `src/frontend/`. `.env.example`
already lives at that same `apps/nufi-agent/` level, so copying it in place
(`cp .env.example .env` from `apps/nufi-agent/`) is correct; no path
translation needed.

## `uv` is not preinstalled here

This environment had no `uv` on `PATH` (`command -v uv` → not found).
Installed with `brew install uv` (got `0.12.3`). `make check_tools` (which
`make init` depends on) fails fast and by name if `uv` or `npm` is missing,
so this is easy to notice — just not automatic the way upstream's doc
implies for a machine that's already set up for other Langflow work.

Python version: `requires-python = ">=3.10,<3.15"` (root `pyproject.toml`,
`src/backend/base/pyproject.toml`, `src/lfx/pyproject.toml` — all three
agree). This machine's Homebrew-default `python3` is `3.14.4`, which
qualifies, so `uv sync` picked it up with no interpreter wrangling and no
`apps/nufi-agent/.python-version` pin exists to force a specific one. That
is closer to the edge of the supported range than it looks — the next
Python feature release (3.15) would put a plain `python3` outside
`requires-python` entirely, and `uv sync` would need `uv python install
3.12` (or similar) plus `uv sync --python 3.12` instead of just working.
Worth a `.python-version` pin if that becomes a recurring problem; not
added here since it wasn't needed to get this task done.

`uv sync --frozen --extra "postgresql"` (what `make install_backend` runs)
took **~7 minutes** and produced a **1.9 GB** `apps/nufi-agent/.venv/` on
this machine — already covered by the vendored `.gitignore` (`.venv`,
`venv/`, `langflow.db`, `.env` are all listed), confirmed with `git status`
showing no drift after the install. `uv run langflow --help` resolves and
lists the full CLI (`run`, `superuser`, `migrate-mcp`, `copy-db`,
`migration`, `api-key`, `lfx`) — the whole dependency graph imports
cleanly.

## `nufi/init.sh`, not `make init` — and why that's a hard requirement, not a preference

`make init` ends with `uvx pre-commit install`, which upstream's doc frames
as optional-but-recommended. In a standalone `langflow` checkout that's
fine. In this monorepo it is worse than merely unsafe — it plausibly
**breaks every commit in the entire monorepo**, not just ones touching
`apps/nufi-agent`. There is exactly one `.git/hooks/` directory shared by
every app here — `apps/chat`, `apps/agents`, `apps/console`, `apps/docs`,
`deploy/*`, all of it. `apps/nufi-agent/.pre-commit-config.yaml`'s local
hooks use `language: system` (`.pre-commit-config.yaml:18-19`,
`entry: uv run ruff check`) — pre-commit always runs a `language: system`
hook's `entry` **from the git root**, not from wherever the config file
lives. The git root here is the monorepo root, which has no `uv` project
at all: `uv run ruff check` invoked from there fails immediately, on
every commit, everywhere, until someone works out the cause is a stray
`.git/hooks/pre-commit` and deletes it by hand. (Several other hooks in
that same config also have no path restriction — `trailing-whitespace` at
all, `end-of-file-fixer`/`mixed-line-ending` by extension only, `files:
\.(py|js|ts)$` — which would additionally reformat files repo-wide even
before the `uv run` failure is diagnosed.)

**Use [`nufi/init.sh`](./init.sh) instead of `make init`.** It runs the
same `install_backend`/`install_frontend` targets and stops there — no
`uvx pre-commit install`, nothing written to `.git/hooks/`. Verified
directly, not just reasoned about:

```
$ ls -la "$(git rev-parse --git-path hooks)/pre-commit"
ls: .git/hooks/pre-commit: No such file or directory
$ ./apps/nufi-agent/nufi/init.sh
Installing backend dependencies (make install_backend)...
...
Installing frontend dependencies (make install_frontend)...
...
OK -- backend and frontend dependencies installed.
$ ls -la "$(git rev-parse --git-path hooks)/pre-commit"
ls: .git/hooks/pre-commit: No such file or directory
```

Fixing `.pre-commit-config.yaml` itself (scoping every `files:` pattern to
`^apps/nufi-agent/`, and giving the `language: system` hooks a `uv run
--project apps/nufi-agent ...`-shaped entry that works from the git root)
is a separate, real decision — it's an upstream-file edit outside the
current `nufi/` allowlist, so it needs a new allowlist entry and a stated
reason in `nufi/README.md`, per `check-fork-diff.sh`'s own failure
message, not a quick fix folded into this task. `nufi/init.sh` is the
barrier in the meantime: it makes the unsafe command avoidable by default
instead of merely documented as dangerous. Same underlying lesson
`nufi-agent-ci.yml`'s `package_json_file` comment (mirrored in this task's
CI job — see below) already states for a different tool: this repo's root
having no `package.json`/`pyproject.toml` is not a gap other tools handle
gracefully, it's a well-known-locally, non-obvious way to lose time.

## Port conflicts with `deploy/platform`

Checked against every host port `deploy/platform/docker-compose.yml` maps
(`3000`, `3001`, `3030`, `3080`, `4000`, `5433`, `5434`, `9090`, `9093`),
confirmed live on this machine (`deploy/platform` was actually running
during this investigation — `lsof -nP -iTCP -sTCP:LISTEN` showed Docker
Desktop bound to all of those).

- **Backend, `make backend` (port `7860`): no conflict.** Not one of
  `deploy/platform`'s mapped ports, and nothing else on this machine was
  listening on it.
- **Frontend, `make frontend` (Vite dev server, port `3000`): direct
  conflict.** `src/frontend/vite.config.mts` defaults to
  `PORT` from `src/frontend/src/customization/config-constants.ts`, which
  is `3000`. `deploy/platform/docker-compose.yml:157` maps `langfuse-web`
  to host `3000:3000` — the same file already documents this exact
  collision class for a different service, one line away from `grafana`'s
  mapping: `# Host port 3030 — host 3000 is taken by langfuse-web.` Live
  confirmation on this machine: `lsof -nP -i:3000` → `com.docke ... TCP
  *:3000 (LISTEN)` while the platform stack was up.

  **Sharper than the port number:** `Makefile.frontend`'s `run_frontend`
  target — what `make frontend` actually calls — runs
  `kill -9 \`lsof -t -i:3000\`` unconditionally, before starting Vite, with
  the port hardcoded. **Correction:** an earlier version of this doc
  claimed `make backend`'s equivalent kill is parameterized on `$(port)`,
  in contrast. That's wrong — checked again against the actual line:

  ```
  Makefile:290    @-kill -9 $$(lsof -t -i:7860) || true
  ```

  `make backend` hardcodes `7860` exactly the same way the frontend
  hardcodes `3000` — `make backend port=8080` does **not** scope the kill
  to `8080`; it still kills whatever holds `7860`. Both targets pre-kill a
  hardcoded port, full stop. The asymmetry that actually matters is
  elsewhere: 7860 does not collide with anything `deploy/platform` runs
  today, and 3000 does — so the backend's hardcoded kill is currently
  harmless and the frontend's isn't, not because one is safer code, only
  because of what happens to be listening on each port on this machine
  right now. Overriding Vite's own port with `VITE_PORT` (see below) does
  **not** change what `run_frontend` tries to kill first, and overriding
  `make backend port=`  does not change what `backend` tries to kill
  first either. On this machine, the process holding port 3000 is Docker
  Desktop's host-side port-forwarder for `langfuse-web`, not a stray Vite
  process — running `make frontend` (or `make run_frontend`) while
  `deploy/platform` is up would `kill -9` that forwarder and take
  `langfuse-web` off port 3000 on the host. **Not executed here** —
  reasoned from the literal recipe in `Makefile.frontend` plus the live
  `lsof` output above; deliberately not run against a service someone else
  might be relying on, to prove a point that's already provable by reading
  the Makefile.

  **What to do instead, in this monorepo:**
  - For a build (not a dev server — no port, nothing to kill): `cd
    apps/nufi-agent/src/frontend && npm run build`. This is exactly what
    `nufi/check-brand-css.sh` already does in CI and takes ~20-35s once
    `node_modules` exists.
  - For an actual hot-reload session, bypass the Makefile target and run
    Vite directly with an explicit free port: `cd
    apps/nufi-agent/src/frontend && VITE_PORT=<free port> npm start`.
    `vite.config.mts` reads `VITE_PORT` from the environment before
    falling back to `3000`, and running `npm start` (`vite`) directly never
    touches the `kill -9 -i:3000` line at all — that only lives in
    `Makefile.frontend`. Pick a port with a quick `lsof -i :<port>` check
    first rather than trusting a hardcoded example to still be free by the
    time you read this.

## Serving the app from one process: `langflow run`, not `make backend`

`make backend` (`Makefile:290-300`) runs
`uv run uvicorn --factory langflow.main:create_app --host 0.0.0.0 --port
$(port) ...`. `create_app()` builds the FastAPI app and its routes only —
it never calls `setup_static_files`. That call lives in `setup_app()`
(`src/backend/base/langflow/main.py:1024-1036`), a *different* function
that `create_app()` does not invoke and that nothing in `make backend`'s
recipe calls either. So `make backend` alone serves the API but not the
UI: hitting `http://localhost:7860/` 404s, and it's easy to read that as
the app being broken rather than as the backend/frontend split being
intentional (`AGENTS.md`'s own "Development Mode (Hot Reload)" section
documents `make backend` + `make frontend` as two terminals for exactly
this reason — the frontend is meant to come from Vite in dev, not from
the backend's static-file mount).

To serve the built frontend and the API from one process instead — e.g.
to smoke-test a production-shaped build, or to hand someone a single
`http://localhost:7860` URL — use the CLI directly, which calls
`setup_app()` (via `setup_app(backend_only=False)`'s default), not
`create_app()` alone:

```
.venv/bin/langflow run --host 127.0.0.1 --port 7860 --no-open-browser
```

`--no-open-browser` maps to the CLI's `open_browser` typer option
(`src/backend/base/langflow/__main__.py`) — a `bool | None` option, which
typer expands to the `--open-browser/--no-open-browser` pair automatically;
useful here since there's no browser to open in this environment. Verified
port `7860` was free on this machine while `deploy/platform` held `3000`
and `3080` (same port-conflict class "Port conflicts with `deploy/platform`"
above documents for `3000`) — one more reason this path, not `make
frontend`'s Vite dev server, is the lower-hazard way to look at a built
frontend here.

## The frontend build has to be copied into the backend package first

`langflow run` (previous section) still won't serve anything at `/` on
its own if the step above it never ran. `get_static_files_dir()`
(`main.py:1018-1021`) resolves to `langflow/frontend` **relative to
`main.py`'s own package** — i.e.
`src/backend/base/langflow/frontend`, a directory that does not exist
until something populates it. It is *not*
`src/frontend/build`, the directory `npm run build` actually writes to.
Nothing links the two automatically; the copy is a separate, required
step:

```
cp -r src/frontend/build/. src/backend/base/langflow/frontend
```

(This is exactly what `Makefile.frontend`'s `build_frontend` target does
at line 45, via `make build_frontend` / `make run_cli` — those targets
already chain this copy after `npm run build`. It only needs doing by
hand when building the frontend directly with `npm run build`, e.g. for
`nufi/check-brand-css.sh` or the workflow above.)

Skip this and `setup_app()`'s own directory-existence check
(`main.py:1030-1032`) raises `RuntimeError: Static files directory ...
does not exist` outright if `backend_only` is false — or, if the stale
copy from days ago is still sitting there, `/` silently serves an old
build instead of erroring, which is worse: it looks like the app is
running the current code when it isn't. Either way it's easy to lose
time here concluding "the app is broken" when the real cause is a missing
build-artifact copy, not a server or routing bug. The target directory
(`src/backend/base/langflow/frontend/`) is gitignored
(`apps/nufi-agent/.gitignore:267-268`), so this copy never shows up in
`git status` and never touches the fork diff — safe to run as often as
needed.

## CI: what `nufi-agent-ci.yml`'s `rebrand` job actually runs, and why not vitest

The task brief for this change said to run
`npx vitest run nufi/rebrand.test.ts`. That's wrong — checked against the
file itself: `nufi/rebrand.test.ts` imports `describe`/`expect`/`it` from
`bun:test`, not from `vitest`, and its own header comment explains why:
this package (like `apps/agents/nufi/adapter`) is standalone, and the
vendored frontend (`apps/nufi-agent/src/frontend/package.json`) is a
**Jest** workspace (`"test": "jest"`) — adding `vitest` there to make
`npx vitest` resolve would itself be an upstream-file edit needing a new
`check-fork-diff.sh` allowlist entry, for a test-runner preference nothing
else in this fork needs. The CI job runs `bun test rebrand.test.ts` from
`apps/nufi-agent/nufi/` instead — confirmed locally: `bun test
rebrand.test.ts` → 15 pass, 0 fail.

No `bun install` / `npm ci` step precedes it, on purpose: `rebrand.test.ts`
only imports `bun:test` (built in) and `./rebrand` — and `rebrand.ts`'s
only external import is `import type { Plugin } from "vite"`, a type-only
import that Bun's transpiler elides at parse time and never resolves at
runtime. Verified, not assumed: `apps/nufi-agent/nufi/` has no
`package.json` and no `node_modules` of its own, and the test still passes
run from a completely clean shell with nothing installed in that
directory. Installing the real frontend `node_modules` first (mirroring
`agents-ci.yml`'s `rebrand` job, which really does need
`pnpm install --filter @paperclipai/ui` for its equivalent test) would
contradict the "standalone" design `rebrand.test.ts`'s own header comment
documents, and would cost real CI minutes for nothing this job actually
needs.

The `package_json_file` lesson from `agents-ci.yml`'s `rebrand` job was
checked against `oven-sh/setup-bun@v2` specifically, not assumed to
transfer: `pnpm/action-setup` genuinely requires either an explicit
`version` or a discoverable `packageManager` field and errors
("No pnpm version is specified") without one — which is why that job
points `package_json_file` at `apps/agents/package.json` instead of
letting it search from the (nonexistent) monorepo root. `oven-sh/setup-bun`
has no equivalent requirement: both of its version inputs
(`bun-version`, `bun-version-file`) default to unset/`null` in the action's
own `action.yml`, and omitting both simply installs the latest release —
there is no root-`package.json` lookup to fail. The new job pins
`bun-version: 1.3.x` anyway, matching the version this was verified against
locally (`1.3.1`) and this repo's existing `console-ci.yml` convention, for
reproducibility — not because leaving it unpinned would hit the
`package_json_file` failure mode here.

## What was not run

`make backend` and `make frontend` (or the direct `VITE_PORT=... npm
start` alternative above) both start long-running dev servers — **not run
in this task**, per its own instructions. Everything short of that was:
`uv sync --frozen --extra "postgresql"` (backend deps installed, CLI
resolves), `npm run build` / `nufi/check-brand-css.sh` (frontend production
build succeeds), and `bun test rebrand.test.ts` (passes, and demonstrated
failing when `rebrand.ts` is deliberately broken). See `task-6-report.md`
for the full transcript, including the exact remaining commands a human
needs to run the backend and frontend hot-reload servers.
