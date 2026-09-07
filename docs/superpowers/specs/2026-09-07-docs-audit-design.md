# NUFI docs: audit and rewrite, one lane at a time

**Status:** approved to build, 2026-09-07
**Site:** `apps/docs` → https://docs.app.nufi.me
**Follows:** PR #60 (one sidebar, Prev/Next across sections)

## The problem

Most of the manual was written in May and June 2026, when NUFI was five
repositories. The code has moved twice since: into one monorepo in July, and
into two agent products (NUFI Studio, NUFI Works) in August. The docs did not
move with it. Measured on 2026-09-07:

| Signal | Where |
|---|---|
| "clone `npuops-platform`" (archived repo) | 30 places in Develop, 4 in Deploy, 2 in Reference |
| `pnpm` (the stack is Bun) | 13 places in Deploy, 5 in Develop |
| "clone each repo as a sibling directory" | Develop index |
| `deploy/platform/README.md`, `deploy/railway/README.md`, `apps/console/README.md` still name the old repos | repo READMEs a developer reads first |
| 15 pages untouched since 2026-05-25 | admin, deployment, developer, overview, reference |

A developer following Develop today is told to clone a repository that no
longer exists. That is the concrete failure this work fixes.

## Goal

A reader in each lane can complete the lane's job by following the pages
literally, in order, without asking anyone.

| Lane | The reader's job |
|---|---|
| Develop | Run the whole platform on a laptop, then change one app and see the change |
| Deploy & operate | Stand up a production instance and keep it healthy |
| Overview + Reference | Understand what runs where; look up any port, variable, or term |
| Administer | Configure models, users, roles, budgets, and read the observability tools |
| Using the app | Do a task in the chat app, the console, Studio, or Works |
| Studio + Works | (recent, light pass) |

Out of scope: a Korean edition, a different docs framework, changes to product
code. Code problems found on the way are reported, not fixed (see Findings).

## Method

**Walk the path, then write what happened.** Each lane is verified by doing the
job the lane describes:

- Develop: start Docker Desktop, run `deploy/platform/scripts/bootstrap.sh`
  from the monorepo checkout with the local Ollama backend, then run the
  console and admin panel dev servers against that stack, then attempt Studio
  and Works the way their pages say. Every command that fails is a finding and
  a rewrite.
- Deploy: compare every page against `deploy/platform/docker-compose.yml`,
  `.env.example`, `deploy/railway/`, the CI workflows, and the live Railway
  services. Pages that cannot be exercised here (Cloudflare tunnel, SSO reverse
  proxy, infra sizing) are checked against source and say so.
- Overview + Reference: regenerate the port and variable tables from the compose
  and env files; check the architecture text against what actually runs
  (the security gateway page already had one such correction in August).
- Administer and Using the app: walk each page against the live surfaces with
  the shared test account and recapture the screenshots with
  `bun run screenshots`.

**Per page.** Extract every claim that can be wrong: command, path, URL, env
var, port, version, product name. Check each one by running it or reading the
source. Classify the page: correct, stale, wrong, or missing. Rewrite. Record
in the PR what was executed and what was only read.

**Product names.** NUFI app (the chat product), NUFI Console, NUFI Admin
Panel, NUFI Studio, NUFI Works, NUFI AI Gateway. Never "NuFi", never
"NUFI Chat" for the product (the chat is one feature of the app).

## Develop lane: new shape

The lane is currently organised by old repository. It becomes organised by
what a developer is trying to do. Proposed pages; names may shift once the
run-through shows where the real seams are.

| Page | Job |
|---|---|
| Develop (index) | The three ways to run NUFI: hosted, the local stack, one app against the hosted gateway. Prerequisites in one table. |
| Run the stack locally | `bootstrap.sh` from `deploy/platform`, what comes up, the URLs, the first message, the smoke test, day-to-day compose commands |
| Work on the chat app | `apps/chat`: dev server against the local stack, where NUFI's changes live, the no-upstream rule |
| Work on the console | `apps/console`: Bun dev server, the identity handoff from chat |
| Work on the admin panel | `apps/admin-panel`: Bun dev server against the chat API |
| Work on NUFI Studio and NUFI Works | The two vendored forks, the allowlist and the fork guards, how to run each |
| Add or change a model | `add-model.sh`, LiteLLM config, what the admin panel does instead |
| Release and deploy | Tags, images, which Railway service tracks what |
| Design notes | `rag-integration` (unchanged) |

Every old URL keeps resolving through `next.config.mjs` redirects.

## Delivery

One pull request per lane, in the order above. Each PR:

1. passes `docs-ci` (the build is the test: a missing screenshot or a bad
   code-fence language fails it);
2. passes `apps/docs/scripts/check-nav.mjs`, the nine navigation checks from
   PR #60, moved into the repo and run in `docs-ci` against `next start`;
3. carries before/after screenshots of the pages that changed shape;
4. lists what was executed to verify it, and what was only read.

Lane 1 also fixes the repository READMEs it touches (`deploy/platform`,
`deploy/railway`, `apps/console`) because those are the first thing a
developer reads, and they currently contradict the docs.

Research runs in parallel, read-only (one subagent per lane building the claim
inventory). Writing happens in one worktree per lane so lanes never touch the
same files at once.

## Findings report

Anything found that is wrong in the code or configuration, rather than in the
docs, goes to `docs/audits/2026-09-07-docs-audit-findings.md`: file and line,
what is wrong against which standard, the proposed fix, and a severity
(blocks a documented path / misleads / cosmetic). The report is committed with
the lane that found the item and summarised in that PR. Nothing in it is
fixed without a separate decision.

## Screenshots

`scripts/capture-screenshots.mjs` needs `NUFI_EMAIL` and `NUFI_PASSWORD` for
the shared test account; the password is never written to the repo. Lanes 4
and 5 cannot be completed until it is provided. Screenshots of a control that
does not exist on the live surface are removed together with the sentence
that pointed at them, not left as a broken image.

## Known risks

- `gh auth` on this machine has no `read:packages` scope; if the GHCR images
  are not already cached by Docker, lane 1 needs a token with that scope
  before `bootstrap.sh` can pull.
- The full compose stack (Postgres, Redis, ClickHouse, MinIO, Langfuse,
  LiteLLM, MongoDB, chat, console, Prometheus, Grafana, Alertmanager, two
  Presidio sidecars, the scanner) wants ~10 GB of disk and several GB of RAM.
  The machine has 45 GB free and 24 GB of RAM.
- Studio runs on Python/uv and Works on Bun with a Kubernetes-backed sandbox;
  "run it locally" may legitimately end at "run the container" for one of them.
  The page will say which, rather than promise a laptop setup that was not done.
