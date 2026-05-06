# syntax=docker/dockerfile:1.7
# ---- Stage 1: install deps + build the SPA ----------------------------------
FROM oven/bun:1.3-alpine AS builder
WORKDIR /app

# Install all deps (incl. dev) so Vite + TanStack Router plugin can run.
COPY package.json bun.lock ./
RUN bun install --frozen-lockfile

# Copy sources and build.
COPY tsconfig.json vite.config.ts components.json index.html ./
COPY src ./src
COPY server ./server

RUN bunx @tanstack/router-cli generate \
 && bun run build

# ---- Stage 2: runtime — only prod deps + built artifacts --------------------
FROM oven/bun:1.3-alpine AS runtime
WORKDIR /app

ENV NODE_ENV=production
ENV PORT=3000

COPY package.json bun.lock ./
RUN bun install --frozen-lockfile --production

COPY --from=builder /app/dist        ./dist
COPY --from=builder /app/server      ./server

EXPOSE 3000

# Healthcheck hits Hono directly (the oRPC handler isn't on /_health).
HEALTHCHECK --interval=15s --timeout=5s --retries=5 --start-period=15s \
  CMD wget --quiet --tries=1 --spider http://127.0.0.1:3000/_health || exit 1

CMD ["bun", "run", "server/index.ts"]
