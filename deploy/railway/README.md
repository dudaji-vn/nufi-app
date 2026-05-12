# nufi-chat

Standalone LibreChat deploy that runs **alongside** the production `chat.codechi.me` instance on the same VM. Pulls a pre-built image from the fork (`ghcr.io/dudaji-vn/librechat:npuops-main`), uses its own MongoDB, and talks to the codechi LiteLLM proxy over the shared Docker network — no source code, no Cloudflare round-trip.

Intended as the frontend-development stack while the Korean team finishes the AI gateway.

## Architecture

```
VM
├── npuops-platform stack (running, untouched)
│   ├── npuops-librechat    → chat.codechi.me   (port 3080)
│   ├── npuops-litellm       (port 4000, network `npuops_npuops`)
│   └── ...
└── nufi-chat stack (this repo)
    ├── nufi-chat-api       → chat.nufi.me      (port 3081)
    │     └── joins npuops_npuops to reach litellm-proxy:4000
    └── nufi-chat-mongo     (own data, no overlap with prod)
```

## Prerequisites

On the VM:
- `npuops-platform` already running (`docker compose ps` shows containers healthy)
- Docker network `npuops_npuops` exists (`docker network ls | grep npuops`)
- Image `ghcr.io/dudaji-vn/librechat:npuops-main` pullable (run `docker login ghcr.io` first if the package is private)

## Deploy

```bash
git clone https://github.com/dudaji-vn/nufi-chat.git
cd nufi-chat
./bootstrap.sh
```

The script creates `.env` from `.env.example`, generates the JWT / CREDS secrets, auto-detects `LITELLM_MASTER_KEY` from a sibling `npuops-platform/.env` (with confirmation), prompts for the rest, then runs `docker compose pull && docker compose up -d`.

Re-running it is safe — already-set values are kept; only missing ones are filled.

### Non-interactive variant

```bash
./bootstrap.sh --yes        # accept all defaults / auto-detect, no prompts
./bootstrap.sh --no-up      # configure .env only, don't start the stack
```

### Manual variant (if you prefer)

```bash
cp .env.example .env
{
  echo "JWT_SECRET=$(openssl rand -hex 32)"
  echo "JWT_REFRESH_SECRET=$(openssl rand -hex 32)"
  echo "CREDS_KEY=$(openssl rand -hex 32)"
  echo "CREDS_IV=$(openssl rand -hex 16)"
} >> .env
grep '^LITELLM_MASTER_KEY=' ~/npuops-platform/.env >> .env
docker compose pull
docker compose up -d
```

Open `http://<VM_IP>:3081`, register an account, pick a model, send a message. The model list is fetched from `litellm-proxy:4000/v1/models` — same as the prod chat — so all models registered on codechi appear here too.

## Verify

```bash
# Both containers healthy
docker compose ps

# Health endpoint
curl http://localhost:3081/api/health

# Internal DNS reaches the codechi LiteLLM proxy
docker compose exec api wget -qO- http://litellm-proxy:4000/health/liveliness
```

If the last command fails with `bad address`, fall back to the container name: edit `librechat.yaml` and change `baseURL` to `http://npuops-litellm:4000/v1`.

## Update after fork code changes

When `dudaji-vn/LibreChat` (`npuops/main`) is pushed and the CI build finishes:

```bash
docker compose pull
docker compose up -d
```

## Update config (this repo)

```bash
git pull
docker compose up -d --force-recreate
```

## Teardown

```bash
docker compose down -v   # -v drops the mongo-data volume
```

## Future work

- Cloudflare Tunnel route `chat.nufi.me` → `nufi-chat-api:3081`
- Swap `LITELLM_MASTER_KEY` for a virtual key with its own budget (created via `console.codechi.me`)
- Once the Korean AI gateway lands, change the `baseURL` in `librechat.yaml` to the new endpoint
