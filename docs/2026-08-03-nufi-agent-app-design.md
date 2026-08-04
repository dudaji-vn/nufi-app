# NuFi Agent App — Design

**Date:** 2026-08-03
**Status:** Phase 1 vendored and white-labelled (§9); Phase 0 not run, and it is
the go/no-go. Gateway routing is configured, **egress enforcement is not proven**
— see §9 and `apps/agents/nufi/README.md`.
**Owner:** minhnhat165
**Companion:** `docs/2026-07-27-llm-security-gateway-design.md` (the gateway every
model call must pass through), `docs/2026-07-29-nufi-security-integration.md`
(the detection engine inside it).

## 1. Context

The next product after the security gateway is an agent app. Paperclip
(`github.com/paperclipai/paperclip`) is the reference point.

Three different kinds of product get called that, and NuFi's position differs in
each.

| Category | What it is | NuFi today |
|---|---|---|
| **A. Chat with agents** | A conversation UI where an agent has tools, memory, files | **Shipped** — `apps/chat` |
| **B. Visual workflow builder** | Drag nodes onto a canvas, wire an LLM pipeline | Not built, not wanted |
| **C. Agent work management** | Durable tasks assigned to agents, org structure, budgets, approval gates | **Not built** — this is the gap |

Paperclip is category C, and it is the only project of any size in it. Dify,
Flowise, Langflow and n8n are category B. Suna, OpenHands and Letta are category
A.

**The two products do not overlap.** `apps/chat` agents are knowledge agents —
LLM plus tools, MCP and RAG over company documents, driven by a person typing.
Paperclip agents are coding agents — Claude Code, Codex and Gemini CLI sessions
running unattended in a sandbox against a git workspace. Different work,
different users, different surface. Building C inside A was considered and
rejected for that reason.

**Decision: fork Paperclip as `apps/agents`, restyle it to the NuFi design
system, and route its model traffic through the NuFi gateway.** §2–3 is the
survey that had to happen first; §4–7 is how the three pieces attach.

---

## 2. Candidate survey

Ten projects, measured 2026-08-03. Reproducible:

```bash
for r in langgenius/dify FlowiseAI/Flowise langflow-ai/langflow \
         activepieces/activepieces kortix-ai/suna n8n-io/n8n \
         OpenHands/OpenHands paperclipai/paperclip \
         danny-avila/LibreChat letta-ai/letta; do
  gh api "repos/$r" --jq '[.full_name,(.stargazers_count|tostring),
    (.license.spdx_id // "NOASSERTION"),(.language),(.pushed_at[0:10])] | @tsv'
done
```

| Project | Cat. | Stars | Licence (actual) | Stack | Last push |
|---|---|---|---|---|---|
| n8n | B | 199,100 | **Sustainable Use License v1.0** | TypeScript | 2026-08-03 |
| Langflow | B | 152,766 | MIT | Python | 2026-08-03 |
| Dify | B | 151,116 | **Apache-2.0, modified** | TypeScript | 2026-08-03 |
| OpenHands | A | 82,912 | MIT | TypeScript | 2026-08-03 |
| **Paperclip** | **C** | **75,457** | **MIT** | TypeScript | 2026-08-03 |
| Flowise | B | 55,108 | Apache-2.0 + commercial `enterprise/` | TypeScript | 2026-07-31 |
| LibreChat | A | 41,583 | MIT | TypeScript | 2026-08-03 |
| Letta | A | 24,062 | Apache-2.0 | Python | 2026-08-01 |
| Activepieces | B | 23,554 | MIT + separate `ee/` licence | TypeScript | 2026-08-02 |
| Suna (Kortix) | A | 20,062 | **Elastic License 2.0** | TypeScript | 2026-08-03 |

The licence column is not from the GitHub API. Five of the ten return
`NOASSERTION` there, meaning the `LICENSE` file is not recognised verbatim text —
which is exactly where the restrictions live. Each was read directly.

**One correction worth recording:** most comparison articles list Suna as Apache
2.0. Its `LICENSE` is Elastic License 2.0. Had that error propagated, it would
have taken the white-labeling requirement with it.

---

## 3. Three criteria, and what survives them

### C1 — The licence must permit white-labeling

NuFi already carries unpaid licence debt (MongoDB SSPL, MinIO AGPL, Redis 7.4).
We do not add more, and a product we cannot rebrand fails on day one.

