# NuFi mesh coordinator

The coordinator is a self-hosted [headscale](https://headscale.net) control
server with its embedded DERP relay and STUN server, behind Caddy. It is what
lets a NuFi box (`deploy/box/`) be reached from a laptop on an LTE hotspot: the
laptop and the box both join this coordinator's mesh (Tailscale/WireGuard),
get stable mesh IPs and a MagicDNS name, and traffic finds a path between them
— directly when possible, relayed through this DERP server when both ends are
behind hostile NAT.

This is the runbook for standing one up on a VPS from cold. Read it top to
bottom the first time; after that, §7–§8 are the day-two half.

**One coordinator serves every box and every member.** It holds no documents,
no models and no chat history — only the list of machines allowed onto the
mesh and the keys they authenticate with. Nothing on it is worth more than the
box it points at, which is why 1 GB of RAM is enough.

---

## 1. What it needs

| | |
|---|---|
| Size | 1 vCPU, 1 GB RAM, 10 GB disk — headscale and Caddy are both light; sqlite is the database |
| OS | Any Linux with Docker Engine + the Compose plugin (this runbook is written for Ubuntu 24.04) |
| DNS | One A record: `MESH_SERVER_HOST` (e.g. `mesh.nufi.me`) → the VPS's public IP |
| Ports inbound | `443/tcp` (control API + DERP-over-HTTPS), `3478/udp` (STUN), `80/tcp` (Let's Encrypt's HTTP-01 challenge and the `/healthz` probe) |
| Ports outbound | 443 to Let's Encrypt; nothing else |

`MESH_BASE_DOMAIN` (e.g. `box.nufi.me`) does **not** need a DNS record —
headscale answers it itself via MagicDNS once a node has joined. It **must
not** be a suffix of `MESH_SERVER_HOST` (headscale requires the two to
differ); `bootstrap.sh` refuses to start otherwise. A member's box then
resolves as `<box-name>.<MESH_BASE_DOMAIN>` — `nufi.box.nufi.me` — and that
name is what every join file and every browser bookmark uses.

Both ports really are needed, and for different reasons. `443/tcp` carries the
control API *and* the DERP relay, so a member behind a firewall that allows
only HTTPS still reaches the box. `3478/udp` is STUN: it is how two machines
discover their own public addresses and try to skip the relay. Blocking it
does not break the mesh — it makes every packet go through the relay, and
through your VPS's bandwidth.

## 2. Stand one up

### 2.1 The VPS

Provision the machine, point the A record at it, and wait for the record to
resolve before going further — in `TLS_MODE=acme` Caddy asks Let's Encrypt for
a certificate on the first start, and Let's Encrypt resolves the name itself.

```sh
dig +short mesh.nufi.me     # must print the VPS's public IP
```

Install Docker Engine and the Compose plugin the usual way:

```sh
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker "$USER"   # log out and back in, or: newgrp docker
docker compose version            # must print v2.x
```

If the VPS runs a firewall, open the three ports before the first start —
Let's Encrypt's challenge fails silently-ish (Caddy retries and logs) if 80 is
shut:

```sh
sudo ufw allow 80/tcp && sudo ufw allow 443/tcp && sudo ufw allow 3478/udp
```

### 2.2 The checkout

The coordinator is `deploy/coordinator/` in this repo. A VPS with GitHub
access can clone it; one without takes an archive carried over by `scp`:

```sh
# on a machine that has the repo
git archive -o coordinator.tar HEAD deploy/coordinator
scp coordinator.tar you@mesh.nufi.me:
# on the VPS
tar xf coordinator.tar && cd deploy/coordinator
```

### 2.3 The three commands

```sh
cd deploy/coordinator
cp .env.example .env   # edit MESH_SERVER_HOST, MESH_BASE_DOMAIN, ACME_EMAIL
./bootstrap.sh --dry-run   # see the rendered headscale.yaml and Caddyfile first
./bootstrap.sh             # render, start, create user `box`, mint its API key
```

`bootstrap.sh` reads `.env` (writing one from your environment on first run
if none exists), renders `config/headscale.yaml.tmpl` and `Caddyfile` with
`sed`, brings up `headscale` + `caddy` with `docker compose`, waits up to five
minutes for both to report healthy, creates the headscale user `box` if it
does not already exist, and mints that user's API key — **printed once**;
headscale cannot show it again.

Re-running is safe, and is how you apply a config change: it keeps `.env`'s
answers, does not recreate the user, and does not mint a second key (prints
`api key already minted; rotate with --rotate-key` instead). Environment
variables passed on the command line win over `.env`; `.env` fills in the
rest.

`--dry-run` prints the two rendered files and the DNS facts and touches
nothing — it is the safe way to check an edit before it goes live.

## 3. Check it works

From the VPS itself:

```sh
docker compose ps                                   # both healthy
curl -fsS https://mesh.nufi.me/health               # headscale's own, through Caddy
docker compose exec headscale headscale users list  # `box` is there
docker compose exec headscale headscale apikeys list
```

From anywhere else — this is the check that matters, because it exercises DNS,
the firewall and the certificate at once:

```sh
curl -fsS https://mesh.nufi.me/health && echo         # 200, publicly trusted cert
```

STUN needs a real probe, and not a generic one. `nc -zu` reports success
against a closed UDP port as readily as an open one, and a stock STUN client
gets no answer at all: headscale's STUN server is tailscale's, and it answers
only a Binding Request shaped the way a Tailscale client sends it — with a
`SOFTWARE` attribute of `tailnode` and a `FINGERPRINT`. Anything else is
dropped in silence, which from outside looks exactly like a firewall eating
the port. `stun-probe.py` sends the shape the server wants:

```sh
./stun-probe.py mesh.nufi.me
# mesh.nufi.me:3478 -> Binding Response (57 ms) · you are 1.52.176.223:55304
```

An answer proves the provider's network passes UDP 3478 in and out — the one
thing the Docker lab could never tell you. No answer in 3 s means the packet
is not arriving or not coming back; `sudo ss -lunp | grep 3478` on the VPS
then separates "not listening" from "the provider drops it". Once a box has
joined, its own client says the same thing from the inside: `tailscale
netcheck` names the DERP region it sees and whether it got a UDP mapping, and
`tailscale ping <box>` says `direct` or `via DERP`.

(There is no shell inside the headscale image — it is a `ko`-built binary — so
every probe of it runs either from the host or through `headscale` itself.)

`/health` is headscale's own endpoint, proxied by Caddy. `http://…/healthz` on
port 80 is Caddy's, and answers before headscale is up — useful for telling
"Caddy is running but headscale is not" from "nothing is running".

Once a box and a laptop have joined, `headscale nodes list` is the whole
picture:

```sh
docker compose exec headscale headscale nodes list
```

## 4. Hand it to a box

A box needs three things from this coordinator, and only the first two come
out of `bootstrap.sh`.

**`MESH_SERVER_URL`** — `https://<MESH_SERVER_HOST>`. The coordinator's own env
variable is `MESH_SERVER_HOST` (just the hostname, since that is what both
`config/headscale.yaml` and the Caddyfile need); the box names the same
coordinator as a full URL, `MESH_SERVER_URL`. That split is intended, not a
typo.

**`MESH_API_KEY`** — the key printed at the end of the first `./bootstrap.sh`
run. It is what `nufi-box invite`, `members` and `revoke` authenticate with,
so a box without it can join the mesh but cannot invite anyone.

**`MESH_AUTH_KEY`** — the box's own single-use pre-auth key, tagged `tag:box`.
`bootstrap.sh` does **not** mint this; you mint one per box, by hand:

```sh
# the --user flag takes headscale's numeric user id, not the name
docker compose exec headscale headscale users list -o json   # find box's id
docker compose exec headscale headscale preauthkeys create \
  --user 1 --tags tag:box --expiration 24h
```

Single-use is the default; the 24-hour expiry only bounds how long the key is
useful before the box is installed. A box that has already joined does not
need a second one — `nufi-box mesh down` then `mesh up` returns it to the same
address on its existing registration.

Then, on the box:

```sh
./install-box.sh --yes \
  --mesh https://mesh.nufi.me \
  --auth-key tskey-auth-… \
  --mesh-api-key hskey-api-…
```

or, on a box that is already installed, put `MESH_SERVER_URL`,
`MESH_AUTH_KEY` and `MESH_API_KEY` in its `.env` and run `nufi-box mesh up`.
See `deploy/box/README.md`, ["From home"](../box/README.md#8-from-home), for
the box half and the member half.

Members' keys are not minted here: `nufi-box invite <name>` on the box calls
this coordinator's API with `MESH_API_KEY` and mints a one-hour `tag:member`
key itself. That is deliberate — the admin who runs the box should not need a
shell on the VPS to add a laptop.

## 5. TLS

```
TLS_MODE=acme      Caddy requests a public certificate from Let's Encrypt
                    for MESH_SERVER_HOST. Needs the DNS record above and
                    ports 80+443 reachable from the internet. ACME_EMAIL
                    is required (Let's Encrypt's expiry-notice contact).
                    This is the field mode.

TLS_MODE=internal  Caddy's own internal CA. No public DNS needed.
                    bootstrap.sh exports the root certificate to
                    data/coordinator-ca.crt — trust it on whatever needs to
                    reach this coordinator (the local Docker lab, a Lima/VM
                    box under test). Used for development, not for the real
                    field deployment.
```

A box joining an `internal` coordinator needs that root in
`MESH_CA_FILE` (see the box's `.env.example`); with `acme` the system bundle
already trusts it and `MESH_CA_FILE` stays at its default.

## 6. Running it on a developer Mac (lab ports)

A Mac already running a NuFi box holds host ports 80 and 3080 etc.
`docker-compose.lab-ports.yml` remaps the coordinator's ports so the two
stacks coexist:

```sh
TLS_MODE=internal MESH_SERVER_HOST=coordinator.lab MESH_BASE_DOMAIN=box.lab \
  COORDINATOR_COMPOSE_EXTRA=docker-compose.lab-ports.yml ./bootstrap.sh
```

This publishes `8443:443`, `8080:80`, `13478:3478/udp` instead of the
standard ports.

```sh
curl -sk --resolve coordinator.lab:8443:127.0.0.1 \
  https://coordinator.lab:8443/health     # headscale's own /health, through Caddy
docker compose exec headscale headscale users list
docker compose exec headscale headscale apikeys list
```

`--resolve` is not optional here: Caddy's site is bound to the literal
hostname `coordinator.lab` (that's the only name on the internal-CA
certificate, and there is no catch-all/on-demand TLS configured), so hitting
this port through the plain `localhost` name fails the TLS handshake —
`localhost` is not in the certificate and Caddy has no site to match it
against. `--resolve` points the connection at `127.0.0.1` while still
sending `coordinator.lab` as the SNI/Host, which is what the certificate and
the Caddyfile actually expect. (An `/etc/hosts` entry for `coordinator.lab`
→ `127.0.0.1` works the same way, if you'd rather not repeat `--resolve` on
every command.)

For the full two-NAT proof — two nodes joining from behind separate NATs, the
DERP relay forced, HTTPS and SMB over the mesh — see [`lab/`](lab/README.md).
`lab/run.sh` brings up this same stack (via compose `include:`) plus the
topology around it and prints a PASS/FAIL table; it writes nothing into this
directory and uses its own compose project, `nufi-lab`.
`lab/day-at-home.sh` goes one step further and points that same NAT'd member
at a real box in a VM.

## 7. Day two

### Rotating the API key

The box's `MESH_API_KEY` expires after 365 days (`apikeys create --expiration
365d`). To rotate it before then:

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

### Removing a machine

Either end can do this. On the box, `nufi-box revoke <name>` is the supported
way. From the VPS:

```sh
docker compose exec headscale headscale nodes list
docker compose exec headscale headscale nodes delete --identifier <id>
```

Nodes do not expire on their own — `node.expiry: 0` in the rendered config
means a box that is switched off for a month is still registered when it comes
back, which is what you want for an appliance and does mean stale rows have to
be deleted deliberately.

### Policy

`config/policy.hujson` is a static two-rule ACL: nodes tagged `tag:member`
(minted by `nufi-box invite`) may reach nodes tagged `tag:box` (the box
itself) on any port, and vice versa. Members cannot reach each other. Both
tags are owned by the user `box` (`"box@"` — headscale/Tailscale's `name@`
syntax for a user acting as a tag owner, confirmed against headscale v0.29.3's
own ACL docs).

It is mounted read-only, so edit `config/policy.hujson` on the host, then tell
the running server to reload it — `policy.mode: file` means the file on disk
is the source of truth; `headscale policy set` is for `policy.mode: database`
and does not apply here:

```sh
docker compose kill -s HUP headscale
```

Check a candidate edit's syntax first with `headscale policy check
--bypass-grpc-and-access-database-directly` (the `-f` flag it also requires
should point at your edited copy) before reloading with it live.

### Upgrading

The two images are pinned in `docker-compose.yml`
(`headscale:v0.29.3`, `caddy:2.10.0-alpine`). Upgrading is a deliberate edit,
not a `pull`:

```sh
docker compose pull && docker compose up -d     # same pins: re-pulls, no change
```

To move headscale, back up first (below), change the tag, then
`./bootstrap.sh` — headscale migrates its own sqlite schema on start. Read its
release notes: this config pins several version-sensitive things (the
`headscale health` healthcheck subcommand, the `name@` policy syntax, the
numeric `--user` id on `preauthkeys create`), and a major version can move any
of them.

## 8. Where the state lives, and backup

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

Restoring is the reverse — stop the stack, put the backup into a fresh volume,
bring it up:

```sh
docker compose down
docker volume rm nufi-coordinator_headscale-data
docker volume create nufi-coordinator_headscale-data
docker run --rm -v nufi-coordinator_headscale-data:/data -v "$PWD":/backup \
  alpine tar xzf /backup/headscale-data.tgz -C /data
docker compose up -d
```

A restore brings the registrations back whole. This was drilled on 22 September
2026 against a real backup holding one joined box: after wiping the volume and
extracting the backup, `headscale nodes list` showed the same node with the
**same IP and the same node key** it had before. That node key is the point —
a box (or laptop) authenticates by the key its own `tailscale` state still
holds, so once the coordinator's record of that key is back, the box reconnects
on its own, keeps its mesh address, and every join file already handed out
stays valid. No re-invite, no new pre-auth key.

So back up `headscale-data` and you are covered. Losing it **without** a backup
is the expensive case: every box and every laptop has to join again with a
fresh pre-auth key, and the mesh addresses they get will be different, which
invalidates the join files already out.

## 9. One coordinator per customer

**One coordinator serves one organisation, never two.** A second company gets
its own coordinator — a second `bootstrap.sh` on a second (or the same) VPS,
with its own `.env`. It is worth understanding why this is a rule and not a
preference before someone tries to save five dollars a month by sharing one.

The mesh ACL (`config/policy.hujson`) is deliberately flat: every node tagged
`tag:member` may reach every node tagged `tag:box`, and both tags are owned by
the one headscale user, `box`. That is exactly what a single organisation
wants — any invited laptop reaches the office box. Put two companies on one
coordinator and that same rule reaches company A's laptops to company B's box.
There is no per-company tag boundary to add, because a single coordinator has a
single tag owner; the boundary **is** the coordinator.

### The naming convention

Give each customer a coordinator hostname and a MagicDNS base domain under it,
and keep `BOX_NAME` for the department or site:

| | Company "Acme" | Company "Globex" |
|---|---|---|
| `MESH_SERVER_HOST` | `acme.mesh.nufi.me` | `globex.mesh.nufi.me` |
| `MESH_BASE_DOMAIN` | `box.acme.nufi.me` | `box.globex.nufi.me` |
| A box named `legal` resolves as | `legal.box.acme.nufi.me` | `legal.box.globex.nufi.me` |

`BOX_NAME` names the box within its company (`legal`, `hanoi`), never the
company — the company is in the coordinator's name, so two customers can both
have a `legal` box without a collision. (Within one coordinator, two boxes
still must not share a name; `nufi-box mesh up` and `invite` refuse a name the
coordinator already holds.)

### The proof

`two-customers.sh` stands two coordinators up side by side (separate compose
projects, separate sqlite, separate DERP keys, internal TLS, no published
ports — the member nodes join over each coordinator's own Docker network) and
asserts the wall between them. Run on the field VPS on 22 September 2026, every
row passed:

```
 ok  a node offering A's member key to B does not join B
 ok  A's API key is not B's — neither coordinator honours the other's
 ok  B's admin store does not contain A's key
 ok  A lists node-a          ok  B never sees node-a
 ok  B lists node-b          ok  A never sees node-b
 ok  node-a sees no peer from B (only itself on A's tailnet)
```

Two coordinators are two separate meshes. A credential minted on one is refused
by the other, and a node joined to one never appears in the other's node list
or as a peer on its tailnet — so a member of one company cannot address, let
alone reach, the other's box. It writes nothing into this directory and tears
both stacks down after (pass `--keep` to leave them up).

```sh
./two-customers.sh
```

## 10. When it does not work

| Symptom | What it is |
|---|---|
| `bootstrap.sh` dies with `MESH_BASE_DOMAIN … must not be a suffix of MESH_SERVER_HOST` | headscale requires the MagicDNS base domain to differ from the server hostname. `mesh.nufi.me` + `box.nufi.me` is fine; `mesh.nufi.me` + `nufi.me` is not. |
| `headscale/caddy did not become healthy in time` | `docker compose logs caddy` first. In `acme` mode the usual cause is the A record not resolving yet, or port 80 closed — Caddy cannot finish the HTTP-01 challenge and has no certificate to serve. |
| The certificate is untrusted from outside | `TLS_MODE=internal` was used. That mode is for the lab and for a VM under test; a real coordinator wants `acme`. Change `TLS_MODE` in `.env` and re-run `./bootstrap.sh`. |
| A STUN probe gets no answer, but `tailscale netcheck` on a joined node says `UDP: true` | The probe was a generic STUN client. headscale's STUN answers only Tailscale-shaped requests (`SOFTWARE=tailnode` + `FINGERPRINT`); use `./stun-probe.py <host>`, which sends that shape. |
| A box or laptop joins, but every packet is relayed and throughput is poor | `3478/udp` is not reachable, so no client can discover its own public address and no direct path can form. Check the VPS firewall and the provider's own network ACL. The mesh still works — it is just all going through this VPS. |
| `nufi-box invite` on the box fails with `401` | Its `MESH_API_KEY` is wrong, expired, or was rotated here without the box being updated. `headscale apikeys list` shows what this coordinator holds. |
| `nufi-box invite` fails on certificate verification | An `internal`-mode coordinator whose root the box does not trust. Copy `data/coordinator-ca.crt` to the box and point `MESH_CA_FILE` at it. |
| A join fails with `requested tags […] are invalid or not permitted` | Something passed `--advertise-tags` on a pre-auth-key registration. headscale v0.29.3 refuses that outright whatever `tagOwners` says — a pre-auth-key node takes its tags from the key (`preauthkeys create --tags`), never from the client. The shipped join files do not pass it; a hand-written one must not either. |
| `preauthkeys create --user box` fails | v0.29.3's `--user` takes the numeric user id. `headscale users list -o json` prints it. |
| Two machines share a name in `nodes list` | headscale does not enforce unique node names. `nufi-box revoke` refuses to guess between them and asks for `--id`; from here, `nodes delete --identifier <id>`. |

## 11. What has been proved, and what has not

This coordinator has been run end to end **in a Docker lab** — two containers
behind separate NATs that forward no inbound UDP but STUN, joining this exact
stack (the lab `include:`s `../docker-compose.yml` rather than copying it) and
then using each other over HTTPS and SMB, with the relay forced. `lab/run.sh`
and `lab/day-at-home.sh` are that proof and print their own PASS/FAIL tables;
`lab/README.md` records the measured runs.

**On 22 September 2026 it was run on a real VPS**, and everything the lab
could not exercise held. The server: a 1 vCPU / 4 GB Hostinger KVM in Kuala
Lumpur, Ubuntu 24.04, 57 ms from the development machine. `mesh.nufi.me` is
an explicit A record in a zone whose wildcard points elsewhere. In order:

| Step | Result |
|---|---|
| `./bootstrap.sh` in `TLS_MODE=acme` | Let's Encrypt issued `CN=mesh.nufi.me` on the first start; `/health` 200 from outside with no `-k`; the API key printed once |
| UDP 3478 through the provider's network | `stun-probe.py` from the office: Binding Response in 52–65 ms, 4 of 4 — Hostinger passes it |
| A box joins (Ubuntu VM, `nufi-box mesh up`) | `100.64.0.1`, MagicDNS `nufi.box.nufi.me`; its `tailscale netcheck`: `UDP: true`, its public endpoint learned, nearest DERP `NuFi DERP` at 65 ms |
| `nufi-box invite` from that box | a `tag:member` key minted through the coordinator's API over the public certificate |
| A member with a direct path | `tailscale ping nufi`: `direct` in 1 ms |
| A member forced through the relay (`TS_DEBUG_ALWAYS_USE_DERP`) | `pong from nufi via DERP(nufi) in 126 ms`; `https://nufi.box.nufi.me:3080/health` 200 over the relay, certificate verified against the box's own CA, 0.53 s |
| Sign-in over the relay | `POST /api/auth/login` 200, a token for the box admin |
| `nufi-box revoke`, `./bootstrap.sh --rotate-key`, `apikeys expire` | all through the API; the box kept working on the new key |
| §8 backup | 10 KB, the five files named there |

What that run did **not** cover, and is still open: a member on a network
other than the box's. Both test members were containers on the machine that
hosts the box VM, so the direct path was found over a local address and the
relayed path was forced by a debug knob rather than by a hostile NAT. The
lab's two-NAT topology and this run's public coordinator together cover every
piece; a laptop on an LTE hotspot is the one measurement that has not been
taken with both at once.
