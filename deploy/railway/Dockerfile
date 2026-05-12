# Wrapper image for PaaS deployments (Railway, Fly.io, etc.) that cannot
# bind-mount librechat.yaml at runtime. Local docker-compose still uses the
# base image directly with a volume mount.
#
# Pin BASE to a sha256 digest in production:
#   docker pull ghcr.io/dudaji-vn/librechat:npuops-main
#   docker inspect --format='{{index .RepoDigests 0}}' ghcr.io/dudaji-vn/librechat:npuops-main
#   → ghcr.io/dudaji-vn/librechat@sha256:<digest>
ARG BASE=ghcr.io/dudaji-vn/librechat:npuops-main
FROM ${BASE}

COPY librechat.yaml /app/librechat.yaml