| Project | Verbatim | Effect |
|---|---|---|
| **Dify** | *"you may not remove or modify the LOGO or copyright information in the Dify console or applications"*; *"you may not use the Dify source code to operate a multi-tenant environment"* | Restyling is a breach. Multi-tenant is a breach. **Out** |
| **Suna** | *"You may not alter, remove, or obscure any licensing, copyright, or other notices"*; no *"hosted or managed service"* | Same two breaches under ELv2. **Out** |
| **n8n** | *"You may use or modify the software only for your own internal business purposes or for non-commercial or personal use"* | Internal tooling only. Cannot ship to customers. **Out** |

These are backend properties, not UI properties — replacing the frontend does not
escape them. Flowise and Activepieces pass only if their separately-licensed
`enterprise/` and `packages/ee/` directories are deleted, not merely unused.

**Paperclip is MIT.** Fork, restyle, resell — all permitted.

### C2 — The model path must be forcible through the NuFi gateway

`nufi-security` lives in the LiteLLM gateway as G1–G4, not in any application.
`develop` deleted the application-layer guardrails on the strength of that
argument (`63ff9d6fb`, 2026-07-29 — 20 files removed under
`apps/chat/api/server/middleware/guardrails/`). A second product that reaches
models by another road undoes that.

Paperclip is deliberately unopinionated about where agents run — *"Agents run
wherever they run and phone home."* **As deployed by upstream, it has no
chokepoint.** As a fork we control, it can be given a stronger one than
`apps/chat` has. Two facts make that true:

1. **Adapters are a plugin system, not a hardcoded list.** Each is a separate npm
   package (`@paperclipai/adapter-claude-local`, `-codex-local`, `-cursor-local`,
   `-gemini-local`, `-grok-local`, `-opencode-local`, `-pi-local`,
   `-openclaw-gateway`, `hermes`). An external adapter is auto-loaded at startup
   and, per `docs/adapters/creating-an-adapter.md`, *"doesn't require modifying
   Paperclip's source"*. The server half is one `execute.ts` taking an
   `AdapterExecutionContext`, and it builds the agent's environment through
   `buildPaperclipEnv(agent)`.
2. **Agents already run in sandboxes.** `docker/agent-runtime/` publishes an
   image family (`agent-runtime-base` plus `-claude`, `-codex`, `-gemini`,
   `-opencode`, `-pi`), and `packages/plugins/sandbox-providers/` supports seven
   backends — `kubernetes`, `daytona`, `e2b`, `modal`, `cloudflare`, `novita`,
   `exe-dev`.

Enforcing at the sandbox network boundary rather than in adapter config is what
makes this hold: **an egress policy that permits only the gateway cannot be
broken by an employee record.** That is a harder guarantee than `apps/chat` has
today, where routing is an application-level convention.

This is a design commitment, not a free property. §5.2 specifies it and §10
makes proving it the exit condition of Phase 1.

### C3 — It must actually be category C

Paperclip is the only candidate that manages agent *work*. Everything else would
mean building the task model, org chart, budgets and approval gates ourselves —
the expensive half, and the half no other project supplies in usable form.

### Scorecard

| Project | C1 licence | C2 gateway | C3 category | Verdict |
|---|---|---|---|---|
| **Paperclip** | ✅ MIT | ✅ as a fork | ✅ | **Chosen** |
| Dify | ❌ | ✅ | ❌ | Out on licence |
| Suna | ❌ | ✅ | ❌ | Out on licence |
| n8n | ❌ | ✅ | ❌ | Out on licence |
| Flowise / Activepieces | ⚠️ | ✅ | ❌ | Wrong category |
| Langflow / OpenHands / Letta | ✅ | ✅ | ❌ | Wrong category |

---

## 4. Decision

Fork `paperclipai/paperclip` into `apps/agents`. Ship as
`ghcr.io/dudaji-vn/nufi-agents`, released by tag `nufi-agents-v*` on `main`,
matching the existing per-app release convention.

**The governing rule is that the fork stays thin.** `apps/chat` is a fork we
stopped syncing (`README.md`: *"Do not add upstream remotes"*), and that decision
has an ongoing price — upstream fixes are hand-ported or lost. Paperclip is 4,337
files and pushes daily. Inheriting that and freezing it would be a much larger
version of the same mistake.

The fork can stay syncable because all three pieces we need attach **outside**
the upstream source:

