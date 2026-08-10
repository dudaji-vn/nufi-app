# NuFi Agent — Fork & White-Label Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Vendor Langflow into the monorepo as `apps/nufi-agent`, ship it branded as NuFi Agent with a Korean interface, and put model traffic behind the NuFi gateway — with the fork diff small enough to keep rebasing on upstream releases.

**Architecture:** `git subtree` vendor pinned at a release tag, mirroring `apps/agents`: everything NuFi owns lives under `nufi/`, an allowlist script fails CI on drift, and the product name is rewritten at build time rather than edited into 62 source files.

**Tech Stack:** Python 3.x + `uv` (backend), React + Vite (frontend), Docker. The rebrand transform is a Vite plugin, ported from `apps/agents/ui/nufi-rebrand.ts`.

## Global Constraints

- **Vendor at a release tag, never `main`.** Upstream ships every 1-2 weeks (`v1.11.2`, 2026-08-04) and pushes ~31 commits per 8 days. Tracking tags means a handful of rebases a quarter against something upstream has already stabilised.
- **The fork diff stays inside an allowlist, enforced in CI.** `apps/chat` shows the cost of the alternative: upstream sync dropped permanently, 752 residual `LibreChat` references. Left to review discipline this erodes.
- **Never hand-edit a product name into upstream source.** 471 brand strings live across 62 frontend files; 308 of them are inside the seven locale JSONs. Editing them makes every upstream copy change a merge conflict.
- **Nothing NuFi-owned goes outside `apps/nufi-agent/nufi/`** except the small allowlisted set this plan creates deliberately.
- **Commit messages:** `feat(nufi-agent): …` / `docs(nufi-agent): …`, lowercase after the colon, no trailing period. Every commit carries:
  `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`
  `Claude-Session: https://claude.ai/code/session_01NhbBa7c7GXFztHLzjQkmSr`
- **No subagent opens a browser or starts a long-running server.** Steps requiring that are reported as `NOT RUN — needs a human` with the exact commands and click-path.

---

## File Structure

```
apps/nufi-agent/                     vendored Langflow, byte-identical except:
  nufi/
    upstream.json                    the pin: repo, tag, commit, vendoredAt, resync recipe
    check-fork-diff.sh               allowlist guard, ported from apps/agents
    README.md                        what NuFi owns and why each entry earned its place
    rebrand.ts                       build-time product-name transform (Vite plugin)
    rebrand.test.ts                  its tests, pinning the cases a blind replace breaks
    brand.css                        colour tokens, doubled selectors to win without editing values
    locales/ko.json                  Korean interface. Langflow ships no ko
    egress/verify-egress.sh          falsifies the gateway claim
  src/frontend/index.html            1 line, the title
  src/frontend/src/index.css         1 line, imports nufi/brand.css
  src/frontend/vite.config.mts       2 lines, registers the rebrand plugin
  src/frontend/public/favicon.ico    replaced
  src/frontend/public/manifest.json  replaced
  src/frontend/src/assets/*.svg|png  NuFi marks replacing Langflow marks
```

Task 4 is independent of Tasks 2 and 3 and can run in parallel. Task 5 depends on Task 1 only.

---

## Task 1: Vendor Langflow and lock the fork surface

**Files:**
- Create: `apps/nufi-agent/` (vendored subtree)
- Create: `apps/nufi-agent/nufi/upstream.json`
- Create: `apps/nufi-agent/nufi/check-fork-diff.sh`
- Create: `apps/nufi-agent/nufi/README.md`
- Create: `.github/workflows/nufi-agent-ci.yml`

**Interfaces:**
- Produces: the vendored tree, and a guard script exiting 0 when the diff is confined to the allowlist and 1 otherwise.

- [ ] **Step 1: Confirm the tag to pin**

