# Deploying Meilisearch on Railway for LibreChat

This guide sets up [Meilisearch](https://www.meilisearch.com/) as a separate Railway service so LibreChat's `SEARCH=true` feature can index and search messages.

## Why a separate service?

Railway containers are network-isolated — `localhost:7700` from inside the LibreChat container will never reach Meilisearch. Meilisearch must run as its own Railway service and be reached over Railway's private network at `meilisearch.railway.internal:7700`.

## Prerequisites

- A Railway project with your LibreChat service already deployed.
- LibreChat service is in a Railway region (note which one — Meilisearch should be in the same region).

## Step 1 — Create the Meilisearch service

1. In the Railway project, click **+ Create** → **Database** → **Deploy from Docker Image**.
   (Or **Empty Service** → **Settings → Source → Connect Image**.)
2. **Image**: `getmeili/meilisearch:v1.35.1`
   (Pinned to match LibreChat's `docker-compose.yml`.)
3. Click **Deploy**.
4. Rename the service to `meilisearch` (this becomes its private DNS hostname).

## Step 2 — Networking

On the `meilisearch` service → **Settings → Networking**:

- **Private Networking** — Confirm the hostname is `meilisearch.railway.internal`. This is auto-assigned from the service name.
- **Public Networking** — **Do not** generate a domain or add TCP Proxy. Meilisearch should only be reachable inside the Railway project.

> The port (`7700`) is not auto-resolved by Railway's private DNS — you must include it in the URL: `http://meilisearch.railway.internal:7700`.

## Step 3 — Attach a persistent volume

Without a volume, the search index is wiped on every redeploy and has to reindex from scratch.

1. Right-click the `meilisearch` service on the canvas → **Attach Volume**
   (or **Settings** → scroll down to **Volumes** → **+ New Volume**).
2. **Mount path**: `/meili_data`
3. **Size**: 1 GB to start (grow later without downtime).
4. **Region**: same as the service.
5. **Deploy Changes**.

## Step 4 — Environment variables on `meilisearch`

Generate a master key locally:

```bash
openssl rand -hex 32
```

Save the output — you'll need the **exact same** value on the LibreChat service.

On the `meilisearch` service → **Variables → Raw Editor** → paste:

```env
MEILI_MASTER_KEY=<paste the openssl output here>
MEILI_NO_ANALYTICS=true
MEILI_ENV=production
MEILI_DB_PATH=/meili_data/data.ms
MEILI_DUMP_DIR=/meili_data/dumps
MEILI_HTTP_ADDR=0.0.0.0:7700
```

### Why each variable matters

| Variable | Purpose |
|---|---|
| `MEILI_MASTER_KEY` | Auth secret. Must be ≥16 bytes in production mode. |
| `MEILI_NO_ANALYTICS` | Disables outbound telemetry. |
| `MEILI_ENV=production` | Disables the dev dashboard and enforces the key-length rule. |
| `MEILI_DB_PATH` | Stores the index inside the mounted volume so it persists. |
| `MEILI_DUMP_DIR` | Same — keeps dumps on the volume. |
| `MEILI_HTTP_ADDR=0.0.0.0:7700` | **Critical.** Default is `127.0.0.1:7700`, which Railway's private network cannot reach. |

Click **Deploy Changes**.

## Step 5 — Verify Meilisearch booted

On the `meilisearch` service → **Deployments** → latest deployment → **View Logs**.

Look for:

```
Database path:        "/meili_data/data.ms"
Server listening on:  "http://0.0.0.0:7700"
Environment:          "production"
Anonymous telemetry:  "Disabled"
A master key has been set...
starting service: "actix-web-service-0.0.0.0:7700", workers: N, listening on: 0.0.0.0:7700
```

Red flags:

- `Master key is too short` → regenerate with `openssl rand -hex 32`.
- `Permission denied` on `/meili_data` → volume didn't attach; reattach in Step 3.
- Bound to `127.0.0.1` instead of `0.0.0.0` → `MEILI_HTTP_ADDR` missing.

## Step 6 — Wire LibreChat to Meilisearch

On the **LibreChat** service → **Variables → Raw Editor** → add:

```env
SEARCH=true
MEILI_HOST=http://meilisearch.railway.internal:7700
MEILI_MASTER_KEY=<the SAME key set on the meilisearch service>
MEILI_NO_ANALYTICS=true
```

> ⚠️ The master key must be byte-for-byte identical. Copy it from the meilisearch service's variables — don't retype. A one-character mismatch causes `403 Invalid API key` and search will silently fail.

Click **Deploy Changes**.

## Step 7 — Verify end-to-end

1. Wait for LibreChat to finish redeploying.
2. Check the LibreChat service logs for any `MeiliSearchCommunicationError` or `MeiliSearchApiError`.
3. Open LibreChat in your browser.
4. The **search icon** should appear in the sidebar.
5. Search across existing conversations.
   - New messages index in real time.
   - Historical messages reindex in the background on first run — give it a few minutes on a large DB.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `MeiliSearchCommunicationError` in LibreChat logs | Wrong `MEILI_HOST`, missing port, or `MEILI_HTTP_ADDR` not set on meilisearch. |
| `MeiliSearchApiError: Invalid API key` | `MEILI_MASTER_KEY` mismatch between services. |
| Meilisearch container restart loop | Master key under 16 bytes, or volume mount failed. |
| Search icon never appears in UI | `SEARCH=true` missing on LibreChat service, or LibreChat didn't redeploy after adding it. |
| Index disappears after redeploy | Volume not mounted at `/meili_data`, or `MEILI_DB_PATH` points elsewhere. |
| High latency on search | Meilisearch service in a different Railway region from LibreChat. |

## Reference

- Meilisearch env var docs: <https://www.meilisearch.com/docs/learn/configuration/instance_options>
- LibreChat search config: see `SEARCH`, `MEILI_HOST`, `MEILI_MASTER_KEY` in `.env.example`.
- Image version pinned: see `docker-compose.yml` (`getmeili/meilisearch:v1.35.1`).
