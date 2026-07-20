# LibreChat Admin Panel

A browser-based management interface for [LibreChat](https://github.com/danny-avila/LibreChat). It connects to the same database as the main application and provides a GUI for tasks that would otherwise require editing `librechat.yaml` directly.

## Features

- **Configuration management** — View and edit all LibreChat settings through a dynamic, schema-driven form. New fields added to the schema appear automatically.
- **Role and group overrides** — Apply configuration overrides scoped to specific roles or groups, with a priority-based cascade that determines the final resolved value for each user.
- **User and group administration** — Create and manage groups, assign roles, and control access.
- **Authentication** — Supports username/password login and OpenID SSO when enabled on the LibreChat instance.
- **Localization** — Full multi-language support for all UI strings.
- **Accessibility** — Keyboard navigable with ARIA regions, focus management, and screen reader support.

## Getting started

### Local development

```bash
cp .env.example .env   # then edit .env
bun install
bun dev                 # http://localhost:3000
```

### Docker

```bash
cp .env.example .env
# Set SESSION_SECRET (min 32 chars)
# Set VITE_API_BASE_URL=http://host.docker.internal:3080

docker compose up -d    # builds and starts on http://localhost:3000
docker compose down     # stop
```

> **Note:** Inside Docker, `localhost` refers to the container, not your machine.
> Use `http://host.docker.internal:3080` for `VITE_API_BASE_URL` to reach
> LibreChat running on the host.

#### Environment variables

| Variable                        | Required                            | Default                                                                                              | Description                                |
| ------------------------------- | ----------------------------------- | ---------------------------------------------------------------------------------------------------- | ------------------------------------------ |
| `PORT`                          | No                                  | `3000`                                                                                               | Port the admin panel listens on            |
| `SESSION_SECRET`                | **Yes** (always required in Docker) | Dev fallback only when running `bun dev` locally; no default in the Docker image                     | Encryption key for sessions (min 32 chars) |
| `VITE_API_BASE_URL`             | **Yes** (Docker)                    | `http://localhost:3080` (local dev only)                                                             | LibreChat API server URL; use `http://host.docker.internal:<port>` in Docker |
| `ADMIN_SSO_ONLY`                | No                                  | `false`                                                                                              | Hide email/password form, SSO only         |
| `ADMIN_SESSION_IDLE_TIMEOUT_MS` | No                                  | `1800000` (30 min)                                                                                   | Session idle timeout in ms                 |

#### Standalone Docker build

```bash
docker build -t librechat-admin-panel .
docker run -p 3000:3000 \
  --add-host=host.docker.internal:host-gateway \
  -e SESSION_SECRET=your-secret-here-at-least-32-characters \
  -e VITE_API_BASE_URL=http://host.docker.internal:3080 \
  librechat-admin-panel
```