Run:
```bash
gh api "repos/langflow-ai/langflow/releases?per_page=5" --jq '.[] | [.tag_name, .published_at[0:10]] | @tsv'
```
Pin the newest stable tag. As of writing that is `v1.11.2` (2026-08-04). If a newer one exists, use it and record the actual value everywhere below.

- [ ] **Step 2: Vendor it**

```bash
cd /Users/sun/Workspace/DudajiVN/nufi-app
git remote add langflow https://github.com/langflow-ai/langflow.git 2>/dev/null || true
TAG=v1.11.2
git fetch --depth 1 langflow "refs/tags/$TAG:refs/tags/langflow-$TAG"
git subtree add --prefix=apps/nufi-agent "langflow-$TAG" --squash
```
Expected: `apps/nufi-agent/` exists with roughly 8,929 tracked files.

- [ ] **Step 3: Record the pin**

`apps/nufi-agent/nufi/upstream.json`:

```json
{
  "repository": "https://github.com/langflow-ai/langflow.git",
  "tag": "v1.11.2",
  "commit": "<fill from: git rev-parse langflow-v1.11.2>",
  "license": "MIT",
  "vendoredAt": "2026-08-10",
  "method": "git subtree add --prefix=apps/nufi-agent <tag> --squash",
  "resync": "git fetch --depth 1 langflow refs/tags/<newtag>:refs/tags/langflow-<newtag> && git subtree pull --prefix=apps/nufi-agent langflow-<newtag> --squash",
  "resyncAlsoDo": "Re-run nufi/rebrand.test.ts and check-locale-parity.sh; an upstream release that adds English keys silently leaves Korean gaps."
}
```

The `commit` field must be the real SHA, not a placeholder. The guard reads this file to know what to diff against.

- [ ] **Step 4: Port the fork guard**

Copy `apps/agents/nufi/check-fork-diff.sh` to `apps/nufi-agent/nufi/check-fork-diff.sh` and change two things: verify the `cd` depth still resolves to the repo root (both scripts live two levels below it, so `../../..` should still apply), and replace the `ALLOWLIST` array:

```bash
ALLOWLIST=(
  "nufi/"
  "src/frontend/index.html"
  "src/frontend/src/index.css"
  "src/frontend/vite.config.mts"
  "src/frontend/public/favicon.ico"
  "src/frontend/public/manifest.json"
  "src/frontend/src/assets/LangflowLogo.svg"
  "src/frontend/src/assets/LangflowLogoColor.svg"
  "src/frontend/src/assets/langflow_logo_white.svg"
  "src/frontend/src/assets/langflow_logo_black.svg"
  "src/frontend/src/assets/logo_dark.png"
  "src/frontend/src/assets/logo_light.png"
)
```

**Keep the upstream asset filenames.** Renaming `LangflowLogo.svg` to `NufiLogo.svg` means editing every import that references it, which is how a thin fork stops being thin. `apps/agents/nufi/README.md` records the same lesson about `paperclip-thinking.svg`.

Preserve the script's failure message. It tells a future contributor the three options in order: external package, upstream PR, or a deliberate allowlist entry.

- [ ] **Step 5: Prove the guard can fail**

A guard that cannot go red is not a guard.

```bash
chmod +x apps/nufi-agent/nufi/check-fork-diff.sh
./apps/nufi-agent/nufi/check-fork-diff.sh
echo "// drift" >> apps/nufi-agent/src/frontend/src/App.tsx
./apps/nufi-agent/nufi/check-fork-diff.sh
git checkout apps/nufi-agent/src/frontend/src/App.tsx
./apps/nufi-agent/nufi/check-fork-diff.sh
```
Expected: OK with 0 violations, then exit 1 naming `src/frontend/src/App.tsx`, then OK again. Paste all three outputs into the report.

- [ ] **Step 6: Wire CI**

`.github/workflows/nufi-agent-ci.yml`, modelled on `.github/workflows/agents-ci.yml`:

