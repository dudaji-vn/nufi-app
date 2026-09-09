# The NAT lab

Two machines, each behind its own NAT with no port forwarding, join the
coordinator and then use each other: HTTPS to the box's MagicDNS name and a
file written over SMB. On a laptop, in about a minute, with no VPS.

This is P2's acceptance criterion until a real coordinator exists. `run.sh`
exits 0 only if all five checks pass.

```
./run.sh                # whatever NAT traversal finds; reports direct or DERP
./run.sh --force-relay  # UDP blocked except STUN: the path MUST be DERP
./run.sh --keep         # leave it up afterwards
./run.sh --dry-run      # print the plan; touch nothing
```

## What it proves

| check | what has to be true |
| --- | --- |
| `join-a` | a member's laptop, behind NAT, registers with a one-hour `tag:member` pre-auth key and reaches `BackendState=Running`; headscale lists it |
| `join-b` | the box does the same with `tag:box` and the hostname `nufi` |
| `path` | `direct` or `DERP`, read from `tailscale ping` — and with `--force-relay`, `DERP` or the run fails |
| `http-over-mesh` | `curl --cacert box-ca https://nufi.box.lab:3080/health` from the member's side: MagicDNS name, mesh route, a certificate that validates |
| `smb-round-trip` | `smbclient //nufi.box.lab/lab -c 'put …'` from the member, file read back inside the box |

## The topology

```
     lan-a 10.10.0.0/24                       lan-b 10.20.0.0/24
     ┌──────────────────────────┐             ┌──────────────────────────┐
     │ node-a  10.10.0.3        │             │ node-b  10.20.0.3        │
     │  tailscale, tag:member   │             │  tailscale, tag:box      │
     │  hostname node-a         │             │  hostname nufi           │
     │  + tools-a: curl,        │             │  + box-caddy :3080 https │
     │    smbclient (same netns)│             │  + box-samba :445  smb   │
     └────────────┬─────────────┘             └────────────┬─────────────┘
                  │ default route                          │
     ┌────────────┴─────────────┐             ┌────────────┴─────────────┐
     │ router-a 10.10.0.2       │             │ router-b 10.20.0.2       │
     │  MASQUERADE, no inbound  │             │  MASQUERADE, no inbound  │
     └────────────┬─────────────┘             └────────────┬─────────────┘
                  │ 172.30.0.11                            │ 172.30.0.12
     ═════════════╧════════════════════════════════════════╧═════════════
           wan 172.30.0.0/24         │ 172.30.0.10 = coordinator.lab
                          ┌──────────┴───────────┐
                          │ headscale + caddy    │  443/tcp control + DERP
                          │  (../docker-compose) │  3478/udp STUN
                          └──────────────────────┘
```

The coordinator is not a copy — `lab/docker-compose.yml` `include:`s
`../docker-compose.yml` itself, with `lab/coordinator.lab.yml` layered on top
and `lab/lab.env` supplying `MESH_SERVER_HOST=coordinator.lab`,
`MESH_BASE_DOMAIN=box.lab`, `TLS_MODE=internal`. `run.sh` renders its config by
piping `../bootstrap.sh --dry-run`, so the lab runs the same YAML a VPS would.

Three design points worth knowing before you change anything:

**Caddy shares headscale's network namespace.** On a VPS the coordinator is one
host: 443/tcp and 3478/udp answer on the same address, which is the only
address headscale puts in the DERP map it hands to clients. Two containers on a
bridge have two addresses, and `coordinator.lab` can only point at one. A UDP
proxy is not a way out — it rewrites the source, so the reflexive address
headscale's STUN server reports back would be the proxy's and nothing could
ever hole-punch. Sharing the namespace is the only arrangement that reproduces
the VPS's shape.

**The LANs use `enable_ip_masquerade: "false"`, not `internal: true`.** Docker
implements `internal` as a host rule dropping any frame on the bridge whose
destination is outside the subnet, and with `br_netfilter` loaded that catches
container-to-container frames on the *same* bridge too — so a node's packet to
its own router's WAN address dies before the router sees it. Without the
per-bridge masquerade the host will not translate these addresses, docker's own
inter-bridge isolation keeps them off `wan`, and the only packets that leave are
the ones the routers re-emit.

**The routers refuse to forward private destinations upstream** (`LEAKGUARD` in
`router/entrypoint.sh`). The docker host has an interface on every lab bridge
and will route between them; left open, the two nodes find each other's *LAN*
addresses and "direct" would mean "never really behind NAT". `run.sh` also
fails the `path` check outright if the winning endpoint is on 10.10/10.20 — a
LAN shortcut is a topology bug, not a pass.

## Observed on a MacBook (Docker Desktop 29.4.2, compose 2.39.2), 2026-09-09

```
$ ./run.sh
==> Measuring the path node-a -> nufi
    pong from nufi (100.64.0.1) via DERP(nufi) in 3ms
    pong from nufi (100.64.0.1) via 172.30.0.12:53306 in 1ms
 ok path is direct
==> GET https://nufi.box.lab:3080/health from node-a's namespace
    ok
==> SMB round trip //nufi.box.lab/lab
    putting file /etc/hostname as \hello.txt (0.6 kb/s)
 ok hello.txt arrived on node-b: node-a

  check            result
  ---------------- ------
  join-a           PASS
  join-b           PASS
  path             PASS (direct)
  http-over-mesh   PASS
  smb-round-trip   PASS

  force-relay 0 | coordinator up 21s | both nodes joined 8s | total 58s
```

