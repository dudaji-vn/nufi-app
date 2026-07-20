# Tiered Plans — Design Note

**Status:** Design only. Not implemented.
**Slot in the roadmap:** post-W5 (after Prometheus / Grafana lands the
limit-aware monitoring foundation). ~1 week of work to ship a usable v1.

## Goal

Cap how much a user can consume per period, and let them upgrade to a
larger cap. Mirrors what ChatGPT and Claude do: free users hit a wall,
see a clear "you've used X / Y this period — upgrade for more" prompt,
and click through to a higher plan. Today everyone is effectively
unlimited (the only caps are at issue-time on individual API keys).

## What LiteLLM already gives us

Limits exist on the Internal-User, Team, and Key levels — every level
supports the same fields:

| Field                   | Effect on exceed                                     |
| ----------------------- | ---------------------------------------------------- |
| `max_budget` + `budget_duration` | 403 — "Budget exceeded for the period"     |
| `tpm_limit`             | 429 — tokens-per-minute rate limit                   |
| `rpm_limit`             | 429 — requests-per-minute rate limit                 |
| `max_parallel_requests` | 429 — concurrent-request cap                         |
| `model_max_budget`      | 403 — per-model spend cap (e.g. gpt-4 lower than 3.5)|

Enforcement is free — LiteLLM returns structured error responses,
LibreChat / curl / SDK clients all see the same 429 / 403 with a
descriptive message. We only need to *configure* the limits and
respond gracefully on the 429 / 403.

## Recommended pattern — tiers as Teams

Create one LiteLLM Team per plan. Set the plan's limits on the Team.
Move users between Teams when they upgrade or downgrade. Existing keys
inherit the Team's caps automatically — no key rotation on upgrade.

```
Team: tier-free                  Team: tier-pro                Team: tier-premium
  max_budget: 1.00 / 30d           max_budget: 50.00 / 30d       max_budget: 1000 / 30d
  tpm_limit: 5,000                 tpm_limit: 50,000             tpm_limit: 200,000
  rpm_limit: 10                    rpm_limit: 60                 rpm_limit: 300
  max_parallel: 2                  max_parallel: 10              max_parallel: 50
```

**Why Team-as-tier and not per-user:**

- One source of truth — bumping every Pro user from $50 to $75 is one
  call, not N. If we used per-user limits we'd be doing N updates and
  guaranteed to drift.
- Composable — individual overrides on top of a Team are still
  supported (promo grant: bump *this user* by +$10 once, without
  touching the Pro tier config).
- LiteLLM's "team_id" field on requests means dashboards in Langfuse +
  Grafana can break down spend by tier for free.

## Architecture

```
                   ┌───────────────────────┐
                   │ Console (Bun + Hono)  │
                   │  /plan  /keys  /usage │
                   └─────────┬─────────────┘
                             │ HTTPS (master key)
                             ▼
        ┌──────────────────────────────────────────┐
        │  LiteLLM admin API                        │
        │   /team/* (per-tier limits)               │
        │   /team/member_{add,delete} (move users) │
        │   /user/update    (per-user override)    │
        └──────────────────────────────────────────┘

   ┌───────────────┐                  ┌──────────────────┐
   │ plans.json    │                  │ Stripe / billing │
   │ tier name →   │                  │  (paid plans)    │
   │  team_id      │                  │  webhook → API   │
   │  pricing      │                  │  → tier change   │
   │  copy         │                  └──────────────────┘
   └───────────────┘
```

## What we'd build

### 1. Plan registry — `console/server/lib/plans.ts`

Static map of plan key → LiteLLM team_id + display copy. The Team
itself is provisioned in LiteLLM via a one-shot script (or by hand) and
its `team_id` recorded here. Pricing is metadata for the upgrade page;
the source of truth for *what users actually get* is the Team's limits.

```ts
export const PLANS = {
  free:    { teamId: 'team-free',    label: 'Free',
             pricePerMonth: 0,    limits: { budget: 1, tpm: 5_000,  rpm: 10 } },
  pro:     { teamId: 'team-pro',     label: 'Pro',
             pricePerMonth: 20,   limits: { budget: 50, tpm: 50_000, rpm: 60 } },
  premium: { teamId: 'team-premium', label: 'Premium',
             pricePerMonth: 200,  limits: { budget: 1_000, tpm: 200_000, rpm: 300 } },
};
```

