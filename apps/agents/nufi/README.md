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
