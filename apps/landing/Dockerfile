# NuFi Box marketing site. Vite build -> static dist, served by bun + Hono.
# Mirrors apps/admin-panel: oven/bun alpine, PORT env, non-root bun user.
FROM oven/bun:1.3.11-alpine AS base
WORKDIR /app

# --- Install ---
FROM base AS deps
COPY package.json bun.lock ./
RUN bun install --frozen-lockfile

# --- Build ---
FROM base AS build
COPY --from=deps /app/node_modules node_modules
COPY . .
ENV NODE_ENV=production
RUN bun run build

# --- Runtime ---
FROM base AS runtime
ENV NODE_ENV=production
COPY --from=deps /app/node_modules node_modules
COPY --from=build /app/dist dist
COPY server.ts package.json ./
RUN chown -R bun:bun /app
USER bun
ENV PORT=3000
EXPOSE 3000
CMD ["bun", "run", "server.ts"]