Display copy lives next to the team mapping so the upgrade UI doesn't
fan out into multiple places.

### 2. New procedures

```
plan.current   → which tier the signed-in user is on (read team membership)
plan.list      → all plans + the user's current one (for the upgrade page)
plan.change    → admin-only direct switch; users go through plan.subscribe
plan.subscribe → starts a billing flow (paid only; Stripe checkout)
```

For W3-style internal MVP: skip Stripe, expose `plan.change` for free
upgrades. Layer billing in a later phase.

### 3. New routes

- `/plan` — current plan card on top, upgrade options below, downgrade
  option in a less-prominent place. Mirror Vercel / Replicate.
- Banner on the existing pages when usage > 80 % of the period budget,
  linking to `/plan`.

### 4. Soft-warning system (the one ChatGPT does well)

Hard limits surprise users. Soft warnings give them time to act:

| Threshold     | UX                                                       |
| ------------- | -------------------------------------------------------- |
| 50 % of budget| Nothing — silent                                         |
| 80 %          | Banner: "You've used 80 % of this month's budget. Upgrade →" |
| 100 %         | LiteLLM returns 403; console shows the error + upgrade CTA |

Threshold check happens in `me.get` (already aggregating spend); banner
component reads from there.

### 5. Limit-aware error surfacing

When any LiteLLM call returns 403 or 429, the console BFF should
translate the LiteLLM error into a user-facing variant:

```
LiteLLM:  { "error": "Budget exceeded …" }
Console:  { code: "BUDGET_EXCEEDED", upgradePath: "/plan", message:
            "You've used your monthly $1 free budget. Upgrade for more." }
```

LibreChat / SDK callers see the LiteLLM error directly; the console UI
gets a nicer shape it can render with a CTA.

### 6. Message-count limits ("40 messages in 3 hours")

OpenAI / Anthropic-style "X messages per Y hours" isn't expressible
with `rpm_limit` alone. Two paths:

- **Approximation** — set `rpm_limit` low for free tier (e.g. 2/min →
  ~360/3hr, close enough for most users).
- **Custom guardrail** — Redis sliding-window counter keyed on user_id,
  registered as a LiteLLM guardrail. This is the path if the
  limit-by-window is a marketing requirement (it usually is for
  consumer SaaS — fits the "you have 13 messages left this hour"
  copy users expect). Implement in W5 alongside the LLM Guard work.

## Open questions

1. **Free tier metering** — by spend ($1/mo) or by message count? Spend
   is honest but unintuitive ("$0.01" doesn't feel like "1 message");
   message count is intuitive but doesn't reflect actual cost variance
   between models. Both is allowed if we add the custom guardrail.
2. **Mid-period upgrades** — does upgrading reset the budget, or carry
   over the spent amount? Default is "reset" (new period starts at $0)
   which matches Stripe's "prorated upgrade" UX.
3. **Per-model caps** — should `tier-free` be allowed to use the
   expensive models at all, or restricted to cheap ones? LiteLLM has
   `models: []` on Team to whitelist; useful for "premium model gating".
4. **Free-tier abuse** — one email = one free tier, but users can make
   many emails. Add CAPTCHA on registration? Email-domain whitelist for
   internal use? Decide before public launch.

## Implementation slot

Earliest sensible week is **post-W5** because:

- W5 brings Prometheus + Grafana, which we want for tier-level dashboards
  ("free-tier RPS vs pro-tier RPS over time").
- W5 brings LLM Guard / guardrail infrastructure, which is the same
  plugin surface we'd use for message-count limits.
- W3 (this branch) builds the console + JIT user provisioning, both
  prerequisites.

Day-by-day estimate when we're ready:

| Day | Work                                                    |
| --- | ------------------------------------------------------- |
| 1   | Provision the three Teams in LiteLLM; write `plans.ts`  |
| 2   | `plan.current / list / change` procedures + tests       |
| 3   | `/plan` route, current-plan card, upgrade picker        |
| 4   | Soft-warning banner + 403/429 friendly translation      |
| 5   | (Paid) Stripe wiring OR (custom) message-count guardrail|

Plus 1–2 days of buffer for the integration with whichever billing
provider gets picked.
