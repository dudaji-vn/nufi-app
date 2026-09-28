FROM oven/bun:1.4.2-alpine
WORKDIR /app
COPY package.json bun.lock ./
RUN bun install --frozen-lockfile --production
COPY src ./src
# The member-connector templates, shared VERBATIM with `nufi-box invite`
# (single source of truth: deploy/box/lib/join-templates). Provided as a named
# build context so this Dockerfile's own context stays deploy/box/owner-console.
# box-images passes it (build-contexts); for a local build add:
#   docker build --build-context templates=../lib/join-templates .
COPY --from=templates . ./join-templates
ENV PORT=8890 JOIN_TEMPLATES_DIR=/app/join-templates
EXPOSE 8890
USER bun
CMD ["bun", "run", "src/server.ts"]
