# Two agent products behind one door

2026-08-26

## The problem

NUFI has two agent products and neither is reachable. Both live in this
monorepo, both are branded, both run on a laptop and nowhere else.

- `apps/nufi-agent` — a Langflow fork. A canvas: drag components, wire them
  into a flow, run it.
- `apps/agents` — a Paperclip fork. An operations app: companies, an org
  chart, goals, approvals, costs. Agents that do work.

They need to be public, reachable from `chat.nufi.me`, and a member who
arrives from there must already be signed in — the way `console.nufi.me`
already works. Right now a visitor would meet two unfamiliar login screens
and two unfamiliar product names.

## What already exists

Five findings from reading the code. Four of them mean less to build than
expected; the fifth nearly invalidated the design.

**The gateway-key half already ships.** `console.nufi.me/connect` verifies the
chat-issued `refreshToken` cookie, renders a consent screen, mints a LiteLLM
key bound to `user_id`, and returns it by `postMessage` to an origin matched
against `AGENTS_ALLOWED_ORIGINS`. The Paperclip side is a plugin under
`apps/agents/nufi/connect-plugin/`. Deploying does not change any of it —
only the allow-list gains a host.

**The Langflow fork already supports external identity.** `langflow/services/
auth/external.py` accepts a credential issued by an upstream identity layer
from a configured header or cookie, validates it against JWKS, and hands it to
`BaseAuthService.get_or_create_user_from_claims`, which provisions the local
user on first sight. Access level maps from a claim onto viewer / editor /
admin. Every knob is a `LANGFLOW_EXTERNAL_AUTH_*` environment variable. **No
fork change at all.**

**The Paperclip fork can consume OIDC for the price of one file.** It runs
better-auth 1.6.23 with email and password only and no plugins. That version
already ships `generic-oauth` in `node_modules`; turning it on is an edit to
`server/src/auth/better-auth.ts`.

**Sandbox providers install at runtime.** All seven —
cloudflare, daytona, e2b, exe-dev, kubernetes, modal, novita — are npm
packages installed from the Plugins page. Choosing or switching one is an
operational decision, not a code change.

**Only the Kubernetes provider enforces the egress invariant.** A grep across
all seven for network configuration returns: `kubernetes` exposes
`egressAllowFqdns` and `egressAllowCidrs`; `modal` exposes `blockNetwork` and
a CIDR allow-list; the other five expose nothing. `nufi/adapters.json` pins
every adapter to `allowFqdns: ["api.codechi.me"]` and `verify-adapters.mjs`
asserts it, warning that a regression here is silent — the app keeps working
and the guardrails simply stop seeing the traffic. **Only the Kubernetes
provider reads that field.** On E2B or Daytona the guard would be asserting
something no layer enforces, which is worse than no guard, because it reads
like a guarantee.

## Names

The two products had already named themselves, and the names collided:
`apps/agents` renders as `NUFI Agents` and `apps/nufi-agent` as `NuFi Agent`
— one letter apart, indistinguishable aloud.

They are renamed by what they do:

| Fork | Product | Host |
|---|---|---|
| `apps/nufi-agent` (Langflow) | **NuFi Studio** | `studio.nufi.me` |
| `apps/agents` (Paperclip) | **NuFi Works** | `works.nufi.me` |
| — | the chooser | `agents.nufi.me` |

Both `PRODUCT` constants live in allow-listed `nufi/` directories
(`apps/agents/nufi/rebrand.mjs`, `apps/nufi-agent/nufi/rebrand.ts`), so the
rename costs two lines and does not widen either fork diff. It has to happen
before the products are shown to anyone, because the cost afterwards is
withdrawing material already handed out.

## The shape

```
chat.nufi.me ──"Agents"──▶ agents.nufi.me     (a route on the console service)
                                 │
                                 ├──▶ studio.nufi.me    NuFi Studio
                                 └──▶ works.nufi.me     NuFi Works
                                                │
console.nufi.me ── identity issuer ─────────────┘
   has:  chat session verification · per-user LiteLLM keys · /connect
   adds: JWKS · authorize · token · userinfo

Kubernetes + Cilium ── where a NuFi Works agent actually runs
```

