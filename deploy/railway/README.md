# nufi-chat

Self-hosted LibreChat deployment that talks to any OpenAI-compatible LLM endpoint.

## Prerequisites

- Docker Engine + Compose plugin
- `openssl`
- A reachable OpenAI-compatible API endpoint and its bearer key. Anything that speaks the OpenAI Chat Completions API works — OpenAI itself, OpenRouter, Together, Groq, LiteLLM, vLLM, TGI, etc.

The endpoint can be:
- A public URL — `https://api.openai.com/v1`
- A LAN address — `http://192.168.1.10:4000/v1`
- A service on another Compose stack on the same host, reachable by Docker service name — `http://litellm-proxy:4000/v1` (requires shared-network mode, see below)

## Quick start

```bash
git clone https://github.com/dudaji-vn/nufi-chat.git
cd nufi-chat
./bootstrap.sh
```

The script:

1. Verifies prerequisites
2. Creates `.env` from `.env.example`
3. Generates `JWT_SECRET`, `JWT_REFRESH_SECRET`, `CREDS_KEY`, `CREDS_IV`
4. Prompts for `DOMAIN_CLIENT`, `DOMAIN_SERVER`, `APP_TITLE`, `BACKEND_BASE_URL`
5. Auto-detects `BACKEND_API_KEY` from a sibling stack's `.env` if present, otherwise prompts
6. Asks whether to enable shared-network mode (needed only when `BACKEND_BASE_URL` uses a Docker service name)
7. Runs `docker compose pull` and `docker compose up -d`

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
# Set BACKEND_BASE_URL and BACKEND_API_KEY in .env
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
| `BACKEND_BASE_URL` | OpenAI-compatible endpoint URL |
| `BACKEND_API_KEY` | Bearer key sent to that endpoint |
| `SHARED_DOCKER_NETWORK` | Name of the external network when shared-network mode is on |

Endpoint behaviour lives in `librechat.yaml`. `baseURL` and `apiKey` are interpolated from `BACKEND_BASE_URL` and `BACKEND_API_KEY`, so you usually don't touch this file.

### Shared-network mode

Activate when the gateway runs as a service on another Compose stack on the same host. Bootstrap does this for you on the prompt, or manually:

```bash
ln -sf docker-compose.shared-network.yml docker-compose.override.yml
# Make sure SHARED_DOCKER_NETWORK in .env matches an existing external network
docker compose up -d
```

Deactivate:

```bash
rm docker-compose.override.yml
docker compose up -d --force-recreate
```

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

**`network <name> not found`** — shared-network mode is on but the named external network doesn't exist. Either create it (or its owning stack), change `SHARED_DOCKER_NETWORK` in `.env`, or disable shared-network mode (`rm docker-compose.override.yml`).

**`Server listening` never appears in logs** — check `docker compose logs api` for missing `.env` values; re-run `./bootstrap.sh`.

**Model dropdown is empty** — the proxy isn't reachable. Verify with `docker compose exec api wget -qO- http://litellm-proxy:4000/health/liveliness`. If that works but `/v1/models` is empty, check that the LiteLLM proxy has models registered.

**Cannot pull image** — run `docker login ghcr.io` with a personal access token that has `read:packages`.

## Ports

| Port | Container | Purpose |
|---|---|---|
| 3081 | `nufi-chat-api` | HTTP, exposed on host |
| 27017 | `nufi-chat-mongo` | MongoDB, internal only |
