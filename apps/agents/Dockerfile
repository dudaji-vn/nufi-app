# syntax=docker/dockerfile:1.20
FROM node:lts-trixie-slim AS base
ARG USER_UID=1000
ARG USER_GID=1000
RUN apt-get update \
  && apt-get install -y --no-install-recommends ca-certificates gosu curl gh git wget ripgrep python3 \
  && rm -rf /var/lib/apt/lists/* \
  && corepack enable

# Modify the existing node user/group to have the specified UID/GID to match host user
RUN usermod -u $USER_UID --non-unique node \
  && groupmod -g $USER_GID --non-unique node \
  && usermod -g $USER_GID -d /paperclip node

FROM base AS deps
WORKDIR /app
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml .npmrc ./
COPY cli/package.json cli/
COPY server/package.json server/
COPY ui/package.json ui/
COPY packages/shared/package.json packages/shared/
COPY packages/db/package.json packages/db/
COPY packages/adapter-utils/package.json packages/adapter-utils/
COPY packages/google-sheets-mcp-server/package.json packages/google-sheets-mcp-server/
COPY packages/kv-demo-mcp-server/package.json packages/kv-demo-mcp-server/
COPY packages/mcp-server/package.json packages/mcp-server/
COPY packages/skills-catalog/package.json packages/skills-catalog/
COPY packages/teams-catalog/package.json packages/teams-catalog/
COPY packages/adapters/claude-local/package.json packages/adapters/claude-local/
COPY packages/adapters/codex-local/package.json packages/adapters/codex-local/
COPY packages/adapters/cursor-cloud/package.json packages/adapters/cursor-cloud/
COPY packages/adapters/cursor-local/package.json packages/adapters/cursor-local/
COPY packages/adapters/gemini-local/package.json packages/adapters/gemini-local/
COPY packages/adapters/grok-local/package.json packages/adapters/grok-local/
COPY packages/adapters/hermes/package.json packages/adapters/hermes/
COPY packages/adapters/hermes-gateway/package.json packages/adapters/hermes-gateway/
COPY packages/adapters/openclaw-gateway/package.json packages/adapters/openclaw-gateway/
COPY packages/adapters/opencode-local/package.json packages/adapters/opencode-local/
COPY packages/adapters/pi-local/package.json packages/adapters/pi-local/
COPY packages/plugins/sdk/package.json packages/plugins/sdk/
COPY --parents packages/plugins/sandbox-providers/./*/package.json packages/plugins/sandbox-providers/
COPY packages/plugins/paperclip-plugin-fake-sandbox/package.json packages/plugins/paperclip-plugin-fake-sandbox/
COPY packages/plugins/plugin-llm-wiki/package.json packages/plugins/plugin-llm-wiki/
COPY packages/plugins/plugin-workspace-diff/package.json packages/plugins/plugin-workspace-diff/
COPY patches/ patches/
COPY scripts/link-plugin-dev-sdk.mjs scripts/

RUN pnpm install --frozen-lockfile

FROM base AS build
WORKDIR /app
COPY --from=deps /app /app
COPY . .
RUN pnpm --filter @paperclipai/ui build
RUN pnpm --filter @paperclipai/plugin-sdk build
RUN pnpm --filter @paperclipai/server build
RUN test -f server/dist/index.js || (echo "ERROR: server build output missing" && exit 1)
# The NuFi adapter is an EXTERNAL adapter: it lives in nufi/ rather than
# packages/adapters/ so it needs no upstream source change, and the fork guard
# rejects additions there anyway. The cost of that choice is that nothing else
# builds it -- nufi/adapter/dist is gitignored, so an image without this line
# ships a server that cannot offer `nufi_agent` at all, which is the only
# adapter that routes model calls through the NuFi gateway.
# --ignore-workspace: this package is deliberately outside pnpm-workspace.yaml
# (nufi/ is NuFi-owned; adding it to the workspace file would be an upstream
# edit), so it installs its own typescript and @types/node. Before it declared
# them it compiled only where a hoisted linker happened to expose the server's
# copies -- true on a dev box, false here, where tsc failed with
# "Cannot find name 'process'".
RUN pnpm --dir nufi/adapter install --frozen-lockfile --ignore-workspace
RUN pnpm --dir nufi/adapter build
RUN test -f nufi/adapter/dist/index.js || (echo "ERROR: nufi adapter build output missing" && exit 1)
# The box's Docker sandbox provider (packages/plugins/sandbox-providers/docker)
# is outside the pnpm workspace like every sandbox provider, so nothing above
# builds it -- and the box installs it with plugin auto-build OFF, because a
# plugin install must never reach for npm from inside a box. Built here, with
# its one runtime dependency (dockerode) installed beside it. The
# @paperclipai/plugin-sdk link comes from the root postinstall
# (scripts/link-plugin-dev-sdk.mjs); it is re-run because an --ignore-workspace
# install may prune a link it did not make.
RUN pnpm --dir packages/plugins/sandbox-providers/docker install --frozen-lockfile --ignore-workspace \
 && node scripts/link-plugin-dev-sdk.mjs \
 && pnpm --dir packages/plugins/sandbox-providers/docker build
RUN test -f packages/plugins/sandbox-providers/docker/dist/manifest.js \
 && test -f packages/plugins/sandbox-providers/docker/dist/worker.js \
 && test -e packages/plugins/sandbox-providers/docker/node_modules/dockerode \
 && test -e packages/plugins/sandbox-providers/docker/node_modules/@paperclipai/plugin-sdk \
 || (echo "ERROR: docker sandbox provider build output missing" && exit 1)

FROM base AS production
ARG USER_UID=1000
ARG USER_GID=1000
WORKDIR /app
COPY --chown=node:node --from=build /app /app
RUN npm install --global --omit=dev @anthropic-ai/claude-code@latest @openai/codex@latest opencode-ai @google/gemini-cli@latest \
  && apt-get update \
  && apt-get install -y --no-install-recommends openssh-client jq \
  && rm -rf /var/lib/apt/lists/* \
  && mkdir -p /paperclip \
  && chown node:node /paperclip

COPY scripts/docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

ENV NODE_ENV=production \
  HOME=/paperclip \
  HOST=0.0.0.0 \
  PORT=3100 \
  SERVE_UI=true \
  PAPERCLIP_HOME=/paperclip \
  PAPERCLIP_INSTANCE_ID=default \
  USER_UID=${USER_UID} \
  USER_GID=${USER_GID} \
  PAPERCLIP_CONFIG=/paperclip/instances/default/config.json \
  PAPERCLIP_DEPLOYMENT_MODE=authenticated \
  PAPERCLIP_DEPLOYMENT_EXPOSURE=private \
  OPENCODE_ALLOW_ALL_MODELS=true \
  GEMINI_SANDBOX=false

EXPOSE 3100

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["node", "--import", "./server/node_modules/tsx/dist/loader.mjs", "server/dist/index.js"]
