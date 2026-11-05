# --- Base ---
FROM oven/bun:1.3.11-alpine AS base
WORKDIR /app

# --- Install ---
FROM base AS deps
COPY package.json bun.lock .npmrc ./
COPY patches/ patches/
COPY tools/ tools/
RUN bun install --frozen-lockfile

# --- Build ---
FROM base AS build
COPY --from=deps /app/node_modules node_modules
COPY . .
ENV NODE_ENV=production
RUN bun run build

# --- Production dependencies (patches applied, then devDeps stripped) ---
FROM base AS prod-deps
COPY package.json bun.lock .npmrc ./
COPY patches/ patches/
COPY tools/ tools/
RUN bun install --frozen-lockfile \
    && bun install --frozen-lockfile --production

# --- Runtime ---
FROM base AS runtime
ENV NODE_ENV=production

# Own the files at copy time. A separate `RUN chown -R bun:bun /app` rewrites
# every file's metadata into a new layer that duplicates all of /app — about
# 680 MB of node_modules and build output copied for nothing. --chown on each
# COPY sets ownership in the same layer.
COPY --from=prod-deps --chown=bun:bun /app/node_modules node_modules
COPY --from=build --chown=bun:bun /app/dist dist
COPY --from=build --chown=bun:bun /app/src/server src/server
COPY --chown=bun:bun server.ts package.json ./

USER bun

ENV PORT=3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD bun -e "fetch(\`http://localhost:\${process.env.PORT}\`).then(r=>{if(!r.ok)throw 1}).catch(()=>process.exit(1))"

EXPOSE 3000
CMD ["bun", "run", "start"]
