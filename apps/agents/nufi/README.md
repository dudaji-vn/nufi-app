# What NuFi owns in `apps/agents`

`apps/agents` is [paperclipai/paperclip](https://github.com/paperclipai/paperclip)
(MIT) vendored at release tag **`v2026.722.0`** via `git subtree`. Design and
rationale: `docs/2026-08-03-nufi-agent-app-design.md`.

**Everything outside the list below is upstream and must stay byte-identical**,
so `git subtree pull` keeps working. `.github/workflows/agents-fork-guard.yml`
fails the build if that is violated.

| Path | What it is |
|---|---|
| `nufi/` | This directory — configuration and notes. Never in upstream |
| `nufi/verify-adapters.mjs` | Asserts the gateway invariant. **Not** named `check-*.mjs`: upstream's `.gitignore:20` ignores that pattern, and the file silently never gets committed |
| `ui/src/nufi-brand.css` | Brand tokens. Doubled selectors so they win without editing upstream values |
| `ui/nufi-rebrand.ts` | Build-time product-name transform |
| `ui/nufi-rebrand.test.ts` | Its tests |
| `ui/public/favicon.*`, `apple-touch-icon.png`, `android-chrome-*.png`, `site.webmanifest` | NuFi marks |
| `ui/src/index.css` | **1 line** — imports `nufi-brand.css` |
| `ui/vite.config.ts` | **2 lines** — registers `nufiRebrand()` |

Two edited upstream lines in total. Everything else is additive.

---

## Routing every model call through the NuFi gateway

`nufi/adapters.json` is the adapter registry. Point the server at it:

```bash
PAPERCLIP_ADAPTERS_FILE=/path/to/apps/agents/nufi/adapters.json
```

Upstream ships these defaults (`packages/plugins/sandbox-providers/kubernetes/src/adapter-defaults.ts`):

| Adapter | Default egress |
|---|---|
| `claude_local`, `pi_local` | `api.anthropic.com` |
| `codex_local` | `api.openai.com` |
| `gemini_local` | `generativelanguage.googleapis.com` |
| `opencode_local` | `api.anthropic.com`, `api.openai.com`, `openrouter.ai` |
| `cursor_local` | `api.anthropic.com`, `api.openai.com` |

Each one reaches a vendor directly, which is the thing NuFi cannot allow: the
guardrails (G1–G4) live in the LiteLLM gateway, and `apps/chat` deleted its
application-layer copies on the strength of the gateway being the only road to a
model (`63ff9d6fb`). `nufi/adapters.json` replaces every entry so that:

- `defaultEnv` points the harness at `https://api.codechi.me`
- `allowFqdns` is **only** `api.codechi.me`

The registry has **replace semantics** — when supplied it is the complete
declared set, so an adapter absent from the file is unavailable rather than
silently falling back to a vendor default. That is why disabled entries are
still listed explicitly.

### Two adapters are off, on purpose

| Adapter | Why |
|---|---|
| `cursor_local` | `cursor-agent` authenticates against Cursor's own cloud. There is no base-URL override that redirects it, so it cannot be held behind the gateway |
| `gemini_local` | Gemini CLI speaks Google's generative-language API shape, not the OpenAI or Anthropic one. Routing it through LiteLLM is unverified — until it is measured, it does not ship |

Turning either on means proving the traffic lands on the gateway first, not
assuming it.

### `defaultEnv` is the advisory half

`buildAdapterEnv` layers the secret API key over `defaultEnv`, so a base URL set
here is what the harness reads. That is enough to *route* traffic, not enough to
*confine* it — a harness can read its own config file, and a user can paste a key.

`allowFqdns` is the enforcing half: on the Kubernetes sandbox provider it becomes
the agent pod's egress allow-list, which no employee record can talk its way out
of. **The prototype configures both; only a Kubernetes deployment enforces the
second.** Running the local/process sandbox gives routing, not containment.

### Verifying, rather than believing

The claim is falsifiable, so falsify it:

```bash
# Point an adapter at a vendor and confirm the run cannot reach it.
PAPERCLIP_ADAPTERS_FILE=nufi/adapters.json \
ANTHROPIC_BASE_URL=https://api.anthropic.com \
  <dispatch a run on the kubernetes sandbox>
```

A run that **succeeds** means the egress policy is not in force and the security
argument in the design doc §3 C2 is wrong for this deployment.

---

## Running it locally

```bash
cd apps/agents
pnpm install --frozen-lockfile --node-linker=isolated
```

**`--node-linker=isolated` is not optional if your pnpm is configured otherwise.**
`ui/vite.config.ts` aliases lexical to a hardcoded `./node_modules/lexical/dist/Lexical.mjs`,
which only exists under pnpm's default isolated layout. With `node-linker=hoisted`
the package lands at the workspace root instead and the build dies with:

```
[vite:load-fallback] Could not load .../ui/node_modules/lexical/dist/Lexical.mjs
  (imported by ../node_modules/@mdxeditor/editor/dist/index.js): ENOENT
```

The setting can come from a global file — on macOS `~/Library/Preferences/pnpm/rc`
— so `.npmrc` in the repo looking clean does not mean the layout is. Check with
`pnpm config get node-linker`. CI uses a clean runner and gets the default, so
this only ever bites locally.

### Install size

The install pulls `@openai/codex`, whose platform binaries are published as
version suffixes (`0.142.5-darwin-arm64`, `-linux-x64`, `-win32-x64`, …) rather
than as separate `os`/`cpu`-tagged packages. pnpm's `supportedArchitectures`
filters the latter, not the former, so every platform is fetched — roughly
550 MB, most of it unusable on any one machine. It lands in the shared pnpm
store, so it is paid once per machine rather than once per clone.

Nothing here fixes it: the dependency is upstream's and the packaging choice is
OpenAI's. Worth revisiting if install time becomes a problem — the honest fix is
upstream making the codex adapter an optional install, which is a pull request,
not a local patch.

## The rename covers both bundles

`nufi/rebrand.mjs` holds the rules. Two consumers apply them, and they must
never diverge:

| Bundle | Applied by | When |
|---|---|---|
| `ui/dist` | `ui/nufi-rebrand.ts`, a Vite plugin | every `vite build` |
| `server/dist` | `nufi/rebrand-server-dist.mjs` | **must be run after every `tsc`** |

The server step is not optional. Skip it and the two sides disagree: the client
looks for `"NUFI needs a disposition…"` while the server keeps writing
`"Paperclip needs a disposition…"`, and every comparison between them stops
matching with no error. `--check` exists to catch that:

```bash
pnpm --filter @paperclipai/server build
node nufi/rebrand-server-dist.mjs server/dist          # apply
node nufi/rebrand-server-dist.mjs --check server/dist  # assert, exit 1 if not
```

Measured on a clean build: 42 of 336 emitted files carried the upstream name;
after the pass, `--check` is green and all three of `server/dist/**/*.js`,
`server/dist/**/*.d.ts` and `ui/dist/assets/*.js` contain the identical
sentence. Declarations are included deliberately — tsc emits literal types for
exported string constants, and a `.d.ts` that disagrees with its own `.js` is
worse than none.

### The test suite cannot catch a rename regression

`ui/vitest.config.ts` is standalone: it does not extend `vite.config.ts`, so the
plugin never runs under vitest. Tests therefore execute against the **upstream**
strings while the shipped bundle carries the renamed ones.

That is not a bug to fix here — wiring the plugin into vitest would make every
upstream test assert NuFi copy, which is a much larger diff and exactly what
§7's thin-fork rule forbids. But it means the guarantee is one-sided: 955 of 956
`src/lib` tests pass and cannot say anything about the rename either way. (The
one failure, `attention.test.ts`, is a timezone-dependent date-bucketing test
and is unrelated — the plugin does not run there at all.)

One concrete residue, recorded rather than hidden:
`ui/src/lib/successful-run-handoff.ts:71` matches with a **regex literal**,
which the transform does not touch:

```
/^Paperclip exhausted the bounded successful-run handoff correction\b/i
```

Nothing currently emits that sentence — 0 occurrences in `server/src` and
`server/dist`; it appears only in the client's own test fixture. So it is inert
today. If upstream starts emitting it, this fork will silently fail to match,
because the server will say NUFI and the pattern still says Paperclip. Anyone
rebasing onto a tag that adds that message needs to update the pattern by hand.

## The rename was partial, and why it no longer is

`ui/nufi-rebrand.ts` rewrites the product name only in props the client
**renders** (`children`, `title`, `placeholder`, `label`, `hint`, …). It does not
rewrite every string, and the reason is a bug that version had.

`ui/src/lib/successful-run-handoff.ts` holds:

```ts
const SUCCESSFUL_RUN_HANDOFF_REQUIRED_NOTICE_BODY =
  "Paperclip needs a disposition before this issue can continue.";
…
return trimmed === SUCCESSFUL_RUN_HANDOFF_REQUIRED_NOTICE_BODY;
```

The value being compared is a comment body **the server wrote**, and the server
is not transformed — this is a Vite plugin, so it only reaches the browser
bundle. Renaming the constant makes that equality fail silently: the UI stops
recognising its own system notices and renders them as ordinary comments.
Nothing throws, nothing logs.

So `message`, `body`, `detail`, `error` and `name` are deliberately excluded —
measured against the built bundle, that is where server-authored notice bodies
live.

Measured on the current build:

| | Rewrite every string | Rendered props only |
|---|---|---|
| `Paperclip` left in bundle | 4 | **172** |
| `NUFI` in bundle | 257 | **89** |
| Handoff comparison | **broken** | intact |

The second column is worse branding and correct behaviour. A missed rename is
cosmetic; a broken equality is a production bug found by a user.

**The real fix is to rename on both sides** so client and server agree, at which
point the whole-string rewrite becomes safe again. That is a follow-up, not a
prototype step, and until it lands the app will show "Paperclip" in some error
and notice text.

## Theme coverage

The brand layer reaches anything styled through a shadcn token and nothing
styled with a literal Tailwind palette class. Measured in `ui/src`:

```bash
grep -rhoE "\b(bg|text|border)-(background|foreground|card|popover|primary|secondary|muted|accent|sidebar|border)\b" \
  . --include="*.tsx" | wc -l          # → 8642  token-driven, themed
grep -rhoE "\b(bg|text|border)-(zinc|neutral|gray|slate|stone)-[0-9]{2,3}\b" \
  . --include="*.ts*" | wc -l          # → 215   hardcoded, NOT themed
```

About 97.6% of styled surfaces follow the tokens. The remaining 215 — mostly
`bg-neutral-950`, `border-zinc-800`, `text-zinc-400` — stay upstream neutral
grey, which is why some secondary panels still read grey rather than NuFi navy.

Fixing them means editing upstream components, which the allowlist forbids and
`git subtree pull` would punish. The cheap approximation, if it ever matters, is
a Tailwind config mapping those palette scales onto the brand ramp. It is not
done here, and the design doc records the gap rather than hiding it.

## Known white-label debt

- `ui/public/paperclip-thinking.svg` — a 14×14 inline glyph in `BoardChat.tsx`.
  Renaming the file means editing an upstream component, so the filename stays;
  only its contents are ours to change.
- Server-side strings (`server/src/**`) are not covered. `ui/nufi-rebrand.ts` is
  a Vite transform, so it only reaches the browser bundle. API error text still
  says Paperclip.
- `apps/chat` has the same debt in the other direction: `client/public/assets/icon-192x192.png`
  is still LibreChat's feather, while `favicon-32x32.png` is the real NuFi mark.
  The icons here were generated from `nufi-logo.svg` rather than copied, for
  exactly that reason.

## The NuFi adapter

`nufi/adapter` is a first-party **external** adapter (`nufi_agent`). It lives
here rather than under `packages/adapters/` because that directory is vendored
upstream and the fork guard rejects additions to it — which is the point:
`docs/adapters/external-adapters.md` says external adapters need no upstream
source change at all.

Register it for development by writing `~/.paperclip/adapter-plugins.json`:

```json
[{
  "packageName": "@nufi/paperclip-adapter",
  "localPath": "<repo>/apps/agents/nufi/adapter",
  "type": "nufi_agent",
  "installedAt": "2026-08-04T08:00:00.000Z"
}]
```

Then `pnpm --dir nufi/adapter build` and restart the server. Confirmation looks
like:

```
Loaded external adapters from plugin store {"count":1,"adapters":["nufi_agent"]}
reconciled adapter availability … "enabled":[… ,"nufi_agent"]
```

### It owns the disposition, not just the answer

This is the requirement the spike produced. Paperclip does not treat "the agent
said something" as progress; it wants a disposition, and when three consecutive
runs failed to give it one it escalated to a recovery owner and then stopped
dispatching (`docs/2026-08-04-nufi-agents-spike-findings.md` §3).

So every run ends in exactly one of two states and never in neither:

| Outcome | Status set | Comment |
|---|---|---|
| A substantive answer | `in_review` | the answer |
| The model declines or returns nothing | `blocked` | the model's own words, so a human can judge |
| The run throws | `blocked` | the error |

The error path is not theoretical. Observed with a rate-limited key, three runs
in a row posted `The agent run failed: gateway 429: … Remaining: 0` and left the
issue readable instead of silently stalled.

### Config

The key is named, never stored: `apiKeyEnv` holds the **name** of an env var,
because adapter config is visible in the UI.

```json
{ "target": "gateway", "model": "gemini", "apiKeyEnv": "NUFI_MODEL_API_KEY" }
```

`target: "chat"` swaps the gateway for an `apps/chat` agent (`chatUrl`,
`chatAgentId`), which brings RAG and tools. The spike ran against the gateway
only, so that path is written but unproven.

Do not lower `maxTokens` (default 4096). The model spends its reasoning budget
before emitting text — a 20-token cap returned empty content with no error, and
`resolveDisposition` would then block the issue for entirely the wrong reason.