| Piece | Where it lives | Upstream files touched |
|---|---|---|
| NuFi agents as employees | External adapter npm package | **0** |
| Gateway enforcement | Sandbox egress policy, deployment config | **0** |
| NuFi look and copy | Theme layer — see §6 | **~11** |

Roughly eleven files out of 4,337. That is a diff we can rebase across upstream
releases indefinitely, which is the difference between owning a product and
inheriting one.

---

## 5. Integration

### 5.1 NuFi agents as an adapter

Paperclip's `http` adapter (`docs/adapters/http.md`) calls an external agent over
HTTP. `apps/chat` exposes an agent-run endpoint; a NuFi employee in Paperclip is
an agent defined in chat, invoked over HTTP, executing inside our own service —
which already routes to the gateway.

This is the cheapest possible integration and it should be built **first**,
before any fork work, as a spike. It proves the product model fits NuFi's users
while touching nothing.

The fuller version is a first-party external adapter package (`@nufi/adapter-nufi`)
following `docs/adapters/creating-an-adapter.md`: `src/index.ts` for metadata,
`src/server/execute.ts` for the run, `src/ui-parser.ts` for the transcript. Still
zero upstream edits — external adapters are auto-loaded at startup.

### 5.2 Gateway enforcement

Two layers, and the second is the one that matters:

**Environment (advisory).** The adapter sets provider base URLs through
`buildPaperclipEnv(agent)` so every runtime — `agent-runtime-claude`,
`-codex`, `-gemini` — points at LiteLLM rather than the vendor:

```
ANTHROPIC_BASE_URL=https://api.codechi.me
OPENAI_BASE_URL=https://api.codechi.me/v1
GEMINI_BASE_URL=https://api.codechi.me/v1
```

**Network (enforcing).** The sandbox gets an egress policy allowing only the
gateway host. Env vars alone are advisory — a harness can read its own config
file or a user can paste a key. A `NetworkPolicy` on the sandbox namespace cannot
be talked out of.

This is why `kubernetes` is the right sandbox provider for NuFi despite being the
heaviest of the seven. `daytona`, `e2b`, `modal`, `cloudflare` and `novita` are
hosted third parties: sending customer code and prompts to them is both an egress
NuFi does not control and a data-residency problem for on-prem buyers.
`exe-dev` runs unsandboxed on the host — unacceptable for agents executing
generated code.

**Verification is a measurement, not an assumption.** With the policy applied, a
run whose adapter env has been deliberately pointed at `api.openai.com` must
fail. If it succeeds, the chokepoint does not exist and everything in §3 C2 is
wrong.

### 5.3 Deployment

Paperclip is a Node server plus a React UI on **PostgreSQL**. `deploy/platform`
already runs `postgres:16-alpine`, so this adds a database user, not a service.

The platform is already at roughly twenty services. `apps/agents` adds the app
container plus a sandbox execution path. On Railway, staging can follow the
existing wrapper-image pattern; the kubernetes sandbox provider is an on-prem
concern and does not block a staging deploy that runs the `http` adapter only.

---

## 6. White-labeling

This is the main body of work and it is smaller than the file count suggests,
because Paperclip's UI is built on primitives designed to be themed.

**Stack** (`ui/components.json`, `ui/package.json`): shadcn/ui in the `new-york`
style with **`cssVariables: true`**, Tailwind v4, `radix-ui`, `lucide-react`,
`class-variance-authority`, React Router, TanStack Query.

`cssVariables: true` is the good news: the entire colour system is custom
properties in `ui/src/index.css`, so the palette is one file.

### Copy is not in the locale files

`i18next` and `react-i18next` are dependencies, which invites the assumption
that user-facing text is externalised. Measured, it is not:

```bash
cd apps/agents
wc -l ui/src/i18n/locales/en.json          # → 9 lines, 3 strings
grep -rhoI "Paperclip" ui/src | wc -l      # → 531
```

i18n is scaffolded but barely adopted. Of those 531 references, 12 are package
specifiers, 27 are identifiers or CSS custom properties, and **492 are inline
English copy** — error messages, tooltips, empty states.

Renaming them at the source would touch hundreds of files and make every
upstream copy edit a merge conflict, which contradicts §7. So the product name
is rewritten **at build time** instead (`ui/nufi-rebrand.ts`, a Vite transform):
the vendored source stays byte-identical, and the shipped bundle says NuFi.

