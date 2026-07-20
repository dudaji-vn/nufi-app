# nufi-app Monorepo Consolidation — Design

**Date:** 2026-07-20
**Status:** Approved in discussion; pending spec review
**Owner:** minhnhat165

## 1. Context & Goals

The NuFi system is currently spread across six repositories under
`dudaji-vn`, which causes two concrete pains:

1. **Context switching** — a single feature change often requires PRs in
   2–3 repos.
2. **Onboarding / visibility** — newcomers cannot see the whole system in
   one place.

Decision: consolidate all six NuFi-owned repos into a single new private
monorepo **`dudaji-vn/nufi-app`**, all via `git filter-repo`. The chat app
(formerly a LibreChat fork) becomes a first-class owned app at
`apps/chat` — **upstream sync is intentionally dropped** (decision
2026-07-20: the current feature set is sufficient; future LibreChat
changes will be hand-ported if ever needed). This mirrors how
`nufichat-admin-panel` already works: an ex-fork (of
ClickHouse/librechat-admin-panel) treated fully as our own code.

## 2. Scope

### Merged into `nufi-app` (6 repos)

| Source repo | Role | Commits | Target |
|---|---|---|---|
| `nufichat` | The chat app (ex-fork of `danny-avila/LibreChat`, now fully ours) | 4413 (~207MB) | `apps/chat` |
| `nufi-console` | End-user API-key/usage console (Bun + Vite + Hono + oRPC) | 25 | `apps/console` |
| `nufichat-admin-panel` | Admin panel (TanStack Start + React 19 + Bun) | 49 | `apps/admin-panel` |
| `nufi-docs` | Docs site (Fumadocs / Next.js) | 14 | `apps/docs` |
| `nufi-chat` | Railway deployment wrapper (Dockerfile, compose, `librechat.yaml`) | 19 | `deploy/railway` |
| `npuops-platform` | On-prem platform infra (litellm, langfuse, llm-guard, monitoring) | 112 | `deploy/platform` |

All six use the same mechanism (`git filter-repo --to-subdirectory-filter`
then merge with `--allow-unrelated-histories`) — history and blame
preserved. filter-repo rewrites commit IDs, which permanently severs the
chat app's merge base with upstream LibreChat; that is an **accepted
consequence** of dropping upstream sync, not an oversight.

### Explicitly OUT of scope

- `librechat-admin-panel` (local clone of the ClickHouse upstream) — a
  reference clone, not ours.
- Unrelated products in the workspace (middo*, mingo, cat, nufi-security).

## 3. Target Layout

```
nufi-app/
├── apps/
│   ├── chat/             ← nufichat (api/, client/, packages/ — its .github/
│   │                        with 27 inherited workflows is deleted, see §5)
│   ├── console/          ← nufi-console (unchanged internally)
│   ├── admin-panel/      ← nufichat-admin-panel (unchanged internally)
│   └── docs/             ← nufi-docs (unchanged internally)
├── deploy/
│   ├── railway/          ← nufi-chat: Dockerfile, bootstrap.sh,
│   │                        docker-compose*.yml, librechat.yaml (staging)
│   └── platform/         ← npuops-platform: docker-compose.yml, litellm/,
│                            langfuse/, llm-guard/, monitoring/, scripts/, docs/
├── .github/workflows/    ← merged workflows with per-directory path filters
├── nufi.code-workspace   ← committed workspace file (just nufi-app now that
│                            chat/ is inside); note: npuops-platform previously
│                            gitignored *.code-workspace — reversed here
│                            intentionally so newcomers get it for free
└── README.md             ← system map: every component, where it deploys,
                            how it relates to the LibreChat fork
```

Design choices:

- **Future win (out of scope here):** `apps/admin-panel` currently
  installs a *published* `@librechat/data-schemas` and lags the chat
  app's version. With both in one repo it can later consume
  `apps/chat/packages/data-schemas` directly.
- **No unified package manager / workspace tooling.** The apps are
  polyglot (Bun, Next.js, Python callbacks). Each app keeps its own
  lockfile and builds independently. The monorepo is organizational, not
  build-coupled — near-zero migration risk.
- **`librechat.yaml` duplication**: `npuops-platform/librechat/` contains
  only config (no source). Both environment configs move to `deploy/` and
  sit side by side, clearly named per environment (Railway staging vs
  on-prem platform). `deploy/platform/librechat/` directory is dissolved;
  its `librechat.yaml` becomes the platform-environment config. Shared
  fragments may be factored out later — not part of this migration.

## 4. Migration Approach (Approved: Option A — preserve history)

One uniform procedure for all six repos: use
`git filter-repo --to-subdirectory-filter` on a fresh clone of each repo,
then merge each rewritten history into `nufi-app` with
`git merge --allow-unrelated-histories`. Result: `git log --follow` and
`git blame` work seamlessly, as if every file had always lived in its
subdirectory.

Steps per repo (worked in a scratch directory, never in the live working
copies):

1. `git clone --branch <import-branch> <repo> scratch/<repo>`.
2. `git filter-repo --to-subdirectory-filter <target-subdir>` inside the clone.
3. In `nufi-app`: add the clone as a remote, `git fetch`, then
   `git merge --allow-unrelated-histories <remote>/<import-branch>`.
4. Remove the temporary remote.

Chat-specific notes:

1. **Reconcile branches first** (in `nufichat`): `develop` and `fork/main`
   have diverged 3–3; merge `fork/main` → `develop` so `develop` is the
   single import source. Merge open PR #14 (litellm rewrite seam) or
   decide to re-create it against the monorepo.
