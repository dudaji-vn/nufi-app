# NUFI Studio and NUFI Works on Railway

Deploy notes for the two agent products and the identity the console issues
for them. Written so the next person can rebuild this from nothing.

Project `nufi` = `06c8dad0-f74c-412e-b9cf-f563676520d5`, environment
`production` = `57cf6b17-ab70-466c-a7d8-fcbbe8b01d49`.

Design: `docs/superpowers/specs/2026-08-26-nufi-agents-cloud-design.md`.
Plan: `docs/superpowers/plans/2026-08-26-nufi-agents-cloud.md`.

## Hostnames

| Host | Service | What it is |
|---|---|---|
| `agents.nufi.me` | `nufi-console` | the chooser — a route, not a service |
| `studio.nufi.me` | `nufi-studio` | NUFI Studio, the flow canvas |
| `works.nufi.me` | `nufi-works` | NUFI Works, the agent operations app |
| `console.nufi.me` | `nufi-console` | the identity issuer, unchanged otherwise |

`agents.nufi.me` is a second custom domain on the existing console service.
The console's server redirects `/` to `/choose` when the request's Host is the
chooser host, and leaves every other path alone on both hostnames. This is
deliberate: idle memory is most of the Railway bill, and a service whose whole
job is serving one static page would be a recurring cost for nothing.

## Services

### `nufi-agents-db` — Postgres

One instance, two databases:

```sql
CREATE DATABASE nufi_studio;
CREATE DATABASE nufi_works;
```

Both products on one server couples their availability. That is accepted
rather than overlooked: a second instance would be a second idle footprint,
and neither product is load-bearing for the other.

### `nufi-studio`

Image `ghcr.io/dudaji-vn/nufi-studio`, built by `.github/workflows/nufi-agent-image.yml`.
Listens on `$PORT`, default 7860.

```
PORT=7860
LANGFLOW_DATABASE_URL=postgresql://…/nufi_studio
LANGFLOW_AUTO_LOGIN=false
LANGFLOW_SECRET_KEY=            # openssl rand -hex 32
LANGFLOW_SUPERUSER=             # an admin address
LANGFLOW_SUPERUSER_PASSWORD=    # generated; store in the team vault

# Identity. Set these only after the console is issuing tokens — turning them
# on against an issuer that does not exist yet locks everyone out.
LANGFLOW_EXTERNAL_AUTH_ENABLED=true
LANGFLOW_EXTERNAL_AUTH_TOKEN_COOKIE=nufi_id
LANGFLOW_EXTERNAL_AUTH_JWKS_URL=https://console.nufi.me/.well-known/jwks.json
LANGFLOW_EXTERNAL_AUTH_ISSUER=https://console.nufi.me
LANGFLOW_EXTERNAL_AUTH_AUDIENCE=nufi-studio
LANGFLOW_EXTERNAL_AUTH_SUBJECT_CLAIM=sub
LANGFLOW_EXTERNAL_AUTH_EMAIL_CLAIM=email
LANGFLOW_EXTERNAL_AUTH_ACCESS_CEILING_ENABLED=true
LANGFLOW_EXTERNAL_AUTH_ACCESS_CLAIM=access
LANGFLOW_EXTERNAL_AUTH_DEFAULT_ACCESS_LEVEL=editor
```

`LANGFLOW_EXTERNAL_AUTH_TRUSTED_JWT_DECODE` stays unset. It skips signature
verification and is only safe behind a proxy that has already validated the
token. There is no such proxy here, and the JWKS path costs nothing.

### `nufi-works`

Image `ghcr.io/dudaji-vn/nufi-works`, built by `.github/workflows/agents-image.yml`.
Listens on 3100. **Needs a volume mounted at `/paperclip`** — agent
workspaces, uploads and instance config live there, and without it every
redeploy starts empty.

```
PORT=3100
DATABASE_URL=postgresql://…/nufi_works
BETTER_AUTH_SECRET=             # openssl rand -hex 32
PAPERCLIP_DEPLOYMENT_MODE=authenticated
PAPERCLIP_DEPLOYMENT_EXPOSURE=public
PAPERCLIP_PUBLIC_URL=https://works.nufi.me
PAPERCLIP_HOME=/paperclip

# Identity. Set these last: PAPERCLIP_AUTH_DISABLE_SIGN_UP with no working
# OAuth client leaves no way into the instance at all.
NUFI_OIDC_ISSUER=https://console.nufi.me
NUFI_OIDC_CLIENT_ID=nufi-works
NUFI_OIDC_CLIENT_SECRET=        # same value as in OIDC_CLIENTS on the console
PAPERCLIP_AUTH_DISABLE_SIGN_UP=true
```

### `nufi-console` — additions

```
OIDC_ISSUER=https://console.nufi.me
OIDC_PRIVATE_KEY_PEM=           # openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048
OIDC_CLIENTS=[{"clientId":"nufi-works","clientSecret":"…","redirectUris":["https://works.nufi.me/api/auth/oauth2/callback/nufi"]}]
CHOOSER_HOST=agents.nufi.me
STUDIO_URL=https://studio.nufi.me
```

and append to the existing variable:

```
AGENTS_ALLOWED_ORIGINS=…,https://works.nufi.me
```

Exact string equality is the entire security boundary of the connect flow. No
trailing slash, no wildcard.

Two constraints that are easy to trip over later:

- **`OIDC_PRIVATE_KEY_PEM` must be set.** Without it the console generates an
  ephemeral key at boot, so tokens stop verifying after a restart and two
  replicas would never agree.
- **The console runs as one instance.** Authorization codes are held in
  memory, so a code issued by one replica is not found by another. Scaling out
  means moving them to a shared store first.

## Order

The identity variables come last on both products, for the same reason in each
case: switching a product to an issuer that is not answering yet locks
everyone out of it, including whoever has to fix it.

1. Postgres service and the two databases.
2. `nufi-studio` and `nufi-works` with everything except the identity block.
   Confirm each serves and carries the NuFi name.
3. Console: `OIDC_*`, `CHOOSER_HOST`, `STUDIO_URL`, the extra origin.
4. Identity block on `nufi-studio`, then on `nufi-works`.
5. `deploy/railway/verify-agents.sh`.

## DNS

Railway issues a CNAME target per custom domain; the records are created at
the registrar, which is the one step none of the above can do for you.

| Host | CNAME target |
|---|---|
| `studio.nufi.me` | _(fill in from Railway once the domain is added)_ |
| `works.nufi.me` | _(fill in from Railway once the domain is added)_ |
| `agents.nufi.me` | _(fill in from Railway once the domain is added)_ |

## Verifying

```bash
deploy/railway/verify-agents.sh
```

Reachability, white-label, and — the part that matters — that the identity
endpoints answer 401 without a session and the published JWKS carries no
private key component.

## Not deployed yet

Agents in NUFI Works cannot run until there is a Kubernetes cluster with
Cilium. It is the only sandbox provider that reads `nufi/adapters.json`'s
`allowFqdns`, so it is the only one where "model traffic goes to the gateway
and nowhere else" is enforced rather than merely asserted. Everything above
stands without it: both products are reachable, branded, and entered with a
NUFI account.
