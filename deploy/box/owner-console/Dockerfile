# Build the NufiBox Agent bundles (both client arches) so the box can serve them
# offline — the fetch from pkgs.tailscale.com happens HERE, at image build, not
# on the member's machine. `agent` is a named build context (deploy/box/agent);
# box-images passes it, like `templates`.
FROM alpine:3.20 AS agentbuild
RUN apk add --no-cache bash curl tar
COPY --from=agent . /agent-src
RUN cd /agent-src \
 && OUT=/dist ARCH=amd64 ./build-agent.sh \
 && OUT=/dist ARCH=arm64 ./build-agent.sh
# The SIGNED, NOTARIZED macOS .pkg is built on the self-hosted signing Mac (the
# `agent-macos` workflow) and can't be produced here on Linux. box-images fetches
# it from the release into the agent context (deploy/box/agent/dist) before the
# build; copy it in if present. Best-effort: without it, /agent/nufibox-agent-
# macos.pkg simply 404s until a signed release exists.
RUN cp /agent-src/dist/nufibox-agent-macos.pkg /dist/ 2>/dev/null || true

# Build the React SPA (web/) to web/dist; the runtime stage copies only dist.
FROM oven/bun:1.4.2-alpine AS webbuild
WORKDIR /web
COPY web/package.json web/bun.lock* ./
RUN bun install --frozen-lockfile
COPY web ./
RUN bun run build

FROM oven/bun:1.4.2-alpine
WORKDIR /app
# docker CLI + compose plugin: the console's allowlisted control shells out to
# `docker compose` over the mounted socket.
RUN apk add --no-cache docker-cli docker-cli-compose
COPY package.json bun.lock ./
RUN bun install --frozen-lockfile --production
COPY src ./src
COPY entrypoint.sh ./entrypoint.sh
COPY --from=webbuild /web/dist ./web/dist
# The member-connector templates, shared VERBATIM with `nufi-box invite`
# (single source of truth: deploy/box/lib/join-templates). Provided as a named
# build context so this Dockerfile's own context stays deploy/box/owner-console.
# box-images passes it (build-contexts); for a local build add:
#   docker build --build-context templates=../lib/join-templates \
#                --build-context agent=../agent .
COPY --from=templates . ./join-templates
# The de-branded NufiBox Agent bundles the box serves at /agent (both arches).
COPY --from=agentbuild /dist ./agent-dist
ENV PORT=8890 JOIN_TEMPLATES_DIR=/app/join-templates AGENT_DIST_DIR=/app/agent-dist
EXPOSE 8890
USER bun
ENTRYPOINT ["/bin/sh", "/app/entrypoint.sh"]
