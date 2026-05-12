# nufi-chat

Self-hosted LibreChat deployment that talks to an external LiteLLM proxy over a shared Docker network.

## Prerequisites

- Docker Engine + Compose plugin
- `openssl`
- An existing LiteLLM proxy reachable on a Docker network. By default this repo expects:
  - Network name: `npuops_npuops`
  - Service hostname: `litellm-proxy` on port `4000`
  - A master key for that proxy

Change these in `docker-compose.yml` and `librechat.yaml` if your setup differs.

## Quick start

```bash
git clone https://github.com/dudaji-vn/nufi-chat.git
cd nufi-chat
./bootstrap.sh
```

The script:

1. Verifies prerequisites and that the LiteLLM network exists
2. Creates `.env` from `.env.example`
3. Generates `JWT_SECRET`, `JWT_REFRESH_SECRET`, `CREDS_KEY`, `CREDS_IV`
4. Auto-detects `LITELLM_MASTER_KEY` from a sibling `npuops-platform/.env` if present, otherwise prompts
5. Prompts for `DOMAIN_CLIENT`, `DOMAIN_SERVER`, `APP_TITLE`
6. Runs `docker compose pull` and `docker compose up -d`

Re-running is safe — values already in `.env` are kept; only missing ones are filled.

### Flags

```bash
./bootstrap.sh --yes      # no prompts; use defaults and auto-detected values
./bootstrap.sh --no-up    # configure .env only, don't start containers
./bootstrap.sh --help
```

### Manual setup

```bash
cp .env.example .env
{
  echo "JWT_SECRET=$(openssl rand -hex 32)"
  echo "JWT_REFRESH_SECRET=$(openssl rand -hex 32)"
  echo "CREDS_KEY=$(openssl rand -hex 32)"
  echo "CREDS_IV=$(openssl rand -hex 16)"
} >> .env
# Set LITELLM_MASTER_KEY in .env to your proxy's master key
docker compose pull
docker compose up -d
```

## Configuration

`.env` controls runtime values:

| Variable | Purpose |
|---|---|
| `DOMAIN_CLIENT` | Public URL clients connect to |
| `DOMAIN_SERVER` | Public URL used for emails / OAuth callbacks |
| `APP_TITLE` | Brand title shown in the UI |
| `ALLOW_REGISTRATION` | Allow new user signup (`true` / `false`) |
| `ALLOW_EMAIL_LOGIN` | Allow email/password login |
| `JWT_SECRET`, `JWT_REFRESH_SECRET` | Session signing keys |
| `CREDS_KEY`, `CREDS_IV` | Credential encryption |
| `LITELLM_MASTER_KEY` | Auth header sent to the LiteLLM proxy |

Endpoint and model behaviour lives in `librechat.yaml`. The `baseURL` there points at the LiteLLM proxy and is the value to change when your proxy moves.

## Verify

```bash
docker compose ps
curl http://localhost:3081/api/health
docker compose exec api wget -qO- http://litellm-proxy:4000/health/liveliness
```

If the last command returns `bad address`, change `baseURL` in `librechat.yaml` to use the proxy's container name instead of its service name.

Open `http://<host>:3081`, register an account, pick a model from the dropdown (fetched live from the proxy), and send a message.

## Common commands

```bash
docker compose logs -f api          # tail application logs
docker compose pull && docker compose up -d   # apply image updates
git pull && docker compose up -d --force-recreate   # apply config updates
docker compose down                 # stop containers, keep data
docker compose down -v              # stop and drop mongo data
```

## Troubleshooting

**`network npuops_npuops not found`** — start the LiteLLM proxy stack first, or change the network name in `docker-compose.yml`.

**`Server listening` never appears in logs** — check `docker compose logs api` for missing `.env` values; re-run `./bootstrap.sh`.

**Model dropdown is empty** — the proxy isn't reachable. Verify with `docker compose exec api wget -qO- http://litellm-proxy:4000/health/liveliness`. If that works but `/v1/models` is empty, check that the LiteLLM proxy has models registered.

**Cannot pull image** — run `docker login ghcr.io` with a personal access token that has `read:packages`.

## Ports

| Port | Container | Purpose |
|---|---|---|
| 3081 | `nufi-chat-api` | HTTP, exposed on host |
| 27017 | `nufi-chat-mongo` | MongoDB, internal only |
