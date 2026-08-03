# NuFi

Single repo for the whole NuFi system. One clone = the whole picture.

| Directory | What it is | Deploys as |
|---|---|---|
| `apps/chat/` | The chat app (originally a LibreChat fork; fully ours since 2026-07 — no upstream sync) | `ghcr.io/dudaji-vn/nufichat` (tag `nufi-v*` on main) |
| `apps/console/` | End-user API-key/usage console (Bun + Vite + Hono) | `ghcr.io/dudaji-vn/nufi-console` |
| `apps/admin-panel/` | Admin panel (TanStack Start + Bun; originally an ex-fork of ClickHouse/librechat-admin-panel) | `ghcr.io/dudaji-vn/nufichat-admin-panel` |
| `apps/docs/` | Docs site (Fumadocs / Next.js) | — |
| `deploy/railway/` | Railway staging wrapper (pulls the nufichat image, bakes `librechat.yaml`) | Railway service |
| `deploy/platform/` | On-prem platform: LiteLLM, Langfuse, guardrails, monitoring | docker-compose |

## Rules of the road

- **Releasing chat:** tag `nufi-vX.Y.Z` on `main` → CI builds the GHCR image.
- Active CI lives in `.github/workflows/` with per-directory path filters.
- Each app is self-contained: own lockfile, own build. There is no root
  package manager on purpose.
- `apps/chat` has **no upstream relationship** anymore — LibreChat changes
  are hand-ported if ever needed. Do not add upstream remotes.

History: consolidated 2026-07 from six repos (nufichat, nufi-console,
nufichat-admin-panel, nufi-docs, nufi-chat, npuops-platform) — full design
in `docs/2026-07-20-nufi-app-monorepo-design.md`.