The transform rewrites string literals only. `Paperclip` is also a lucide-react
icon rendered as `<Paperclip />` in at least ten places; a blind word
replacement renames the import and breaks the build. `ui/nufi-rebrand.test.ts`
pins that case and the `@paperclipai/*`, `paperclip-*`, `PAPERCLIP_*` and
`--paperclip-*` namespaces that must survive untouched.

### The surface

| What | Where | Kind |
|---|---|---|
| Colour tokens | `ui/src/nufi-brand.css` | New file; `ui/src/index.css` gains **1 line** to import it |
| Product name in ~490 strings | `ui/nufi-rebrand.ts` | New file; `ui/vite.config.ts` gains **2 lines** |
| Favicons and touch icons | `ui/public/favicon.{ico,svg}`, `favicon-{16,32}x{16,32}.png`, `apple-touch-icon.png`, `android-chrome-{192,512}.png` | 7 replaced |
| PWA identity | `ui/public/site.webmanifest` | Replaced |
| Gateway config | `nufi/adapters.json` | New directory |

**Two edited upstream lines**, plus replaced binary assets. Everything else is
additive, which is what keeps §7 viable.

Not touched, deliberately: upstream's status hues, agent-capsule gradients and
chart scales. `index.css` documents them as AA-tuned per status; re-tinting them
trades a measured contrast guarantee for a cosmetic one.

Still outstanding: `ui/public/paperclip-thinking.svg` (a 14×14 glyph referenced
by `BoardChat.tsx` — the filename must stay or the diff grows) and server-side
strings under `server/src/`, which a Vite transform cannot reach.

Two upstream mechanisms are worth reusing rather than reinventing.
`server/src/ui-branding.ts` already injects favicon and branding blocks into
`index.html` between marker comments (`PAPERCLIP_FAVICON_START` /
`PAPERCLIP_RUNTIME_BRANDING_START`) — a seam that exists for worktree previews
but takes NuFi branding without modification. And `packages/db/src/schema/company_logos.ts`
means per-company logos are already a product feature; that is customer branding,
distinct from ours.

### The discipline that keeps sync alive

The rule is not "restyle carefully". It is: **NuFi changes live only in the table
above.** Anything else goes upstream as a pull request, or into an external
adapter package.

The moment a colour is hardcoded in a component or a string is inlined, the
rebase cost starts compounding, and the fork drifts toward `apps/chat`'s
frozen state. This should be enforced in CI, not by review discipline — a check
that fails when the diff against the upstream tag touches a file outside the
allowlist.

`apps/chat` shows what the alternative costs: 752 residual `LibreChat` references
in source, and the upstream feather icon reappeared once already (`d032a454b`)
because a fix lived in a repo that had been archived. Assets regress silently
because nothing tests them.

---

## 7. Fork strategy

**Track upstream. Do not freeze.** This is the opposite of the `apps/chat`
decision, and the reason is the diff surface: eleven files against 4,337, all of
them leaves — a stylesheet, a locale file, images. None sit on a code path
upstream is likely to restructure.

| | `apps/chat` (LibreChat) | `apps/agents` (Paperclip) |
|---|---|---|
| Diff surface | Pervasive, 752 residual refs | ~11 files, all leaves |
| Upstream sync | Dropped | **Kept** |
| Remote | Forbidden | `upstream` remote, rebase on tags |

Rebase on upstream **release tags**, not `master`. The gap between the two is the
whole argument:

```bash
gh api --paginate "repos/paperclipai/paperclip/commits?since=2026-07-27T00:00:00Z" \
  --jq '.[].sha' | wc -l                                    # → 164 in 8 days
gh api "repos/paperclipai/paperclip/releases?per_page=5" \
  --jq '.[] | [.tag_name, .published_at[0:10]] | @tsv'
# v2026.722.0  2026-07-22
# v2026.720.0  2026-07-20
# v2026.707.0  2026-07-07
# v2026.626.0  2026-06-27
# v2026.618.0  2026-06-18
```

Roughly twenty commits a day, but CalVer releases every one to two weeks.
Tracking `master` means rebasing against a moving target daily; tracking tags
means a handful of rebases a quarter against something upstream has already
stabilised.

If sync ever becomes untenable, that is the signal the fork has stopped being
thin — the response is to move the offending change into an adapter package or
upstream it, not to give up on sync.

---

## 8. Documentation

