# Docs audit, 2026-09-07: what was wrong in the code, not the docs

Companion to `docs/superpowers/specs/2026-09-07-docs-audit-design.md`. Each
entry is something a documented path ran into that a doc rewrite cannot fix.
Nothing here has been changed; each item is a proposal.

Severity: **blocks** a documented path · **misleads** a reader or operator ·
**cosmetic**.

## Lane 1: Develop

### F1. The gateway image goes stale silently, and nothing rebuilds it — blocks

**Seen:** on a machine that had run the stack in July, `docker compose up -d`
after pulling `main` brought up every service except the gateway.
`npuops-litellm` restarted 8 times with

```
ValueError: G1: unknown threshold key(s) ['tool'], expected ['assistant', 'system', 'untrusted', 'user']
ERROR:    Application startup failed. Exiting.
```

**Why:** `litellm-proxy` is a derived image (`deploy/platform/docker-compose.yml:193`,
`build: ./litellm`, `image: nufi/litellm:local`) with the guardrail package
baked in, while the policy it loads comes from the checkout. The local image
was built 2026-07-30; `litellm/guardrails/policy.yaml` gained the `tool` span
source on 2026-09-04 (`a3ee40e85`). Compose does not rebuild a `build:` service
on `up -d`, `scripts/bootstrap.sh` never runs `docker compose build`, and
`README.md` never says to. Every developer who pulls a guardrail change gets a
gateway that will not start, with an error that names a policy key rather than
the cause.

**Proposed fix:** make the build part of the documented path and the script:
`bootstrap.sh` runs `docker compose build litellm-proxy nufi-scanner` (or
`up -d --build`) before `up`, and the "Run the stack locally" page says the
same for `git pull`. Longer term, publish `nufi/litellm` to GHCR from CI like
the other images so the checkout and the image cannot drift.

### F2. The local console talks to production chat for identity — misleads

**Seen:** `deploy/platform/docker-compose.yml:415` hands the console
`LIBRECHAT_URL`. Nothing in `apps/console/server` reads that name. The
identity resolver reads `CHAT_BASE_URL`
(`apps/console/server/lib/chat-identity.ts:19`) and, when it is unset, falls
back to `https://chat.nufi.me`.

**Effect:** on the local stack every console feature that needs the member's
email and role (the handoff into NUFI Studio and NUFI Works) asks production
chat about a locally issued cookie. It cannot succeed, and the failure surfaces
inside Studio or Works as a missing email rather than in the console. A
developer working on the handoff locally cannot reproduce production.

**Proposed fix:** pass `CHAT_BASE_URL: http://librechat:3080` (the in-network
address) in the compose service, drop the unread `LIBRECHAT_URL` line, and make
the resolver refuse to start without an explicit value instead of defaulting to
a production host.

### F3. The published chat and console images are amd64-only — blocks (Apple Silicon)

**Seen:** `ghcr.io/dudaji-vn/nufichat:main` and `nufi-console:main` publish a
single `linux/amd64` manifest. On an arm64 Mac `docker compose up` fails with
`no matching manifest for linux/arm64/v8`, and because the pull is one
transaction it takes the already-running services down with it. The developer
who hit this keeps a gitignored `docker-compose.override.yml` pinning
`platform: linux/amd64` for both services, which nothing in the repo or the
docs mentions.

**Proposed fix:** build the two images for `linux/amd64,linux/arm64` in
`chat-release.yml` and `console-image.yml` (`docker/build-push-action` with
`platforms:`). Until then, the "Run the stack locally" page tells Apple Silicon
developers to add the override, and ships it as
`docker-compose.override.example.yml`.
