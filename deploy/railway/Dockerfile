# Wrapper image for PaaS deployments (Railway, Fly.io, etc.) that cannot
# bind-mount librechat.yaml at runtime. Local docker-compose still uses the
# base image directly with a volume mount.
#
# Override BASE at build time to upgrade (Railway: set as a service variable):
#   BASE=ghcr.io/dudaji-vn/nufichat:nufi-v0.8.6
#
# Pin BASE to a sha256 digest in production:
#   docker pull ghcr.io/dudaji-vn/nufichat:main
#   docker inspect --format='{{index .RepoDigests 0}}' ghcr.io/dudaji-vn/nufichat:main
#   → ghcr.io/dudaji-vn/nufichat@sha256:<digest>
ARG BASE=ghcr.io/dudaji-vn/nufichat:main
FROM ${BASE}

COPY librechat.yaml /app/librechat.yaml

# Railway's ephemeral disk (~230MB free) is below LibreChat's 500MB startup
# floor. The check source is bundled deep; patch the uncaughtException
# handler so the process doesn't exit(1) on disk-space errors.
RUN sed -i 's|process.exit(1);|if (err \&\& err.message \&\& err.message.includes("disk space")) { return; } process.exit(1);|' \
    /app/api/server/index.js