`agents.nufi.me` is a route on the existing console service, not a service of
its own. The page is static and identity already lives in the console. Idle
memory is 84% of the Railway bill, so a service that exists to serve one
static page is a recurring cost that buys nothing.

## Identity: one issuer, two standard consumers

The console already brokers NUFI identity into another app — it verifies a
chat session and issues a gateway credential from it. Issuing a session
instead of a key is the same job with a different output. That is the reason
to put the issuer there rather than build a third thing: there is then exactly
one place where "who may enter which product" is decided and audited.

### NuFi Studio

The console sets a short-lived signed JWT as a cookie scoped to `.nufi.me`.
Studio reads it via `LANGFLOW_EXTERNAL_AUTH_TOKEN_COOKIE`, verifies it against
`LANGFLOW_EXTERNAL_AUTH_JWKS_URL` on the console, and provisions the user on
first sight. Settings, in full:

```
LANGFLOW_AUTO_LOGIN=false
LANGFLOW_EXTERNAL_AUTH_ENABLED=true
LANGFLOW_EXTERNAL_AUTH_TOKEN_COOKIE=nufi_id
LANGFLOW_EXTERNAL_AUTH_JWKS_URL=https://console.nufi.me/.well-known/jwks.json
LANGFLOW_EXTERNAL_AUTH_ISSUER=https://console.nufi.me
LANGFLOW_EXTERNAL_AUTH_AUDIENCE=nufi-studio
LANGFLOW_EXTERNAL_AUTH_SUBJECT_CLAIM=sub
LANGFLOW_EXTERNAL_AUTH_EMAIL_CLAIM=email
LANGFLOW_EXTERNAL_AUTH_ACCESS_CEILING_ENABLED=true
LANGFLOW_EXTERNAL_AUTH_DEFAULT_ACCESS_LEVEL=editor
```

`EXTERNAL_AUTH_TRUSTED_JWT_DECODE` stays off. It skips signature verification
and is only safe behind a proxy that has already checked the token; there is
no such proxy here, and the JWKS path costs nothing.

### NuFi Works

better-auth's `genericOAuth` plugin points at the console's authorize, token
and userinfo endpoints and runs an ordinary authorization-code flow, ending in
better-auth's own host-scoped session cookie. `PAPERCLIP_AUTH_DISABLE_SIGN_UP=true`
makes the console the only way in.

This is the one file added to the `apps/agents` allow-list. `generic-oauth` is
a supported better-auth extension point rather than a patch, so the diff stays
small and is a candidate to send upstream.

### Why no proxy in front of either app

An earlier shape put a thin authentication proxy in front of each host, so the
proxy could set a session cookie scoped to exactly that host. It was dropped:
two more services, two more idle footprints, and two more things to keep
running, in exchange for narrowing a cookie that is already only sent to hosts
we operate.

The cost is real and stated rather than hidden: the `.nufi.me` cookie carrying
the Studio token reaches every NUFI subdomain. It is audience-scoped and
short-lived, so another subdomain cannot use it for anything except replaying
it to Studio, which is where it was going anyway. If a subdomain is ever
operated by someone else, this decision has to be revisited, and the
per-host proxy is the upgrade.

## Running agents for real

Agents must actually run, which requires a sandbox provider, which — given the
egress invariant — means Kubernetes with Cilium.

Cilium specifically, not Kubernetes generally. `network-policy.ts` documents
its own limit: standard NetworkPolicy cannot express FQDNs, so when FQDNs are
configured without explicit CIDRs it falls back to "public IPv4 except
RFC1918, link-local, loopback and multicast". That keeps agent pods out of
cluster internals but does nothing to keep model traffic on the gateway, which
is the whole point of the invariant. Exact FQDN allow-listing needs
`egressMode: "cilium"`.

### The direction of travel, which is the opposite of the obvious guess

