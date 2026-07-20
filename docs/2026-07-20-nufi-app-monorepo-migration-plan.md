# nufi-app Monorepo Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Consolidate six NuFi repos into a new private monorepo `dudaji-vn/nufi-app` — ALL six via `git filter-repo` (history preserved), with the chat app (formerly the LibreChat fork) as a first-class own app in `apps/chat`. Upstream LibreChat sync is **intentionally dropped** (user decision 2026-07-20: current feature set is sufficient; future upstream changes will be hand-ported if ever needed).

**Architecture:** Layout `apps/{chat,console,admin-panel,docs}` + `deploy/{railway,platform}`. Each app stays self-contained (own lockfile, own build). Root `.github/workflows/` holds all active CI with per-directory path filters; every imported `.github/` dir (including chat's 27 upstream workflows) is deleted, with only the needed workflows ported to root.

**Tech Stack:** git filter-repo (installed: `/opt/homebrew/bin/git-filter-repo`), gh CLI, GitHub Actions, Bun, Docker.

**Spec:** `docs/2026-07-20-nufi-app-monorepo-design.md`

## Global Constraints

- New repo: `dudaji-vn/nufi-app`, **private**.
- **Never** run `git filter-repo` inside a live working copy — scratch clones only (`~/Workspace/DudajiVN/_migration-scratch`).
- GHCR image names unchanged: `ghcr.io/dudaji-vn/nufichat`, `ghcr.io/dudaji-vn/nufi-console`, `ghcr.io/dudaji-vn/nufichat-admin-panel`.
- Old repos are archived only after their replacement path is verified; the chat repo `dudaji-vn/nufichat` is archived **last**, only after Task 8 (first monorepo release) passes.
- Import sources: console=`develop`, admin-panel=`main`, docs=`main`, nufi-chat=`main`, npuops-platform=`develop`, nufichat=`develop` (after Task 0 reconcile).
- No upstream relationship survives this migration — chat is an owned app exactly like admin-panel (itself an ex-fork of ClickHouse/librechat-admin-panel). Do not add upstream remotes or sync tooling.
- Latest chat release tag is `nufi-v0.1.9` → first monorepo release is `nufi-v0.1.10`.

---

### Task 0: Close out in-flight work (gates the freeze)

**Files:** none in nufi-app; operates on `nufi-chat` and the fork.

**Interfaces:**
- Produces: all six source repos in a clean, importable state (no unmerged branches, no open PRs, fork `develop` ⊇ `fork/main`).

- [ ] **Step 1: Merge nufi-chat's in-flight branch to main**

```bash
cd /Users/sun/Workspace/DudajiVN/nufi-chat
git add .env.example docs/demo-script-security.md
git commit -m "feat: finish LiteLLM gateway sync env docs + security demo script"
git push origin feat/litellm-gateway-sync
git checkout main && git pull
git merge --no-ff feat/litellm-gateway-sync -m "merge: feat/litellm-gateway-sync"
git push origin main
```

Expected: merge commit on `origin/main`. Note: `docs/superpowers/` stays untracked here on purpose — spec + plan are copied into nufi-app in Task 4.

- [ ] **Step 2: Merge fork PR #14**

```bash
gh pr merge 14 --repo dudaji-vn/nufichat --merge
```

Expected: PR #14 (fix/litellm-rewrite-seam) merged into its base branch.

- [ ] **Step 3: Reconcile fork develop ⊇ fork/main**

```bash
cd /Users/sun/Workspace/DudajiVN/LibreChat
git fetch origin
git checkout develop && git pull
git merge origin/fork/main -m "merge: fork/main → develop (pre-monorepo reconcile)"
git push origin develop
git rev-list --left-right --count origin/develop...origin/fork/main
```

Expected: final count `N 0` (fork/main has zero unique commits). If the merge conflicts, resolve favoring develop's newer work and re-run the count.

---

### Task 1: Create nufi-app repo and local skeleton

**Files:**
- Create: `~/Workspace/DudajiVN/nufi-app/` (git repo, branch `main`, one empty commit)

**Interfaces:**
- Produces: empty GitHub repo `dudaji-vn/nufi-app` (private) + local clone with an initial commit for merges to land on.

- [ ] **Step 1: Create the GitHub repo**

```bash
gh repo create dudaji-vn/nufi-app --private --description "NuFi monorepo: chat, console, admin-panel, docs, deploy"
```

Expected: `https://github.com/dudaji-vn/nufi-app` created.

- [ ] **Step 2: Init local repo with an initial commit**

```bash
cd /Users/sun/Workspace/DudajiVN
git clone https://github.com/dudaji-vn/nufi-app.git
cd nufi-app
git checkout -b main 2>/dev/null || git checkout main
git commit --allow-empty -m "chore: repo init"
git push -u origin main
```

Expected: `main` exists on origin with one empty commit.

---

### Task 2: Import all six repos with filter-repo

**Files:**
- Create: `apps/chat/`, `apps/console/`, `apps/admin-panel/`, `apps/docs/`, `deploy/railway/`, `deploy/platform/` (full trees + history)

**Interfaces:**
- Consumes: Task 1's `nufi-app` clone; Task 0's reconciled chat `develop`.
- Produces: six subdirectories whose `git log --follow` reaches pre-merge history. Mapping (used by all later tasks): `nufichat→apps/chat`, `nufi-console→apps/console`, `nufichat-admin-panel→apps/admin-panel`, `nufi-docs→apps/docs`, `nufi-chat→deploy/railway`, `npuops-platform→deploy/platform`.

- [ ] **Step 1: Clone and rewrite each repo in a scratch dir**

```bash
mkdir -p /Users/sun/Workspace/DudajiVN/_migration-scratch
cd /Users/sun/Workspace/DudajiVN/_migration-scratch
pairs=(
  "nufichat|develop|apps/chat"
  "nufi-console|develop|apps/console"
  "nufichat-admin-panel|main|apps/admin-panel"
  "nufi-docs|main|apps/docs"
  "nufi-chat|main|deploy/railway"
  "npuops-platform|develop|deploy/platform"
)
for p in "${pairs[@]}"; do
  IFS='|' read -r repo branch subdir <<< "$p"
  git clone --branch "$branch" "https://github.com/dudaji-vn/$repo.git" "$repo"
  (cd "$repo" && git filter-repo --to-subdirectory-filter "$subdir")
done
```

Expected: six scratch clones, each with every path rewritten under its target subdir (`git -C nufichat ls-tree --name-only HEAD` → `apps`). The `nufichat` clone is ~207MB / 4413 commits — the clone and rewrite take a few minutes.

- [ ] **Step 2: Merge each rewritten history into nufi-app**

```bash
cd /Users/sun/Workspace/DudajiVN/nufi-app
pairs=(
  "nufichat|develop|apps/chat"
  "nufi-console|develop|apps/console"
  "nufichat-admin-panel|main|apps/admin-panel"
  "nufi-docs|main|apps/docs"
  "nufi-chat|main|deploy/railway"
  "npuops-platform|develop|deploy/platform"
)
for p in "${pairs[@]}"; do
  IFS='|' read -r repo branch subdir <<< "$p"
  git remote add "import-$repo" "/Users/sun/Workspace/DudajiVN/_migration-scratch/$repo"
  git fetch "import-$repo" "$branch"
  git merge --allow-unrelated-histories -m "chore: import $repo → $subdir (history preserved)" "import-$repo/$branch"
  git remote remove "import-$repo"
done
```

Expected: six merge commits, zero conflicts (disjoint subdirectories).

- [ ] **Step 3: Verify history survived**

```bash
git log --follow --oneline -- apps/console/package.json | tail -3
git log --oneline -- deploy/platform | head -3
git log --oneline -- apps/chat | head -3
```

Expected: console's earliest commits visible; npuops commits (e.g. `04d06e8`, `af14b87`) present; chat's recent commits (e.g. the nufi-v0.1.9 release merge `d4a3bb5` — note: filter-repo rewrites SHAs, match by message) present.

---

### Task 3: Push the imported history

**Files:** none (push only).

**Interfaces:**
- Consumes: Task 2's merged `main`.
- Produces: `origin/main` on GitHub containing all six trees — the base every later task builds on.

- [ ] **Step 1: Push**

```bash
cd /Users/sun/Workspace/DudajiVN/nufi-app
git push origin main
```

Expected: push succeeds (~250MB first push; may take minutes).

- [ ] **Step 2: Spot-check on GitHub**

```bash
gh api repos/dudaji-vn/nufi-app/contents --jq '.[].name'
```

Expected: `apps`, `deploy` listed (plus root files from the imports).

---

### Task 4: Root scaffolding, dedupe, and docs

**Files:**
- Create: `README.md`, `.gitignore`, `nufi.code-workspace`, `docs/2026-07-20-nufi-app-monorepo-design.md`, `docs/2026-07-20-nufi-app-monorepo-migration-plan.md`
- Modify: `deploy/platform/librechat/` → dissolved into `deploy/platform/librechat.yaml`
- Delete: `apps/chat/.github/`, `apps/console/.github/`, `apps/admin-panel/.github/`, `deploy/platform/.github/`

**Interfaces:**
- Produces: clean root the CI files in Task 5 land on. Every imported `.github/` dir is deleted — including `apps/chat/.github/` with its 27 inherited LibreChat workflows; the one workflow chat actually needs (`build-image.yml`, reproduced in Task 5 Step 6) is ported to root as `chat-release.yml`.

- [ ] **Step 1: Dissolve the duplicated librechat config dir**

```bash
cd /Users/sun/Workspace/DudajiVN/nufi-app
git mv deploy/platform/librechat/librechat.yaml deploy/platform/librechat.yaml
git rm deploy/platform/librechat/.dockerignore
```

Expected: `deploy/platform/librechat/` gone; the platform-environment config is now `deploy/platform/librechat.yaml` (Railway's stays at `deploy/railway/librechat.yaml`).

- [ ] **Step 2: Remove all imported workflow dirs (needed ones are ported to root in Task 5)**

```bash
git rm -r apps/chat/.github apps/console/.github apps/admin-panel/.github deploy/platform/.github
```

- [ ] **Step 3: Write root .gitignore**

Create `.gitignore`:

```gitignore
.DS_Store
.env
node_modules/
```

(Per-directory `.gitignore` files imported with each repo remain authoritative for their subdirectories. `*.code-workspace` is intentionally NOT ignored.)

- [ ] **Step 4: Write nufi.code-workspace**

Create `nufi.code-workspace`:

```json
{
  "folders": [
    { "name": "chat", "path": "apps/chat" },
    { "name": "console", "path": "apps/console" },
    { "name": "admin-panel", "path": "apps/admin-panel" },
    { "name": "docs", "path": "apps/docs" },
    { "name": "deploy", "path": "deploy" },
    { "name": "∙ root", "path": "." }
  ]
}
```

- [ ] **Step 5: Write the root README (system map)**

Create `README.md`:

```markdown
# NuFi

Single repo for the whole NuFi system. One clone = the whole picture.

| Directory | What it is | Deploys as |
|---|---|---|
| `apps/chat/` | The chat app (originally a LibreChat fork; fully ours since 2026-07 — no upstream sync) | `ghcr.io/dudaji-vn/nufichat` (tag `nufi-v*` on main) |
| `apps/console/` | End-user API-key/usage console (Bun + Vite + Hono) | `ghcr.io/dudaji-vn/nufi-console` |
| `apps/admin-panel/` | Admin panel (TanStack Start + Bun; originally an ex-fork of ClickHouse/librechat-admin-panel) | `ghcr.io/dudaji-vn/nufichat-admin-panel` |
| `apps/docs/` | Docs site (Fumadocs / Next.js) | — |
| `deploy/railway/` | Railway staging wrapper (pulls the nufichat image, bakes `librechat.yaml`) | Railway service |
| `deploy/platform/` | On-prem platform: LiteLLM, Langfuse, llm-guard, monitoring | docker-compose |

## Rules of the road

- **Releasing chat:** tag `nufi-vX.Y.Z` on `main` → CI builds the GHCR image.
- Active CI lives in `.github/workflows/` with per-directory path filters.
- Each app is self-contained: own lockfile, own build. There is no root
  package manager on purpose.
- `apps/chat` has **no upstream relationship** anymore — LibreChat changes
  are hand-ported if ever needed. Do not add upstream remotes.

History: consolidated 2026-07 from six repos (nufichat, nufi-console,
nufichat-admin-panel, nufi-docs, nufi-chat, npuops-platform) — full design
in `docs/2026-07-20-nufi-app-monorepo-design.md`.
```

- [ ] **Step 6: Copy in the spec and this plan**

```bash
mkdir -p docs
cp /Users/sun/Workspace/DudajiVN/nufi-chat/docs/superpowers/specs/2026-07-20-nufi-app-monorepo-design.md docs/
cp /Users/sun/Workspace/DudajiVN/nufi-chat/docs/superpowers/plans/2026-07-20-nufi-app-monorepo-migration.md docs/2026-07-20-nufi-app-monorepo-migration-plan.md
```

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "chore: root scaffolding — README map, workspace, dedupe librechat config, drop imported workflows"
git push origin main
```

---

### Task 5: Root CI workflows with path filters

**Files:**
- Create: `.github/workflows/console-ci.yml`, `.github/workflows/console-image.yml`, `.github/workflows/admin-panel-ci.yml`, `.github/workflows/admin-panel-image.yml`, `.github/workflows/platform-ci.yml`, `.github/workflows/chat-release.yml`

**Interfaces:**
- Consumes: source workflow contents (reproduced below — the old repos' `.github` dirs were deleted in Task 4).
- Produces: the six active workflows Task 7 verifies and Task 8 releases with. GitHub gotcha relied on: **`paths` filters are ignored for tag pushes**, so `nufi-v*` tags always build even with `paths: ['apps/chat/**']` present.

- [ ] **Step 1: console-ci.yml**

```yaml
name: console-ci

on:
  pull_request:
    paths: ['apps/console/**']
  push:
    branches: [main]
    paths: ['apps/console/**']

concurrency:
  group: console-ci-${{ github.ref_name }}
  cancel-in-progress: true

defaults:
  run:
    working-directory: apps/console

jobs:
  lint:
    name: Lint + typecheck
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: oven-sh/setup-bun@v2
        with:
          bun-version: 1.3.x
      - name: Install dependencies
        run: bun install --frozen-lockfile
      - name: Generate route tree (TanStack Router)
        run: bunx @tanstack/router-cli generate
      - name: Biome
        run: bun run lint
      - name: TypeScript
        run: bun run typecheck
```

- [ ] **Step 2: console-image.yml**

Same as the old `nufi-console/docker-publish.yml` with four changes: workflow name, triggers (main + paths), build context, Dockerfile path.

```yaml
name: console-image

on:
  push:
    branches: [main]
    paths: ['apps/console/**']
    tags: ['nufi-console-v*']
  workflow_dispatch:
    inputs:
      librechat_url:
        description: "Public chat URL to bake into the SPA (overrides repo variable LIBRECHAT_URL)"
        required: false
        default: ""
      litellm_url:
        description: "Public LiteLLM URL shown in API key code snippets (overrides repo variable LITELLM_URL)"
        required: false
        default: ""

permissions:
  contents: read
  packages: write

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository_owner }}/nufi-console

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
            type=match,pattern=nufi-console-(v.+),group=1
            type=raw,value=latest,enable=${{ startsWith(github.ref, 'refs/tags/nufi-console-v') }}
            type=sha,prefix=sha-,format=short
      - name: Resolve LIBRECHAT_URL build arg
        id: librechat
        run: |
          url="${{ github.event.inputs.librechat_url }}"
          url="${url:-${{ vars.LIBRECHAT_URL }}}"
          url="${url:-http://localhost:3080}"
          echo "url=$url" >> "$GITHUB_OUTPUT"
      - name: Resolve LITELLM_URL build arg
        id: litellm
        run: |
          url="${{ github.event.inputs.litellm_url }}"
          url="${url:-${{ vars.LITELLM_URL }}}"
          url="${url:-http://localhost:4000}"
          echo "url=$url" >> "$GITHUB_OUTPUT"
      - uses: docker/build-push-action@v6
        with:
          context: apps/console
          file: apps/console/Dockerfile
          platforms: linux/amd64
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          build-args: |
            LIBRECHAT_URL=${{ steps.librechat.outputs.url }}
            LITELLM_URL=${{ steps.litellm.outputs.url }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

- [ ] **Step 3: admin-panel-ci.yml**

```yaml
name: admin-panel-ci

on:
  pull_request:
    paths: ['apps/admin-panel/**']

concurrency:
  group: admin-panel-ci-${{ github.ref_name }}
  cancel-in-progress: true

defaults:
  run:
    working-directory: apps/admin-panel

jobs:
  lint:
    name: Lint
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: oven-sh/setup-bun@v2
      - name: Install dependencies
        run: bun install --frozen-lockfile
      - name: ESLint
        run: bunx eslint src/ --max-warnings 0
  typecheck:
    name: Type Check
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: oven-sh/setup-bun@v2
      - name: Install dependencies
        run: bun install --frozen-lockfile
      - name: TypeScript
        run: bunx tsc --noEmit
  test:
    name: Unit Tests
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: oven-sh/setup-bun@v2
      - name: Install dependencies
        run: bun install --frozen-lockfile
      - name: Vitest
        run: bun run test
        env:
          NODE_ENV: development
          SESSION_SECRET: ci-test-secret-do-not-use-in-production
```

- [ ] **Step 4: admin-panel-image.yml**

```yaml
name: admin-panel-image

on:
  push:
    branches: [main]
    paths: ['apps/admin-panel/**']
    tags: ['nufi-admin-v*']
  workflow_dispatch:

permissions:
  contents: read
  packages: write

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository_owner }}/nufichat-admin-panel

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
            type=raw,value=main,enable=${{ github.ref == 'refs/heads/main' }}
            type=match,pattern=nufi-admin-(v.+),group=1
            type=raw,value=latest,enable=${{ startsWith(github.ref, 'refs/tags/nufi-admin-v') }}
            type=sha,prefix=sha-,format=short
      - uses: docker/build-push-action@v6
        with:
          context: apps/admin-panel
          file: apps/admin-panel/Dockerfile
          platforms: linux/amd64
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

- [ ] **Step 5: platform-ci.yml**

```yaml
name: platform-ci

on:
  push:
    branches: [main]
    paths: ['deploy/platform/**']
  pull_request:
    paths: ['deploy/platform/**']

jobs:
  lint:
    name: Lint
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Lint YAML
        uses: ibiqlik/action-yamllint@v3
        with:
          file_or_dir: deploy/platform
          config_file: deploy/platform/.yamllint.yml
      - name: Lint Dockerfiles
        run: |
          for f in deploy/platform/litellm/Dockerfile; do
            [ -f "$f" ] || continue
            echo "==> hadolint $f"
            docker run --rm -i hadolint/hadolint:latest < "$f"
          done
      - name: Detect shell scripts
        id: scripts
        run: |
          if [ -n "$(find deploy/platform/scripts -maxdepth 2 -name '*.sh' -print -quit 2>/dev/null)" ]; then
            echo "found=true" >> "$GITHUB_OUTPUT"
          else
            echo "found=false" >> "$GITHUB_OUTPUT"
          fi
      - name: Lint shell scripts
        if: steps.scripts.outputs.found == 'true'
        uses: ludeeus/action-shellcheck@2.0.0
        with:
          scandir: ./deploy/platform/scripts
  compose:
    name: Validate docker-compose
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Seed .env from .env.example
        run: cp .env.example .env
        working-directory: deploy/platform
      - name: Validate compose syntax
        run: |
          if [ -s docker-compose.yml ]; then
            docker compose config --quiet
          else
            echo "docker-compose.yml is empty — skipping validation"
          fi
        working-directory: deploy/platform
  build:
    name: Build images
    runs-on: ubuntu-latest
    needs: [lint, compose]
    steps:
      - uses: actions/checkout@v4
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3
      - name: Build LiteLLM image
        if: hashFiles('deploy/platform/litellm/Dockerfile') != ''
        uses: docker/build-push-action@v5
        with:
          context: ./deploy/platform/litellm
          push: false
          load: true
          tags: npuops/litellm:ci
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

- [ ] **Step 6: chat-release.yml** (port of the old repo's `build-image.yml`)

```yaml
name: chat-release

on:
  push:
    branches: [main]
    paths: ['apps/chat/**']
    tags: ['nufi-v*']
  workflow_dispatch:

permissions:
  contents: read
  packages: write

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository_owner }}/nufichat

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
            type=raw,value=main,enable=${{ github.ref == 'refs/heads/main' }}
            type=match,pattern=nufi-(v.+),group=1
            type=raw,value=latest,enable=${{ startsWith(github.ref, 'refs/tags/nufi-v') }}
            type=sha,prefix=sha-,format=short
      - uses: docker/build-push-action@v6
        with:
          context: apps/chat
          file: apps/chat/Dockerfile
          platforms: linux/amd64
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

Note: `:main` image now builds on any main push touching `apps/chat/**` (previously: any push to `fork/main`). The Railway wrapper's default `BASE=ghcr.io/dudaji-vn/nufichat:main` keeps working.

- [ ] **Step 7: Commit and push**

```bash
cd /Users/sun/Workspace/DudajiVN/nufi-app
git add .github
git commit -m "ci: port all workflows to monorepo root with path filters"
git push origin main
```

Expected: push itself fires NO app workflows (commit touches only `.github/`) — confirm with `gh run list --repo dudaji-vn/nufi-app --limit 5`.

---

### Task 6: Local build verification

**Files:** none (verification only).

**Interfaces:**
- Consumes: Task 2/3 trees.

- [ ] **Step 1: Build the three Bun apps**

```bash
cd /Users/sun/Workspace/DudajiVN/nufi-app
(cd apps/console && bun install --frozen-lockfile && bunx @tanstack/router-cli generate && bun run build)
(cd apps/admin-panel && bun install --frozen-lockfile && bun run build)
(cd apps/docs && bun install --frozen-lockfile && bun run build)
```

Expected: three successful builds. Known docs gotchas (from prior sessions): missing `/screenshots/*.png` fails the Fumadocs build — the imported tree already contains them; if the build fails on screenshots, run `bun run screenshots` first.

- [ ] **Step 2: Validate both compose stacks**

```bash
(cd deploy/railway && cp -n .env.example .env; docker compose config --quiet && echo railway-OK)
(cd deploy/platform && cp -n .env.example .env; docker compose config --quiet && echo platform-OK)
rm -f deploy/railway/.env deploy/platform/.env
```

Expected: `railway-OK` and `platform-OK`. (Chat's own build is intentionally not run locally — Task 8's GHCR build is its verification.)

---

### Task 7: CI touch-tests (path filters fire correctly)

**Files:**
- Modify: one marker line appended to `apps/console/README.md`, `deploy/platform/README.md`, `apps/chat/README.md`

**Interfaces:**
- Consumes: Task 5 workflows.

- [ ] **Step 1: Touch console only → expect console workflows only**

```bash
cd /Users/sun/Workspace/DudajiVN/nufi-app
echo "" >> apps/console/README.md
git add -A && git commit -m "test: ci touch console" && git push origin main
sleep 20 && gh run list --repo dudaji-vn/nufi-app --limit 5 --json name,headBranch,status --jq '.[].name'
```

Expected: `console-ci` and `console-image` listed; NOT `chat-release`, NOT `platform-ci`.

- [ ] **Step 2: Touch platform only → expect platform-ci only**

```bash
echo "" >> deploy/platform/README.md
git add -A && git commit -m "test: ci touch platform" && git push origin main
sleep 20 && gh run list --repo dudaji-vn/nufi-app --limit 3 --json name --jq '.[].name'
```

Expected: `platform-ci` only.

- [ ] **Step 3: Touch chat only → expect chat-release (builds :main image)**

```bash
echo "" >> apps/chat/README.md
git add -A && git commit -m "test: ci touch chat" && git push origin main
sleep 20 && gh run list --repo dudaji-vn/nufi-app --limit 3 --json name --jq '.[].name'
gh run watch --repo dudaji-vn/nufi-app --exit-status
```

Expected: `chat-release` fires and completes green (pushes `ghcr.io/dudaji-vn/nufichat:main`).

---

### Task 8: First release from the monorepo

**Files:** none (tag + CI).

**Interfaces:**
- Consumes: `chat-release.yml` (Task 5).
- Produces: `ghcr.io/dudaji-vn/nufichat:v0.1.10` — the proof the release pipeline moved. Railway (Task 9) can pin it. This green run is the gate for archiving `dudaji-vn/nufichat` in Task 10.

- [ ] **Step 1: Tag and push**

```bash
cd /Users/sun/Workspace/DudajiVN/nufi-app
git tag nufi-v0.1.10
git push origin nufi-v0.1.10
gh run watch --repo dudaji-vn/nufi-app --exit-status
```

Expected: `chat-release` runs green (paths filter is ignored for tag pushes — that is documented GitHub behavior, verified here).

- [ ] **Step 2: Verify the image exists**

```bash
docker manifest inspect ghcr.io/dudaji-vn/nufichat:v0.1.10 > /dev/null && echo IMAGE-OK
```

Expected: `IMAGE-OK`.

---

### Task 9: Railway cutover (manual dashboard step + verification)

**Files:** none (Railway settings).

**Interfaces:**
- Consumes: verified `deploy/railway/` tree + the Task 8 image.

- [ ] **Step 1: Repoint the Railway service** (dashboard, done by a human)

In the Railway service that currently deploys from `dudaji-vn/nufi-chat`:
- Source repo: `dudaji-vn/nufi-app`, branch `main`
- Root Directory: `deploy/railway`
- Watch Paths: `deploy/railway/**`
- Keep the existing `BASE` service variable (bump to `ghcr.io/dudaji-vn/nufichat:v0.1.10` if desired).

- [ ] **Step 2: Trigger and verify a deploy**

Trigger a redeploy in the dashboard; verify the staging site (chat.nufi.me staging) loads and logs in. Rollback if broken: repoint the service back to `dudaji-vn/nufi-chat` (untouched until Task 10).

---

### Task 10: Archive old repos, clean up locally, update tooling

**Files:**
- Modify: `README.md` of each of the six old repos (banner line)
- Modify: the `/nufi-release` skill definition (locate via `ls ~/.claude/skills/`, `ls ~/.claude/plugins/`, or `grep -r "nufi-release" ~/.claude --include=SKILL.md -l`)

**Interfaces:**
- Consumes: green results from Tasks 7–9. **Do not start until all three passed.**

- [ ] **Step 1: Banner + archive the five satellites**

```bash
for pair in "nufi-console|apps/console" "nufichat-admin-panel|apps/admin-panel" \
            "nufi-docs|apps/docs" "nufi-chat|deploy/railway" "npuops-platform|deploy/platform"; do
  IFS='|' read -r repo subdir <<< "$pair"
  d="/Users/sun/Workspace/DudajiVN/$repo"
  git -C "$d" checkout "$(git -C "$d" symbolic-ref --short refs/remotes/origin/HEAD | sed 's|origin/||')" && git -C "$d" pull
  printf '> **MOVED:** this repo now lives in [dudaji-vn/nufi-app](https://github.com/dudaji-vn/nufi-app) under `%s/`.\n\n%s' "$subdir" "$(cat "$d/README.md" 2>/dev/null)" > "$d/README.md"
  git -C "$d" add README.md && git -C "$d" commit -m "docs: repo moved to dudaji-vn/nufi-app" && git -C "$d" push
  gh repo archive "dudaji-vn/$repo" --yes
done
```

Expected: five repos show "archived" on GitHub.

- [ ] **Step 2: Banner + archive the old chat repo (ONLY after Task 8 ran green)**

```bash
d=/Users/sun/Workspace/DudajiVN/LibreChat
git -C "$d" checkout develop && git -C "$d" pull
printf '> **MOVED:** development continues in [dudaji-vn/nufi-app](https://github.com/dudaji-vn/nufi-app) under `apps/chat/`. This repo is frozen; no upstream sync is maintained anymore.\n\n%s' "$(cat "$d/README.md")" > "$d/README.md"
git -C "$d" add README.md && git -C "$d" commit -m "docs: repo moved to dudaji-vn/nufi-app (apps/chat)" && git -C "$d" push
gh repo archive dudaji-vn/nufichat --yes
```

- [ ] **Step 3: Local workspace cleanup (non-destructive)**

```bash
cd /Users/sun/Workspace/DudajiVN
mkdir -p _archived-repos
mv nufi-console nufichat-admin-panel nufi-docs nufi-chat npuops-platform LibreChat _archived-repos/
rm -rf _migration-scratch
```

Expected: workspace contains `nufi-app` (open via `nufi-app/nufi.code-workspace`); old checkouts parked under `_archived-repos/` for reference, deletable later.

- [ ] **Step 4: Rewrite the /nufi-release skill for the monorepo flow**

Locate the skill file, replace its procedure with:

1. Preconditions: on `main` of `nufi-app`, clean tree, CI green.
2. Determine next version: `git tag -l 'nufi-v*' --sort=-v:refname | head -1` → bump patch (or take an explicit version argument).
3. `git tag nufi-vX.Y.Z && git push origin nufi-vX.Y.Z`.
4. `gh run watch --repo dudaji-vn/nufi-app --exit-status` — verify `chat-release` publishes `ghcr.io/dudaji-vn/nufichat:vX.Y.Z`.
5. (No develop → fork/main merge — that flow died with the old chat repo.)

- [ ] **Step 5: Final commit of any doc updates in nufi-app and push**

```bash
cd /Users/sun/Workspace/DudajiVN/nufi-app
git add -A && git diff --cached --quiet || git commit -m "docs: post-migration updates"
git push origin main
```

---

## Verification (end-to-end, mirrors spec §8)

- `git log --follow apps/console/package.json` reaches pre-merge history; `git log apps/chat/ | head` shows the chat repo's commits.
- All three touch-tests fired exactly the matching workflows (Task 7).
- `ghcr.io/dudaji-vn/nufichat:v0.1.10` exists (Task 8).
- Railway staging serves from `nufi-app` (Task 9).
- Six old repos archived with MOVED banners (Task 10).