```yaml
name: nufi-agent-ci

on:
  pull_request:
    paths: ['apps/nufi-agent/**', '.github/workflows/nufi-agent-ci.yml']

concurrency:
  group: nufi-agent-ci-${{ github.ref_name }}
  cancel-in-progress: true

jobs:
  fork-guard:
    name: Fork diff stays in the allowlist
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
        with:
          # The guard diffs against the vendored upstream tag, so it needs
          # real history rather than the default single-commit checkout.
          fetch-depth: 0
      - name: Compare apps/nufi-agent against its vendored upstream tag
        run: ./apps/nufi-agent/nufi/check-fork-diff.sh
```

- [ ] **Step 7: Write the ownership README**

`apps/nufi-agent/nufi/README.md`, following the shape of `apps/agents/nufi/README.md`: a table of every allowlisted path, what it is, and for each one *why it earned a place*. An allowlist without reasons grows by reflex.

- [ ] **Step 8: Commit**

```bash
git add apps/nufi-agent .github/workflows/nufi-agent-ci.yml
git commit -m "feat(nufi-agent): vendor langflow v1.11.2 with an allowlist guard"
```

---

## Task 2: Build-time product-name rewrite

**Files:**
- Create: `apps/nufi-agent/nufi/rebrand.ts`
- Create: `apps/nufi-agent/nufi/rebrand.test.ts`
- Modify: `apps/nufi-agent/src/frontend/vite.config.mts` (2 lines)
- Modify: `apps/nufi-agent/src/frontend/index.html` (1 line)

**Interfaces:**
- Produces: `rewrite(code: string): string` (pure, testable without Vite) and `nufiRebrand(): Plugin`.

- [ ] **Step 1: Read the proven implementation**

`apps/agents/ui/nufi-rebrand.ts` and `apps/agents/ui/nufi-rebrand.test.ts` already solve this problem for Paperclip. Read both before writing anything. The Langflow version is the same shape with a different word list and different exclusions.

- [ ] **Step 2: Write the failing test first**

`apps/nufi-agent/nufi/rebrand.test.ts`. Each case is a specific way a blind find-and-replace breaks this codebase, not a hypothetical:

```ts
import { describe, expect, it } from "vitest";
import { rewrite } from "./rebrand";

describe("rebrand", () => {
  it("renames the product in user-facing copy", () => {
    expect(rewrite('const t = "Welcome to Langflow";')).toBe('const t = "Welcome to NuFi Agent";');
  });

  it("rewrites the same word inside a locale JSON value", () => {
    expect(rewrite('{"welcome": "Langflow guide"}')).toBe('{"welcome": "NuFi Agent guide"}');
  });

  /**
   * 308 of the 471 brand hits are locale VALUES. Keys are addressed by code and
   * must survive, or every lookup misses and the UI renders raw key paths.
   */
  it("never rewrites a locale key", () => {
    expect(rewrite('{"langflow_version": "1.11.2"}')).toBe('{"langflow_version": "1.11.2"}');
  });

  /**
   * Asset filenames stay upstream on purpose (Task 1 Step 4). Rewriting an
   * import path breaks the build.
   */
  it("leaves import paths and asset filenames alone", () => {
    const src = 'import Logo from "@/assets/LangflowLogo.svg";';
    expect(rewrite(src)).toBe(src);
  });

  it("leaves python package and module namespaces alone", () => {
    expect(rewrite("from langflow.services import x")).toBe("from langflow.services import x");
    expect(rewrite('"lfx.langflow_core"')).toBe('"lfx.langflow_core"');
  });

  it("leaves env var namespaces alone", () => {
    expect(rewrite("LANGFLOW_AUTO_LOGIN=true")).toBe("LANGFLOW_AUTO_LOGIN=true");
  });

  it("leaves documentation urls alone", () => {
    const src = '"https://docs.langflow.org/get-started"';
    expect(rewrite(src)).toBe(src);
  });
});
```

