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

All MDX pages live in `content/docs/`. Sidebar grouping is controlled by
`meta.json` files in each folder.

```
content/docs/
├── index.mdx                 # Welcome
├── meta.json                 # Top-level sidebar order
├── overview/                 # What is NUFI, architecture, components
├── getting-started/          # Prerequisites, quick start, verification
├── end-user/                 # Chat, models, agents, files, console keys
├── admin/                    # Admin panel, LiteLLM, Langfuse, Grafana
├── developer/                # Per-repo local dev
├── deployment/               # Compose, SSO, Cloudflare tunnel, monitoring
├── operations/               # Troubleshooting, upgrades, FAQ
└── reference/                # Ports, env vars, glossary
```

Add a new page by dropping an `.mdx` file with frontmatter (`title`,
`description`) into a folder and re-running `pnpm dev`.
