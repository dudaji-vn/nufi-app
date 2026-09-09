# NuFi mesh coordinator

The coordinator is a self-hosted [headscale](https://headscale.net) control
server with its embedded DERP relay and STUN server, behind Caddy. It is what
lets a NuFi box (`deploy/box/`) be reached from a laptop on an LTE hotspot: the
laptop and the box both join this coordinator's mesh (Tailscale/WireGuard),
get stable mesh IPs and a MagicDNS name, and traffic finds a path between them
— directly when possible, relayed through this DERP server when both ends
are behind hostile NAT. This is a runbook for standing one up on a VPS.

## 1. What it needs

| | |
|---|---|
| Size | 1 vCPU, 1 GB RAM, 10 GB disk — headscale and Caddy are both light; sqlite is the database |
| OS | Any Linux with Docker Engine + the Compose plugin |
| DNS | One A record: `MESH_SERVER_HOST` (e.g. `mesh.nufi.me`) → the VPS's public IP |
| Ports inbound | `443/tcp` (control API, DERP-over-HTTPS) and `3478/udp` (STUN); `80/tcp` for Let's Encrypt's HTTP-01 challenge and the `/healthz` probe |

`MESH_BASE_DOMAIN` (e.g. `box.nufi.me`) does **not** need a DNS record —
headscale answers it itself via MagicDNS once a node has joined. It **must
not** be a suffix of `MESH_SERVER_HOST` (headscale requires the two to
differ); `bootstrap.sh` refuses to start otherwise.

## 2. The three commands

```sh
cd deploy/coordinator
cp .env.example .env   # edit MESH_SERVER_HOST, MESH_BASE_DOMAIN, ACME_EMAIL
./bootstrap.sh --dry-run   # see the rendered config.yaml and Caddyfile first
./bootstrap.sh             # render, start, create user `box`, mint its API key
```

`bootstrap.sh` reads `.env` (writing one from your environment on first run
if none exists), renders `config/headscale.yaml.tmpl` and `Caddyfile` with
`sed`, brings up `headscale` + `caddy` with `docker compose`, waits for both
to report healthy, creates the headscale user `box` if it does not already
exist, and mints that user's API key — **printed once**; headscale cannot
show it again. Re-running is safe: it keeps `.env`'s answers, does not
recreate the user, and does not mint a second key (prints "api key already
minted; rotate with `--rotate-key`" instead).

What you hand the box operator when it finishes:

- `MESH_SERVER_URL` — `https://<MESH_SERVER_HOST>`
- `MESH_API_KEY` — the key printed at the end of the first `./bootstrap.sh` run

Both go into the box's `.env` (see `deploy/box/README.md`, "From home").

## 3. TLS

```
TLS_MODE=acme      Caddy requests a public certificate from Let's Encrypt
                    for MESH_SERVER_HOST. Needs the DNS record above and
                    ports 80+443 reachable from the internet. ACME_EMAIL
                    is required (Let's Encrypt's expiry-notice contact).

TLS_MODE=internal  Caddy's own internal CA. No public DNS needed.
                    bootstrap.sh exports the root certificate to
                    data/coordinator-ca.crt — trust it on whatever needs to
                    reach this coordinator (the local Docker lab, a Lima/VM
                    box under test). Used for development, not for the real
                    field deployment.
```

## 4. Running it on a developer Mac (lab ports)

A Mac already running a NuFi box holds host ports 80 and 3080 etc.
`docker-compose.lab-ports.yml` remaps the coordinator's ports so the two
stacks coexist:

```sh
TLS_MODE=internal MESH_SERVER_HOST=coordinator.lab MESH_BASE_DOMAIN=box.lab \
  COORDINATOR_COMPOSE_EXTRA=docker-compose.lab-ports.yml ./bootstrap.sh
```

This publishes `8443:443`, `8080:80`, `13478:3478/udp` instead of the
standard ports. Add `coordinator.lab` to `/etc/hosts` (or a lab DNS sidecar)
pointing at `127.0.0.1`, then:

```sh
curl -sk https://localhost:8443/health   # headscale's own /health, through Caddy
docker compose exec headscale headscale users list
docker compose exec headscale headscale apikeys list
```

## 5. Rotating the API key

The box's `MESH_API_KEY` is what the installer and `nufi-box invite` use to
call the coordinator's API. It expires after 365 days (`apikeys create
--expiration 365d`). To rotate it before then:

```sh
./bootstrap.sh --rotate-key
```

This mints a new key and prints it once; the old key keeps working until it
expires or you expire it by hand:

```sh
docker compose exec headscale headscale apikeys list
docker compose exec headscale headscale apikeys expire --prefix <old-key-prefix>
```

Update the box's `.env` with the new `MESH_API_KEY` and restart anything that
read it.

## 6. Where the state lives, and backup

Everything headscale knows — registered users, nodes, pre-auth keys, API
keys, its own noise/DERP private keys — lives in the `headscale-data` Docker
volume (`/var/lib/headscale` in the container), a single sqlite database plus
two key files. Caddy's certificates and ACME account state live in
`caddy-data`. Back up `headscale-data`; `caddy-data` is disposable (Caddy
re-issues or regenerates on the next start; internal-mode nodes would need to
re-trust a fresh root, so treat it as a nuisance, not a disaster).

```sh
docker run --rm -v nufi-coordinator_headscale-data:/data -v "$PWD":/backup \
  alpine tar czf /backup/headscale-data.tgz -C /data .
```

Restoring is the reverse: stop the stack, extract into a fresh volume,
`docker compose up -d`.

## 7. Policy

`config/policy.hujson` is a static two-rule ACL: nodes tagged `tag:member`
(minted by `nufi-box invite`) may reach nodes tagged `tag:box` (the box
itself) on any port, and vice versa. Both tags are owned by the user `box`
(`"box@"` — headscale/Tailscale's `name@` syntax for a user acting as a tag
owner, confirmed against headscale v0.29.3's own ACL docs). It is mounted
read-only, so edit `config/policy.hujson` on the host, then tell the running
server to reload it — `policy.mode: file` means the file on disk is the
source of truth; `headscale policy set` is for `policy.mode: database` and
does not apply here:

```sh
docker compose kill -s HUP headscale
```

Check a candidate edit's syntax first with `headscale policy check
--bypass-grpc-and-access-database-directly` (the `-f` flag it also requires
should point at your edited copy) before reloading with it live.
