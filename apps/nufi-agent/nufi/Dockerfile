# syntax=docker/dockerfile:1.7
#
# NUFI Studio — the Langflow fork, built with the NuFi brand baked in.
#
# Upstream's docker/build_and_push.Dockerfile is not in the fork allowlist, so
# the NuFi image is defined here instead of by patching that file.
#
# Two things this reproduces on purpose, because they are what makes the image
# branded rather than merely built:
#
#   1. The frontend is built from src/frontend with nufi/ present as a sibling.
#      src/frontend/src/style/index.css imports ../../../../nufi/brand.css and
#      vite.config.mts imports ../../nufi/rebrand -- both resolve above the
#      frontend directory, so the build context has to carry nufi/ too.
#   2. The built assets land in src/backend/base/langflow/frontend, which is
#      what Makefile.frontend's build_frontend target does after vite writes
#      to src/frontend/build. Langflow serves that directory; skipping the move
#      produces an image that boots and has no UI.
#
# Workspace members install editable, so the copied frontend is served straight
# from the source tree -- the same arrangement a developer runs locally.

# ---- Stage 1: the rebranded frontend ---------------------------------------
FROM node:22-slim AS frontend
WORKDIR /app/src/frontend

# Puppeteer is pulled in by the frontend's test tooling and downloads a
# Chromium build on install. node:22-slim ships no tar or unzip, so that
# download fails and takes `npm ci` down with it. Installing an archiver to
# satisfy it would be the wrong fix: a production bundle needs no browser.
ENV PUPPETEER_SKIP_DOWNLOAD=1

# Node sizes its heap from the cgroup limit, which inside a build container is
# far below what this bundle needs -- the default aborts with a heap OOM part
# way through `vite build`. 4 GB is enough here and stays under a standard
# CI runner's memory.
ENV NODE_OPTIONS=--max-old-space-size=4096

COPY src/frontend/package.json src/frontend/package-lock.json ./
RUN npm ci

COPY nufi /app/nufi
COPY src/frontend ./
RUN npm run build

# ---- Stage 2: python runtime ------------------------------------------------
FROM python:3.12-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    PORT=7860
WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential curl git libpq-dev \
 && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY --from=frontend /app/src/frontend/build ./src/backend/base/langflow/frontend

RUN uv sync --frozen --no-dev
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 7860
CMD ["sh", "-c", "langflow run --host 0.0.0.0 --port ${PORT}"]
