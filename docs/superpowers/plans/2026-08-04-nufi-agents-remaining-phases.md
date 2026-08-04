# NuFi Agents — Remaining Phases Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Take `apps/agents` from "a white-labelled fork that boots" to "a product NuFi can defend, brand and ship" — by running the product-fit spike that was skipped, making the gateway chokepoint real instead of advisory, finishing the rename on both sides, and releasing it.

**Architecture:** Nothing here edits vendored Paperclip source. The spike is a standalone bridge service that speaks Paperclip's webhook contract on one side and `apps/chat`'s OpenAI-compatible agent API on the other. The egress lock is Cilium configuration plus a falsification test. The rename becomes safe by applying the same transform to the server bundle, so both sides agree. Everything NuFi owns stays under `apps/agents/nufi/` or `ui/nufi-*`, inside the allowlist enforced by `.github/workflows/agents-ci.yml`.

**Tech Stack:** TypeScript, Bun + Hono (bridge service), Node 22, pnpm 9.15.4, Vitest, Docker, Kubernetes + Cilium, GitHub Actions, GHCR.

## Global Constraints

- **Never edit vendored upstream files.** The allowlist in `apps/agents/nufi/check-fork-diff.sh` is the contract. If a change seems to require an upstream edit, the answer is an external package, a config file, or a pull request to `paperclipai/paperclip` — in that order.
- The gateway host is `api.codechi.me`. Every enabled adapter's `allowFqdns` and `defaultEnv` base URL must point there and nowhere else (`apps/agents/nufi/verify-adapters.mjs` asserts it).
- Adapter type strings come from each adapter's own `export const type`, **not** from the kubernetes provider's `adapter-defaults.ts` — those disagree (`cursor` vs `cursor_local`), and the wrong one is a boot failure.
- Local installs need `pnpm install --frozen-lockfile --node-linker=isolated`. A hoisted layout breaks `ui/vite.config.ts`'s hardcoded lexical alias.
- pnpm is pinned to `9.15.4` via `apps/agents/package.json`. The repo root has no `package.json` on purpose — CI actions must be pointed at `apps/agents/package.json`.
- Never name a NuFi script `check-*.mjs` under `apps/agents/`: upstream's `.gitignore:20` ignores that pattern and the file silently never gets committed, with a clean `git status`.
- Do not write a `*/` glob inside a block comment. It ends the comment.
- Secrets only via `.env` or Kubernetes secrets. `apps/agents/.env` is already gitignored. Never commit an API key.
- All three CI jobs must be green before merge: `Fork diff stays in the allowlist`, `Every enabled adapter egresses only to the gateway`, `Rebrand transform`.
- Work on `develop`, branching per task group. `apps/agents` was merged in PR #3.

## What Changed During The Prototype

Two findings from building the prototype change what this plan must do. Both are recorded in `apps/agents/nufi/README.md`.

1. **`allowFqdns` alone confines nothing.** `packages/plugins/sandbox-providers/kubernetes/src/network-policy.ts:8-16` states that standard Kubernetes NetworkPolicy cannot express FQDNs, and that when `allowFqdns` is set without explicit CIDRs it falls back to *"public IPv4 except RFC1918/link-local/loopback/multicast"* — the whole internet. Exact FQDN allow-listing requires `egressMode: "cilium"`. Task 4 is therefore about Cilium, not about Kubernetes generally, and the containment claim in the design doc §3 C2 is unproven until Task 5 passes.

2. **Phase 0 is not pure configuration.** The `http` adapter POSTs a Paperclip-shaped payload and expects the agent to call back into `/api/*` (`docs/adapters/http.md`, `.claude/skills/paperclip/SKILL.md`). `apps/chat` exposes `POST /api/agents/chat/completions`, an OpenAI-compatible endpoint. The shapes do not meet, so the spike needs a bridge — small, but real code.

## File Structure

```
apps/agents/nufi/
├── adapters.json                  MOD  re-add the `http` adapter (Task 1)
├── verify-adapters.mjs            MOD  allow gateway-less http entry (Task 1)
├── rebrand.mjs                    NEW  the transform core, shared by UI and server (Task 6)
├── rebrand-server-dist.mjs        NEW  applies it to server/dist after tsc (Task 6)
├── egress/
│   ├── cilium-values.yaml         NEW  sandbox provider config, egressMode: cilium (Task 4)
│   └── verify-egress.sh           NEW  the falsification test (Task 5)
└── bridge/
    ├── package.json               NEW  Bun + Hono (Task 2)
    ├── src/index.ts               NEW  webhook endpoint, Hono app (Task 2)
    ├── src/paperclip.ts           NEW  control-plane client (Task 2)
    ├── src/chat.ts                NEW  apps/chat agent client (Task 2)
    ├── src/run.ts                 NEW  the orchestration: context → chat → comment (Task 2)
    └── src/run.test.ts            NEW  (Task 2)

apps/agents/ui/
├── nufi-rebrand.ts                MOD  import the shared core (Task 6)
└── nufi-rebrand.test.ts           MOD  whole-string cases return (Task 7)

packages/adapters-nufi/            NEW  the first-party external adapter (Task 8)
├── package.json
├── src/index.ts                   metadata + createServerAdapter re-export
├── src/server/execute.ts          the run
├── src/server/execute.test.ts
└── src/ui-parser.ts               transcript parser

apps/docs/content/docs/            NEW pages (Task 9)
.github/workflows/agents-release.yml  NEW  (Task 10)
apps/agents/Dockerfile.nufi        NEW  (Task 10)
```

---

## Task 1: Re-enable the `http` adapter

The registry disables `http` by omission, and the spike drives NuFi agents through exactly that adapter. Confirmed from the running server log:

```
disabled: ... openclaw_gateway, hermes_*, acpx_local, process, http
```

`http` is a webhook adapter, not a sandboxed harness — it has no `runtimeImage` and does not egress to a model provider itself. `verify-adapters.mjs` currently requires every enabled adapter to have a gateway `allowFqdns` and a `*_BASE_URL`, which is right for harnesses and wrong for this one.

**Files:**
- Modify: `apps/agents/nufi/adapters.json`
- Modify: `apps/agents/nufi/verify-adapters.mjs`

**Interfaces:**
- Produces: an enabled `http` adapter type, consumed by Task 3's spike.

- [ ] **Step 1: Write the failing check case**

Add to `apps/agents/nufi/verify-adapters.mjs`, just above the `for (const entry of registry)` loop:

```js
/**
 * `http` is a webhook adapter: Paperclip POSTs to an external service that
 * calls back into /api. It runs no harness, so it has no runtimeImage, no
 * sandbox and no model egress of its own — the gateway invariant applies to
 * whatever it calls, not to it. Holding it to the harness rules would force a
 * fake runtimeImage and a meaningless allowFqdns.
 */
const WEBHOOK_ADAPTERS = new Set(["http"]);
```

- [ ] **Step 2: Relax the harness-only assertions**

Replace the `if (!entry.runtimeImage) { … }` block and the body of `if (!entry.enabled) continue;` onwards with:

```js
  if (!entry.runtimeImage && !WEBHOOK_ADAPTERS.has(name)) {
    problems.push(`${name}: runtimeImage is required`);
  }

  if (!entry.enabled) continue;
  if (WEBHOOK_ADAPTERS.has(name)) continue;
```

- [ ] **Step 3: Add `http` and `process` to the known types**

`http` and `process` are built-in adapter types the server reports, not packages under `packages/adapters/`. Extend `KNOWN_ADAPTERS`:

```js
  "opencode_local",
  "pi_local",
  "http",
  "process",
]);
```

- [ ] **Step 4: Add the registry entry**

Append to `apps/agents/nufi/adapters.json`, inside the array:

```json
  {
    "adapterType": "http",
    "enabled": true
  }
```

- [ ] **Step 5: Verify**

```bash
cd /Users/sun/Workspace/DudajiVN/nufi-app
node apps/agents/nufi/verify-adapters.mjs
```

Expected: `5 adapters — 5 enabled, 0 disabled` then `OK — every enabled adapter routes and egresses only to api.codechi.me.`

- [ ] **Step 6: Verify the server accepts it**

```bash
cd apps/agents
docker run -d --name nufi-agents-pg -e POSTGRES_USER=paperclip \
  -e POSTGRES_PASSWORD=paperclip -e POSTGRES_DB=paperclip \
  -p 5433:5432 postgres:16-alpine
set -a; . ./.env; set +a
pnpm db:migrate && pnpm dev:server 2>&1 | grep -m1 "reconciled adapter availability"
```

Expected: the `enabled` list now contains `http`.

- [ ] **Step 7: Commit**

```bash
git add apps/agents/nufi/adapters.json apps/agents/nufi/verify-adapters.mjs
git commit -m "feat(agents): enable the http adapter for the product-fit spike

Phase 0 drives NuFi agents through the http webhook adapter, which the
registry disabled by omission. It runs no harness and has no model egress
of its own, so the gateway assertions that apply to sandboxed harnesses
would only force a fake runtimeImage here."
```

---

## Task 2: The spike bridge

Paperclip POSTs a run to a URL and expects the agent to call back into `/api`. `apps/chat` speaks OpenAI chat-completions. This service is the translation, and it is deliberately throwaway — its job is to answer one question, not to become a product.

**Files:**
- Create: `apps/agents/nufi/bridge/package.json`
- Create: `apps/agents/nufi/bridge/src/paperclip.ts`
- Create: `apps/agents/nufi/bridge/src/chat.ts`
- Create: `apps/agents/nufi/bridge/src/run.ts`
- Create: `apps/agents/nufi/bridge/src/index.ts`
- Test: `apps/agents/nufi/bridge/src/run.test.ts`

**Interfaces:**
- Consumes: the `http` adapter enabled in Task 1.
- Produces: `handleRun(deps, payload): Promise<RunOutcome>` — consumed by Task 3.

- [ ] **Step 1: Scaffold**

`apps/agents/nufi/bridge/package.json`:

```json
{
  "name": "@nufi/agents-bridge",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "bun run src/index.ts",
    "test": "bun test"
  },
  "dependencies": {
    "hono": "^4.6.14"
  }
}
```

```bash
cd apps/agents/nufi/bridge && bun install
```

- [ ] **Step 2: Write the failing test**

`apps/agents/nufi/bridge/src/run.test.ts`:

```ts
import { describe, expect, it } from "bun:test";

import { handleRun } from "./run";

const payload = {
  runId: "run_1",
  agentId: "agent_1",
  companyId: "co_1",
  context: { taskId: "issue_1", wakeReason: "issue_assigned" },
};

function deps(overrides = {}) {
  const calls: string[] = [];
  return {
    calls,
    paperclip: {
      checkout: async () => { calls.push("checkout"); return { ok: true }; },
      heartbeatContext: async () => {
        calls.push("context");
        return { title: "Translate the login screen", body: "Vietnamese to English." };
      },
      comment: async (_id: string, body: string) => { calls.push(`comment:${body}`); },
      setStatus: async (_id: string, s: string) => { calls.push(`status:${s}`); },
    },
    chat: {
      complete: async () => { calls.push("chat"); return "Done — 14 strings translated."; },
    },
    ...overrides,
  };
}

describe("handleRun", () => {
  it("checks out, reads context, asks chat, then reports back", async () => {
    const d = deps();
    const outcome = await handleRun(d, payload);

    expect(outcome.status).toBe("succeeded");
    expect(d.calls).toEqual([
      "checkout",
      "context",
      "chat",
      "comment:Done — 14 strings translated.",
      "status:in_review",
    ]);
  });

  it("does not comment or move the task when checkout is refused", async () => {
    const d = deps({
      paperclip: {
        ...deps().paperclip,
        checkout: async () => ({ ok: false, conflict: true }),
      },
    });
    const outcome = await handleRun(d, payload);

    expect(outcome.status).toBe("skipped");
    expect(d.calls.some((c) => c.startsWith("comment"))).toBe(false);
  });

  it("reports the failure as a comment and leaves the task open", async () => {
    const d = deps({ chat: { complete: async () => { throw new Error("gateway 503"); } } });
    const outcome = await handleRun(d, payload);

    expect(outcome.status).toBe("failed");
    expect(d.calls.at(-1)).toBe("comment:Run failed: gateway 503");
  });
});
```

- [ ] **Step 3: Run it and watch it fail**

```bash
cd apps/agents/nufi/bridge && bun test
```

Expected: FAIL — `Cannot find module './run'`.

- [ ] **Step 4: Implement the orchestration**

`apps/agents/nufi/bridge/src/run.ts`:

```ts
export interface RunPayload {
  runId: string;
  agentId: string;
  companyId: string;
  context: { taskId: string; wakeReason: string };
}

export interface RunOutcome {
  status: "succeeded" | "failed" | "skipped";
  detail?: string;
}

export interface RunDeps {
  paperclip: {
    checkout(issueId: string, agentId: string, runId: string): Promise<{ ok: boolean; conflict?: boolean }>;
    heartbeatContext(issueId: string): Promise<{ title: string; body: string }>;
    comment(issueId: string, body: string, runId: string): Promise<void>;
    setStatus(issueId: string, status: string, runId: string): Promise<void>;
  };
  chat: {
    complete(prompt: string): Promise<string>;
  };
}

/**
 * One heartbeat. Checkout first — a 409 means another agent owns the issue and
 * the correct response is to stop, never to retry (SKILL.md, Step 5).
 */
export async function handleRun(deps: RunDeps, payload: RunPayload): Promise<RunOutcome> {
  const { taskId } = payload.context;

  const claim = await deps.paperclip.checkout(taskId, payload.agentId, payload.runId);
  if (!claim.ok) {
    return { status: "skipped", detail: claim.conflict ? "owned by another agent" : "checkout refused" };
  }

  const issue = await deps.paperclip.heartbeatContext(taskId);

  try {
    const answer = await deps.chat.complete(`${issue.title}\n\n${issue.body}`);
    await deps.paperclip.comment(taskId, answer, payload.runId);
    await deps.paperclip.setStatus(taskId, "in_review", payload.runId);
    return { status: "succeeded" };
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err);
    await deps.paperclip.comment(taskId, `Run failed: ${detail}`, payload.runId);
    return { status: "failed", detail };
  }
}
```

- [ ] **Step 5: Run the tests**

```bash
cd apps/agents/nufi/bridge && bun test
```

Expected: 3 pass.

- [ ] **Step 6: Implement the Paperclip client**

`apps/agents/nufi/bridge/src/paperclip.ts`. Every mutating call carries `X-Paperclip-Run-Id`, which the control plane requires for the audit trail:

```ts
const API_URL = process.env.PAPERCLIP_API_URL ?? "http://localhost:3100";
const API_KEY = process.env.PAPERCLIP_API_KEY ?? "";

function headers(runId?: string) {
  const h: Record<string, string> = {
    "content-type": "application/json",
    authorization: `Bearer ${API_KEY}`,
  };
  if (runId) h["X-Paperclip-Run-Id"] = runId;
  return h;
}

export const paperclip = {
  async checkout(issueId: string, agentId: string, runId: string) {
    const res = await fetch(`${API_URL}/api/issues/${issueId}/checkout`, {
      method: "POST",
      headers: headers(runId),
      body: JSON.stringify({
        agentId,
        expectedStatuses: ["todo", "backlog", "blocked", "in_review"],
      }),
    });
    if (res.status === 409) return { ok: false, conflict: true };
    return { ok: res.ok };
  },

  async heartbeatContext(issueId: string) {
    const res = await fetch(`${API_URL}/api/issues/${issueId}/heartbeat-context`, {
      headers: headers(),
    });
    if (!res.ok) throw new Error(`heartbeat-context ${res.status}`);
    const data = (await res.json()) as { issue?: { title?: string; body?: string } };
    return { title: data.issue?.title ?? "", body: data.issue?.body ?? "" };
  },

  async comment(issueId: string, body: string, runId: string) {
    const res = await fetch(`${API_URL}/api/issues/${issueId}/comments`, {
      method: "POST",
      headers: headers(runId),
      body: JSON.stringify({ body }),
    });
    if (!res.ok) throw new Error(`comment ${res.status}`);
  },

  async setStatus(issueId: string, status: string, runId: string) {
    const res = await fetch(`${API_URL}/api/issues/${issueId}`, {
      method: "PATCH",
      headers: headers(runId),
      body: JSON.stringify({ status }),
    });
    if (!res.ok) throw new Error(`status ${res.status}`);
  },
};
```

- [ ] **Step 7: Implement the chat client**

`apps/agents/nufi/bridge/src/chat.ts`:

```ts
const CHAT_URL = process.env.NUFI_CHAT_URL ?? "http://localhost:3080";
const CHAT_KEY = process.env.NUFI_CHAT_API_KEY ?? "";
const AGENT_ID = process.env.NUFI_CHAT_AGENT_ID ?? "";

export const chat = {
  async complete(prompt: string) {
    const res = await fetch(`${CHAT_URL}/api/agents/chat/completions`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        authorization: `Bearer ${CHAT_KEY}`,
      },
      body: JSON.stringify({
        model: AGENT_ID,
        messages: [{ role: "user", content: prompt }],
        stream: false,
      }),
    });
    if (!res.ok) throw new Error(`chat ${res.status}: ${await res.text()}`);
    const data = (await res.json()) as { choices?: { message?: { content?: string } }[] };
    const content = data.choices?.[0]?.message?.content;
    if (!content) throw new Error("chat returned no content");
    return content;
  },
};
```

- [ ] **Step 8: Wire the webhook**

`apps/agents/nufi/bridge/src/index.ts`:

```ts
import { Hono } from "hono";

import { chat } from "./chat";
import { paperclip } from "./paperclip";
import { handleRun, type RunPayload } from "./run";

const app = new Hono();

app.get("/health", (c) => c.json({ ok: true }));

app.post("/run", async (c) => {
  const payload = (await c.req.json()) as RunPayload;
  const outcome = await handleRun({ paperclip, chat }, payload);
  return c.json(outcome, outcome.status === "failed" ? 500 : 200);
});

const port = Number(process.env.PORT ?? 8099);
console.log(`nufi agents bridge on :${port}`);

export default { port, fetch: app.fetch };
```

- [ ] **Step 9: Smoke it**

```bash
cd apps/agents/nufi/bridge
bun run src/index.ts &
curl -s localhost:8099/health
```

Expected: `{"ok":true}`.

- [ ] **Step 10: Commit**

```bash
git add apps/agents/nufi/bridge
git commit -m "feat(agents): a throwaway bridge for the product-fit spike

Paperclip's http adapter POSTs a run and expects a callback into /api;
apps/chat speaks OpenAI chat-completions. Neither knows the other, so the
spike needs a translator. Deliberately disposable — its job is to answer
whether Paperclip's goal/task model suits NuFi's users, not to become a
product. Checkout refusal is a stop, never a retry: a 409 means another
agent owns the issue."
```

---

## Task 3: Run the spike — GATE

This is the decision the design doc §9 says should have come first. Everything after it is wasted if the answer is no.

**Files:**
- Create: `docs/2026-08-04-nufi-agents-spike-findings.md`

- [ ] **Step 1: Bring the stack up**

