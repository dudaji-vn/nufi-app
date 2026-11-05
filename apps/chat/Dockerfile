# v0.8.6-rc1
#
# Multi-stage. The heavy `npm ci` installs every dependency, including the dev
# deps needed to build the client, so it runs in a build stage. The runtime
# stage copies only the pruned, production `/app` — the final image never
# carries the ~2.5 GB dev-deps layer a single-stage build keeps even after
# `npm prune --production` (a later RUN cannot shrink the earlier `npm ci`
# layer; it only hides files behind a whiteout). Runtime is unchanged from the
# single-stage image: same base, jemalloc, uv, working directory and CMD, and
# the same pruned `/app` the single-stage image already ran.

ARG NODE_MAX_OLD_SPACE_SIZE=6144
ARG NPM_CI_TIMEOUT_SECONDS=1500
ARG NPM_CI_ATTEMPTS=2

# ---- Build: all deps, build the client, prune to production ----
FROM node:20-alpine AS build
ARG NODE_MAX_OLD_SPACE_SIZE
ARG NPM_CI_TIMEOUT_SECONDS
ARG NPM_CI_ATTEMPTS

RUN apk upgrade --no-cache
# python3/pip for any node-gyp native build during npm ci (as the single-stage
# image installed them before npm ci).
RUN apk add --no-cache python3 py3-pip

RUN mkdir -p /app && chown node:node /app
WORKDIR /app
USER node

COPY --chown=node:node package.json package-lock.json ./
COPY --chown=node:node api/package.json ./api/package.json
COPY --chown=node:node client/package.json ./client/package.json
COPY --chown=node:node packages/data-provider/package.json ./packages/data-provider/package.json
COPY --chown=node:node packages/data-schemas/package.json ./packages/data-schemas/package.json
COPY --chown=node:node packages/api/package.json ./packages/api/package.json

RUN \
    # Allow mounting of these files, which have no default
    touch .env ; \
    # Create directories for the volumes to inherit the correct permissions
    mkdir -p /app/client/public/images /app/logs /app/uploads ; \
    npm config set fetch-retry-maxtimeout 600000 ; \
    npm config set fetch-retries 5 ; \
    npm config set fetch-retry-mintimeout 15000 ; \
    attempt=1 ; \
    until timeout "$NPM_CI_TIMEOUT_SECONDS" npm ci --no-audit ; do \
        status=$? ; \
        if [ "$attempt" -ge "$NPM_CI_ATTEMPTS" ]; then \
            exit "$status" ; \
        fi ; \
        echo "npm ci --no-audit failed with exit code $status; retrying attempt $((attempt + 1))/$NPM_CI_ATTEMPTS" ; \
        attempt=$((attempt + 1)) ; \
        npm cache clean --force || true ; \
        sleep 10 ; \
    done

COPY --chown=node:node . .

RUN \
    # React client build with configurable memory
    NODE_OPTIONS="--max-old-space-size=${NODE_MAX_OLD_SPACE_SIZE}" npm run frontend ; \
    npm prune --production ; \
    npm cache clean --force

# ---- Runtime: the pruned /app only, same entrypoint as the single-stage image ----
FROM node:20-alpine AS node

RUN apk upgrade --no-cache
RUN apk add --no-cache jemalloc
RUN apk add --no-cache python3 py3-pip uv

# Set environment variable to use jemalloc
ENV LD_PRELOAD=/usr/lib/libjemalloc.so.2

# Add `uv` for extended MCP support
COPY --from=ghcr.io/astral-sh/uv:0.9.5-python3.12-alpine /usr/local/bin/uv /usr/local/bin/uvx /bin/
RUN uv --version

RUN mkdir -p /app && chown node:node /app
WORKDIR /app
USER node

COPY --from=build --chown=node:node /app /app

# Node API setup
EXPOSE 3080
ENV HOST=0.0.0.0
CMD ["npm", "run", "backend"]
