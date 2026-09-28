# Box Owner Console — design

- Date: 2026-09-28
- Status: approved design; implementation starts with sub-task 01
- Scope: `deploy/box`

## Context and goal

The person who runs a NuFi box (the *owner*) today has only the `nufi-box`
command line to check on it and to bring members on. Everything the owner needs
— is the box healthy, is it on the mesh, invite a laptop, list members — is a
shell command over SSH. That is a poor fit for the target deployment: a
self-contained appliance at a site with no internet and a strict security
posture, run by an operator who should not need a terminal.

The goal is a small web console for the owner that answers "is my box working,
and who can reach it" and lets the owner bring a member on **without the command
line**, while keeping the box's defining properties intact: no dependency on
anything outside the box, and the smallest attack surface we can manage on a
sold appliance.

This document covers the whole console at a high level and its foundation
(sub-task 01) in detail. Later sub-tasks get their own plans.

## Non-goals (YAGNI)

- Not a replacement for the LibreChat/identity `console` service (that stays on
  `:3001` for chat identity and the products chooser).
- Not a user/model admin panel — that is `admin-panel` on `:3002`.
- No multi-owner accounts, roles, or an external identity provider. One owner
  secret, set locally.
- No new persistent datastore. The console holds no state of its own beyond a
  signed session cookie; every fact it shows is read live from the box.

## Architecture

### A new service, alongside the others

A new directory `deploy/box/owner-console/` holds a Bun + Hono application,
built into the box image and run as a container named `owner-console` in
`docker-compose.yml` (shared by the linux and mac overlays). It is named
`owner-console`, not `console`, so it is never confused with the existing
identity `console`.

Caddy fronts it like every other product, on a new TLS port:

```
{$BOX_HOST}:3009, {$BOX_IP}:3009, localhost:3009 {
	import box_tls
	reverse_proxy owner-console:8890
}
```

`3009` is free on a box (the box never binds it). The owner reaches the console
at `https://<box>:3009`, trusting the box's internal CA once, exactly as they do
for chat. When the box has joined a mesh, the same site is added to
`caddy/mesh.caddy` so the owner can manage the box from off-site over the mesh
(wired in a later sub-task, with the other mesh ports).

### Socket-free: how it reaches box data

The console is a web service on a sold appliance, so it holds **no privileged
access**. It never mounts the Docker socket and never shells out to the host.
It learns everything the way an ordinary network client would:

- **Service health** — an HTTP health probe to each product's health URL (the
  same URLs `nufi-box doctor` already curls: chat `:3080/health`, console
  `:3001/_health`, admin-panel `:3002/`, studio `:7860/health_check`, gateway
  `:4000/health/liveliness`). A probe that fails or times out renders as
  "unreachable", never as a crash.
- **Mesh, members, invites, self-hosted coordinator** — the headscale REST API,
  with the bearer `MESH_API_KEY` and trusting `MESH_CA_FILE`, exactly as
  `lib/mesh.sh`'s `mesh_api` does (including, on a self-host box, the
  `resolve <host>:443:127.0.0.1` that lets a host-side client reach a
  coordinator on this same host — see the note under Risks).
- **Config** — the box `.env`, mounted **read-only**, for `MESH_SERVER_URL`,
  `MESH_API_KEY`, `BOX_HOST`, `BOX_IP`, `DEPARTMENTS`, and the owner secret.

This keeps the console's blast radius to "a thing that can read box status and
mint mesh keys with the API key it was given" — not "a thing that can run
containers as root". It also means the console composes cleanly under
`--egress-enforce`: it talks only to other box services and the on-box
coordinator, all inside the box network.

### Owner authentication

- `BOX_OWNER_PASSWORD` is generated at first boot (by `install-box.sh`) if it is
  not already set, and printed **once** in the install banner. A `nufi-box`
  verb can reshow or reset it (sub-task 01 or 02).
- The console verifies the password with `Bun.password` (argon2, built into the
  Bun runtime — no npm dependency), in constant time.
- On success it issues a session cookie signed with `BOX_OWNER_SESSION_SECRET`
  (also generated at first boot): `HttpOnly`, `Secure`, `SameSite=Lax`, a
  bounded lifetime. Every route except the login page and `/healthz` requires a
  valid session, and **fails closed**: if no owner secret is configured, the
  console still starts but every authed route returns 401, so a
  misconfiguration can never leave the console open.

## Sub-task breakdown

Sub-task 01 is the foundation the rest build on. 02–05 are sketched here and
will each get their own plan.

