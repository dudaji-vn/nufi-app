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

# Only what the frontend build actually reads: index.css imports brand.css,
# brand.css references ./fonts, and vite.config.mts imports rebrand.ts. Copying
# the whole nufi/ directory also copies this Dockerfile, so every edit to it
# invalidated the npm-install and vite layers below for no reason.
COPY nufi/rebrand.ts nufi/brand.css /app/nufi/
COPY nufi/fonts /app/nufi/fonts
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

# A build that succeeds is not evidence of a branded image. The rename is a
# Vite plugin wired in through vite.config.mts; lose the plugin and the build
# still succeeds, still deploys, and greets a customer by the upstream name.
# Asserting here means an unbranded image cannot be produced at all -- better
# than a CI step that checks after the tag is already public.
#
# The bare-word test matches nufi/check-brand-css.sh: compound identifiers like
# LangflowTooltip and translation KEYS like builtWithLangflow are deliberately
# left alone by the rename, so only \bLangflow\b counts.
RUN set -eu; \
    d=./src/backend/base/langflow/frontend; \
    if [ ! -f "$d/index.html" ]; then \
      echo "the frontend was never copied into the image"; exit 1; fi; \
    if ! grep -q 'NUFI Studio' "$d/index.html"; then \
      echo "index.html does not carry the product name -- the rebrand plugin did not run"; exit 1; fi; \
    if grep -qi 'langflow' "$d/index.html"; then \
      echo "index.html still names the upstream product"; exit 1; fi; \
    if grep -rq '\bLangflow\b' "$d"/assets/*.js; then \
      echo "compiled JS still carries the bare word Langflow"; exit 1; fi; \
    echo "brand assertion passed"

# --extra postgresql pulls the drivers Langflow needs to speak to Postgres;
# pyproject declares them in an optional group, so a plain sync installs
# neither and SQLAlchemy dies at boot with ModuleNotFoundError: psycopg2.
# Missed originally because the image was only ever exercised against the
# SQLite default -- not the configuration production actually runs.
RUN uv sync --frozen --no-dev --extra postgresql
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 7860
CMD ["sh", "-c", "langflow run --host 0.0.0.0 --port ${PORT}"]
