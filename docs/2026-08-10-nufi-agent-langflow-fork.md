# NuFi Agent — forking Langflow

**Date:** 2026-08-10
**Status:** Survey complete and measured. Fork not started.
**Owner:** minhnhat165
**Supersedes, in part:** `docs/2026-08-10-nufi-agent-studio-design.md` — the canvas that document proposed building is what Langflow already ships.

## 1. Why this document exists

The direction is to fork Langflow, ship it as NuFi Agent, and build the JDC pilot
agents on top. The open question attached to it was whether a better option
exists. This is the measurement behind the answer.

Everything below was measured today against `langflow-ai/langflow` at
`v1.11.2`, not taken from documentation.

## 2. Langflow is the right pick, and the licence is the cleanest in its category

```sh
gh api repos/langflow-ai/langflow --jq '[.stargazers_count,.license.spdx_id,.language,.pushed_at[0:10]] | @tsv'
# 153001  MIT  Python  2026-08-10
head -3 LICENSE
# MIT License / Copyright (c) 2024 Langflow
```

Against the alternatives in the same category, measured 2026-08-03 by reading
each `LICENSE` rather than trusting the GitHub API — five of ten return
`NOASSERTION` there, which is exactly where the restrictions hide:

| Project | Licence | Blocker |
|---|---|---|
| **Langflow** | **MIT, whole repo** | none |
| Dify | Apache-2.0, modified | *"you may not remove or modify the LOGO or copyright information"*; no multi-tenant. Rebranding is a breach |
| n8n | Sustainable Use v1.0 | *"only for your own internal business purposes"* — cannot ship to a customer |
| Flowise | Apache-2.0 + commercial `enterprise/` | passes only if that directory is **deleted**, not merely unused |
| Activepieces | MIT + separately-licensed `packages/ee/` | same |

Langflow is the only one with no separately-licensed directory anywhere. The
call to drop Dify on licence grounds was correct, and the replacement is the
strongest available.

## 3. What the fork will actually cost

| Measure | Langflow | Paperclip (`apps/agents`, for reference) |
|---|---|---|
| Tracked files | **8,929** | 4,337 |
| Commits in 8 days | **31** | 164 |
| Releases | every 1-2 weeks (`v1.11.2` 2026-08-04) | every 1-2 weeks |
| Frontend brand strings | 471 hits across **62 files** | 550 hits |
| i18n | **real — 7 locales, ~2,231 lines each** | scaffolded, unused (9 lines) |

Twice the files, but **one fifth the commit velocity**. For a fork we intend to
keep rebasing, the second number matters more than the first: Paperclip pushes
~20 commits a day, Langflow ~4. This is a calmer thing to track.

The same discipline applies as in `docs/2026-08-03-nufi-agent-app-design.md` §7:
vendor at a release tag, keep the diff confined to an allowlist, enforce it in
CI. A rebrand that edits 62 files by hand makes every upstream copy change a
merge conflict, so the product name is rewritten at **build time** instead —
the transform already proven in `apps/agents/ui/nufi-rebrand.ts`.

## 4. The finding that changes the plan: there is no application-level chokepoint

This is the one place Langflow is materially weaker than what we have, and it
has to be designed for rather than discovered later.

Langflow does ship an SSRF allowlist — `ssrf_allowed_hosts`,
`is_host_allowed(hostname, ip)` in `src/lfx/src/lfx/utils/ssrf_protection.py`,
with a protected httpx client in `ssrf_httpx.py`. It looked like a ready-made
gateway chokepoint. It is not one:

- Only bundles that make raw httpx calls route through it — `lmstudio`,
  `clickhouse`, `chroma`, `homeassistant`. Grepped: the provider bundles do not.
- The real provider components call LangChain SDKs, which bring their own HTTP
  client and never see the protected transport.