The first ping is relayed and the second is not — that is NAT traversal
finishing, and the endpoint that wins (`172.30.0.12:53306`) is router-b's WAN
address, so the packets really did cross two NATs.

```
$ ./run.sh --force-relay
==> Measuring the path node-a -> nufi
    pong from nufi (100.64.0.2) via DERP(nufi) in 5ms
 ok path is DERP, as --force-relay requires
...
  path             PASS (DERP)
  http-over-mesh   PASS
  smb-round-trip   PASS

  force-relay 1 | coordinator up 12s | both nodes joined 19s | total 105s
```

With `--force-relay` the routers drop every forwarded UDP packet except STUN,
so no direct path can exist and the coordinator's embedded DERP carries the
whole mesh — the HTTPS call and the SMB write included. That is the hostile
case P2 is really about: a member on a mobile network the box can never
reach directly. It is slower to settle (both nodes' joins retry against
blocked DNS) but every check still passes.

## The day at home: the same lab, against the real box

`run.sh` proves the *mesh*: two containers, both stand-ins. `day-at-home.sh`
proves the *product*: the member is still node-a behind router-a with every
direct path blocked, but the other end is the real box — the Lima VM
`nufi-ubuntu` with its thirteen containers (twelve, plus `tailscale` once it is
on the mesh), its own CA, its department drives and its four routines.

```
./day-at-home.sh              run it, then put the machine back
./day-at-home.sh --keep       leave the lab up and the VM running
./day-at-home.sh --dry-run    print the plan; touch nothing
./day-at-home.sh --routine meeting   run a different routine (default: weekly)
```

Three things differ from `run.sh`, and each one matters:

**node-b never starts.** It registers as `nufi`, which is the name the real box
needs. Only `router-a`, `node-a` and `tools-a` come up on the member's side.

**No `down -v`.** The headscale volume holds the box's node registration and
the caddy volume holds the CA the box already trusts at
`/etc/nufi/coordinator-ca.crt`. Wiping them would turn a day-at-home run into a
first-join test.

**The coordinator is published on the Mac's own 443 and 3478.** The VM is a
real machine outside docker's networks and reaches the coordinator through
Lima's vzNAT gateway, and headscale builds its DERP map from `server_url`, so
those two ports are not free choices — the committed 8443/13478 map would leave
the box with no relay at all. The override is *generated* into
`rendered/host-ports.yml` rather than committed, because on a developer Mac 443
belongs to `deploy/box`'s Caddy and `../tests/test_lab.py` rightly asserts the
lab claims neither.

The member's credentials (the box's admin login, its SMB password, its Studio
API key) are read out of the VM's `.env` into `0600` files under `keys/` that
the exit trap deletes. Nothing ever reaches a command line: `smbclient` gets
`-A authfile`, `run_flows.py` reads `$STUDIO_API_KEY` set inside the container.

`tools/` therefore carries `python3` and a read-only mount of
`deploy/platform/scenarios`, so `run_box.py` and `studio/run_flows.py` run on
the member's side of the NAT — resolving `nufi.box.lab` through MagicDNS and
routing over node-a's `tailscale0`. Running them on the Mac would prove nothing
about the mesh.

### Observed 2026-09-09, relay forced, against the VM box

The second end-to-end run, after the three defects the first one found were
fixed or disclosed:

```
  check              result
  ------------------ ------
  box-on-mesh        PASS
  path               PASS (DERP)
  health-over-mesh   PASS
  login-over-mesh    PASS
  drive-write        PASS
  drive-ingested     PASS (31s)
  agent-cites-drive  PASS
  routine-weekly     FAIL

  relay forced | lab up 7s | box up + joined 38s | agent 493s | routine 5s | total 586s
```

The mesh half is unambiguous: `tailscale ping` says `via DERP` on every packet,
`https://nufi.box.lab:3080/health` is 200 through MagicDNS with a certificate
the box's own CA signs, the chat app takes the member's credentials, a member's
`smbclient put` onto `//nufi.box.lab/legal` lands and `nufi-ingest` embeds it in
31 s, and the Legal agent answers a question about that drive with a citation
(`contract.txt`, `계약검토_표준조항.txt`) — all of it over the relay, from
behind a NAT that forwards no UDP but STUN.

The agent's 493 s is a cold `qwen2.5:0.5b` on a VM that had just booted, loading
the model for the first question; 1 of the 4 judge verdicts passed, which is the
model's score and not the box's. The gate here is that an answer carried a
citation at all, and the check now prints what was cited so a PASS shows its
evidence.

The one failure, and it is not the mesh's:

- **`routine-weekly`** — `no Studio API key: pass --key or set $STUDIO_API_KEY`,
  in 5 s. The box's `.env` had no `STUDIO_API_KEY`: `install-box.sh` rewrites
  `.env` without it (the key is minted afterwards by `nufi-box flows install`,
  not asked for as an answer), and on this box the routines step had not put a
  new one back. So the run never reached the model, and it says nothing either
  way about the limitation this check usually finds — that nothing caps how much
  a routine generates, or stops a run whose caller has gone. `nufi-box flows
  install` mints a fresh key and repairs it; the box README's troubleshooting
  table carries the row.

For what the first run measured, and the two defects it found that are now
fixed (`drive-write`'s `NT_STATUS_ACCESS_DENIED` from the Samba uid mismatch,
and an upgraded mesh box crash-looping Caddy on a stale generated
`caddy/mesh.caddy`), see the P2 phase notes in
`docs/2026-09-08-nufi-team-box-plan.md` §4.

## Requirements and collisions

Docker Desktop with `/dev/net/tun` (the standard Linux VM has it) and about
1 GB of headroom. Host ports used: **8443** (Caddy, for your own poking) and
**13478/udp** (STUN). Nothing else is published — 80/443 belong to
`deploy/box`'s Caddy on a developer Mac, 445 and 3080 to its SMB and chat, and
8080 to whatever dev server you have running.

The compose project is `nufi-lab`, so it can never share a container, network
or volume with `nufi-box` (P1) or `nufi-coordinator` (a real one). Everything
`run.sh` generates lands in `lab/keys/` (pre-auth keys, the two CA roots) and
`lab/rendered/` (the coordinator config); both are gitignored and both are
wiped at the start of every run. Nothing is written into
`deploy/coordinator/` itself.

Subnets claimed: `172.30.0.0/24`, `10.10.0.0/24`, `10.20.0.0/24`. If one of
those already exists on your machine, `docker network create` fails loudly
rather than doing something subtle.

## Version facts this lab pinned down

- **headscale v0.29.3 rejects `--advertise-tags` for any pre-auth-key
  registration**, whatever `tagOwners` says:
  `hscontrol/state/state.go` — *"Reject advertise-tags for PreAuthKey
  registrations early … PreAuthKey nodes get their tags from the key itself,
  not from client requests"* → `requested tags [tag:member] are invalid or not
  permitted`. The tag comes from `preauthkeys create --tags`, which is also how
  `nufi-box invite` will mint a member's key. The nodes here pass only
  `--login-server` and `--hostname`.
- **MagicDNS name format is `<hostname>.<base_domain>`** — `nufi.box.lab`, not
  `nufi.<user>.box.lab`. Read out of the netmap (`tailscale debug netmap` →
  `nufi.box.lab.`) and exercised by the HTTPS and SMB checks, both of which use
  the name and nothing else.
- **Go honours `SSL_CERT_FILE`**, so `SSL_CERT_FILE=/lab/keys/coordinator-ca.crt`
  is all tailscaled needs to trust Caddy's internal CA (`crypto/x509`'s unix
  root loader reads it in place of the system bundle). The node entrypoint also
  drops the root into the system store for the non-Go tools in the image.
- **`TS_USERSPACE=false` is mandatory here.** In userspace mode tailscaled has
  no TUN device and the container's own curl and smbclient never leave through
  the mesh — the two things this lab exists to prove.
- **Caddy matches sites by SNI and refuses the handshake for a name it does not
  serve.** Probing `https://127.0.0.1:3080` fails at the TLS layer no matter how
  many `--no-check-certificate` flags it carries; the box stand-in's site
  therefore answers to `nufi.box.lab` *and* `localhost` so its own healthcheck
  has a name to send.
- **netfilter's MASQUERADE stops preserving the source port** once an inbound
  packet has created a conntrack entry claiming the same reply tuple. The
  peer's hole-punch packets do exactly that if the router accepts unsolicited
  inbound — the NAT then behaves as symmetric and no direct path can ever form
  (observed: 52872 → 48955). `router/entrypoint.sh` drops non-established
  inbound on the WAN leg, which is both what a real router does and what makes
  `direct` reachable here.

## Files

| file | what it is |
| --- | --- |
| `docker-compose.yml` | the topology; `include:`s the real coordinator stack |
| `coordinator.lab.yml` | the lab-only override of that stack (shared netns, ports, rendered-config paths) |
| `lab.env` | `coordinator.lab` / `box.lab` / `TLS_MODE=internal` |
| `router/` | alpine + iptables: MASQUERADE, no inbound, LEAKGUARD, optional UDP block |
| `node/entrypoint.sh` | default route via the router, CA trust, pre-auth key off disk, then `containerboot` |
| `tools/` | alpine + curl + smbclient + python3 in node-a's namespace: the member's laptop |
| `box/Caddyfile` | the box's HTTPS front, `tls internal`, `/health` |
| `run.sh` | the whole thing, and the PASS/FAIL table |
| `day-at-home.sh` | the same member, against the real VM box, over the relay |

Static checks live in `../tests/test_lab.py` (topology, pins, namespaces,
published ports, `bash -n`, `--dry-run`) and run in `box-ci.yml` with the rest
of the coordinator suite. They need the docker CLI but no daemon; `run.sh` is
the only thing that starts containers.
