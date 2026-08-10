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

Two edited upstream lines pending, zero committed by this task — Task 1 is
vendor-and-guard only. The rows above are the surface a later white-labeling
task is allowed to touch; none of it is edited yet.

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
forward, and this task closes it). `description` reworded the same way,
meaning preserved. Added `theme_color` and `background_color`, both
`#080810` (navy-900) — neither key existed in the upstream manifest at all
(nothing to "fix" in place), and the app defaults to dark
(`<body class="dark">`), so navy-900 is the correct default surface for a
PWA install/splash-screen. The `icons` array still points at
`icons/32x32.png`, `icons/128x128.png`, `icons/128x128@2x.png` and
`icons/icon.ico`, none of which exist anywhere in this vendored tree —
confirmed again for this task (`find src/frontend -iname 'icons' -o -iname
'32x32.png'` etc. → nothing). Task 1's report already logged this as a
pre-existing upstream gap (generated by Langflow's desktop/Tauri packaging,
never committed to the OSS repo); left alone here too, per the same
reasoning — inventing icon files nobody asked for isn't in scope, and the
`favicon.ico` link in `index.html` doesn't depend on this array.

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

## Resyncing

```bash
git fetch --depth 1 langflow refs/tags/<newtag>:refs/tags/langflow-<newtag>
git subtree pull --prefix=apps/nufi-agent langflow-<newtag> --squash
```

Then re-run `nufi/rebrand.test.ts` and `check-locale-parity.sh` once those
exist (see `nufi/upstream.json` → `resyncAlsoDo`). An upstream release that
adds English keys silently leaves Korean gaps — Langflow ships `de`, `es`,
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