- [ ] **Step 3: Run it and watch it fail**

Run: `cd apps/nufi-agent/src/frontend && npx vitest run ../../nufi/rebrand.test.ts`
Expected: FAIL, cannot resolve `./rebrand`.

- [ ] **Step 4: Implement**

`apps/nufi-agent/nufi/rebrand.ts`:

```ts
import type { Plugin } from "vite";

/**
 * The product name is rewritten at build time rather than edited into source.
 *
 * Measured on v1.11.2: 471 occurrences of "Langflow" across 62 frontend files,
 * 308 of them inside the seven locale JSONs. Renaming them at the source would
 * make every upstream copy edit a merge conflict, which is exactly what
 * apps/chat did to itself.
 *
 * The exclusions below are not defensive programming. Each is a namespace that
 * must survive untouched or the build breaks: import paths (asset filenames
 * stay upstream by design), python module paths, LANGFLOW_* env vars, locale
 * keys, and documentation URLs.
 */
const PRODUCT = "NuFi Agent";

const SKIP: RegExp[] = [
  /import\s+[^;]*from\s+["'][^"']*["']/g,
  /from\s+["'][^"']*["']/g,
  /https?:\/\/[^\s"']+/g,
  /\bLANGFLOW_[A-Z0-9_]+\b/g,
  /\blangflow[._][A-Za-z0-9_.]+/g,
  /"[a-z0-9_]*langflow[a-z0-9_]*"\s*:/gi,
];

export function rewrite(code: string): string {
  const holes: string[] = [];
  let masked = code;
  for (const pattern of SKIP) {
    masked = masked.replace(pattern, (m) => ` ${holes.push(m) - 1} `);
  }
  masked = masked.replace(/\bLangflow\b/g, PRODUCT);
  return masked.replace(/ (\d+) /g, (_, i) => holes[Number(i)]!);
}

export function nufiRebrand(): Plugin {
  return {
    name: "nufi-rebrand",
    enforce: "pre",
    transform(code, id) {
      if (!/\.(tsx?|jsx?|json|html)$/.test(id)) return null;
      if (id.includes("node_modules")) return null;
      const out = rewrite(code);
      return out === code ? null : { code: out, map: null };
    },
  };
}
```

- [ ] **Step 5: Run the tests**

Run: `npx vitest run ../../nufi/rebrand.test.ts`
Expected: 7 pass. If the masking approach fails a case, fix the implementation. Do not weaken the test.

- [ ] **Step 6: Register the plugin and fix the title**

In `src/frontend/vite.config.mts` add the import and one array entry, nothing else. In `src/frontend/index.html` line 19, change `<title>Langflow</title>` to `<title>NuFi Agent</title>`.

- [ ] **Step 7: Build and account for the residue**

```bash
cd apps/nufi-agent/src/frontend && npm ci && npm run build
grep -rhoI "Langflow" dist/ | wc -l
```
The count will not be zero. Asset filenames, env vars and documentation URLs are deliberately preserved. Report what the residue actually is, category by category, so a reader can tell deliberate from missed.

- [ ] **Step 8: Confirm the guard still passes, then commit**

```bash
./apps/nufi-agent/nufi/check-fork-diff.sh
git add apps/nufi-agent
git commit -m "feat(nufi-agent): rewrite the product name at build time"
```

---

## Task 3: Brand tokens and marks

**Files:**
- Create: `apps/nufi-agent/nufi/brand.css`
- Modify: `apps/nufi-agent/src/frontend/src/index.css` (1 line)
- Replace: `public/favicon.ico`, `public/manifest.json`, and the six logo assets

- [ ] **Step 1: Find the token surface, and stop if it is not tokens**

