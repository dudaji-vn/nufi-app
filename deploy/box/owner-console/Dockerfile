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

FROM oven/bun:1.4.2-alpine
WORKDIR /app
COPY package.json bun.lock ./
RUN bun install --frozen-lockfile --production
COPY src ./src
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
CMD ["bun", "run", "src/server.ts"]