```bash
cd apps/agents
docker start nufi-agents-pg || docker run -d --name nufi-agents-pg \
  -e POSTGRES_USER=paperclip -e POSTGRES_PASSWORD=paperclip \
  -e POSTGRES_DB=paperclip -p 5433:5432 postgres:16-alpine
set -a; . ./.env; set +a
pnpm dev:server
```

- [ ] **Step 2: Create a company and one agent through the UI**

Open `http://localhost:3100`. Complete onboarding. Create one employee whose adapter is **HTTP**, with config:

```json
{ "url": "http://localhost:8099/run", "timeoutSec": 300 }
```

Set `PAPERCLIP_API_KEY` in the adapter config — for non-local adapters the operator supplies it (`SKILL.md`, Authentication).

- [ ] **Step 3: Give it three real tasks**

Not toy tasks. Use work someone actually wants done, so the answer means something. Suggested, drawn from live NuFi work:

1. "Summarise what changed in `docs/2026-08-03-nufi-agent-app-design.md` between the first and current version."
2. "List every `apps/chat` asset that still carries LibreChat branding."
3. "Draft the `end-user` docs page for approvals."

- [ ] **Step 4: Record what happened — honestly**

Write `docs/2026-08-04-nufi-agents-spike-findings.md` with this shape. Fill every row from observation, not expectation:

```markdown
# NuFi Agents — product-fit spike findings

**Date:** 2026-08-04
**Setup:** upstream Paperclip @ v2026.722.0, `http` adapter → nufi/bridge → apps/chat agent

## What was asked, and what came back

| Task | Ran? | Useful output? | Where it broke down |
|---|---|---|---|

## Does the model fit

- **Goal → task hierarchy:** [does forcing every task under a company goal help or annoy]
- **Checkout / single assignee:** [does one-agent-owns-one-task match how NuFi work is shaped]
- **Approval gates:** [would a reviewer actually use these]
- **Budgets:** [is per-company spend the unit anyone wants]

## Verdict

[ ] Continue — the model fits, proceed to Task 4
[ ] Continue with changes — [what has to differ]
[ ] Stop — [what does not fit, and what to do instead]
```

- [ ] **Step 5: Commit, and stop if the verdict is stop**

```bash
git add docs/2026-08-04-nufi-agents-spike-findings.md
git commit -m "docs: what the agent-app spike actually showed"
```

**If the verdict is Stop, this plan ends here.** Tasks 4-11 assume the model fits. Do not continue on momentum.

---

## Task 4: Cilium egress — make the chokepoint real

`network-policy.ts:8-16` is explicit that standard NetworkPolicy cannot express FQDNs and falls back to the whole public internet. The gateway claim in the design doc §3 C2 is therefore false under `egressMode: "standard"`.

**Files:**
- Create: `apps/agents/nufi/egress/cilium-values.yaml`
- Modify: `apps/agents/nufi/README.md`

**Interfaces:**
- Consumes: `allowFqdns: ["api.codechi.me"]` from `nufi/adapters.json`.
- Produces: a sandbox-provider configuration consumed by Task 5's test.

- [ ] **Step 1: Read what the provider expects**

```bash
cd apps/agents
sed -n '1,60p' packages/plugins/sandbox-providers/kubernetes/src/tenant-orchestrator.ts
sed -n '1,40p' packages/plugins/sandbox-providers/kubernetes/src/cilium-network-policy.ts
```

Note the gotcha at `tenant-orchestrator.ts:40` about switching `standard → cilium` — it leaves the previously-created standard policies behind. Carry that into Step 3.

- [ ] **Step 2: Write the config**

`apps/agents/nufi/egress/cilium-values.yaml`:

```yaml
# Sandbox-provider configuration for NuFi Agents.
#
# egressMode MUST be "cilium". Under "standard", packages/plugins/
# sandbox-providers/kubernetes/src/network-policy.ts falls back to
# "public IPv4 except RFC1918/link-local/loopback/multicast" whenever
# allowFqdns is set — which is the entire internet, and makes the gateway
# a convention rather than a chokepoint.
egressMode: cilium

# Only the gateway. This must stay in step with allowFqdns in
# nufi/adapters.json; nufi/egress/verify-egress.sh proves it at runtime.
egressAllowFqdns:
  - api.codechi.me

# The agent pod also needs to reach paperclip-server to call back into /api.
# network-policy.ts records that the model is pull/callback — the server never
# pushes to agent pods — so no ingress rule is required.
paperclipServerPort: 3100
```

- [ ] **Step 3: Document the migration hazard**

Append to `apps/agents/nufi/README.md` under `## Routing every model call through the NuFi gateway`:

```markdown
### Switching an existing cluster to Cilium

`tenant-orchestrator.ts` warns that moving `egressMode` from `standard` to
`cilium` leaves the previously-created standard NetworkPolicies in place. Two
policy sets then apply to the same pods, and Kubernetes unions them — so the
broad "public IPv4" fallback from the old set silently keeps the internet open
while the new Cilium policy looks correct.

Delete the old ones as part of the switch:

```bash
kubectl -n <agent-namespace> get networkpolicy
kubectl -n <agent-namespace> delete networkpolicy <the standard-mode ones>
```

Then re-run `nufi/egress/verify-egress.sh`. A green run before deleting them
proves nothing.
```

- [ ] **Step 4: Commit**

```bash
git add apps/agents/nufi/egress/cilium-values.yaml apps/agents/nufi/README.md
git commit -m "feat(agents): pin sandbox egress to Cilium, not standard NetworkPolicy

network-policy.ts states that standard NetworkPolicy cannot express FQDNs
and falls back to public IPv4 whenever allowFqdns is set. Under that mode
our allowFqdns list documents an intention and confines nothing. Cilium is
the only mode that enforces it.

Also records the migration hazard: switching standard -> cilium leaves the
old policies in place and Kubernetes unions them, so the broad fallback
keeps the internet open while the new policy looks right."
```

---

## Task 5: Prove the lock — GATE

Until this passes, the design doc's C2 argument is a claim. Nothing ships before it.

**Files:**
- Create: `apps/agents/nufi/egress/verify-egress.sh`
- Modify: `docs/2026-08-03-nufi-agent-app-design.md`

- [ ] **Step 1: Write the test**

`apps/agents/nufi/egress/verify-egress.sh`:

```bash
#!/usr/bin/env bash
#
# Falsify the containment claim.
#
# A run whose base URL points at a vendor must FAIL. If it succeeds, the egress
# policy is not in force and docs/2026-08-03-nufi-agent-app-design.md §3 C2 is
# wrong for this deployment. Passing proves the chokepoint; not running it
# proves nothing, and a green CI badge on the other checks does not substitute.
#
# Usage: apps/agents/nufi/egress/verify-egress.sh <agent-namespace>

set -euo pipefail

NS="${1:?usage: verify-egress.sh <agent-namespace>}"
GATEWAY="api.codechi.me"
VENDOR="api.anthropic.com"
POD="egress-probe-$$"

cleanup() { kubectl -n "$NS" delete pod "$POD" --ignore-not-found --wait=false >/dev/null 2>&1 || true; }
trap cleanup EXIT

echo "Launching probe in namespace $NS with the agent pod's labels…"
kubectl -n "$NS" run "$POD" \
  --image=curlimages/curl:8.11.1 \
  --labels="paperclip.ai/component=agent-runtime" \
  --restart=Never --command -- sleep 300 >/dev/null

kubectl -n "$NS" wait --for=condition=Ready "pod/$POD" --timeout=90s >/dev/null

probe() {
  kubectl -n "$NS" exec "$POD" -- \
    curl -s -o /dev/null -w '%{http_code}' --max-time 8 "https://$1/" 2>/dev/null || echo "000"
}

gw=$(probe "$GATEWAY")
vd=$(probe "$VENDOR")

echo "  $GATEWAY -> $gw"
echo "  $VENDOR  -> $vd"

fail=0
if [ "$gw" = "000" ]; then
  echo "FAIL: the gateway is unreachable — agents cannot work at all."
  fail=1
fi
if [ "$vd" != "000" ]; then
  echo "FAIL: $VENDOR is reachable. Egress is NOT confined."
  echo "      Check egressMode is 'cilium' and that standard-mode policies were deleted."
  fail=1
fi

if [ "$fail" -eq 0 ]; then
  echo "PASS: only the gateway is reachable from an agent pod."
fi
exit "$fail"
```

- [ ] **Step 2: Make it executable and run it**

```bash
chmod +x apps/agents/nufi/egress/verify-egress.sh
apps/agents/nufi/egress/verify-egress.sh <agent-namespace>
```

Expected: `PASS: only the gateway is reachable from an agent pod.`

- [ ] **Step 3: If it fails, fix the cluster, not the test**

The failure modes, in likelihood order: `egressMode` still `standard`; old standard-mode NetworkPolicies not deleted (Task 4 Step 3); Cilium not installed in the cluster; the pod label selector in the policy not matching `paperclip.ai/component=agent-runtime` — check with `kubectl -n <ns> describe cnp`.

- [ ] **Step 4: Update the design doc**

In `docs/2026-08-03-nufi-agent-app-design.md`, replace the §9 Phase 1b row's `**not done — C2 is still a claim**` with `**done** — verified <date>, `verify-egress.sh` PASS`, and change the Status header line accordingly.

- [ ] **Step 5: Commit**

```bash
git add apps/agents/nufi/egress/verify-egress.sh docs/2026-08-03-nufi-agent-app-design.md
git commit -m "test(agents): prove the egress lock by trying to break it

A run pointed at api.anthropic.com must fail. Asserting the policy exists
proves nothing -- Kubernetes unions policies, so a correct-looking Cilium
rule can sit beside a permissive leftover and both apply. The only evidence
is a probe from inside the agent pod's own label set."
```

---

## Task 6: Rename the server too

The client rename is deliberately partial because a Vite plugin cannot reach the server, and renaming one side of a comparison breaks it. Rename both and the comparison holds again.

**Files:**
- Create: `apps/agents/nufi/rebrand.mjs`
- Create: `apps/agents/nufi/rebrand-server-dist.mjs`
- Modify: `apps/agents/ui/nufi-rebrand.ts`
- Modify: `apps/agents/nufi/check-fork-diff.sh` (allowlist the two new files)

**Interfaces:**
- Produces: `rebrandAll(code: string): string` and `rebrandRenderedProps(code: string): string`, both consumed by Task 7.

- [ ] **Step 1: Extract the core**

`apps/agents/nufi/rebrand.mjs` — plain ESM so both the Vite plugin and a Node post-build script can import it:

```js
export const BRAND = "NUFI";
export const PRODUCT = "NUFI Agents";

/** Double/single quoted (single line) or backtick (multi-line) literals. */
const STRING_LITERAL = /"(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*'|`(?:[^`\\]|\\.)*`/g;

/** Whole word `Paperclip`, never in JSX or identifier position. */
const PRODUCT_NAME = /(?<![<\/\w])\bPaperclip\b/g;

const RENDERED_PROPS = [
  "children", "title", "placeholder", "alt", "label", "description",
  "summary", "tooltip", "helpText", "helperText", "guidanceMd", "hint",
  "heading", "subtitle", "caption", "aria-label", "ariaLabel",
];

const RENDERED_PROP_STRING = new RegExp(
  String.raw`(["']?(?:${RENDERED_PROPS.join("|")})["']?\s*:\s*)` +
    String.raw`("(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*'|` + "`(?:[^`\\\\]|\\\\.)*`)",
  "g",
);

/** Safe on one side only: rewrites text the client renders, never a constant. */
export function rebrandRenderedProps(code) {
  return code.replace(
    RENDERED_PROP_STRING,
    (_m, prefix, literal) => prefix + literal.replace(PRODUCT_NAME, BRAND),
  );
}

/**
 * Every string literal. Only safe when BOTH the client bundle and the server
 * bundle get it, so the two sides of a comparison still agree.
 */
export function rebrandAll(code) {
  return code.replace(STRING_LITERAL, (literal) => literal.replace(PRODUCT_NAME, BRAND));
}
```

- [ ] **Step 2: Write the server post-build script**

`apps/agents/nufi/rebrand-server-dist.mjs`:

```js
#!/usr/bin/env node
/**
 * Apply the rename to the server bundle after `tsc`, so client and server agree.
 *
 * The server builds with plain tsc (server/package.json "build"), so there is no
 * plugin hook — this rewrites the emitted JS in place. It must run on every
 * server build, or the two sides drift and string comparisons break.
 */
import { readFileSync, writeFileSync } from "node:fs";
import { readdir } from "node:fs/promises";
import { join } from "node:path";

import { rebrandAll } from "./rebrand.mjs";

const DIST = process.argv[2] ?? "apps/agents/server/dist";

async function* files(dir) {
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) yield* files(path);
    else if (entry.name.endsWith(".js")) yield path;
  }
}

