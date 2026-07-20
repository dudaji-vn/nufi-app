# NUFI Console

Self-service developer console for the NUFI AI platform: end users manage
LiteLLM API keys, budgets, and usage. Single container — Hono serves both
the Vite-built React SPA and the oRPC API at one origin
(`http://localhost:3001` in the running stack).

Deployed alongside the chat product (LibreChat fork) by the
[npuops-platform](https://github.com/dudaji-vn/npuops-platform) compose stack,
which pulls this image from `ghcr.io/dudaji-vn/nufi-console`.

## Stack

- **Bun 1.3** — package manager + server runtime (TypeScript runs natively)
- **Hono** — HTTP framework
- **oRPC** — type-safe RPC; one procedure → typed TanStack Query hook
- **Vite + React 19** — SPA build
- **TanStack Router** — file-based, type-safe routes
- **TanStack Query** — server-state cache (consumed via oRPC hooks)
- **Zustand** — client-state (modals, transient UI flags)
- **Tailwind v4 + shadcn/ui** — UI primitives
- **Zod** — input/output schemas attached to procedures

## Layout

```
nufi-console/
├── server/                    Bun + Hono + oRPC
│   ├── index.ts                Hono app; mounts oRPC handler + SPA fallback
│   ├── orpc.ts                 base oRPC instance with Context type
│   ├── middleware/
│   │   └── auth.ts              JWT verification (LibreChat token)
│   ├── lib/
│   │   ├── litellm.ts           thin client around LiteLLM admin API
│   │   ├── jit-provision.ts     create LiteLLM user on first console open
│   │   └── serve-public.ts      static SPA fallback for non-/rpc paths
│   └── router/
│       ├── index.ts             root router; exports AppRouter type
│       ├── me.ts                me.get
│       ├── keys.ts              keys.list / create / remove / info
│       └── ping.ts              smoke-test procedure
├── src/                       React SPA
│   ├── main.tsx                Router + QueryClient + Toaster wiring
│   ├── routes/
│   │   ├── __root.tsx           layout + nav
│   │   ├── index.tsx            profile page (me.get)
│   │   ├── keys.tsx             keys page
│   │   └── unauthorized.tsx     deep-link to LibreChat sign-in
│   ├── components/
│   │   ├── KeyTable.tsx
│   │   ├── KeyGenerateModal.tsx
│   │   ├── KeyRevealOnceModal.tsx
│   │   ├── ConfirmDialog.tsx
│   │   └── ui/                  shadcn primitives
│   ├── lib/
│   │   ├── orpc.ts              client + TanStack Query utils
│   │   ├── format.ts            mask, currency, dates
│   │   └── utils.ts             shadcn cn()
│   └── stores/
│       └── ui.ts                Zustand store
└── Dockerfile                 multi-stage: Vite build → Bun runtime
```

## Develop locally

```bash
bun install
bun run dev   # Vite at :5173, Hono at :3000 (Vite proxies /rpc and /_health)
```

The dev server expects the rest of the stack to be running:

- LiteLLM at `http://localhost:4000` (env: `LITELLM_BASE_URL`, `LITELLM_MASTER_KEY`)
- LibreChat at `http://localhost:3080` for the JWT cookie source
- Same `JWT_SECRET` and `JWT_REFRESH_SECRET` as the running compose

Easiest workflow: keep `docker compose up -d` running, then `bun run dev`
locally for HMR while editing console code.

## Run inside the compose stack

The image is published to `ghcr.io/dudaji-vn/nufi-console` by
`.github/workflows/docker-publish.yml` on every push to `develop`/`main` and
on `nufi-console-v*` tags. From the npuops-platform repo:

```bash
docker compose pull console
docker compose up -d console
# -> http://localhost:3001
```

Pin a specific tag via `NUFI_CONSOLE_TAG=v0.2.0` in the platform `.env`.

The container is stateless — every restart starts fresh. All persistent
state lives in LiteLLM's Postgres, LibreChat's MongoDB, and Langfuse.

## Auth model (short version)

The console verifies the LibreChat-issued JWT in two ways:

1. `Authorization: Bearer <access_token>` → `JWT_SECRET` (HS256)
2. `refreshToken` cookie → `JWT_REFRESH_SECRET` (HS256)

Browser users get path 2 automatically because LibreChat sets the cookie
on the parent domain (cookies don't bind to ports — `localhost:3080` and
`localhost:3001` share them). On any verification failure → 401.

The user's id (`payload.id` from the JWT) is the canonical identity across
LiteLLM key metadata, spend rows, and Langfuse traces.

## Common tasks

| Task | Command |
| --- | --- |
| Type-check | `bun run typecheck` |
| Build SPA | `bun run build` |
| Run server | `bun run start` |
| Regenerate route tree | `bunx @tanstack/router-cli generate` |
| Add a shadcn component | `bunx --bun shadcn@latest add <name>` |

## Adding a new procedure

1. Add it under `server/router/<resource>.ts` using `o.handler(...)` (and
   `.input(zod)` if it takes arguments).
2. Re-export it from `server/router/index.ts`.
3. Use it on the client: `useQuery(api.<resource>.<proc>.queryOptions(...))`
   or `useMutation(api.<resource>.<proc>.mutationOptions(...))`. No fetch
   wrappers, no manual types — the `AppRouter` type carries the contract.

## Related repos

- [npuops-platform](https://github.com/dudaji-vn/npuops-platform) — docker compose stack that runs this console alongside LiteLLM, LibreChat, Langfuse, and monitoring.
- [LibreChat fork](https://github.com/dudaji-vn/LibreChat) — chat UI that issues the JWT this console verifies.
