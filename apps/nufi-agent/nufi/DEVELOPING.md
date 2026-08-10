# Local development — the delta from upstream

This is **only** the delta from [`../DEVELOPMENT.md`](../DEVELOPMENT.md).
Read that first — it covers the actual walkthrough (installing `uv`/`npm`,
running `make init`, hot-reload, adding components, VS Code debug configs,
the Docusaurus docs server). Repeating any of it here means maintaining two
copies that drift on every `git subtree pull` — the same reasoning
`nufi/README.md` gives for keeping this fork's diff small. This file exists
because four things about running Langflow in *this* monorepo genuinely
differ from a standalone `langflow-ai/langflow` checkout, verified by
actually doing them (see `task-6-report.md` for the full transcript).

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

## Skip `make init`'s pre-commit step in this monorepo

`make init` ends with `uvx pre-commit install`, which upstream's doc frames
as optional-but-recommended. In a standalone `langflow` checkout that's
fine. In this monorepo it is not, because there is exactly one `.git/hooks/`
directory shared by every app — `apps/chat`, `apps/console`, `apps/docs`,
`deploy/*`, all of it. `apps/nufi-agent/.pre-commit-config.yaml` was written
for a repo where it *is* the root: several of its hooks have no path
restriction at all (`trailing-whitespace`), or restrict only by extension
with no directory prefix (`end-of-file-fixer`, `mixed-line-ending`: `files:
\.(py|js|ts)$`). Installed as-is, the hook fires on **every** commit
anywhere in this monorepo and inspects every staged `.py`/`.js`/`.ts` file
repo-wide, not just files under `apps/nufi-agent/`.

Not run here for that reason. Fixing it properly would mean prefixing every
`files:` pattern in `.pre-commit-config.yaml` with `^apps/nufi-agent/` —
which is itself an upstream-file edit outside the current `nufi/`
allowlist, so it's a real decision (new allowlist entry + a stated reason
in `nufi/README.md`, per `check-fork-diff.sh`'s own failure message), not
a quick fix. Flagged here so nobody loses time to a monorepo-wide lint
storm the way `nufi-agent-ci.yml`'s `package_json_file` comment (mirrored
in this task's CI job — see below) says someone already lost time to a
different flavor of the same "tool assumes it owns the repo root" problem.

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
  the port hardcoded rather than parameterized. Contrast `make backend`,
  whose equivalent kill is `kill -9 $(lsof -t -i:$(port))` — scoped to
  whatever `port=` you actually pass. Overriding Vite's own port with
  `VITE_PORT` (see below) does **not** change what `run_frontend` tries to
  kill first. On this machine, the process holding port 3000 is Docker
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