2. **Branch-model change:** the old develop / fork/main split collapses
   into the monorepo flow — feature branches → `main`, release =
   tag `nufi-vX.Y.Z` on `main` after QA. The `/nufi-release` skill must be
   rewritten for this flow post-migration.
3. **No upstream tooling:** no upstream remote, no sync script, nothing to
   maintain — LibreChat changes are hand-ported if ever needed.

Then one cleanup commit: merged root `README.md`, `.gitignore`
consolidation, workflow moves + path filters, workspace file update.

Pre-migration checks (done 2026-07-20):

- ✅ No secrets ever committed in any of the 5 satellite repos (scanned
  tracked files and `--diff-filter=A` history for `.env`, `*.pem`,
  `*secret*`, `*credentials*`; only `.gitignore` + `slack-webhook.example`
  matched).
- ✅ No open PRs on any of the 5 satellite repos.
- ⚠️ `nufichat`: open PR #14 + develop/fork-main 3–3 divergence (see
  chat-specific notes above).
- ⚠️ `nufi-chat` has unmerged local work (`feat/litellm-gateway-sync`
  branch + uncommitted changes). This must be merged or consciously
  carried over before the `nufi-chat` import is frozen.

## 5. CI/CD & Deployment Changes

| Workflow (source) | In nufi-app | Change |
|---|---|---|
| `nufi-console/ci.yml`, `docker-publish.yml` | `.github/workflows/console-*.yml` | add `paths: [apps/console/**]`, set `working-directory` / build context to `apps/console` |
| `nufichat-admin-panel/ci.yml`, `docker-publish.yml` | `.github/workflows/admin-panel-*.yml` | add `paths: [apps/admin-panel/**]`, context `apps/admin-panel` |
| `npuops-platform/ci.yml` | `.github/workflows/platform-ci.yml` | add `paths: [deploy/platform/**]` |
| (nufi-docs has no CI) | — | unchanged |
| chat's GHCR release workflow (`build-image.yml`: `nufi-v*` tag → build `ghcr.io/dudaji-vn/nufichat`) | `.github/workflows/chat-release.yml` | ported to root with build context `apps/chat`; branch trigger `fork/main` → `main` + `paths: [apps/chat/**]` |
| chat's other ~26 workflows (upstream-inherited CI: a11y, locize, gitnexus, …) | **deleted** with `apps/chat/.github/` | same treatment as every imported `.github/` dir — the upstream CI noise dies here |

- **GHCR image names stay the same** (`ghcr.io/dudaji-vn/nufichat`,
  `ghcr.io/dudaji-vn/nufi-console`, `ghcr.io/dudaji-vn/nufichat-admin-panel`)
  — consumers, including `deploy/railway`'s wrapper Dockerfile, unaffected.
- **Railway**: repoint the staging service from `dudaji-vn/nufi-chat` to
  `dudaji-vn/nufi-app`, root directory `deploy/railway`, watch paths
  `deploy/railway/**`. The old repo stays live until the first successful
  deploy from nufi-app is verified.

## 6. Post-Migration Tasks

1. Verify each app builds from its new location (chat, console,
   admin-panel, docs) and platform compose config parses
   (`docker compose config`).
2. Verify CI runs green with path filters (touch one file per area).
3. Cut over Railway; verify staging deploy.
4. Cut one release from the monorepo (tag `nufi-vX.Y.Z` → GHCR image
   builds from `apps/chat/`) before freezing the old chat repo.
5. **Archive** the six source repos on GitHub (read-only) after adding a
   final README line: "Moved to `dudaji-vn/nufi-app` → `<subdir>`".
   The old chat repo (`dudaji-vn/nufichat`) is archived **last**, only
   after step 4 succeeds.
6. Update local workspace: `nufi.code-workspace` now lists only
   `nufi-app` (the `LibreChat/` folder is replaced by
   `nufi-app/apps/chat/`).
7. Rewrite the `/nufi-release` skill for the monorepo flow (tag on main,
   no develop/fork-main dance).
8. Move this spec into `nufi-app/docs/` as the founding design doc.

## 7. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| LibreChat security fixes / features no longer flow in | **Accepted trade-off** (decision 2026-07-20, same posture as admin-panel's ex-fork). Watch upstream advisories manually; hand-port anything critical |
| Monorepo history noisy / clone heavy (4413 chat commits, ~250MB+) | Accepted cost of the single-repo decision; per-directory `git log` stays clean; consider `git clone --filter=blob:none` for CI |
| Release pipeline gap (no GHCR build while porting workflow) | Port + test `chat-release.yml` and cut one release from nufi-app **before** archiving the old chat repo; it remains usable for emergency release until then |
| Railway cutover breaks staging | Old repo untouched until new deploy verified; rollback = repoint service back |
| CI path filters wrong → missed builds | Post-merge test: one touch-commit per area, confirm expected workflows fire |
| In-flight work lost (nufi-chat branch, fork PR #14) | Merge `feat/litellm-gateway-sync` and fork PR #14 (or port them) before freezing those repos |
| Team muscle memory pushes to old repos | Archive makes them read-only immediately after cutover |

## 8. Verification

- `git log --follow apps/console/package.json` shows pre-merge history;
  `git log apps/chat/` shows the chat app's history.
- `bun install && bun run build` (console, admin-panel, docs — Fumadocs:
  watch the known screenshot/MDX gotchas).
- `docker compose config` passes in `deploy/railway` and `deploy/platform`.
- One touch-commit per area triggers exactly the matching workflows.
- Tag `nufi-vX.Y.Z` on main builds `ghcr.io/dudaji-vn/nufichat` from
  `apps/chat/` — this green run gates archiving the old chat repo.
- Railway staging deploy from `nufi-app` serves chat.nufi.me staging as before.
