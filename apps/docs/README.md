# NUFI Docs

User manual for the entire NUFI AI platform — chat, console, admin panel, and
self-hosted deployment. Built with [Fumadocs](https://fumadocs.dev) on top of
Next.js 15 + MDX.

## Run locally

```bash
pnpm install
pnpm dev          # → http://localhost:3000
```

## Build

```bash
pnpm build
pnpm start
```

## Content layout

All MDX pages live in `content/docs/`. The sidebar is one tree: every section
is visible at once, only the section you are reading is expanded, and
Prev/Next runs straight through from Overview to Reference. The order of
folders in `content/docs/meta.json` is both the sidebar order and the
Prev/Next order; each folder's own `meta.json` orders its pages and groups
them with `---Label---` separators. Do not mark a folder `root: true` — that
turns it back into a tab that hides the other sections and fences Prev/Next
inside it. Do not list `index` in a folder's `pages` either: leaving it out
makes the folder header the link to that intro page; listing it repeats the
intro as a first child with the same label.

```
content/docs/
├── index.mdx                 # Welcome — a task router, not a section list
├── meta.json                 # Section order (= reading order)
├── overview/                 # What NUFI is, architecture, components, security
├── end-user/                 # Chat, models, agents, files, teams, API keys
├── studio/                   # NUFI Studio: flows on a canvas, publish as endpoint
├── works/                    # NUFI Works: agents, tasks, approvals, costs
├── admin/                    # Admin panel, roles, LiteLLM, Langfuse, Grafana
├── deployment/               # Compose, SSO, tunnel, monitoring, troubleshooting
├── developer/                # Local stack, the codebases, release flow, design notes
└── reference/                # Ports, env vars, glossary
```

Moved a page? Add a permanent redirect in `next.config.mjs` so old links keep
resolving.

Add a new page by dropping an `.mdx` file with frontmatter (`title`,
`description`) into a folder and re-running `pnpm dev`.
