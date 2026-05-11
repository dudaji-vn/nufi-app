# Cloudflare Tunnel + Access — Public Routing for NPUOps

Exposes the internal NPUOps stack (192.168.10.147 on Seoul LAN) to company
employees from any network, without a public IP, VPN, or firewall changes.

- **Domain:** `codechi.me`
- **Auth model:** Cloudflare Access (SSO via email magic link / Google) for
  human-facing surfaces; LiteLLM virtual keys for the programmatic API
- **Cost:** $0 — Cloudflare Free plan + Zero Trust Free tier (≤ 50 users)

## Architecture

```
User (anywhere) -> Cloudflare edge -> outbound tunnel -> 192.168.10.147 -> Docker services
                          |
                      Access policy
                  (allow @dudaji.com)
```

The server makes an **outbound** connection to Cloudflare, so no inbound
firewall hole is required on the company network.

## Hostname routing

| Public URL | Service | Local port | Access policy |
|---|---|---|---|
| `chat.codechi.me` | LibreChat | 3080 | Required (SSO) |
| `console.codechi.me` | Admin Console | 3081 | Required (SSO) |
| `langfuse.codechi.me` | Langfuse | 3000 | Required (SSO) |
| `grafana.codechi.me` | Grafana | 3001 | Required (SSO) |
| `api.codechi.me` | LiteLLM proxy | 4000 | **None** — virtual key auth |

`api.codechi.me` is intentionally not behind Access so SDK / `curl` clients
can authenticate with their `sk-...` virtual key.

## Prerequisites

- Domain registered (`codechi.me`) with access to its registrar
- Sudo on the target server
- `cloudflared` will be installed during setup

## Setup

### 1. Add the domain to Cloudflare

1. Sign in at <https://dash.cloudflare.com> (Free plan)
2. **Add a Site** → enter `codechi.me` → choose **Free**
3. Cloudflare assigns two nameservers (e.g. `nina.ns.cloudflare.com`,
   `walt.ns.cloudflare.com`) — copy them

### 2. Update nameservers at the registrar

Log in to wherever the domain is registered, switch to **Custom nameservers**,
paste the two from Cloudflare, save. Propagation typically completes within
5–30 minutes; Cloudflare emails confirmation.

### 3. Enable Cloudflare Zero Trust

1. From the Cloudflare dashboard, open **Zero Trust** (or
   <https://one.dash.cloudflare.com>)
2. Pick a team name (e.g. `dudaji`) — this becomes
   `dudaji.cloudflareaccess.com`
3. Select the **Free** plan (a payment method is required at signup but is
   not charged below the 50-user free tier)

### 4. Create the tunnel and capture the install token

1. **Networks → Tunnels → Create a tunnel**
2. Connector type: **Cloudflared**
3. Tunnel name: `npuops-seoul`
4. Copy the Debian/Ubuntu install command shown on the next screen — it
   embeds a long-lived token

### 5. Install `cloudflared` on the server

SSH to the server and run the commands from step 4:

```bash
curl -L --output cloudflared.deb \
  https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
sudo dpkg -i cloudflared.deb
sudo cloudflared service install <TOKEN_FROM_STEP_4>
```

Verify the service:

```bash
sudo systemctl status cloudflared
```

Back in the Cloudflare dashboard the connector should now report **Online**.

### 6. Add the five public hostnames

The initial wizard only accepts one route; finish the wizard, then return to
**Networks → Tunnels → npuops-seoul → Published application routes** and add
the remaining four.

For each route:

- **Subdomain:** as in the table above
- **Domain:** `codechi.me`
- **Path:** leave empty (the example regex in the help text is illustrative —
  do not paste it into the field)
- **Type:** HTTP
- **URL:** `localhost:<port>`

DNS records are created automatically. Verify with `dig +short chat.codechi.me`
once propagation finishes.

### 7. Lock down the human-facing surfaces with Access

For each of `chat`, `console`, `langfuse`, `grafana` (not `api`):

1. **Zero Trust → Access → Applications → Add an application**
2. Type: **Self-hosted**
3. Application name: descriptive (e.g. `NPUOps Chat`)
4. Session duration: `24h` (raise to 7d / 30d for less frequent re-auth)
5. Application domain: the full hostname (e.g. `chat.codechi.me`)
6. Identity provider: enable **One-time PIN** (email magic link) to start;
   Google / Microsoft SSO can be added later from **Settings → Authentication**
7. Add a policy:
   - Action: **Allow**
   - Rule: **Emails ending in** → `@dudaji.com`
   - (For an initial pilot, narrow this to a specific email list)

### 8. Update `.env` and recreate affected containers

Edit `.env` on the server:

```
DOMAIN_CLIENT=https://chat.codechi.me
DOMAIN_SERVER=https://chat.codechi.me
NEXTAUTH_URL=https://langfuse.codechi.me
LANGFUSE_HOST=https://langfuse.codechi.me
```

Any other base-URL references (Console SSO callbacks, LibreChat OAuth, etc.)
should be updated to the matching `*.codechi.me` URL.

Recreate:

```bash
docker compose up -d --force-recreate librechat console langfuse-web
```

## Verification

From a network **outside** the Seoul VPN (e.g. mobile hotspot or a Vietnam
laptop):

1. `https://chat.codechi.me` → Cloudflare email-PIN prompt → after auth,
   LibreChat loads
2. `https://api.codechi.me/v1/models` with no auth header → returns 401 from
   LiteLLM (proves the tunnel reaches LiteLLM and that LiteLLM's auth is
   intact)
3. `https://api.codechi.me/v1/chat/completions` with a valid `sk-...` key →
   returns a completion

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `DNS_PROBE_FINISHED_NXDOMAIN` | DNS not yet propagated | Wait 5–10 min, retry |
| Cloudflare **Error 1033** ("Argo Tunnel error") | Connector offline | `sudo systemctl restart cloudflared` |
| Page loads but **502 Bad Gateway** | Service unhealthy or wrong port | `docker compose ps`; recheck the route's local URL |
| `chat.codechi.me` skips the Cloudflare login | Access policy not attached to that hostname | Re-check the Application's domain field exactly matches |
| `api.codechi.me` returns Cloudflare login page | Access policy was accidentally added to `api` | Remove the Access application for `api.codechi.me` |

## Operations

- **Tunnel logs:** `sudo journalctl -u cloudflared -f`
- **Rotating tunnel token:** create a new tunnel, run
  `sudo cloudflared service install <NEW_TOKEN>` on the server, delete the
  old tunnel after the new connector reports Online
- **Revoking a user:** disable their `@dudaji.com` account (or remove them
  from the Access policy email list); next page load fails the policy check
- **Adding a new service:** add a hostname row in the tunnel's published
  applications page, then add an Access application + policy if it is
  human-facing

## Scope and limits

- Free Zero Trust tier supports up to **50 users**; bump to the paid Standard
  plan ($7/user/mo) before that ceiling
- This setup keeps the platform **internal-only** in the license-debt sense —
  access is gated to `@dudaji.com` employees, which keeps MongoDB SSPL /
  MinIO AGPL / Redis tri-license risks contained until the Q3 component swap
- For multi-server / HA tunnel topology, add a second `cloudflared`
  connector with the same tunnel token on a second server; Cloudflare will
  load-balance across them automatically
