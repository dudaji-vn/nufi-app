# nufi-sandbox -- what an agent's code runs in on the box.
#
# One image for every coding harness the box's adapter file enables, because
# the Docker provider (apps/agents/packages/plugins/sandbox-providers/docker)
# takes one image per environment. Upstream's per-adapter runtime images are
# Ubuntu + Node + one CLI each; this is the union, on the box's own base.
#
# Ubuntu, not Alpine, on purpose: the provider wraps every exec in GNU
# coreutils' `timeout -s KILL`, and busybox's timeout cannot signal the way
# the deadline needs (see the provider's README, "The deadline").
FROM ubuntu:24.04@sha256:69cecf4bbf72d2d44a9eef1b71fb98c7fb973d78af11399deccef19beb008ad9

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl gnupg git ripgrep python3 \
 && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && rm -rf /var/lib/apt/lists/*

# The three harnesses the box enables (works/adapters.json). Exact versions:
# a sandbox that pulls "latest" at build time is a sandbox nobody can
# reproduce. Bump on purpose.
RUN npm install -g --omit=dev \
      @openai/codex@0.154.0 \
      @anthropic-ai/claude-code@2.1.273 \
      opencode-ai@1.18.31 \
 && npm cache clean --force

# ubuntu:24.04 ships uid 1000 as `ubuntu`; the provider runs the container as
# whatever the image says, and A's spec says not root.
RUN mkdir -p /workspace && chown 1000:1000 /workspace
USER 1000:1000
WORKDIR /workspace
# The rootfs is read-only under the provider (only /workspace and /tmp are
# writable); the harnesses keep their config under $HOME, so HOME is the
# workspace.
ENV HOME=/workspace
# The provider sets Cmd to `sleep infinity` and execs into the container; this
# is only what a bare `docker run` of the image does.
CMD ["sleep", "infinity"]
