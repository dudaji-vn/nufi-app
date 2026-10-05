# Privileged exec sidecar: holds the docker socket, runs ONLY the allowlisted
# commands from the shared owner-console/src/exec-core.ts (single source of truth).
# BUILD CONTEXT = deploy/box (so exec-core can be copied from a sibling dir):
#   docker build -f owner-exec/Dockerfile .   (run from deploy/box)
# The relative layout is preserved so `../../owner-console/src/exec-core` resolves.
FROM oven/bun:1.4.2-alpine
RUN apk add --no-cache docker-cli docker-cli-compose
WORKDIR /app/owner-exec
COPY owner-exec/package.json owner-exec/bun.lock ./
RUN bun install --frozen-lockfile --production
COPY owner-console/src/exec-core.ts /app/owner-console/src/exec-core.ts
COPY owner-exec/src ./src
ENV EXEC_SOCK=/sock/exec.sock NUFI_STATE_DIR=/state
# Runs as root by design: it holds the docker socket; the allowlist is the control.
RUN mkdir -p /sock /state
ENTRYPOINT ["bun", "run", "src/server.ts"]