- Where the base URL *is* settable, it is a per-node field, not a server
  default. In `src/bundles/openai/src/lfx_openai/components/openai/openai.py:41`:
  ```python
  MessageTextInput(name="openai_api_base", display_name="OpenAI API Base", advanced=True)
  ```
  Any flow author can type `api.openai.com` into that box on any node.
- There are **71 provider bundles**.

Compare what `apps/agents` has: nine adapters, egress declared centrally in
`nufi/adapters.json` with replace semantics, so an adapter absent from the file
is unavailable rather than silently falling back to a vendor default.

**Conclusion: for Langflow, network egress policy is not the second layer of
defence, it is the only one.** `docs/2026-08-03-nufi-agent-app-design.md` §5.2
already argued that env configuration is advisory and only the network boundary
enforces. Here there is not even an advisory layer worth configuring centrally.

The consequence for the JDC bid is direct: JDC requires network separation
anyway (SER-002), so an egress-restricted deployment is a requirement we were
going to meet regardless. But it must be built and **falsified** — a flow whose
node is deliberately pointed at `api.openai.com` must fail — before anyone
claims model traffic is governed. Patching 71 bundles to force a base URL is the
alternative, and it is exactly the fat fork §7 forbids.

## 5. What white-labeling touches

| What | Where | Kind |
|---|---|---|
| Product name in 471 strings | build-time transform, new file | additive |
| Colour tokens | new stylesheet + 1 import line | 1 edited line |
| Marks | `src/frontend/public/favicon.ico`, `manifest.json` | replaced |
| Korean locale | `src/frontend/src/locales/ko.json` | **new — 2,232 lines to translate** |
| Gateway egress | deployment config, not source | 0 source files |

Korean is the item to note. Langflow ships `de`, `es`, `fr`, `ja`, `pt`,
`zh-Hans` and `en` — **no `ko`**. For a Korean public-sector bid that is not
optional. The good news is that the machinery is real and adopted, so this is a
bounded translation job against an existing key set rather than an
externalisation project. `apps/agents` could not have said the same: its 40
locale files are nine lines each.

## 6. Where it lives, and what happens to `apps/agents`

The fork lands at `apps/nufi-agent/`, vendored by `git subtree` at a pinned
release tag, mirroring the `apps/agents` layout: a `nufi/` directory holding
everything we own, `nufi/upstream.json` recording the pin, and a
`nufi/check-fork-diff.sh` allowlist guard wired into CI.

`apps/agents` is **not** deleted yet, and the reason is not sunk cost — it is
six commits. It is that the 2026-08-04 spike found one property there that
Langflow does not have: Paperclip refuses to loop. After three runs that
produced no classifiable disposition it escalated to a human and stopped
dispatching, and would not be argued out of it. Langflow has no equivalent, no
RBAC, no audit log and no approval gate, and the JDC RFP asks for all three
(`INR-002` AI governance settings, `SER-001`-`003` access control, `SFR-007`
usage and prompt management).

Carrying two forks is a real cost and this should not become permanent by
default. The decision point is at the end of white-labeling, once we can see
whether the governance layer is better rebuilt on Langflow or kept where it
already works.

## 7. Risks

**Langflow answers the visible half of SFR-008 and none of the governed half.**
The canvas, multi-agent orchestration and MCP server support are all there and
mature. RBAC, audit logging and human approval gates are absent, and
third-party assessments of the project say the same: governance is something
you assemble yourself. That is the expensive half of the RFP and it is now
unowned.

**A forked Langflow is not, by itself, a differentiator.** It is MIT and has
153,001 stars; a Korean SI can fork it in a weekend. What makes a bid defensible
is the governance and gateway layer around it. If the proposal shows a
recoloured Langflow, we are competing on price.

**Python.** Every other NuFi service is TypeScript. This adds a language, a
runtime, a dependency scanner and a deployment path. It is a real operational
cost, not a blocker.

**The evaluation criteria are still missing.** Pages 37+ of the Korean RFP hold
the scoring weights, and they decide whether a strong SFR-008 answer moves the
result at all. This is the second decision in a row being made without them.