let changed = 0;
for await (const path of files(DIST)) {
  const before = readFileSync(path, "utf8");
  if (!before.includes("Paperclip")) continue;
  const after = rebrandAll(before);
  if (after !== before) {
    writeFileSync(path, after);
    changed++;
  }
}
console.log(`rebranded ${changed} server file(s) in ${DIST}`);
```

- [ ] **Step 3: Point the Vite plugin at the shared core**

In `apps/agents/ui/nufi-rebrand.ts`, delete the local regex constants and `rebrandStrings`, and re-export from the core:

```ts
import { rebrandAll, rebrandRenderedProps, PRODUCT } from "../nufi/rebrand.mjs";

/**
 * Whole-string rewriting is safe only once the server bundle gets the same
 * treatment (nufi/rebrand-server-dist.mjs). Task 7 flips this; until then the
 * rendered-props form is the correct one.
 */
export const rebrandStrings = rebrandRenderedProps;
export { rebrandAll };
```

- [ ] **Step 4: Allowlist the new files**

In `apps/agents/nufi/check-fork-diff.sh` the `nufi/` prefix already covers `nufi/rebrand*.mjs`. No change needed — confirm with:

```bash
./apps/agents/nufi/check-fork-diff.sh
```

Expected: `violations: 0`.

- [ ] **Step 5: Verify the UI tests still pass**

```bash
cd apps/agents/ui && npx vitest run nufi-rebrand.test.ts
```

Expected: 15 pass.

- [ ] **Step 6: Commit**

```bash
git add apps/agents/nufi/rebrand.mjs apps/agents/nufi/rebrand-server-dist.mjs \
        apps/agents/ui/nufi-rebrand.ts
git commit -m "feat(agents): share the rebrand core so the server can use it too

The client rename is partial because a Vite plugin cannot reach the server,
and renaming one side of a comparison breaks it silently. Extracting the
transform into plain ESM lets a post-tsc script apply the same rules to
server/dist, which is the precondition for widening the rewrite in the next
commit."
```

---

## Task 7: Widen the rename, now that both sides agree

**Files:**
- Modify: `apps/agents/ui/nufi-rebrand.ts`
- Modify: `apps/agents/ui/nufi-rebrand.test.ts`
- Modify: `apps/agents/nufi/README.md`

**Interfaces:**
- Consumes: `rebrandAll` from Task 6.

- [ ] **Step 1: Add the failing test**

In `apps/agents/ui/nufi-rebrand.test.ts`, replace the `describe("leaves protocol values alone")` block with:

```ts
  /**
   * These were unsafe while only the client was renamed. Once
   * nufi/rebrand-server-dist.mjs runs on every server build, both sides of the
   * comparison say NUFI and the equality holds again.
   */
  describe("rewrites protocol values too, because the server matches", () => {
    it("renames a bare string constant", () => {
      const src =
        'const NOTICE_BODY = "Paperclip needs a disposition before this issue can continue.";';
      expect(rebrandStrings(src)).toBe(
        'const NOTICE_BODY = "NUFI needs a disposition before this issue can continue.";',
      );
    });

    it("renames a bare call argument", () => {
      expect(rebrandStrings('toast("Paperclip failed to dispatch")')).toBe(
        'toast("NUFI failed to dispatch")',
      );
    });
  });
