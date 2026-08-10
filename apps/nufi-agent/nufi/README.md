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

Zero edited upstream lines committed by this task — Task 1 is vendor-and-guard
only. The rows above are the surface a later white-labeling task is allowed to
touch; none of it is edited yet.

## What's deliberately not in this list

`src/frontend/src/assets/` also ships `DataStaxLogo.svg`, `MCPLangflow.png`,
`langflow-icon-smooth.{png,svg}`, `langflow_assistant.svg` and
`langflow_assistant_idle.svg`. These are real Langflow-branded assets but the
task brief did not ask for them, so they stay pure upstream. Anyone who wires
one of them into a NuFi-facing surface later must add it here first, or the
guard will flag the diff.

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
