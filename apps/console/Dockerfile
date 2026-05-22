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
# Vite copies the contents of public/ to dist/ at build time. Holds the
# brand logo (referenced as /nufi-logo.svg from the SPA) and any future
# static assets — required for the runtime stage to serve them.
COPY public ./public

# Where the chat UI lives. Inlined into the Vite bundle so the unauthorized
# page can deep-link users back to sign in. Override via build-args in CI
# (see .github/workflows/docker-publish.yml).
ARG LIBRECHAT_URL=http://localhost:3080
ENV VITE_LIBRECHAT_URL=$LIBRECHAT_URL

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