- **01 — scaffold + owner login** (this task): the Bun + Hono app; owner
  login/logout with a signed session cookie; an empty authed dashboard shell
  (placeholder cards); `/healthz`. The `owner-console` compose service
  (socket-free, env wired, health-checked). The Caddy `:3009` site.
  `install-box.sh` generates and prints the owner password and session secret.
  Tests (below).
- **02 — status dashboard**: the health probes and the mesh/coordinator status,
  rendered as cards — the read-only "is my box working" view.
- **03 — invite = share link**: mint a `tag:member` pre-auth key over the REST
  API, wrap it in a short-lived signed token, and hand the owner a
  `/connect?token=…` **link to share**, replacing today's emailed join script.
- **04 — `/connect` page**: a branded, no-login, OS-picker page that turns a
  token into a one-click connector download. Served on `:80` (plain HTTP)
  as well, so a brand-new laptop that has not yet trusted the box CA can still
  open it. Ties to the branded zero-config connector track.
- **05 — drives and day-two**: the SMB drives view and the remaining day-two
  actions the owner currently runs on the CLI.

## Data flow (01)

```
browser ──TLS:3009──▶ Caddy ──▶ owner-console (Bun/Hono :8890)
  GET  /           → if session valid: dashboard shell; else redirect /login
  GET  /login      → login form
  POST /login      → Bun.password.verify(BOX_OWNER_PASSWORD); set signed cookie; 303 → /
  POST /logout     → clear cookie; 303 → /login
  GET  /healthz    → 200 "ok" (unauthenticated; Caddy/compose health)
```

No outbound calls in 01 beyond `/healthz`; the health probes and REST calls
arrive in 02–03.

## Error handling

- Any health probe or REST call (02+) that errors or times out renders its card
  as "unreachable" with the reason; the page always renders.
- A box that has not joined a mesh (no `MESH_API_KEY`) shows the mesh area as
  "not on a mesh yet"; the LAN status still renders.
- Missing/!unparseable owner secret → console runs, authed routes 401
  (fail-closed), login shows a clear "owner password is not configured on this
  box" message.
- Wrong password → 401 with a generic message; no lockout in 01 (a bounded
  attempt-rate limit is a later hardening item, noted in Risks).

## Security boundaries

- No Docker socket, no host shell, no write to `.env` (read-only mount).
- The only credential the console holds is `MESH_API_KEY` (already on the box)
  and the owner secret; both come from the read-only `.env`.
- Cookie is `HttpOnly`/`Secure`/`SameSite=Lax`, signed, bounded lifetime.
- Opt-in and additive: a box that does not enable the console is byte-for-byte
  unchanged (the service can be gated behind a profile / an install flag so the
  plain box carries nothing new — decided in the plan).

## Testing and CI

- **Daemon-free pytest** (the box suite's style), so it runs in the existing
  box-ci `Box suites` job with no new services:
  - compose config asserts: the `owner-console` service exists, mounts **no**
    Docker socket, mounts `.env` read-only, and has the health/REST/owner env
    wired;
  - Caddyfile asserts: the `:3009` site exists and imports `box_tls`;
  - `install-box.sh --dry-run` asserts: the owner password and session secret
    are generated and the banner prints the console URL and password.
- **`bun test`** for the Hono handlers: right/wrong password → 200/401, a cookie
  is issued on success, a protected route 401s without a session, `/healthz` is
  public. This needs a Bun step in CI. Plan decision: add a small Bun test job
  to box-ci (or run `bun test` in the image build). Recorded as an open item
  for the plan so the handler logic is not left unverified.

## Risks and open items

- **CI gains a Bun step.** The box suite is pytest-only today; the console's
  handler tests need Bun. The plan picks between a dedicated CI job and a
  build-time `bun test`. The pytest-level asserts (compose/Caddy/install) do not
  need Bun and land regardless.
- **Self-host coordinator name resolution.** On a `--self-host-coordinator`
  box, the coordinator answers on this host's loopback under its cert name; the
  console's REST client must resolve that name to `127.0.0.1` the way
  `mesh_api` now does (fixed 2026-09-28). The console reuses that rule rather
  than re-deriving it.
- **Login rate-limiting.** 01 has no attempt throttle; a bounded per-IP limit
  is a follow-up hardening item before the console is exposed on the mesh.
- **`/connect` on plain `:80`.** Serving a member page over HTTP is deliberate
  (a fresh laptop has not trusted the CA), but the token in the URL must be
  short-lived and single-use — a sub-task 04 constraint noted here so it is not
  forgotten.
- **Image size.** Adding a Bun runtime image to the box image set grows the
  offline bundle; the plan pins the Bun base image (and adds it to `make save`
  and the LAN-registry mirror, the same coverage the tailscale fix added).