```

- [ ] **Step 2: Run it and watch it fail**

```bash
cd apps/agents/ui && npx vitest run nufi-rebrand.test.ts
```

Expected: FAIL — the constant is unchanged.

- [ ] **Step 3: Flip the export**

In `apps/agents/ui/nufi-rebrand.ts`:

```ts
export const rebrandStrings = rebrandAll;
```

- [ ] **Step 4: Run the tests**

```bash
cd apps/agents/ui && npx vitest run nufi-rebrand.test.ts
```

Expected: all pass. The regex-literal case still passes — `rebrandAll` only touches string literals, and `/^Paperclip …/` is not one. That regex is matched against a **server-written** body, which the server transform now renames, so update it in the same pass: confirm `server/dist` output contains `NUFI exhausted the bounded` after Step 6.

- [ ] **Step 5: Rebuild and measure**

```bash
cd apps/agents && pnpm --filter @paperclipai/server build
node nufi/rebrand-server-dist.mjs server/dist
cd ui && rm -rf dist && npx vite build
cd dist && find assets -name "*.js" -exec grep -ohE "\bPaperclip\b" {} \; | wc -l
```

Expected: close to 0. Record the actual number.

- [ ] **Step 6: Verify the regex and the constant still agree**

```bash
cd apps/agents
grep -o "NUFI exhausted the bounded successful-run handoff correction" server/dist/**/*.js | head -1
grep -oh "NUFI exhausted the bounded successful-run handoff correction" ui/dist/assets/*.js | head -1
```

Both must print the same string. If the client says NUFI and the server says Paperclip, stop — the server transform did not run.

**Note on existing data:** rows already written to Postgres keep the old text. On a database with real history, renaming both sides breaks matching against those rows. This is safe now because no production data exists; it stops being safe the moment there is.

- [ ] **Step 7: Update the README**

Replace the `## The rename is partial, on purpose` section's table with the new measured numbers and note that both sides are now transformed.

- [ ] **Step 8: Commit**

```bash
git add apps/agents/ui apps/agents/nufi/README.md
git commit -m "feat(agents): rename every string, now that the server agrees

Safe only because nufi/rebrand-server-dist.mjs applies the same transform to
server/dist. Both sides of every comparison now say NUFI, so the handoff
equality that broke under a one-sided rewrite holds again -- verified by
grepping both bundles for the same sentence.

Caveat recorded in the README: rows already in Postgres keep the old text.
That is harmless today because there is no production data, and stops being
harmless the day there is."
```

---

## Task 8: The first-party NuFi adapter

The bridge from Task 2 is disposable. This is its supported replacement — an external adapter package, which `docs/adapters/creating-an-adapter.md` says needs no upstream source changes and is auto-loaded at startup.

**Files:**
- Create: `packages/adapters-nufi/package.json`
- Create: `packages/adapters-nufi/src/index.ts`
- Create: `packages/adapters-nufi/src/server/execute.ts`
- Create: `packages/adapters-nufi/src/server/index.ts`
- Test: `packages/adapters-nufi/src/server/execute.test.ts`
- Create: `packages/adapters-nufi/src/ui-parser.ts`
- Modify: `apps/agents/nufi/adapters.json`

**Interfaces:**
- Consumes: the orchestration proven in Task 2 (`handleRun`), ported.
- Produces: adapter type `nufi_agent`.

- [ ] **Step 1: Read the contract**

```bash
cd apps/agents
cat docs/adapters/external-adapters.md
cat docs/adapters/adapter-ui-parser.md
```

Follow those two documents exactly. They define `createServerAdapter`, the `AdapterExecutionContext` / `AdapterExecutionResult` shapes, and the UI-parser contract. Do not invent alternatives.

- [ ] **Step 2: Metadata**

`packages/adapters-nufi/src/index.ts`:

```ts
export const type = "nufi_agent";
export const label = "NuFi Agent";
export const models = [{ id: "nufi-default", label: "NuFi default agent" }];

export const agentConfigurationDoc = `# nufi_agent configuration

Use when: the employee should be a NuFi knowledge agent — tools, MCP and RAG
over company documents — rather than a coding harness.

Don't use when: the work is repository editing. Use claude_local or codex_local,
which run in a sandbox with a git workspace.

Core fields:
  chatUrl    NuFi chat base URL, e.g. https://chat.nufi.me
  agentId    the agent id in NuFi chat
  apiKeyEnv  name of the env var holding the chat API key (never the key itself)
`;

export { createServerAdapter } from "./server/index.js";
```

- [ ] **Step 3: Write the failing test**

`packages/adapters-nufi/src/server/execute.test.ts`:

```ts
import { describe, expect, it, vi } from "vitest";

import { execute } from "./execute";

const ctx = {
  agent: { config: { chatUrl: "https://chat.example", agentId: "a1", apiKeyEnv: "NUFI_KEY" } },
  runtime: { sessionParams: {} },
  prompt: "Summarise the design doc.",
} as never;

describe("execute", () => {
  it("posts to the chat completions endpoint and returns the content", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ choices: [{ message: { content: "Two pages." } }] }),
    });
    vi.stubGlobal("fetch", fetchMock);
    vi.stubEnv("NUFI_KEY", "secret");

    const result = await execute(ctx);

    expect(result.output).toBe("Two pages.");
    expect(fetchMock.mock.calls[0][0]).toBe("https://chat.example/api/agents/chat/completions");
  });

  it("fails loudly when the key env var is unset", async () => {
    vi.stubEnv("NUFI_KEY", "");
    await expect(execute(ctx)).rejects.toThrow(/NUFI_KEY/);
  });
});
```

- [ ] **Step 4: Run it and watch it fail**

```bash
cd apps/agents && npx vitest run packages/adapters-nufi/src/server/execute.test.ts
```

Expected: FAIL — module not found.

- [ ] **Step 5: Implement**

`packages/adapters-nufi/src/server/execute.ts`:

```ts
interface NufiConfig {
  chatUrl: string;
  agentId: string;
  apiKeyEnv: string;
}

export async function execute(ctx: {
  agent: { config: NufiConfig };
  prompt: string;
}): Promise<{ output: string }> {
  const { chatUrl, agentId, apiKeyEnv } = ctx.agent.config;

  const key = process.env[apiKeyEnv];
  if (!key) {
    throw new Error(`${apiKeyEnv} is not set — the NuFi adapter has no credential to call chat with`);
  }

  const res = await fetch(`${chatUrl}/api/agents/chat/completions`, {
    method: "POST",
    headers: { "content-type": "application/json", authorization: `Bearer ${key}` },
    body: JSON.stringify({
      model: agentId,
      messages: [{ role: "user", content: ctx.prompt }],
      stream: false,
    }),
  });
  if (!res.ok) throw new Error(`chat ${res.status}`);

  const data = (await res.json()) as { choices?: { message?: { content?: string } }[] };
  const output = data.choices?.[0]?.message?.content;
  if (!output) throw new Error("chat returned no content");

  return { output };
}
```

- [ ] **Step 6: Run the tests**

```bash
cd apps/agents && npx vitest run packages/adapters-nufi/src/server/execute.test.ts
```

Expected: 2 pass.

- [ ] **Step 7: Wire the server entry point**

`src/index.ts` re-exports `createServerAdapter` from `./server/index.js`, which
is the name the plugin loader looks for (`docs/adapters/external-adapters.md`).
Create `packages/adapters-nufi/src/server/index.ts`:

```ts
import { execute } from "./execute.js";

/**
 * The plugin loader calls this at startup to build the adapter. `execute` is
 * the only hook this adapter needs: it has no session state to resume and no
 * environment to probe, because the work happens in NuFi chat, not here.
 */
export function createServerAdapter() {
  return { execute };
}
```

- [ ] **Step 8: Register it and drop the http entry**

In `apps/agents/nufi/adapters.json`, remove the `http` entry added in Task 1 and add:

```json
  {
    "adapterType": "nufi_agent",
    "enabled": true
  }
```

Add `"nufi_agent"` to both `KNOWN_ADAPTERS` and `WEBHOOK_ADAPTERS` in `verify-adapters.mjs` — it calls chat over HTTPS and runs no sandboxed harness, so the same reasoning as `http` applies.

- [ ] **Step 9: Commit**

```bash
git add packages/adapters-nufi apps/agents/nufi/adapters.json apps/agents/nufi/verify-adapters.mjs
git commit -m "feat(agents): a first-party NuFi adapter, replacing the spike bridge

External adapters are auto-loaded and need no upstream source change, so
this is the supported shape for what nufi/bridge proved. The bridge stays in
the tree until the docs in the next commit stop referring to it.