Both policy builders let the agent pod reach paperclip-server through an
**in-cluster selector** — a namespace match in the standard policy, an endpoint
match on `app: paperclip-server` in the Cilium policy — on port 3100. Read in
isolation that says the server must live in the cluster, which would put NuFi
Works on Kubernetes rather than Railway.

It does not. `onEnvironmentExecute` runs commands through `execInPod`, which
opens a WebSocket **from paperclip-server out to the kube-apiserver** and execs
into the pod. The runtime images under `docker/agent-runtime/` carry no
registration or callback logic at all. `generateBootstrapToken` states the
callback scheme is still ahead: *tighten once the agent runtime shim lands its
callback auth scheme*.

So traffic runs server to apiserver to pod. The pod never dials the server, and
those in-cluster egress rules are provision for a model that has not landed
yet. **NuFi Works stays on Railway.**

The real network requirement is the mirror image, and it is easy to miss while
looking for the wrong one: **the NuFi Works service must reach the cluster's
Kubernetes API**. The plugin supports exactly this — `inCluster: true` for a
server inside the cluster, or a `kubeconfig` for one outside it. The cluster
therefore needs a reachable API endpoint and a kubeconfig held as a Railway
secret, scoped to a service account that can only manage sandbox namespaces.

Nothing needs to be added to `egressAllowFqdns` for the callback, because
there is no callback. The environment-level field stays available for the day
the shim lands.

## Deployment

Railway, project `nufi` (`06c8dad0-f74c-412e-b9cf-f563676520d5`), environment
`production`.

| Service | Builds | Storage | Outbound |
|---|---|---|---|
| `nufi-studio` | `apps/nufi-agent` | Postgres database | LiteLLM gateway |
| `nufi-works` | `apps/agents/Dockerfile` | Postgres database + volume at `/paperclip` | LiteLLM gateway, **cluster Kubernetes API** |
| `nufi-console` | unchanged, gains routes and the `agents.nufi.me` domain | — | LiteLLM admin API |

Both applications get a database on **one new Postgres service**, not two.
Studio needs one because `LANGFLOW_AUTO_LOGIN=false` makes it multi-user and
its SQLite default does not survive a redeploy; Works needs one because
better-auth is wired to a drizzle adapter with `provider: "pg"`. Two databases
on one server couple their availability, which is accepted here to avoid
paying for a second idle instance.

Changing a Railway service's source through the CLI is not enough:
`railway redeploy` re-runs the old deployment. Use `serviceInstanceUpdate`
followed by `serviceInstanceDeployV2`, with the token at
`~/.railway/config.json` under `.user.accessToken`.

## Order of work

| | Work | Blocked by |
|---|---|---|
| ~~0~~ | ~~Spike: how the agent shim addresses paperclip-server~~ — **done, see above** | — |
| 1 | Rename to Studio and Works, including docs and screenshots | — |
| 2 | NuFi Studio on Railway at `studio.nufi.me` | — |
| 3 | NuFi Works on Railway at `works.nufi.me`, with Postgres and volume | — |
| 4 | Console issues OIDC; the chooser at `agents.nufi.me` | 2, 3 |
| 5 | Cilium cluster and sandbox provider | 0 |

Step 0 led because it was the only thing that could force NuFi Works off
Railway. It came back negative: the pod never dials the server, so Works stays
on Railway and step 3 is safe to build.

Steps 1 through 4 stand alone. Stopping after step 4 yields two branded,
reachable products that a member enters already signed in, with per-user
gateway keys — everything except an agent that runs. That is a coherent place
to stop if step 5 proves too heavy.

## What this does not do

**It does not scope who may enter.** Every `chat.nufi.me` account reaches both
products. There is no invite list and no per-product entitlement. Adding one
later belongs in the console, since that is where the decision is made.

**It does not sandbox NuFi Studio.** Studio executes flow components in its own
process. The egress work here covers Works agents only. A Studio flow with a
code component is not confined by anything described above.

**It does not solve token refresh for Studio.** The `.nufi.me` cookie expires
and the member has to re-enter through `agents.nufi.me`. A silent refresh is
possible and is not built.

**It does not survive a hostile subdomain.** See "Why no proxy in front of
either app".
