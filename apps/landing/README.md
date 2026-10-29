# nufi-landing

Marketing site for **NuFi Box** — the private, on-premise AI appliance. Introduces
the box, hosts the use-case blog, and links to the documentation.

Deployed at **box.nufi.me**.

## Stack

- Vite + React 19 + [TanStack Router](https://tanstack.com/router) (client-side, 3 routes)
- Global stylesheet (`src/styles.css`) — the NuFi brand theme, light + dark, no CSS framework
- Served in production by a small bun + Hono server (`server.ts`) with an SPA fallback

## Routes

| Path | Page |
| --- | --- |
| `/` | Landing — intro, how it works, features, use case, docs CTA |
| `/blog` | Blog index — seeded with the HR use-case post |
| `/blog/hr-private-document-qa` | The HR private-document Q&A post |

## Develop

```sh
bun install
bun run dev        # vite dev server
bun run typecheck  # tsc --noEmit
bun run build      # -> dist/
bun run start      # serve dist/ on $PORT (default 3000)
```

## Deploy (Railway)

Build the `Dockerfile` (multi-stage: Vite build → bun+Hono runtime, listens on
`$PORT`). Point a Railway service at `apps/landing` and attach the `box.nufi.me`
domain. No environment variables are required.

## Content

Product and blog screenshots live in `public/shots/` and `public/blog/` — real,
unretouched captures from a live NuFi Box (the handbook shown is a synthetic
sample). The blog post text mirrors the published "private document Q&A" use case.
Docs links point at the box guide: `https://docs.app.nufi.me/docs/box`.