`apps/docs` is Fumadocs. `content/docs/` holds eight sections — `overview`,
`getting-started`, `end-user`, `admin`, `developer`, `operations`, `deployment`,
`reference`. Agent work touches four:

| Tab | Page | Content |
|---|---|---|
| `end-user` | Goals and tasks | Create a goal, break it down, assign an agent, read a run |
| `end-user` | Approvals | What a review gate is, what approving commits you to |
| `admin` | Agent org chart | Roles, who can approve what, budgets |
| `developer` | Writing an adapter | How to connect an internal agent |
| `operations` | Sandbox and egress | The egress policy, how to verify it, what a blocked run looks like |
| `deployment` | Installing `apps/agents` | Postgres, sandbox provider, gateway URL |

Two constraints carry over from prior work. Missing `/screenshots/*.png` **fails
the docs build**, so screenshots land with the page or the page does not merge.
And the `nufi-docs` Railway service still points at the archived
`dudaji-vn/nufi-docs` repo — until it is repointed
(`docs/2026-08-03-deploy-develop-to-production.md` §2), **nothing written here
reaches production.**

---

## 9. Phases

| Phase | Ships | Done when | State |
|---|---|---|---|
| **0. Spike** | Upstream Paperclip, `http` adapter pointed at an `apps/chat` agent endpoint | A NuFi agent completes a Paperclip task — the go/no-go on product fit | **not run** |
| **1. Fork** | `apps/agents` vendored at `v2026.722.0`, `nufi/adapters.json`, allowlist CI | Fork builds; every enabled adapter is configured to reach only the gateway | **done** |
| **1b. Lock** | Kubernetes sandbox with the `allowFqdns` egress policy applied | A run whose base URL is deliberately set to `api.openai.com` **fails** | **not done — C2 is still a claim** |
| **2. White-label** | Brand tokens, build-time rebrand, NuFi marks | Nothing user-visible says Paperclip; a rebase onto the next tag lands clean | **done for the UI**; server strings outstanding |
| **3. NuFi adapter** | `@nufi/adapter-nufi` as an external package | NuFi agents are first-class employees with a transcript view | not started |
| **4. Docs and release** | The pages in §8, `nufi-agents-v0.1.0` | Installable from documentation alone | not started |

Phase 0 was skipped to get something inspectable in front of reviewers. That
inverts the intended order and the risk it was meant to retire — whether
Paperclip's goal/task/org model suits NuFi's users — is still open. It should be
run before Phase 3, not after.

Phase 1b is the one that must not slip. Configuration routes traffic; only the
sandbox egress policy confines it. A white-labelled product that can still reach
a vendor directly is worse than no product, because it looks protected.

Phase 0 costs days and can invalidate the whole plan cheaply — that is its
purpose. Phase 1 is the one that must not be deferred: a white-labeled product
that reaches models outside the gateway is worse than no product, because it
looks protected.

---

## 10. Risks

**The runtime harnesses are proprietary and separately licensed.** Claude Code,
Codex, Gemini CLI and Cursor each carry their own terms and their own
credentials. Paperclip's MIT licence says nothing about shipping them to
customers. **This is unresolved and it is a commercial question, not a technical
one** — it needs an answer before anything is sold, and it is the risk most
likely to require a decision from outside engineering.

**Agents get a git workspace.** The base image ships `git` and mounts
`/workspace`. An agent that writes code and opens pull requests has repository
access, which is a threat surface the LLM gateway does not cover at all. Egress
control answers "which model did it call", not "what did it commit". Scoping
those credentials is Phase 1 work that this document does not yet specify.

**Upstream velocity.** 164 commits in 8 days across a 4,337-file codebase — this
is a fast-moving project, not a settled one, and a breaking change to the adapter
interface would land on us without warning. §7 (track tags) and §6 (allowlist)
are the mitigations; they hold only as long as the allowlist does.

**Kubernetes as a prerequisite.** The enforcing chokepoint needs a sandbox with
network policy. On-prem customers who do not run kubernetes get either a weaker
guarantee or a heavier install. No good answer yet.

**Two products, one login, different agent models.** Chat agents are knowledge
agents; Paperclip employees are coding agents. Sharing SSO but not the agent
definition is coherent, but users will ask why an agent built in chat is not an
employee. Phase 3 narrows this; it does not close it.

**Paperclip's category is one project deep.** 75k stars and no serious
competitor. Either it is early, or the category is narrower than the star count
suggests. Phase 0 is how we find out at low cost.