```bash
cd apps/nufi-agent/src/frontend
grep -n "^\s*--" src/index.css | head -40
head -60 tailwind.config.mjs
```
Record whether the palette is CSS custom properties (as Paperclip's is) or Tailwind literals. If it is literals, **stop and report**: re-tinting through Tailwind config is a much larger diff and needs a decision, not an assumption.

- [ ] **Step 2: Write the token override**

`apps/nufi-agent/nufi/brand.css`. Use doubled selectors (`:root:root`) so NuFi values win without editing upstream declarations, the technique already used in `apps/agents/ui/src/nufi-brand.css`. Take the palette from that file so both products look like one company.

Do **not** re-tint status hues, chart scales or semantic colours. Paperclip's `index.css` documents them as AA-tuned per status; assume the same here until measured, and note the assumption in `nufi/README.md`.

- [ ] **Step 3: Import it**

Add exactly one line to `src/frontend/src/index.css`.

- [ ] **Step 4: Replace the marks**

Replace `public/favicon.ico`, `public/manifest.json` (name, short_name, theme_color), and the six logo files listed in Task 1's allowlist, **keeping every upstream filename**.

Source the mark from `apps/agents/ui/public/`. The real NuFi mark is the "NF" wordmark. The purple feather disc is LibreChat's icon and must never be used as NuFi.

- [ ] **Step 5: Verify and commit**

```bash
npm run build && ./apps/nufi-agent/nufi/check-fork-diff.sh
git commit -m "feat(nufi-agent): nufi brand tokens and marks"
```
Report the visual check as `NOT RUN — needs a human`, with the URL to open and what to look at.

---

## Task 4: Korean interface

**Files:**
- Create: `apps/nufi-agent/nufi/locales/ko.json`
- Create: `apps/nufi-agent/nufi/check-locale-parity.sh`
- Modify: `.github/workflows/nufi-agent-ci.yml`

Langflow ships `de`, `en`, `es`, `fr`, `ja`, `pt`, `zh-Hans`. There is no Korean. For a Korean public-sector bid that is not optional.

- [ ] **Step 1: Confirm the key set and how a locale registers**

```bash
cd apps/nufi-agent/src/frontend
wc -l src/locales/en.json
grep -n "zh-Hans\|ja\|locales" src/i18n.ts | head -20
```
Record exactly how `src/i18n.ts` enumerates locales. That determines whether `ko` can be added without editing it. **If `i18n.ts` must be edited, it becomes a 13th allowlist entry: add it deliberately and say why in `nufi/README.md`.**

- [ ] **Step 2: Author `ko.json`**

Translate every key from `en.json` (2,232 lines). Rules:
- Use the same key set exactly. A missing key renders English mid-sentence.
- Do not translate the product name; the rebrand transform owns it.
- Prefer the vocabulary a Korean public agency uses.

- [ ] **Step 3: Guard parity in CI**

`check-locale-parity.sh`: compare the key sets of `en.json` and `ko.json`, exit non-zero listing any key present in one and absent in the other.

This matters at resync. An upstream release that adds English keys silently leaves Korean gaps, and nothing else would notice. Wire it into `nufi-agent-ci.yml` as a second job.

- [ ] **Step 4: Prove it fails**

Delete one key from `ko.json`, run the script, confirm exit 1 naming that key, restore it, confirm exit 0. Paste both outputs.

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(nufi-agent): korean interface with a locale parity guard"
```

---

## Task 5: Gateway egress, and a test that tries to break it

**Files:**
- Create: `apps/nufi-agent/nufi/egress/README.md`
- Create: `apps/nufi-agent/nufi/egress/verify-egress.sh`
- Create: `apps/nufi-agent/nufi/egress/networkpolicy.yaml`

**This task exists because the survey found no application-level chokepoint.** `docs/2026-08-10-nufi-agent-langflow-fork.md` section 4 has the measurement: the SSRF allowlist does not cover provider SDK calls, `openai_api_base` is a per-node advanced field a flow author can type anything into, and there are 71 provider bundles. Patching them is the fat fork we are avoiding.

So the network boundary is not the second layer of defence here. It is the only one, and an unverified claim about it is worse than no claim.

- [ ] **Step 1: Write the egress policy**

`networkpolicy.yaml` permitting DNS plus `api.codechi.me` only, for the namespace the container runs in. Model it on the Cilium approach in `docs/superpowers/plans/2026-08-04-nufi-agents-remaining-phases.md` Task 4, which records why `egressMode: standard` is insufficient: under it an `allowFqdns` setting falls back to "public IPv4 except private ranges", which is the entire internet.

- [ ] **Step 2: Write the falsification test**

`verify-egress.sh` must try to break the claim, not confirm it:

```bash
#!/usr/bin/env bash
#
# Falsify the containment claim.
#
# A flow whose model node is deliberately pointed at a vendor must FAIL. If it
# succeeds, the egress policy is not in force and every statement we make about
# governed model traffic is wrong for this deployment. Passing proves the
# chokepoint; not running it proves nothing, and a green badge on the other
# checks does not substitute.
#
# Usage: apps/nufi-agent/nufi/egress/verify-egress.sh <namespace>
set -euo pipefail
```

Body: exec into the running pod, `curl -sS --max-time 10 https://api.openai.com/v1/models`, and **invert the result**. A non-zero curl is a pass. A 2xx is a hard failure whose message says the chokepoint does not exist.

- [ ] **Step 3: Document what this does and does not cover**

`egress/README.md`: state plainly that this constrains **where traffic can go**, not **what a flow does with it**. A flow with a database or git component still has whatever access its credentials carry, and the gateway sees none of it. `docs/2026-08-03-nufi-agent-app-design.md` section 10 raises the same gap for Paperclip and it is still open.

- [ ] **Step 4: Report honestly**

Running this needs a cluster. Report `NOT RUN — needs a human` with the exact commands, and state in the report that **until it runs, gateway containment for NuFi Agent is a claim and not a measurement.** Do not let it be written up as done.

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(nufi-agent): egress policy and a test that tries to break it"
```

---

## Task 6: Build, run and deploy

**Files:**
- Create: `apps/nufi-agent/nufi/DEVELOPING.md`
- Modify: `.github/workflows/nufi-agent-ci.yml`

- [ ] **Step 1: Get it running locally and write down what actually worked**

```bash
cd apps/nufi-agent
head -60 DEVELOPMENT.md
head -40 Makefile
```
Follow upstream's own instructions. Record every deviation needed to make it work inside this monorepo: path assumptions, Python version, `uv` behaviour, and port conflicts with the roughly twenty services already in `deploy/platform`.

- [ ] **Step 2: Write `nufi/DEVELOPING.md`**

Only the delta from upstream's `DEVELOPMENT.md`. Duplicating upstream docs means maintaining them.

- [ ] **Step 3: Add a build job to CI**

Extend `nufi-agent-ci.yml` with a job that installs frontend dependencies and runs `npx vitest run nufi/rebrand.test.ts`. Mirror the `rebrand` job in `agents-ci.yml`, including its comment about `package_json_file`: the repo root has no `package.json`, so setup actions cannot infer a version and fail without it.

- [ ] **Step 4: Commit**

```bash
git commit -m "docs(nufi-agent): local development delta and ci build job"
```

---

## What this plan does not cover

- **The JDC pilot agents.** That is item (3), to be discussed once (1) and (2) land. The RFP asks for two or three; the candidates are the six domains it names: development, duty-free, budget, safety, contract, HR.
- **Governance.** Langflow has no RBAC, no audit log and no approval gate, and the RFP asks for all three (`INR-002` AI governance settings, `SER-001` to `SER-003` access control, `SFR-007` usage and prompt management). Nothing here builds them. This is the largest open item and it needs an owner.
- **What happens to `apps/agents`.** Carrying two forks is a real cost. The decision point is the end of this plan, when we can see whether the governance layer is better rebuilt on Langflow or kept where it already runs.
