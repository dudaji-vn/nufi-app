# NPUOps soft fork of LibreChat.
#
# Tracks upstream tag v0.7.5 via the `source/` submodule. Customizations live
# as `.patch` files in `patches/` and are applied before `npm install` so the
# React build picks them up. To track a newer upstream:
#
#   1. cd librechat/source && git fetch && git checkout <new-tag>
#   2. cd .. && for p in patches/*.patch; do
#        git -C source apply --check "../$p" || echo "REBASE: $p"
#      done
#   3. fix any conflicting patches, commit the submodule SHA
#
# Build context is `librechat/` (parent of `source/`) so the patches dir is
# visible. The submodule MUST be initialized before building:
#
#   git submodule update --init librechat/source
#
# Mirrors upstream's single-stage build (source/Dockerfile, v0.7.5) so any
# layout changes there are easy to port.

FROM node:20-alpine

# Use sh's pipefail in RUN steps below so a failure inside a pipeline
# (e.g. `grep | while read`) breaks the build instead of being swallowed.
SHELL ["/bin/sh", "-o", "pipefail", "-c"]

# Mirrors upstream Dockerfile: no apk version pin (the alpine package
# index moves on every base-image refresh; we follow upstream's convention).
# hadolint ignore=DL3018
RUN apk --no-cache add curl git

RUN mkdir -p /app && chown node:node /app
WORKDIR /app

# Copy patches first so the layer cache invalidates only when patches change.
COPY --chown=node:node patches/ /patches/

# Copy upstream source (submodule checkout).
COPY --chown=node:node source/ /app/

USER node

# Apply every patch in lexicographic order. Fail fast if any patch doesn't
# apply cleanly — that's the signal to rebase against a new upstream tag.
#
# Before applying, strip CRLF on each file the patch is about to touch
# (parsed from the `+++ b/...` headers). Windows clones with default
# `core.autocrlf=true` check out submodule files with CRLF, which makes
# `git apply` reject patches against LF context. This auto-scales to any
# number of patches without listing files explicitly.
#
# DL4006: the embedded `set -eu` re-invokes /bin/sh, so the global SHELL
# pipefail above doesn't propagate. The pipeline below would lose its exit
# code on a `grep` failure — but `grep` here ignores its exit code by
# design (a patch with no `+++ b/` lines is a no-op header check, not an
# error). Suppressing the warning is correct, not just convenient.
# hadolint ignore=DL4006
RUN set -eu; \
    for p in /patches/*.patch; do \
        [ -e "$p" ] || { echo "No patches to apply (zero-patch parity build)"; break; }; \
        grep -E '^\+\+\+ b/' "$p" | sed 's|^+++ b/||' | while IFS= read -r f; do \
            [ -f "/app/$f" ] && sed -i 's/\r$//' "/app/$f"; \
        done; \
        echo "Applying $p"; \
        git apply --verbose "$p"; \
    done

# Build-time customization. Vite inlines VITE_* env vars into the bundle, so
# changing CONSOLE_URL requires rebuilding the image — that's by design here:
# the console runs alongside LibreChat in the same compose stack, so the URL
# is part of the deployment, not per-request config.
ARG CONSOLE_URL=
ENV VITE_CONSOLE_URL=$CONSOLE_URL

RUN \
    touch .env ; \
    mkdir -p /app/client/public/images /app/api/logs ; \
    npm config set fetch-retry-maxtimeout 600000 ; \
    npm config set fetch-retries 5 ; \
    npm config set fetch-retry-mintimeout 15000 ; \
    npm install --no-audit ; \
    NODE_OPTIONS="--max-old-space-size=2048" npm run frontend ; \
    npm prune --production ; \
    npm cache clean --force

RUN mkdir -p /app/client/public/images /app/api/logs

EXPOSE 3080
ENV HOST=0.0.0.0
CMD ["npm", "run", "backend"]
