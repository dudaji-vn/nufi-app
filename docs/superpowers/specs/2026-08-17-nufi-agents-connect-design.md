# Connecting NUFI Agents to a gateway key without pasting one

2026-08-17

## The problem

Running an agent on the `nufi_agent` adapter requires a gateway credential.
Today that credential arrives one way: an operator sets `NUFI_MODEL_API_KEY` in
the agents server's process environment before boot.

That has three costs.

1. **It is a shared key.** Every agent in every company on that server calls the
   gateway as the same LiteLLM principal. Spend is one number. When it climbs,
   nothing in the data says whose work caused it.
2. **It needs an operator.** A member who wants to try an agent cannot; they
   file a ticket. The credential is a deploy-time artefact, so changing it is a
   restart.
3. **It cannot be revoked narrowly.** Someone leaves; the only key is the one
   everyone uses.

Meanwhile the same person already has a NUFI account, already signed in at
`chat.nufi.me`, and the console at `console.nufi.me` already mints per-user
gateway keys from that session. The credential they need exists and is one
click away — through a different app, with a copy-paste in between.

This closes that gap: **the member clicks Connect in the agents app and their
own gateway key is provisioned into their own agent runs.**

## What already exists

Four findings from reading the code, because three of them mean less to build
than expected.

**Paperclip already delivers per-user secrets to a run.** `heartbeat.ts`
resolves an agent's env bindings before dispatch and merges the result into
`resolvedConfig.env`; that object is passed to `adapter.execute` as
`ctx.config`. One binding type — `user_secret_ref` — resolves against the run's
`responsibleUserId`, so the same agent hands each member their own value. The
adapter only has to read it.

**Paperclip already has the UX for "everyone fills in their own".** A company
admin declares a *user secret definition*; each member supplies a value under
Settings → My secrets, and a banner nags whoever has not. We are adding a button
to a surface that already exists, not inventing a surface.

**The console already does the credential half.** `middleware/auth.ts` verifies
the chat-issued `refreshToken` cookie; `keys.create` mints a LiteLLM key bound
to `user_id`. What is missing is a way for another app to ask for one.

**The fork must stay thin.** `check-fork-diff.sh` rejects any change under
`apps/agents` outside `nufi/` and a short branding allowlist. So the button
cannot be added to `ui/src`. It ships as a Paperclip plugin — the extension
point upstream provides — living entirely in `apps/agents/nufi/`.

## The flow

```
agents app                        console.nufi.me                LiteLLM
──────────                        ───────────────                ───────
Settings → NUFI
  "Connect NUFI account"
        │
        │  window.open (top-level navigation)
        └──────────────────────────▶ /connect?origin=…&state=…&company=…
                                     │
                                     │  refreshToken cookie rides along
                                     │  verify session
                                     │  check origin against allow-list
                                     │
                                     ▼
                                   consent screen
                                   (budget, expiry, what it replaces)
                                     │
                                     │  Approve
                                     ├───────────────────────────▶ key/generate
                                     │                             user_id=<me>
                                     │                             alias=nufi-agents:<company>
        ◀────────────────────────────┘
        postMessage({state, key}) → the origin the SERVER validated
        │
        ├─ POST /api/companies/:id/me/user-secrets  { NUFI_MODEL_API_KEY }
        │  (the value is never rendered)
        │
        └─ agent env: NUFI_MODEL_API_KEY = { type: "user_secret_ref", … }
                                                          │
                                       run dispatch ──────┘
                                       ctx.config.env.NUFI_MODEL_API_KEY
```

### Why a popup and not a direct call

`chat.nufi.me` and `console.nufi.me` are the same site, so a plain
`fetch(…, {credentials:"include"})` from an agents app also hosted on
`nufi.me` would carry the cookie. It would also stop working the moment agents
is deployed anywhere else — an on-prem customer's domain, or `localhost` during
development — because the cookie is then cross-site.

A popup is a *top-level navigation*, which carries a `SameSite=Lax` cookie
regardless of where the opener is hosted. The same code path works in
production, on-prem, and on a laptop.

It also puts a consent screen in front of minting a credential, which is the
honest place for one.

### The security boundary

**The origin allow-list on the console is the only thing standing between this
flow and a credential-theft page.** Any site can open a popup to
`console.nufi.me/connect`; the victim's cookie will be sent; the console will
recognise them. What must not happen is the console handing the key back to
whoever asked.

So:

- `origin` is matched against `AGENTS_ALLOWED_ORIGINS` — exact string equality
  against a parsed origin, no wildcards, no prefix or suffix matching.
- An unlisted origin is refused **before** the consent screen renders, so no
  user can be talked through approving one.
- `postMessage` targets the origin the *server* returned, never the one the
  client sent.
- Unset `AGENTS_ALLOWED_ORIGINS` disables the endpoint rather than defaulting
  open.
- `state` is generated by the opener and echoed back; a response that does not
  match the pending request is dropped.
- No opener means no delivery path, so the console refuses before minting
  rather than leaving an orphan key behind.

### Accepted risk

The key passes through the agents tab's JavaScript before being stored. Closing
that would need a server-to-server code exchange, which needs the console to
hold state it currently does not have.

The trade is not worth it here: plugin UI is same-origin trusted code by
Paperclip's own model, and the console already reveals freshly minted keys to
the browser on its own keys page. The exposure is unchanged; the architecture
would not be. Revisit if the console ever grows a store for other reasons.

## Components

### 1. Adapter — read the resolved env

`nufi/adapter/src/server/client.ts` resolves the credential from
`ctx.config.env[apiKeyEnv]` first and `process.env[apiKeyEnv]` second. Process
env stays as the single-tenant and self-hosted path; it becomes the fallback
rather than the only option.

`testEnvironment` drops from `error` to `warn` when process env is unset,
because it is no longer fatal — a per-user secret satisfies the run and
`testEnvironment` cannot see one.

### 2. Console — `/connect`

- `server/lib/connect-origins.ts` — parse and match the allow-list.
- `server/router/connect.ts` — `begin` (validate origin + session, return the
  canonical origin and the terms) and `approve` (re-validate, revoke the prior
  key for this company alias, mint, return once).
- `src/routes/connect.tsx` — consent screen, `postMessage`, close.

Reconnecting revokes the key previously issued for the same
`nufi-agents:<companyId>` alias. Scoping by company means a member connected to
two Paperclip instances does not knock out one by reconnecting the other.

### 3. Agents — the connect plugin

`nufi/connect-plugin/`, a `companySettingsPage` slot. Shows connection state,
runs the popup, writes the value through the host's own user-secrets API, and —
for an admin who has not done it yet — offers to create the
`NUFI_MODEL_API_KEY` definition.

The console's URL comes from the worker (`NUFI_CONSOLE_URL`), not the bundle, so
one build serves every deployment.

### 4. Documentation

Deployment gets the two new variables and the plugin install step. The end-user
page gets the connect flow.

## What this does not do

- **It does not force the key through the gateway.** That is still Cilium's job
  and still unbuilt. A member who pastes any OpenAI key into the same secret
  gets an agent that talks to OpenAI.
- **It does not budget agents separately from chat.** The key inherits the
  console's per-user defaults; agent spend and chat spend land on one person's
  ledger, which is the point, but nothing caps agents on their own.
- **It does not remove the operator from first-time setup.** Someone still
  installs the plugin and declares the definition once per company.
