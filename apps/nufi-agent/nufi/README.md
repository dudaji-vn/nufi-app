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
