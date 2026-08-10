# What NuFi owns in `apps/nufi-agent`

`apps/nufi-agent` is [langflow-ai/langflow](https://github.com/langflow-ai/langflow)
(MIT) vendored at release tag **`v1.11.2`** via `git subtree`. Design and
rationale: `docs/2026-08-10-nufi-agent-langflow-fork.md`.

**Everything outside the list below is upstream and must stay byte-identical**,
so `git subtree pull` keeps working. `.github/workflows/nufi-agent-ci.yml`
fails the build if that is violated.

| Path | What it is | Why it earned a place |
|---|---|---|
| `nufi/` | This directory — configuration and notes. Never in upstream | The one place a fork can hold arbitrary files without ever conflicting with `git subtree pull` |
| `src/frontend/index.html` | The HTML shell | Carries `<title>Langflow</title>` and the `<link rel="icon">` / `<link rel="manifest">` tags — the one entry point where the product name and marks are wired in before any JS runs |
| `src/frontend/src/style/index.css` | The real CSS entry point — imported first in `index.tsx`, ahead of `App.css` and `applies.css` | Holds the Tailwind/shadcn `:root` CSS variable tokens (`--foreground`, `--background`, `--primary`, …). This is where brand colours get overridden, the same role `apps/agents/ui/src/index.css` plays for Paperclip. **Note:** the task brief named this file `src/frontend/src/index.css`; that path does not exist in `v1.11.2` — the file was moved to `src/frontend/src/style/index.css` at some point in Langflow's history. The allowlist below uses the real path so a future brand-token edit here doesn't turn CI red |
| `src/frontend/vite.config.mts` | The Vite build config | Where a NuFi rebrand plugin will be registered, mirroring `nufiRebrand()` in `apps/agents/ui/vite.config.ts` — a build-time product-name transform rather than 62 hand-edited files (see design doc §3) |
| `src/frontend/public/favicon.ico` | Browser-tab icon | Swapped for the NuFi mark |
| `src/frontend/public/manifest.json` | PWA manifest | Carries `"name": "Langflow"` / `"short_name": "Langflow"` strings that must read NuFi. (Its `icons` array points at `icons/32x32.png` etc., which are not present anywhere in this vendored tree — they're generated as part of upstream's desktop/Tauri packaging, not committed here. Nothing to allowlist for them yet) |
| `src/frontend/src/assets/LangflowLogo.svg` | Primary in-app wordmark | Imported in 15 files — app header, login, sign-up, delete-account, playground chat bot message, empty states. Kept under its upstream filename: renaming it means editing all 15 import sites, which is exactly how a thin fork stops being thin (`apps/agents/nufi/README.md` records the same lesson about `paperclip-thinking.svg`) |
| `src/frontend/src/assets/LangflowLogoColor.svg` | Colour wordmark variant | Imported once, in the playground/IO modal header |
| `src/frontend/src/assets/langflow_logo_white.svg` | Dark-background logo variant | Not imported anywhere in `v1.11.2` — grepped, zero hits. Reserved anyway: it's a real upstream asset most likely lit up by a theming pass, and the allowlist exists to let its *contents* change without a rename, not to certify it's wired up today |
| `src/frontend/src/assets/langflow_logo_black.svg` | Light-background logo variant | Same as above — currently unreferenced, kept under its upstream name for the same reason |
| `src/frontend/src/assets/logo_dark.png` | Dark-theme hero mark | Imported in `pages/MainPage/pages/empty-page.tsx` — the empty-project placeholder graphic |
| `src/frontend/src/assets/logo_light.png` | Light-theme hero mark | Same call site as `logo_dark.png`, the light-theme counterpart |
| `src/frontend/src/assets/langflow_assistant.svg` | The assistant panel's mascot icon | Imported in 5 non-test files: `canvasControlsComponent/CanvasControls.tsx` and four states of the assistant panel (`assistant-message.tsx`, `assistant-empty-state.tsx`, `assistant-disabled-state.tsx`, `assistant-no-models-state.tsx`). Rendered today, not reserved for later |
| `src/frontend/src/assets/langflow_assistant_idle.svg` | The assistant icon's idle/dimmed state | Imported in `canvasControlsComponent/CanvasControls.tsx:8` — the canvas toolbar, which is always visible while editing a flow |
| `src/frontend/src/assets/MCPLangflow.png` | MCP composer notice illustration | Imported in `mcp-server-notice.tsx:30`, rendered inline in the sidebar |
| `src/frontend/src/locales/ko.json` | Korean translation bundle | Doesn't exist upstream at all — Langflow ships `de`, `en`, `es`, `fr`, `ja`, `pt`, `zh-Hans`, not `ko`. `loadLanguage()` in `i18n.ts` dynamically imports `./locales/${lang}.json`, so the file has to physically sit here for Vite to bundle it. See "Korean locale (demo path)" below — this is a **provisional, machine-authored, unreviewed** partial translation, not the full 2,232-key set |
| `src/frontend/src/i18n.ts` | i18next setup | One line added to the hardcoded `SUPPORTED_LANGUAGES` array (`"ko"`) so `normalizeLanguage()` accepts the new locale instead of silently falling back to `en`. No other line touched |
| `src/frontend/src/constants/languages.ts` | Language-picker labels | One line added (`{ code: "ko", label: "한국어" }`) so the Settings → Language picker offers Korean. No other line touched |

Two edited upstream lines, both from Task 4: one in `i18n.ts`, one in
`constants/languages.ts`, each adding exactly one array entry. A Vite
transform that injected all three allowlisted paths without touching
upstream was considered and rejected — a transform that rewrites an array
silently stops working the moment upstream reformats that array, which is
the exact failure class this fork keeps fighting elsewhere (see the
rebrand-transform design note under "Brand tokens and marks"). Two edited
lines fail as a merge conflict on the next `git subtree pull` instead,
which is loud.

## Asset sweep: what's rendered vs. what's genuinely inert

The first draft of this file grouped five unlisted Langflow/DataStax-branded
assets together as "not our concern yet." That was wrong for three of them —
they render on screen today, not just in some future rebrand pass. An
unlisted asset nobody touches costs nothing; an unlisted asset a later task
must replace turns CI red on a path nobody's expecting, mid-branding-change.
So every file under `src/frontend/src/assets/` and `src/frontend/public/`
carrying Langflow or DataStax branding was checked for a non-test import site,
not just its filename:

| Asset | Rendered (non-test import)? | Allowlisted? | Notes |
|---|---|---|---|
| `LangflowLogo.svg` | Yes — 15 files | Yes | see table above |
| `LangflowLogoColor.svg` | Yes — 1 file | Yes | see table above |
| `langflow_logo_white.svg` | No — 0 files | Yes | reserved for a future theming pass |
| `langflow_logo_black.svg` | No — 0 files | Yes | reserved for a future theming pass |
| `logo_dark.png` | Yes — 1 file | Yes | see table above |
| `logo_light.png` | Yes — 1 file | Yes | see table above |
| `langflow_assistant.svg` | **Yes — 5 files** | **Yes** | added in this fix round |
| `langflow_assistant_idle.svg` | **Yes — 1 file** | **Yes** | added in this fix round |
| `MCPLangflow.png` | **Yes — 1 file** | **Yes** | added in this fix round |
| `DataStaxLogo.svg` | No — 0 files | **No, deliberately** | genuinely inert, *and* it's a third-party company's mark (DataStax), not NuFi's to rebrand even if it were wired in |
| `langflow-icon-smooth.svg` | No — 0 files | **No, deliberately** | genuinely inert |
| `langflow-icon-smooth.png` | No — 0 files | **No, deliberately** | genuinely inert |

`src/frontend/public/` has only `favicon.ico` and `manifest.json`, both
already allowlisted above — nothing else there carries Langflow branding.

12 assets swept, 9 rendered, 9 allowlisted, 3 genuinely inert and kept off the
list on purpose. If `DataStaxLogo.svg` or `langflow-icon-smooth.*` ever gain a
real import site, that changes the DataStax-ownership question, not just the
allowlist — treat it as a decision, not a reflex addition.

## Brand tokens and marks

`nufi/brand.css` is the CSS-variable override layer, imported by
`src/frontend/src/style/index.css` (the one line that file is allowed to
carry — see the allowlist table above). It follows the same doubled-selector
technique (`:root:root`, `.dark.dark`) as `apps/agents/ui/src/nufi-brand.css`,
raising specificity above upstream's single-class declarations so these
values win without editing an upstream rule. In practice the doubling is
belt-and-suspenders: `style/index.css` writes its tokens inside
`@layer base { ... }`, and `brand.css` deliberately does not use `@layer` at
all — unlayered rules always beat layered ones in the CSS cascade regardless
of specificity, so the override would win even at `:root` alone. The
doubling is kept for parity with the Paperclip file and as a second line of
defence if a future upstream refactor moves the layer boundaries.

**Import position matters.** `@import` must be the first statement in a
stylesheet (only `@charset`/`@layer` may precede it) — an earlier draft
placed the import after the three `@tailwind` directives and the production
build silently dropped it (no error; the browser/bundler's CSS parser just
discards an `@import` in an invalid position). Verified by building once
with the import in the wrong place (the compiled CSS had zero occurrences of
the override values) and once at the top of the file (the compiled CSS
carries `:root:root{--primary:236.2 42.7% 56.9% ...}` and
`.dark.dark{--background:240 33.3% 4.7% ...}` — see `npm run build` output
in the Task 3 report). The line in `style/index.css` is
`@import "../../../../nufi/brand.css";` on line 1.

**Theme mechanism.** `tailwind.config.mjs` sets `darkMode: ["class"]`, and
the app toggles a plain `.dark` class on `<body id="body">` (see
`src/App.tsx`, `document.getElementById("body")!.classList.add("dark")`) —
`index.html` even ships `<body id="body" class="dark">`, so dark is the
default. There is no `data-theme` attribute and no `prefers-color-scheme`
media query anywhere in `style/index.css` — `.dark.dark` is the only
mechanism that needs covering, and it's the only one `brand.css` targets.

**Value format — not hex.** Unlike Paperclip's `nufi-brand.css`, Langflow's
tokens are bare `H S% L%` triplets, consumed as `hsl(var(--primary))` in
`tailwind.config.mjs` (`theme.extend.colors`). A hex value in one of these
vars would make `hsl(var(--primary))` invalid at the point of use — CSS
custom properties don't fall back on a bad reference, the whole declaration
just drops. `brand.css` converts every Paperclip palette hex to its exact
HSL triplet (round-tripped hex → HSL → hex to confirm no drift) and documents
both forms in comments. Three tokens (`--ice`, `--selected`, `--hover`) are
consumed as bare `var(--x)` with no `hsl()` wrapper; none of them are
brand/accent surfaces, so none are touched.

**Tokens overridden:** `--primary`, `--primary-foreground`, `--primary-hover`,
`--ring` (light and dark), plus `--background`, `--card`, `--popover`,
`--secondary`, `--muted`, `--accent` (dark only — light-mode surfaces stay
upstream white, matching Paperclip's choice not to touch light-mode
surfaces either). `--primary-hover` has no counterpart in Paperclip's file
(shadcn/Paperclip doesn't define that token); Langflow does, and it's wired
to `primary.hover` in `tailwind.config.mjs`, so leaving it at upstream's
near-black/near-white default would flip a hovered primary button off-brand
the moment a mouse touched it. `apps/chat` defines
`--brand-primary-hover: #6970e0` as a single value shared across its light
and dark themes (not two shades), so it's applied unchanged in both modes.

**Left alone, deliberately:** `style/index.css` documents several of its
own tokens as measured for WCAG AA (`--muted-foreground`,
`--placeholder-foreground` both carry "darkened/lightened for WCAG" comments
in the source), the same pattern Paperclip's file calls out for its status
hues. Applying that same caution broadly, `brand.css` does not touch:
`--status-*`, the `--datatype-*` type-badge scale (14 pairs), `--warning`/
`--error`/`--success`/`--info` and their `-background`/`-foreground`
partners, `--accent-emerald`/`-indigo`/`-blue`/`-pink`/`-purple` and their
`-foreground`/`-hover`/`-muted` satellites, `--accent-assistant-brand`/
`-purple` (documented in-file as "kept identical in light and dark so the
assistant glyph + input glow read the same in either theme" — exactly the
kind of intentional-parity note that deserves respect, not a re-tint),
`--note-*`, `--jse-*` (the embedded JSON editor's own theme), `--border`/
`--input` (solid neutral greys tuned against Langflow's original
background lightness — see the comment in `brand.css` for why these are a
known imperfect edge case rather than a silent gap), and the `--sidebar-*`
tokens defined only inside `.dark` (`--sidebar-background`,
`--sidebar-primary`, `--sidebar-accent`, `--sidebar-border`, `--sidebar-ring`
— confirmed dead: zero references in `tailwind.config.mjs` and zero
non-generated call sites in `src/`; Langflow's actual sidebar renders with
`bg-background`/`bg-card`/`bg-muted` like the rest of the chrome, so the
`--sidebar-*` set looks like leftover shadcn boilerplate that was never
wired up. Overriding dead tokens is zero-risk but also zero-value, so it was
skipped rather than padding the diff).

**`public/manifest.json`.** `name`/`short_name` changed `"Langflow"` →
`"NuFi Agent"` (matching `PRODUCT` in `nufi/rebrand.ts` — this file is a
static asset in `public/`, copied byte-for-byte by Vite, so the build-time
rebrand transform never touches it; Task 2's report flagged this as carried
forward, and this task closes it). Added `theme_color` and
`background_color`, both `#080810` (navy-900) — neither key existed in the
upstream manifest at all (nothing to "fix" in place), and the app defaults
to dark (`<body class="dark">`), so navy-900 is the correct default surface
for a PWA install/splash-screen.

`description` needed more than a mechanical rename. The first pass swapped
the noun in Langflow's own sentence ("NuFi Agent is a low-code builder that
makes it easier to build powerful AIs that can use any API, model, or
database.") — legally fine under Langflow's MIT license, but adopting a
competitor's positioning as NuFi's own product description is a business
call, not an engineering one, and this build is customer-facing. Replaced
with a plain factual description in NuFi's own words:
"NuFi Agent is a visual editor for building, testing, and running AI
workflows that connect language models, APIs, and data sources." — see
`NEEDS PRODUCT SIGN-OFF` in the Task 3 report; a human should confirm or
replace this before it ships.

The `icons` array still points at `icons/32x32.png`, `icons/128x128.png`,
`icons/128x128@2x.png` and `icons/icon.ico`, none of which exist anywhere in
this vendored tree — confirmed again for this task (`find src/frontend
-iname 'icons' -o -iname '32x32.png'` etc. → nothing). Task 1's report
already logged this as a pre-existing upstream gap (generated by Langflow's
desktop/Tauri packaging, never committed to the OSS repo); left alone here
too, per the same reasoning — inventing icon files nobody asked for isn't in
scope. This does have a real, if narrow, effect: Chrome's PWA
installability check requires at least one *fetchable* icon ≥192×192 in the
manifest, so "Add to Home Screen"/the browser's install prompt won't offer
the NF mark (and may not offer install at all) until real icon files exist
at those paths. It does **not** affect the browser tab favicon — that comes
from `index.html`'s separate `<link rel="icon" href="/favicon.ico">`, which
now points at a real multi-resolution NF-mark ICO (see below).

**`favicon.ico`.** Upstream shipped a single-resolution 256×256 ICO.
Replaced with a multi-resolution ICO (16/32/48/64/128/256, matching the
common favicon convention) rasterized from `apps/agents/ui/public/favicon.svg`
— the real NuFi "NF" wordmark on its native white square background. That
SVG is the one genuine NuFi mark asset available anywhere in the repo; the
`android-chrome-*.png`/`apple-touch-icon.png` family next to it in
`apps/agents/ui/public/` are the same mark pre-rasterized at other sizes
(confirmed opaque white background via a pixel probe, not just format
metadata claiming alpha support).

**The four in-app logo SVGs**
(`LangflowLogo.svg`, `LangflowLogoColor.svg`, `langflow_logo_white.svg`,
`langflow_logo_black.svg`) all now carry the same real NF-mark path
geometry, taken verbatim from `apps/agents/ui/public/favicon.svg`'s inner
`<svg>` (the wordmark paths, with the outer white background `<rect>`
dropped since these render inline, not as a favicon):

- `LangflowLogo.svg` — single `fill="currentColor"` on the root `<svg>`,
  no per-shape fill (matching upstream's own pattern exactly: this file was
  already a monochrome currentColor icon before the edit, just with
  Langflow's abstract glyph instead of NuFi's).
- `LangflowLogoColor.svg` — same geometry, real two-tone fill
  (`#3c4d8a`/`#293069` navy, `#e99a97` coral), matching upstream's own
  pattern (this was already the "keep the brand colours" variant).
- `langflow_logo_white.svg` / `langflow_logo_black.svg` — solid
  `#ffffff` / `#000000` fill respectively. Both are unreferenced in
  `v1.11.2` (0 non-test import sites, confirmed again for this task —
  reserved for a future theming pass per the asset-sweep table above), so
  there is no live call site to visually verify against.

**Deliberate viewBox change.** Upstream's `viewBox` numbers differed per
file — `LangflowLogo.svg`/`LangflowLogoColor.svg` were small near-square
icons (`24 22` / `18 18`); `langflow_logo_white.svg`/`_black.svg` were the
full wordmark text "Langflow" at `1318 258` (≈5.1:1). All four now share one
viewBox, `0 0 427.28 183.69` — the NF mark's own native bounding box,
≈2.33:1. Rationale: every call site sizes these via Tailwind classes
(`h-5 w-5`, `h-7 w-8`, `h-[18px] w-[18px]`, confirmed by grepping every
non-test import site), so the SVG's own intrinsic `width`/`height`
attributes never drive layout — only the `viewBox` aspect ratio affects how
much of a square slot gets filled (SVG's default
`preserveAspectRatio="xMidYMid meet"` letterboxes the rest). Forcing the NF
mark's real proportions to fill a 5.1:1 canvas would have meant either
stretching the mark (distorting the real asset) or padding it out
arbitrarily (inventing new composition) — both worse than shipping one
faithful, undistorted rendering of the real mark and letting it letterbox
where the container is squarer than the mark. All four render correctly at
their actual call-site sizes (checked at 20px, matching `h-5 w-5`) — see the
Task 3 report for the rendered previews.

**`logo_dark.png` / `logo_light.png`.** Both replaced with the same
480×480 transparent PNG (matching upstream's 480×480 dimensions), rasterized
from the same `favicon.svg` NF-mark paths (background `<rect>` dropped,
alpha reconstructed by un-premultiplying against the known white backdrop
rather than a hard chroma-key cutoff, to avoid a light fringe on the navy
shapes). One asset for both files rather than two upstream-style dark/light
variants: the mark's navy-and-coral palette reads legibly on both a navy
page background and a white one (checked directly — see the Task 3 report),
and `--accent-assistant-brand`/`-purple` in `style/index.css` already
establish "same brand asset in both themes" as the norm in this codebase,
not an exception.

## Korean locale (demo path)

> **PROVISIONAL — every string in `ko.json` is machine-authored and has not
> been reviewed by a native Korean speaker.** Register, terminology, and
> grammar are believed correct but unverified. **A native speaker must sign
> off on this file before it is shown to a customer.** Treat it the same way
> you'd treat an unreviewed machine translation anywhere else in the
> product: good enough to demo the mechanism, not good enough to represent
> the product in front of the actual evaluation panel without a human
> checking it first.

### Why demo-path only, not all 2,232 keys

Langflow ships `de`, `en`, `es`, `fr`, `ja`, `pt`, `zh-Hans` — no Korean —
and this is being pitched to a Korean public agency, so that gap isn't
optional. But `i18n.ts:58` sets `fallbackLng: "en"` with
`returnEmptyString: false` (confirmed on this tree before writing a single
key): any key absent from `ko.json` renders its English string, never a
blank or a raw key path. Partial coverage degrades gracefully by design —
so the question is which subset is worth the translation risk, not whether
100% is required for the app to function.

A machine translation of 2,232 keys of Korean public-sector vocabulary
carries more risk than value. A string that reads wrong in front of a JDC
evaluation panel says "we don't understand this market" — worse than an
English string, which just says "not localized yet." So this translates
**the screens an evaluator actually sees during a live demo**, translated
carefully, formally registered, and flagged provisional — not the whole
app translated fast and unevenly.

### The demo path, surface by surface

The six surfaces named in the task brief, mapped to the actual `en.json`
namespaces that render them (`en.json` is a flat `"namespace.key": "…"`
map, not nested — namespace here means the dotted prefix):

| Surface | Namespaces included | Why |
|---|---|---|
| Flow canvas and its controls | `flow.*` (minus `flow.defaultDescription.*`, see below), `canvas`, `canvasControls`, `nodeToolbar`, `node`, `editNode`, `noteNode`, `dialog` (the canvas toolbar's icon tooltips — export/settings/logs/code/chat/prompt), `deleteModal` (delete confirmations for a flow/component/item), `mainPage` (the flow list an evaluator lands on before opening a flow) | Where 80% of a live demo happens: opening a flow, wiring nodes, saving, locking, renaming |
| Component sidebar | `sidebar.*` in full, including every `sidebar.category.*` label | The searchable component palette evaluators watch get dragged onto the canvas |
| Run/playground panel | `playground`, `playgroundComponent`, `chat`, `output`, `inspectionPanel`, `input`, `humanInput`, `ioModal` | Running a flow and reading its output is the payoff moment of any demo |
| Save and export | `apiModal`, plus the save/export/duplicate strings already inside `flow.*`, `misc.*` (`export`, `deploy`, `share`, `apiAccess`, `embedIntoSite`, …), and the relevant `errors.*`/`success.*` entries below | What an evaluator asks about right after seeing a flow run: "can we take this with us" |
| Error and empty states | `crash`, `emptyPage`, a **curated** subset of `errors` (32 of 92), `success` (14 of 29), `alerts` (8 of 11), plus `common`, `header`, `nav`, `misc` | A demo that hits a network hiccup or an empty project and switches to raw English mid-sentence looks broken, not just untranslated |
| Settings entry points | `settings.title`/`description`/`languageTitle`/`languageDescription`/`languageRecommended`/`languageSelectAriaLabel`/`saveButton`/`generalTitle`/`generalDescription` and all of `settings.nav.*` (the left-rail menu labels) — **not** the remaining deep configuration screens behind most entries (API key management, DB provider wiring, model provider credentials, …) | "Entry points," not "the whole Settings section" — literally the brief's wording. The Language picker itself (`settings.nav.label`, `languageTitle`, …) matters more than usual here: it's how an evaluator would switch into Korean during the demo |
| Deployments and MCP (**Fix round 1**) | `deployments.*` in full (220 keys), `mcp.*` in full (82 keys), `settings.mcpClient.*` in full (11 keys) | Not one of the original six — added after review flagged that `mainPage.tabDeployments`/`misc.deploy` and `sidebar.mcp.*`/`settings.nav.mcpServers` were already translated **doors**, opening onto entirely-English **rooms**. See "A translated door into an English room" below |

**Deliberately excluded, and why (so a gap doesn't read as a missed key):**

- `flow.defaultDescription.0`–`.60` (61 keys) — whimsical placeholder
  taglines for a brand-new untitled flow ("Chain the Words, Master
  Language!", "Promptly Ingenious!", …), confirmed by grep to be the *only*
  thing `flow_constants.tsx` uses that key range for. Cosmetic flavor text,
  not something an evaluator reads for meaning, and translating 61
  English wordplay puns well is exactly the kind of effort-for-no-signal
  this task explicitly says to skip.
- `common.langflowLogo` / `common.langflowLogoLight` / `common.langflowLogoDark`
  — image alt text whose *entire content* is the bare product word. The
  build-time rebrand transform (`nufi/rebrand.ts`) already rewrites
  `"Langflow"` to `"NuFi Agent"` in every locale JSON value; a Korean
  translation here would only be `"Langflow 로고"`-shaped noise around a
  word the transform already owns, with no informational content of its
  own to localize.
- Everything else outside the table above — `knowledge` (162 keys),
  `assistant` (93), `memory` (85), `agentTab` (72), `modelProviders` (59),
  `trace` (56), `store` (34), `globalVars` (34), `admin` (29),
  `auth`/`authModal` (56 combined), `shortcuts` (42), `voice` (20),
  `fileManager`/`files` (60 combined), `table`/`paginator` (31 combined),
  `messages` (8), and the deep-settings keys under `settings.dbProviders.*`
  / `settings.apiKeys.*` / `modal.secretKey.*` — are real features, just not
  ones a first-look demo walkthrough of the canvas/sidebar/playground/save
  flow reaches. **Unlike `deployments`/`mcp` above, none of these currently
  sit directly behind an already-translated click target** — see the
  door/room sweep below for the full evidence on that claim, including the
  ones that came close. Auth in particular is arguably "first thing an
  evaluator sees," but the brief's six named surfaces don't include it, and
  login screens for a live agency demo are typically pre-authenticated
  before the evaluator sits down — so it stayed out rather than being added
  by inference.

### A translated door into an English room (Fix round 1 finding, fixed)

Translating a nav item or button label makes a promise: click here and the
Korean continues. `mainPage.tabDeployments` ("배포") and `misc.deploy`
("배포") were translated in the original pass; the `deployments.*`
namespace behind them — the entire deploy wizard, provider selection,
connection management, environment variables, the whole thing — was 220
keys at 0%. Same shape of bug at `sidebar.mcp.*`/`settings.nav.mcpServers`
opening onto the 82-key `mcp.*` Add/Edit Server modal and the 11-key
`settings.mcpClient.*` connection guide, both untranslated. MCP has a
second reason this one mattered more than an ordinary gap: the customer
requirement (SFR-008) names "multi-agent architecture with MCP servers"
explicitly, so an evaluator clicking through to MCP is checking the
requirement, not wandering off the demo path.

This inverts the graceful-degradation argument the rest of this document
makes for staying partial: English sitting among English degrades
gracefully (see "Why demo-path only" above). **A Korean tab that promises
Korean and then breaks mid-click reads as a failed translation, not a
scoping decision** — worse than if the tab had stayed in English to begin
with. All 313 keys (`deployments.*` + `mcp.*` + `settings.mcpClient.*`) were
translated in Fix round 1 to close this specific gap. Verified in the
compiled bundle, not just the source JSON: `build/assets/ko-*.js` after
`npm run build` shows zero literal `"Langflow"` and the expected
`"NuFi Agent ..."` rewrites for every string in the new namespaces that
named the product, e.g. `NuFi Agent 및 Watsonx Orchestrate에서 배포
{{name}}을(를) 영구적으로 삭제합니다.` (from `deployments.deleteDeploymentConfirm`)
— and `"Watsonx Orchestrate"` / `"watsonx Orchestrate"`, a third-party
product name, survives untouched in both castings, as it should.

**Door/room sweep — the rest of the exclusion list, checked against the
same lens.** Every remaining translated sidebar/settings nav item was
traced to the actual screen component it opens (`grep`, not guesswork —
see the file paths below), and every namespace behind it was counted. This
is a report, not a silent fix — none of the below is translated in this
round:

| Translated door | Opens (confirmed by source) | Room size | Risk |
|---|---|---|---|
| `sidebar.knowledge` ("지식") | `modals/knowledgeBaseUploadModal/*` → `knowledge.*` | 162 keys, 0% | High — larger than the original `deployments` gap, one click from the sidebar |
| `sidebar.nav.agent` ("에이전트") | `pages/FlowPage/components/AgentMainContent/*` → `agentTab.*` | 72 keys, 0% | High — reached from the canvas, not a settings sub-page |
| `sidebar.myFiles` ("내 파일") | `modals/fileManagerModal/*` → `files.*` + `fileManager.*` | 60 keys, 0% | Medium-high |
| `sidebar.nav.traces` ("트레이스") | `pages/FlowPage/components/TraceComponent/*` → `trace.*` | 56 keys, 0% | Medium-high — the run/observability panel, adjacent to the already-translated playground |
| `settings.nav.modelProviders` ("모델 제공업체") | `modals/modelProviderModal/*` → `modelProviders.*` | 59 keys, 0% | Medium |
| `settings.nav.shortcuts` ("단축키") | `pages/SettingsPage/pages/ShortcutsPage/*` → `shortcuts.*` | 42 keys, 0% | Medium |
| `settings.nav.dbProviders` ("DB 제공업체") | in-namespace → `settings.dbProviders.*` | 44 keys, 0% | Medium |
| `settings.nav.globalVariables` ("전역 변수") | `pages/SettingsPage/pages/GlobalVariablesPage/*` → `globalVars.*` | 34 keys, 0% | Medium |
| `settings.nav.store` ("Langflow 스토어") | `pages/StorePage/*` → `store.*` | 34 keys, 0% | Medium |
| `settings.nav.apiKeys` ("Langflow API 키") | `pages/SettingsPage/pages/ApiKeysPage/*` → `settings.apiKeys*` + `modal.secretKey.*` | 22 keys, 0% | Lower |
| `sidebar.nav.versions` / `versionHistory` ("버전"/"버전 기록") | `flowSidebarComponent/components/FlowVersionSidebar/*` → `flowVersion.*` | 15 keys, 0% | Lower — the generic save/restore-version strings a user reads *are* translated (`flow.saveVersion`, `flow.restoreVersion`, `modal.restoreVersion`); only the version-list panel's own chrome is English |
| `settings.nav.messages` ("메시지") | `pages/SettingsPage/pages/messagesPage/*` → `messages.*` | 8 keys, 0% | Lower — small room |
| **`editNode.openTable` / the playground session view** (already in scope, already translated) | `components/core/.../tableComponent/*`, `modals/IOModal/components/session-view.tsx` → `table.*` | 23 keys, 0% | **Flagged separately below — this one sits *inside* an already-claimed-covered surface, not behind a new door** |
| Any translated list view (Main Page, Deployments, Knowledge) | `components/common/paginatorComponent/*` → `paginator.*` | 8 keys, 0% | Cross-cutting — shared pagination chrome under nearly every list in the app |

**Two of these are a different, more serious shape than the rest and are
called out on their own:** `table.*` and `paginator.*` are not behind a
*new* door — they're generic shared components used *inside* surfaces this
document already claims as covered (`table.*` backs the playground's
session view and the `editNode`/`inspectionPanel` "Open Table" field type;
`paginator.*` backs pagination on every list view, including the
now-translated Main Page and Deployments tabs). That means the current
"flow canvas / sidebar / run-playground / settings-entry-points" coverage
claim has a real hole in it today, not a hypothetical one for a future
click. Recommend prioritizing these 31 keys highest of everything in this
table if scope expands again, specifically because they undercut a claim
already made rather than adding a new one.

The rest (`knowledge` down through `messages`, 608 keys, none currently
behind a translated door within the demo-path table above) are reported so
a scope decision can be made deliberately, not fixed here.

### Key count

**864 of 2,230 keys translated (38.7%)** — `en.json` has 2,230 flat keys,
not 2,232 (`wc -l` counts the file's opening/closing braces as lines too).
551 from the original six-surface pass, 313 more from Fix round 1
(`deployments.*`, `mcp.*`, `settings.mcpClient.*`).

Generated and typo-checked by `nufi/build-ko-locale.py` — the translation
source of truth; `ko.json` **and** `nufi/demo-path-keys.txt` are both its
generated artifacts (see that section below for why the second one changed
from hand-maintained to generated in Fix round 1). Regenerate both with:

```bash
python3 apps/nufi-agent/nufi/build-ko-locale.py
```

Re-running it reproduces both files byte-for-byte (verified: `diff`
against the committed files after a fresh run is empty).

### Typo check: every ko.json key programmatically verified against en.json

A typo in a key path is invisible by inspection — it falls back to English
silently and looks exactly like a key someone chose not to translate. Every
key was checked to be a real `en.json` key, not eyeballed:

```
$ python3 -c "
import json
with open('locales/en.json') as f: en=json.load(f)
with open('locales/ko.json') as f: ko=json.load(f)
print('ko.json key count:', len(ko))
orphans = [k for k in ko if k not in en]
print('orphans:', orphans)
"
ko.json key count: 864
orphans: []
```

Also checked programmatically: every `{{interpolation}}` placeholder and
every react-i18next `<1>…</1>` Trans-tag marker in each translated value
matches its English source exactly (a translation that drops or
mistranslates a placeholder throws at render time, or worse, silently
strips a variable) — zero mismatches across all 864 keys. Re-run after Fix
round 1's 313-key addition with the same result: 0 orphans, 0 placeholder
mismatches, 0 tag mismatches.

### Terminology decisions

Register is formal/public-sector Korean (`-습니다`/`-십시오` endings), per
the task brief's examples: `승인` approve, `검토` review, `저장` save, `실행`
run.

**Correction (Fix round 1):** the original text here claimed this
register was applied "throughout," full stop. That claim was checked, not
just asserted, and it was wrong: a full sentence-form scan (106 values)
found three error-description strings using the softer `-세요` ending
(`errors.incompleteLoop`, `misc.fetchErrorDesc`,
`misc.fetchErrorDescription`, all "please try again" phrasing) sitting
next to eight near-identical strings using `-십시오` for the same "please
retry" instruction. Same surface, same sentence, two speech levels — that
is a real inconsistency, not a stylistic choice. Fixed in Fix round 1: all
three now use `-십시오`, matching the other eight. **Left alone
deliberately:** the softer `-세요`/`-요` form that appears in placeholder
hints and inline prompts (`"정수를 입력하세요"`, `"메시지를 입력하세요..."`,
and similar) — that register split (formal for messages that interrupt
the user, softer for inline hints the user is already typing into) is a
conventional Korean UI pattern, not an inconsistency to flag.

- **`플로우` (loanword) for the product noun "Flow," not `업무 흐름`.** The
  brief's glossary lists `업무 흐름` for "flow." That fits when "flow"
  means the general concept of a business process. But most instances in
  this scope are the concrete UI noun — a saved flow chart a user names,
  opens, and exports ("New Flow," "Flow name," "Untitled Flow") — and
  Korean localizations of comparable tools (n8n, Make.com) render that as
  the loanword `플로우`, the same way `컴포넌트`/`노드` are loanwords here
  rather than translated. `업무 흐름` (or `흐름 제어` for the CS concept
  "flow control") is used instead where the English source means the
  general concept, e.g. `sidebar.category.flowControl` → `흐름 제어`.
  **This is a judgment call, not dictated by the brief, and is exactly the
  kind of thing a native-speaker review should confirm or overrule.**
- **`매개변수` over `파라미터` for "parameter."** Formal Sino-Korean matches
  the public-sector register; `파라미터` (the English loanword) is more
  common in casual developer speech.
- **`"Langflow"` kept as a literal English token wherever the English
  source contains it** (e.g. `crash.restartButton`, `settings.nav.mcpClient`,
  `settings.description`), rather than translated or dropped. The
  build-time rebrand transform (`nufi/rebrand.ts`) runs on every `.json`
  module in the Vite graph — including a dynamically `import()`-ed locale
  file, the same way it already does for `en.json` — and rewrites the
  bare word `"Langflow"` to `"NuFi Agent"`. Translating it into Korean, or
  hardcoding `"NuFi Agent"` directly in `ko.json`, would both produce text
  the transform can no longer find and rewrite consistently with the rest
  of the app. **Not independently re-verified for `ko.json` specifically
  beyond confirming the transform's own logic applies to any `.json`
  module id** — worth a specific look during native-speaker review if the
  compiled bundle is ever spot-checked.
- **Interpolation-adjacent particles.** Korean's subject/object/topic
  particles (`이`/`가`, `을`/`를`, `은`/`는`, `으로`/`로`) take a different
  form depending on whether the preceding syllable ends in a consonant —
  unknowable ahead of time for an interpolated `{{name}}`/`{{id}}`. Handled
  three ways, in order of preference: (1) restructured so no such particle
  sits directly after the variable (`"{{name}} 다운로드 완료"` instead of
  attaching a particle to the name itself); (2) a particle-invariant
  marker instead (`에`, `의`, `보다`, counters like `개`/`년`/`시간`, all
  of which don't change form); (3) where neither was natural, the dual
  form `이(가)` / `을(를)` — the standard Korean UI-localization
  convention for exactly this ambiguity (used in `deleteModal.body`,
  `node.replaceConfirmBody`).
- **Korean has no grammatical plural**, so every i18next `_one`/`_other`
  pair in scope (`chat.deleteSessionsCount_*`,
  `chat.sessionsDeletedSuccess_*`, `mainPage.timeElapsed.*_one`/`_other`)
  carries the identical Korean string in both forms — not a copy-paste
  omission, i18next's Korean pluralization rule genuinely collapses to one
  form.
- **Left in English / kept as proper nouns, deliberately, not by
  omission:** `crash.githubIssues` ("GitHub Issues," the literal name of
  GitHub's own page), `Discord`/`GitHub`/`MCP`/`API`/`JSON`/`CSV`/`PDF`/
  `URL` throughout (acronyms and third-party product names, not English
  prose — translating a protocol acronym or another company's product
  name isn't localization, it's just wrong). Fix round 1 added
  `deployments.*`, which introduces `"watsonx Orchestrate"` — a third-party
  deployment target's product name, same treatment. Both castings that
  occur in `en.json` (`"Watsonx Orchestrate"` in
  `deployments.deleteDeploymentConfirm`, `"watsonx Orchestrate"` in the
  `wxo*` onboarding strings) are reproduced exactly as upstream wrote them,
  not normalized to one casing — normalizing would mean inventing a
  spelling upstream didn't choose.

### `nufi/demo-path-keys.txt`

The frozen list `check-locale-parity.sh` checks `ko.json` against — see
that file's own header comment for what it asserts and why. It's the 864
keys above, one dotted key per line.

**Fix round 1: this file is now generated, not hand-maintained.** It used
to be typed by hand as a second copy of the same key list `ko.json` comes
from — two authoring surfaces for one piece of information, which is
exactly the "stale second copy" failure mode `check-locale-parity.sh`'s
own header warns about. `check-locale-parity.sh` only fails when a
declared key goes *missing* from `ko.json`; it never notices `ko.json`
growing past the declared list, or someone editing one file and
forgetting the other — so the two could still silently drift by omission,
just not by an outright removed key. `build-ko-locale.py` now writes both
`ko.json` and `nufi/demo-path-keys.txt` from the same `T` dict in the same
run, so there is exactly one place to add or remove a key. Proved this
closes the gap, not just narrows it, two ways:

1. **Hand-editing `demo-path-keys.txt` directly no longer sticks.**
   Appended a bogus line; the guard caught it as usual (declared-but-missing,
   the same check it always ran); regenerating from `T` — the only
   sanctioned edit path — silently dropped the hand-edit back to the
   correct 864, because the file is now fully overwritten from `T` on
   every run rather than patched.
2. **Editing `T` moves both files together, automatically, in one
   command.** Added `voice.selectLanguage` (a real `en.json` key not
   previously in `T`) to `T`; one `python3 build-ko-locale.py` run put it
   in `ko.json` *and* `nufi/demo-path-keys.txt` simultaneously (865/865,
   guard still green); removing it from `T` and re-running dropped it from
   both files together (back to 864/864, guard still green). There was no
   second file to remember.

Full transcript in "Verifying the locale-parity guard" below.

## Resyncing

```bash
git fetch --depth 1 langflow refs/tags/<newtag>:refs/tags/langflow-<newtag>
git subtree pull --prefix=apps/nufi-agent langflow-<newtag> --squash
```

Then re-run `nufi/rebrand.test.ts` and `nufi/check-locale-parity.sh` (see
`nufi/upstream.json` → `resyncAlsoDo`). An upstream release that adds
English keys doesn't need a Korean response — that's the intended partial
state — but an upstream release that **renames or removes** an English key
`ko.json` still references turns into an orphan key, which
`check-locale-parity.sh`'s first check catches. Langflow ships `de`, `es`,
`fr`, `ja`, `pt`, `zh-Hans` and `en`, not `ko` (design doc §5).

## Verifying the guard

```bash
./nufi/check-fork-diff.sh
```

Exits 0 when the diff between `HEAD:apps/nufi-agent` and the vendored upstream
tag is confined to the table above, 1 otherwise, naming every offending path.

A guard that has never gone red is not known to work. Demonstrated for this
fork by committing a one-line drift to `src/frontend/src/App.tsx` (not
allowlisted), confirming the script caught it and named the file, then
reverting:

```
$ ./apps/nufi-agent/nufi/check-fork-diff.sh
Comparing apps/nufi-agent against https://github.com/langflow-ai/langflow.git @ v1.11.2
changed: 0  allowlisted: 0  violations: 0
OK — the fork diff is confined to the NuFi allowlist.

$ echo "// drift" >> apps/nufi-agent/src/frontend/src/App.tsx && git commit -am "test drift"
$ ./apps/nufi-agent/nufi/check-fork-diff.sh
Comparing apps/nufi-agent against https://github.com/langflow-ai/langflow.git @ v1.11.2
changed: 1  allowlisted: 0  violations: 1

These files diverge from upstream but are not NuFi-owned:
  src/frontend/src/App.tsx
...
exit 1

$ git reset --hard HEAD~1
$ ./apps/nufi-agent/nufi/check-fork-diff.sh
changed: 0  allowlisted: 0  violations: 0
OK — the fork diff is confined to the NuFi allowlist.
```

The script diffs `HEAD:apps/nufi-agent` (the committed tree) against the
fetched upstream tag, not the working tree — this matches what CI actually
sees on a pull request, but it means reproducing the drift locally requires
committing it first (`echo >> file` alone is invisible to the diff until it
lands in a commit).

## Verifying the brand CSS survives the build

`check-fork-diff.sh` only diffs file *paths* — it has no way to know whether
an allowlisted file's *content* still does what it claims. `nufi/brand.css`
is imported by exactly one line, and CSS silently drops an `@import` that
isn't the first statement in a stylesheet (no build error). That bug shipped
once during Task 3 and was only caught by hand-grepping compiled CSS —
`check-brand-css.sh` automates the same check: build the frontend, then
assert the compiled CSS carries the NuFi tokens in both `:root:root` and
`.dark.dark`. Wired into `nufi-agent-ci.yml` as its own job (`brand-css`),
separate from `fork-guard`, since it needs `npm ci` first.

```bash
cd apps/nufi-agent/src/frontend && npm ci   # once
./nufi/check-brand-css.sh
```

Demonstrated red/green the same way `check-fork-diff.sh` was in Task 1 — by
moving the import out of position, confirming failure, then restoring it:

```
$ ./apps/nufi-agent/nufi/check-brand-css.sh
Building apps/nufi-agent/src/frontend...
OK      :root:root carries --primary (light-mode brand primary)
OK      .dark.dark carries --background (dark-mode navy surface)
OK -- the compiled CSS carries the NuFi brand tokens in both theme scopes.

$ # move @import below @tailwind base; (the exact bug this guards against)
$ ./apps/nufi-agent/nufi/check-brand-css.sh
Building apps/nufi-agent/src/frontend...
MISSING :root:root carries --primary (light-mode brand primary)
MISSING .dark.dark carries --background (dark-mode navy surface)
...
exit 1

$ # restore the import to line 1
$ ./apps/nufi-agent/nufi/check-brand-css.sh
Building apps/nufi-agent/src/frontend...
OK      :root:root carries --primary (light-mode brand primary)
OK      .dark.dark carries --background (dark-mode navy surface)
OK -- the compiled CSS carries the NuFi brand tokens in both theme scopes.
```

A real build (rather than a static "is `@import` line 1" check) was chosen
because it verifies the thing that actually matters — what ships — not a
proxy for it: it also catches a renamed/emptied `nufi/brand.css`, a broken
import path, or `brand.css` losing its `:root:root`/`.dark.dark` selectors.
The build costs ~20s once dependencies are installed, paid once per PR that
touches `apps/nufi-agent`, not per commit.

## Verifying the locale-parity guard

```bash
./nufi/check-locale-parity.sh
```

Exits 0 when `ko.json` has no orphan keys and every key in
`nufi/demo-path-keys.txt` is present in `ko.json`, 1 otherwise, naming every
offending key. Wired into `nufi-agent-ci.yml` as its own job
(`locale-parity`) — it only needs `node` to parse two JSON files, no build,
so it doesn't share `fork-guard`'s or `brand-css`'s setup.

Demonstrated failing in **both** directions it's meant to catch, not just
one — two prior guards in this fork shipped without ever being seen to
fail; this one wasn't going to be the third. Re-run in full at the Fix
round 1 baseline (864 keys, after `deployments.*`/`mcp.*`/
`settings.mcpClient.*` were added) — all four runs, back to back:

```
$ ./apps/nufi-agent/nufi/check-locale-parity.sh
OK    no orphan keys -- every ko.json key exists in en.json
OK    all 864 declared demo-path keys are present in ko.json
OK -- ko.json is a clean, declared subset of en.json.

$ # inject a key into ko.json that doesn't exist in en.json
$ ./apps/nufi-agent/nufi/check-locale-parity.sh
FAIL  orphan keys in ko.json with no matching key in en.json:
  sidebar.thisKeyDoesNotExistUpstream
  (an upstream rename/removal, or a typo when ko.json was authored --
  either way, i18next's lookup on this key now silently misses.)
OK    all 864 declared demo-path keys are present in ko.json
exit 1

$ # restore via regeneration
$ python3 apps/nufi-agent/nufi/build-ko-locale.py
$ ./apps/nufi-agent/nufi/check-locale-parity.sh
OK    no orphan keys -- every ko.json key exists in en.json
OK    all 864 declared demo-path keys are present in ko.json
OK -- ko.json is a clean, declared subset of en.json.

$ # delete a key that IS declared in nufi/demo-path-keys.txt
$ python3 -c "... del ko['deployments.deploy'] ..."
$ ./apps/nufi-agent/nufi/check-locale-parity.sh
OK    no orphan keys -- every ko.json key exists in en.json
FAIL  demo-path keys declared in nufi/demo-path-keys.txt but missing from ko.json:
  deployments.deploy
  (coverage shrank. If that's deliberate, remove the key from
  nufi/demo-path-keys.txt in the same change; otherwise restore it in ko.json.)
exit 1

$ # restore via regeneration
$ python3 apps/nufi-agent/nufi/build-ko-locale.py
$ ./apps/nufi-agent/nufi/check-locale-parity.sh
OK    no orphan keys -- every ko.json key exists in en.json
OK    all 864 declared demo-path keys are present in ko.json
OK -- ko.json is a clean, declared subset of en.json.
```

After the fourth run, `ko.json` matches what `nufi/build-ko-locale.py`
regenerates byte-for-byte — confirmed by re-running the generator and
diffing.

Note what this guard deliberately does **not** check: that `en.json` keys
outside the declared demo path are absent from `ko.json` (they may be, by
construction, but that's incidental, not asserted), and it never fails on
`en.json` having keys `ko.json` doesn't — that's the intended partial-
coverage state this whole task is built around, not a defect to flag.

### The two-copy-drift fix (Fix round 1), demonstrated

`nufi/demo-path-keys.txt` "Fix round 1" section above explains why this
file changed from hand-maintained to generated. Both halves of that claim
— hand-edits don't stick, and `T` edits move both files together — proved
live, not just argued:

```
$ # Proof 1: a hand-edit to demo-path-keys.txt no longer survives regeneration
$ echo "bogus.hand.edited.key" >> apps/nufi-agent/nufi/demo-path-keys.txt
$ ./apps/nufi-agent/nufi/check-locale-parity.sh
OK    no orphan keys -- every ko.json key exists in en.json
FAIL  demo-path keys declared in nufi/demo-path-keys.txt but missing from ko.json:
  bogus.hand.edited.key
  ...
exit 1
$ python3 apps/nufi-agent/nufi/build-ko-locale.py   # the only sanctioned edit path
Translated 864 keys of 2230 total (38.7%)
$ grep -c "bogus.hand.edited.key" apps/nufi-agent/nufi/demo-path-keys.txt
0   # gone -- the file was fully overwritten from T, not patched
$ ./apps/nufi-agent/nufi/check-locale-parity.sh
OK    no orphan keys -- every ko.json key exists in en.json
OK    all 864 declared demo-path keys are present in ko.json
OK -- ko.json is a clean, declared subset of en.json.

$ # Proof 2: adding a REAL en.json key to T updates both files together, in one run
$ # (added "voice.selectLanguage": "..." to T in build-ko-locale.py)
$ python3 apps/nufi-agent/nufi/build-ko-locale.py
Translated 865 keys of 2230 total (38.8%)
$ grep -c '"voice.selectLanguage"' apps/nufi-agent/src/frontend/src/locales/ko.json
1
$ grep -c "^voice.selectLanguage$" apps/nufi-agent/nufi/demo-path-keys.txt
1
$ ./apps/nufi-agent/nufi/check-locale-parity.sh
OK    no orphan keys -- every ko.json key exists in en.json
OK    all 865 declared demo-path keys are present in ko.json
OK -- ko.json is a clean, declared subset of en.json.

$ # removed it from T again, back to 864 in both files simultaneously
$ python3 apps/nufi-agent/nufi/build-ko-locale.py
Translated 864 keys of 2230 total (38.7%)
$ ./apps/nufi-agent/nufi/check-locale-parity.sh
OK    no orphan keys -- every ko.json key exists in en.json
OK    all 864 declared demo-path keys are present in ko.json
OK -- ko.json is a clean, declared subset of en.json.
```

What this doesn't prove: that a human can no longer hand-edit `ko.json`
itself (bypassing `build-ko-locale.py` entirely) and add a key without
touching `T`. That remains possible at the filesystem level — nothing
stops a future edit from writing straight into `ko.json`. What changed is
narrower and specific to the finding: the *second hand-maintained copy of
the same key list* is gone, replaced by one generation step from one
source. A direct `ko.json` hand-edit is still caught by the orphan check
if the key is a typo, and is otherwise the same "documented but not
mechanically enforced" convention every other generated file in this repo
relies on (`ko.json` and `nufi/demo-path-keys.txt` both carry a "generated,
do not hand-edit" header for exactly this reason).
