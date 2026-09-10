# NuFi box P2 — "from home" — design

2026-09-09 · status: draft for Sun's approval · spec for `docs/2026-09-08-nufi-team-box-plan.md` §4 P2, plus the two items that close P1

## Decisions taken with Sun on 2026-09-09

- nufi-app builds and runs the mesh coordinator itself (`deploy/coordinator/`); the board's MeshBox portal can sit in front later. Sun tells the board before this lands.
- No VPS date. P2 is proven in a local Docker lab that reproduces the hostile case (both ends behind NAT, no port forwarding, relay forced); the field test on a real VPS becomes the first task of P3 when the VPS exists.
- The old local `npuops` stack is stopped; the Mac box now runs on the standard ports.

## Goal

From an LTE hotspot, a member installs the official Tailscale app, double-clicks one file from the box, and then uses the box exactly as on the office LAN: `https://nufi.<mesh>:3080` in the browser, `\\nufi\legal` as a drive, a routine with an input in NUFI Studio. Nothing about the box needs a public IP, an open port, or a DNS change at the customer.

## Closing P1 first (two tasks at the top of the P2 plan)

1. **Blank Ubuntu install, timed.** A Multipass Ubuntu 24.04 VM on the Mac (arm64), the README open, a clock running. The VM cannot reach GHCR (private packages), so this also exercises the image path a customer box needs: a `NUFI_REGISTRY` variable (default `ghcr.io/dudaji-vn`) on every NuFi image in the compose files, and the VM pulls from a local registry on the Mac (`registry:2`, insecure, LAN only) that holds the arm64 images built here (`nufichat:arm64-dev`, admin-panel, console, litellm, ingest, studio). What the timer and the README miss are P1 defects; they are fixed in the owning file.
2. **The weekly demo video** with the existing machinery in `deploy/platform/scenarios/demo/`: one command → chat → a file into the drive → a cited answer → a Studio flow; English and Korean; the reproducible 10/32 stated plainly.

## Architecture

```
  laptop (LTE)                       coordinator (lab now, VPS later)
  Tailscale app + join file  ───▶    headscale + embedded DERP + STUN, behind Caddy TLS
        │  WireGuard end to end; DERP relays ciphertext when NAT is hostile
        ▼
  the box: tailscale node "nufi" (tag:box)  ── mesh IP 100.64.x.y, MagicDNS "nufi.<base>"
     Caddy sites gain the mesh name + mesh IP as SANs (same box CA, re-issued)
     Samba binds the mesh IP too (Linux); macOS File Sharing already listens on it
     Studio mounts /drives read-only so a routine can read a department file
```

### Components

| Component | Where | What it does |
|---|---|---|
| Coordinator | `deploy/coordinator/docker-compose.yml`, `config/headscale.yaml`, `Caddyfile`, `README.md` | `headscale/headscale` pinned, embedded DERP on 443 + STUN 3478, MagicDNS base domain `${MESH_BASE_DOMAIN}` (default `mesh.nufi.me`), one API key per box, ACL: `tag:box` reachable from `tag:member`; Caddy terminates TLS (Let's Encrypt on the VPS, internal CA in the lab). Runbook: what the VPS needs (1 vCPU, 1 GB, a DNS name, 443/3478 inbound) and the three commands to bring it up. |
| Lab | `deploy/coordinator/lab/` | Compose topology: coordinator on a "WAN" network, `node-a` and `node-b` each behind its own NAT router container (MASQUERADE only), the box's stack joined as `node-b`'s peer; a script proves join → DERP relay (no direct path) → HTTPS to the box over the mesh → SMB round trip. Exit 0 = PASS. This is the acceptance until the VPS exists. |
| Box as a node | `deploy/box/docker-compose.mesh.yml` (profile `mesh`) on Linux: `tailscale/tailscale` pinned, `network_mode: host`, `TS_AUTHKEY`, `--login-server`, `--advertise-tags=tag:box`, state in a volume. macOS: the Tailscale app natively; the installer runs `tailscale login --login-server … --auth-key …` and stores nothing in Docker. | The box gets a stable mesh IP and the MagicDNS name `nufi.<base>`. |
| Caddy SANs | `Caddyfile` sites gain `{$BOX_MESH_HOST}` and `{$BOX_MESH_IP}`; `nufi-box mesh up` writes both into `.env` and reloads Caddy | The existing box CA covers the mesh name; laptops trust it once via the join file. |
| Invite | `nufi-box invite <name> [--os windows|macos|linux] [--drives legal,hr]` → `POST /api/v1/preauthkey` on the coordinator (single-use, 1 h, `tag:member`) → writes `nufi-join-<name>.{cmd,command,sh}` | The file: installs the box CA (per-OS command), `tailscale login --login-server=<coordinator> --auth-key=<key>`, maps the drives (`net use Z: \\nufi\legal` / `mount_smbfs` / `gio mount`), opens `https://nufi.<base>:3080`. `nufi-box members` lists nodes; `nufi-box revoke <name>` deletes one. |
| Drives over the mesh | Linux: Samba `interfaces = 127.0.0.1 <lan-ip> <mesh-ip>`, `bind interfaces only`, rendered by `nufi-box mesh up`; macOS: nothing to do | `\\nufi\legal` works from home. |
| Routine input | Studio service mounts `${NUFI_DATA_DIR}/drives:/drives:ro`; the four recipe flows take a text input and/or a `/drives/<dept>/<file>` path; `build_flows.py --box` installs them at the end of the installer with a Studio API key the installer mints | "Summarise this transcript", "weekly report from the Legal drive" run on real department files. |
| Console/app awareness | `CHAT_PUBLIC_URL`, `OIDC_ISSUER`, `STUDIO_URL`, `PUBLIC_*`, `DOMAIN_CLIENT/SERVER` keep the LAN name; the mesh name is a second Caddy site, not a second identity — cookies are host-scoped so members use ONE name consistently: the join file opens the mesh name and the README says "at the office the same mesh name works too" | Avoids double logins between `nufi.local` and `nufi.<base>`. |

### What is deliberately not in P2

The board's portal and catalog; SSO across the two hostnames (members use the mesh name once joined); the scheduler and event triggers (P3); `nufi-box update|backup|support` (P4); Works.

## Acceptance

- Lab: `deploy/coordinator/lab/run.sh` passes on the Mac: two NAT'd nodes join with one pre-auth key each, `tailscale ping` reports `via DERP`, `curl --cacert box-ca https://nufi.<base>:3080/health` succeeds from `node-a`, an SMB write from `node-a` is read back from the box.
- Box: `nufi-box invite alice --os macos` produces a file that, run on this Mac against the lab coordinator, joins, trusts the CA and opens the chat URL; `nufi-box members` shows `alice`; `nufi-box revoke alice` removes her and the next `tailscale status` shows the node gone.
- Flows: the four recipes exist in Studio after a fresh install and `run_flows.py --only meeting` returns actions from a pasted transcript; `--only weekly` cites a file under `/drives/legal`.
- Video: the "day at home" recorded on the lab (the relay case), stated as a lab.

## Risks

- Headscale's MagicDNS name format changed across versions (`<host>.<user>.<base>` vs `<host>.<base>`); pin the version and assert the name in the lab.
- Tailscale on macOS: the App Store build accepts `--login-server` only through its CLI at `/Applications/Tailscale.app/Contents/MacOS/Tailscale`; the join file must use that path.
- `network_mode: host` for the tailscale container is Linux-only; Docker Desktop on macOS cannot give Caddy the mesh IP, which is why macOS uses the native app.
- A member laptop already on a corporate Tailscale tailnet cannot join a second control server; the README must say so.
