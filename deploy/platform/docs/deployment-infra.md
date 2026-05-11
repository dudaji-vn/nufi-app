# NPUOps Self-Hosted Infrastructure Requirements

Target: single-server internal alpha (~10–50 users), Docker Compose stack.
LLM backend (GPU host) is provisioned separately and is **out of scope for this document**.

## 1. Application server (1x)

Runs all platform services via Docker Compose.

| Resource | Spec | Notes |
|---|---|---|
| CPU | 16 vCPU | 13 services; ML guardrails (Presidio, LLM Guard) are CPU-heavy |
| RAM | 32 GB | ClickHouse + guardrail models dominate |
| Disk | 250 GB SSD (NVMe preferred) | Sized for alpha (10–50 users); expand when ClickHouse + MinIO approach 60% |
| OS | Ubuntu 22.04 LTS | Docker 24+, Docker Compose v2 |
| Network | 1 Gbps | |

## 2. Storage breakdown

Sized for alpha (~10–50 users, first 2–3 months):

| Component | Initial size | Growth |
|---|---|---|
| Postgres (LiteLLM keys + Langfuse metadata) | 10 GB | slow |
| MongoDB (LibreChat conversations) | 20 GB | medium |
| ClickHouse (Langfuse traces) | 50 GB | fast — main grower |
| MinIO (Langfuse blobs: prompts/completions) | 30 GB | medium |
| Prometheus (metrics, 15d retention) | 30 GB | bounded |
| Docker images + logs + buffer | 50 GB | |
| **Allocated** | **~190 GB** | ~60 GB headroom on 250 GB disk |

### Scale-up plan

- **Alert threshold:** disk usage > 60% (~150 GB used)
- **Expand to 500 GB** when ClickHouse + MinIO together cross 100 GB
- **Expand to 1 TB** once user count crosses ~100 or trace volume exceeds 1M/month
- Disk expansion is a one-time ops task (resize volume, no downtime if NVMe + LVM)

## 3. Network & access

- **Internal DNS record** — e.g. `npuops.internal`, or four subdomains: `chat.`, `console.`, `langfuse.`, `grafana.`
- **TLS** — internal CA cert, or Let's Encrypt (needs port 80 egress)
- **Firewall** — inbound 443 only; outbound to Docker registry and the LLM backend host
- **LLM backend reachability** — app server must reach the GPU host over LAN (low-latency path required; latency on this hop is the user-facing metric)
- **VPN / SSO** — recommended to keep the alpha behind corporate VPN

## 4. Backup

- Nightly dump of Postgres + MongoDB to an off-server location
- Estimated volume: ~50 GB/week
- Retention: 30 days

## 5. People / access

- 1 sudo account for ops
- Firewall rule change contact
- DNS record owner

## 6. Out of scope (deferred to Q3+)

- HA / multi-node — current design is single-host
- Managed DB — using containerized Postgres/MongoDB for now
- External (non-internal) users — license debt (MongoDB SSPL, MinIO AGPL, Redis 7.4 tri-license) must clear first