The key is read from an env var named in config, never stored in config --
adapter config is visible in the UI."
```

---

## Task 9: Documentation

**Files:**
- Create: `apps/docs/content/docs/end-user/agents-tasks.mdx`
- Create: `apps/docs/content/docs/end-user/agents-approvals.mdx`
- Create: `apps/docs/content/docs/admin/agents-org-chart.mdx`
- Create: `apps/docs/content/docs/operations/agents-egress.mdx`
- Create: `apps/docs/content/docs/deployment/agents-install.mdx`
- Modify: the relevant `meta.json` files

- [ ] **Step 1: Check the two constraints that bite**

```bash
cd apps/docs
ls public/screenshots | head
```

A missing `/screenshots/*.png` **fails the build**, so every image referenced must exist before the page merges. And `nufi-docs` on Railway still points at the archived `dudaji-vn/nufi-docs` repo — until it is repointed (`docs/2026-08-03-deploy-develop-to-production.md` §2), nothing written here reaches production. Confirm the source has been changed before writing pages, or this task ships into a void.

- [ ] **Step 2: Write the operations page first**

It is the one with a testable claim. `apps/docs/content/docs/operations/agents-egress.mdx`:

```mdx
---
title: Agent egress
description: How NUFI Agents keeps model traffic on the gateway, and how to check.
---

Agent runs execute in a sandbox pod. That pod may reach exactly one host —
`api.codechi.me`, the NUFI gateway, where the security controls live. It cannot
reach a model vendor directly.

## Why Cilium

Standard Kubernetes NetworkPolicy cannot express hostnames. When an FQDN
allow-list is configured under standard mode, the policy falls back to "any
public IPv4 address", which is not a restriction. `egressMode: cilium` is what
turns the allow-list into an enforced rule.

## Checking it

```bash
apps/agents/nufi/egress/verify-egress.sh <agent-namespace>
```

The check launches a probe pod carrying the agent runtime's labels and tries
both hosts. It passes only when the gateway answers and the vendor does not.

A failing vendor probe is the point. If `api.anthropic.com` responds, egress is
not confined — most often because `egressMode` is still `standard`, or because
policies from a previous standard-mode deployment were left in place and
Kubernetes is unioning them with the new ones.
```

- [ ] **Step 3: Write the four remaining pages**

Each must answer: what the reader is trying to do, the steps, and what "done" looks like. Use screenshots from a running local instance and put them in `apps/docs/public/screenshots/`. Follow the house rule already applied in `apps/docs/content/docs/end-user/security`: every claim a reader could check should be checkable.

- [ ] **Step 4: Build the docs**

```bash
cd apps/docs && bun run build
```

Expected: success. A missing screenshot fails here, not in review.

- [ ] **Step 5: Commit**

```bash
git add apps/docs
git commit -m "docs(agents): tasks, approvals, org chart, egress, install

The egress page carries the only claim a reader can falsify, so it leads
with the command that falsifies it."
```

---

## Task 10: Release

**Files:**
- Create: `apps/agents/Dockerfile.nufi`
- Create: `.github/workflows/agents-release.yml`

- [ ] **Step 1: Write the Dockerfile**

`apps/agents/Dockerfile.nufi` — the server build must run the rebrand step, or client and server drift:

```dockerfile
FROM node:22-bookworm-slim AS build
WORKDIR /app

RUN corepack enable && corepack prepare pnpm@9.15.4 --activate

COPY . .
RUN pnpm install --frozen-lockfile --node-linker=isolated
RUN pnpm build

# Both bundles must carry the same product name. The UI gets it from the Vite
# plugin; the server builds with plain tsc and gets it here. Skipping this makes
# string comparisons between the two fail silently.
RUN node nufi/rebrand-server-dist.mjs server/dist

FROM node:22-bookworm-slim
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /app /app
EXPOSE 3100
CMD ["node", "server/dist/index.js"]
```

- [ ] **Step 2: Write the workflow**

`.github/workflows/agents-release.yml`, following `chat-release.yml`:

```yaml
name: agents-release

on:
  push:
    tags: ['nufi-agents-v*']
  workflow_dispatch:

permissions:
  contents: read
  packages: write

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository_owner }}/nufi-agents

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - id: meta
        uses: docker/metadata-action@v5
        with:
          images: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}
      - uses: docker/build-push-action@v6
        with:
          context: apps/agents
          file: apps/agents/Dockerfile.nufi
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
```

- [ ] **Step 3: Build the image locally before tagging**

```bash
cd apps/agents
docker build -f Dockerfile.nufi -t nufi-agents:local .
docker run --rm nufi-agents:local node -e "
  const fs=require('fs');
  const f=fs.readdirSync('/app/server/dist').filter(n=>n.endsWith('.js'));
  console.log('server files:', f.length);
"
```

Expected: a non-zero count, and the build completes. A failure here is cheaper than a failed release.

- [ ] **Step 4: Verify both bundles say the same thing**

```bash
docker run --rm nufi-agents:local sh -c \
  "grep -rho 'NUFI exhausted the bounded' /app/server/dist | head -1; \
   grep -rho 'NUFI exhausted the bounded' /app/ui/dist/assets | head -1"
```

Both lines must print. If only one does, the rebrand step did not run in the image.

- [ ] **Step 5: Tag and release**

```bash
git checkout main && git merge --no-ff develop
git tag nufi-agents-v0.1.0
git push origin main --tags
gh run watch
```

- [ ] **Step 6: Commit**

```bash
git add apps/agents/Dockerfile.nufi .github/workflows/agents-release.yml
git commit -m "build(agents): release image and tag-triggered workflow

The image runs the server rebrand step explicitly. The UI gets its rename
from the Vite plugin at build time; the server builds with plain tsc and
would otherwise ship the upstream name, which puts the two sides of every
string comparison out of step."
```

---

## Task 11: Close the loop on the two commercial risks

These are not engineering tasks, and pretending otherwise is how they get skipped. They block shipping to a customer, not merging to `develop`.

**Files:**
- Modify: `docs/2026-08-03-nufi-agent-app-design.md` §10

- [ ] **Step 1: Get a written answer on harness licensing**

Claude Code, Codex, Gemini CLI and Cursor each carry their own terms and their own per-seat credentials. Paperclip's MIT licence says nothing about redistributing them. Establish, in writing, whether NuFi may run them on a customer's behalf, and under whose account. Record the answer and its source in §10.

- [ ] **Step 2: Scope the agent's repository credentials**

The runtime base image ships `git` and mounts `/workspace`. The gateway answers *which model was called*; it does not answer *what was committed*. Decide and document: which repositories an agent may reach, with which token, and what revokes it. Until then no agent should hold a credential with write access to anything that matters.

- [ ] **Step 3: Commit the answers**

```bash
git add docs/2026-08-03-nufi-agent-app-design.md
git commit -m "docs(agents): the two commercial risks now have answers"
```

---

## Self-Review Notes

Checked against `docs/2026-08-03-nufi-agent-app-design.md`:

- §9 Phase 0 → Tasks 1-3. §9 Phase 1b → Tasks 4-5. §9 Phase 2 remainder → Tasks 6-7. §9 Phase 3 → Task 8. §9 Phase 4 → Tasks 9-10. §10 risks → Task 11.
- **Not covered, deliberately:** the 215 hardcoded `zinc`/`neutral`/`gray` Tailwind classes. Fixing them means editing upstream components, which the allowlist forbids; a Tailwind config mapping those scales onto the brand ramp is the cheap approximation if it ever matters. It is cosmetic and it has no gate, so it does not earn a task.
- Two gates are real stops. Task 3 ends the plan if the model does not fit. Task 5 blocks every later task, because a white-labelled product that can still reach a vendor directly is worse than no product — it looks protected.
