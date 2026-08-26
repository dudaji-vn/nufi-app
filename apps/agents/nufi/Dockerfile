# syntax=docker/dockerfile:1.7
#
# NUFI Works — upstream's image with the NuFi rename applied to server/dist.
#
# Why a wrapper rather than an edit to ../Dockerfile: that file is not in the
# fork allowlist, and a copy of it here would drift out of date on the next
# subtree pull. Wrapping is also the shape the chat app already uses on
# Railway, so this is the house pattern rather than a new one.
#
# Why server/dist needs anything at all: ui/dist is renamed by a Vite plugin
# during the upstream build, wired in through the allowlisted ui/vite.config.ts.
# tsc has no equivalent hook, so the server bundle ships upstream's product
# name unless a pass is run over the output -- see nufi/README.md, "The rename
# covers both bundles".
#
# Build:
#   docker build -f apps/agents/Dockerfile -t nufi-works-base:dev apps/agents
#   docker build --build-arg BASE=nufi-works-base:dev \
#     -f apps/agents/nufi/Dockerfile -t nufi-works:dev apps/agents

ARG BASE
FROM ${BASE} AS branded
WORKDIR /app

# No USER directive: the upstream image leaves the final stage as root and
# drops privileges with gosu inside docker-entrypoint.sh. Pinning a user here
# would take that away from the entrypoint.

# --check runs after the rename and exits non-zero if anything still names the
# upstream product. Without it a silent no-op here would produce an image that
# builds, deploys, and greets a customer by the wrong name.
RUN node nufi/rebrand-server-dist.mjs server/dist \
 && node nufi/rebrand-server-dist.mjs --check server/dist

# Take ownership of the data volume before upstream's entrypoint drops
# privileges. See nufi/docker-entrypoint.sh for why upstream's own chown does
# not fire on Railway.
#
# Done by REPLACING the entrypoint file rather than by setting ENTRYPOINT.
# Declaring ENTRYPOINT in a derived image resets the CMD inherited from the
# base, so upstream's start command silently vanishes and its entrypoint ends
# up running `gosu node` with nothing to exec:
#
#     Usage: gosu user-spec command [args]
#
# Re-declaring CMD here would work but would drift the moment upstream changes
# its start command. Swapping the file leaves both ENTRYPOINT and CMD exactly
# as upstream set them.
RUN mv /usr/local/bin/docker-entrypoint.sh /usr/local/bin/upstream-docker-entrypoint.sh
COPY nufi/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh
