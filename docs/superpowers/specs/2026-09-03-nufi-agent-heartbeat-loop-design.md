# NUFI agent: the Paperclip heartbeat loop, on NUFI models

**Status:** approved to build, 2026-09-03
**Supersedes the one-shot behaviour in** `apps/agents/nufi/adapter/`

## The problem

`nufi_agent` answers one question and stops. Every other Paperclip agent works a
procedure: wake, check the inbox, claim work, do it, leave durable progress,
delegate what does not fit, and ask a person when it genuinely needs one. Watch
NUFI Works next to stock Paperclip and the difference is not subtle — ours looks
like a chatbot bolted to an issue tracker.

The gap is not the model. Measured on the live gateway (2026-09-03), NUFI's
gateway returns real tool calls in both protocol shapes:

| Request | Result |
|---|---|
| `POST /v1/chat/completions` + `tools` | 200, `finish_reason: tool_calls` |
| `POST /v1/messages` + `tools` | 200, `stop_reason: tool_use` |

The gap is that the adapter makes exactly one model call and has no way to act.

Two things were tried first and are recorded here so nobody repeats them:

**Vendor harnesses on NUFI models.** `claude_local` runs end-to-end once the
model names are aliased (PR #52) and `ANTHROPIC_BASE_URL` is set. The output is
not usable: on issue LEG-2 the agent claimed *"First, I'll create a task"*,
*"saved it to `cloudflow_agreement_brief.md`"* and *"I will mark the task as
completed"*. None of it happened — the company still held exactly the two issues
a human had created. Claude Code's prompts assume a Claude model; Gemini narrates
tool use instead of performing it. A harness we do not control, driving a model
it was not written for, produces confident fiction.

**Built-in agents on `nufi_agent`.** Not possible: every built-in definition
lists `allowedAdapterTypes: [claude_local, codex_local, gemini_local,
opencode_local, process]`. `nufi_agent` is not eligible, and the list is vendored
upstream.

## What Paperclip actually gives an agent

Not a curated tool list, and not a policy engine deciding which actions need
approval. Three things (`evals/promptfoo/prompts/heartbeat-system.txt`):

1. **Environment** — `PAPERCLIP_API_URL`, `PAPERCLIP_RUN_ID`, `PAPERCLIP_TASK_ID`,
   `PAPERCLIP_WAKE_REASON`, `PAPERCLIP_APPROVAL_ID`, and a run credential.
2. **A nine-step procedure** against the REST API — identity, inbox, pick work,
   checkout, context, do the work, update status, delegate.
3. **An execution contract**, which is where the behaviour actually lives:
   - *"If the issue is actionable, start concrete work in this heartbeat. Do not
     stop at a plan unless the issue asks for planning."*
   - *"Leave durable progress in comments, documents, or work products, with a
     clear next action."*
   - *"Use child issues for parallel or long delegated work."*
   - *"If blocked, PATCH the issue to blocked and name the unblock owner and
     action."*
   - *"If a tool requires elicitation from the human, pause on a real interaction
     path such as `ask_user_questions` or `request_confirmation`. Do not fabricate
     missing human input."*

Paperclip's own MCP plumbing (`buildPaperclipRuntimeMcpServers`) is for *external*
tool connections — Slack, GitHub — not for its own API. Agents call the REST API
directly. Any design that reaches for MCP to talk to Paperclip is diverging from
the platform, not matching it.

## Decision

Keep Paperclip's prompt, procedure and contract **verbatim**. Replace "the model
writes curl commands" with typed tools over the same endpoints, plus one generic
escape hatch.

Rejected alternatives:

**One generic `paperclip_api(method, path, body)` tool and nothing else.** The
most literal translation — the harnesses have `bash`, this is the equivalent. It
puts URL and body construction on a mid-tier model with no validation layer, and
LEG-2 is direct evidence of what a mid-tier model does when nothing checks its
claims. Kept as an escape hatch, not as the whole surface.

**A curated tool set with our own approval policy** — "propose everything, act on
nothing". Considered and dropped: it is not what Paperclip does. The contract
above says work, delegate, and ask only when a human decision is genuinely
missing. Inventing a more cautious product would make NUFI Works behave unlike
the thing it is a distribution of.

What typed tools buy is not caution, it is **truthfulness**: a tool that is not
called leaves no record, and a tool that is called leaves one. The failure mode
we measured — an agent reporting work it did not do — becomes structurally
impossible for anything behind a tool.

## Architecture

```
execute(ctx)
  └─ runLoop(deps, ctx)
       ├─ systemPrompt()        heartbeat procedure + execution contract
       ├─ wakeMessage(ctx)      wake reason, task id, approval id
       └─ iterate (max 12):
            model.complete(messages, tools)
              ├─ tool_calls?  → run each, append results, continue
              └─ text only    → done
       └─ settle()             guarantee a disposition
```

Four units, each testable alone:

| Unit | File | Responsibility |
|---|---|---|
| Prompt | `src/server/prompt.ts` | System prompt, wake message. Pure string building. |
| Tools | `src/server/tools.ts` | Tool schemas + their HTTP implementations. |
| Loop | `src/server/loop.ts` | Iterate model ↔ tools, enforce limits. Model and tools injected. |
| Client | `src/server/client.ts` | Existing. Gains a tool-calling `complete`. |

`execute.ts` keeps its current job — decide whether there is work, call the loop,
map the outcome to an `ExecutionResult`.

## The tool surface

Every tool carries the run JWT and `X-Paperclip-Run-Id`. Names and descriptions
are written for the model, not for us.

| Tool | Endpoint | Notes |
|---|---|---|
| `get_inbox` | `GET /api/agents/me/inbox-lite` | Step 3 |
| `get_issue` | `GET /api/issues/{id}/heartbeat-context` | Step 6 |
| `checkout_issue` | `POST /api/issues/{id}/checkout` | Step 5. A 409 is returned to the model as "taken by someone else — do not retry", per the contract |
| `comment_on_issue` | `POST /api/issues/{id}/comments` | Durable progress |
| `set_issue_status` | `PATCH /api/issues/{id}` | See handover below |
| `create_child_issue` | `POST /api/companies/{id}/issues` | Delegation |
| `suggest_tasks` | `POST /api/issues/{id}/interactions` | `kind: suggest_tasks`, `continuationPolicy: wake_assignee` — the propose → approve → continue loop |
| `ask_user_questions` | `POST /api/issues/{id}/interactions` | `kind: ask_user_questions` |
| `request_confirmation` | `POST /api/issues/{id}/interactions` | `kind: request_confirmation` |
| `paperclip_api` | any | Escape hatch: method, path, body |

**`set_issue_status` owns the review path.** Moving to `in_review` without one
returns 422 `invalid_issue_disposition`, and adding a human assignee while an
agent still holds the issue returns 422 `Issue can only have one assignee` — both
learned the hard way today (PRs #50, #51). The tool applies the handover itself:
`in_review` with no human assignee sets `assigneeUserId` to the run's responsible
user and clears `assigneeAgentId`. The model is not asked to know this.

## Limits, and why each one exists

- **12 iterations per run.** A loop with no cap is a budget leak with a prompt
  attached. Measured before this design: one task collected four full answers in
  twenty seconds when the adapter had no stop condition.
- **`max_tokens` 4096, never lower.** Gemini spends its reasoning budget before
  emitting text — measured on the gateway, `gemini-2.5-pro` burned 148 output
  tokens to answer "OK", and a 64-token cap returned *empty content with no
  error*. A small cap reads as a refusal rather than a truncation.
- **Already-answered guard stays.** `in_review` or `done` on entry means exit
  idle. Paperclip re-dispatches an agent that still holds an assignment.
- **Every run ends in a disposition.** If the loop finishes without the model
  setting a status, `settle()` sets one. Three consecutive dispositionless runs
  make Paperclip escalate and stop dispatching.

## Error handling

Tool failures are **returned to the model as tool results**, not thrown — the
contract expects an agent to read a 403 or 429 and choose another path. Two
exceptions abort the run: a missing run token (nothing will work, and the server
answers 404 rather than 401, so it must be named here — see `requireRunToken`),
and a model-endpoint auth failure.

The run's `errorMessage` keeps the server's response body, not just its status
code. `status 422` cost a full diagnosis cycle today; the body said exactly which
review path was missing.

## Testing

**Unit** (`bun test`, fakes for model and HTTP): loop terminates on text; loop
runs tool calls and feeds results back; iteration cap fires; already-answered
exits idle; dispositionless loop still settles; `set_issue_status(in_review)`
performs the handover; tool error reaches the model rather than killing the run.

**Integration, before any deploy**: a script that runs the real loop against
`works.nufi.me` with a board-issued token, driving a real issue in the test
company, asserting on the API afterwards — issue status, comment count, and
whether promised child issues *exist*. LEG-2 is the reason this assertion is on
the list: the agent's narration and the database disagreed, and only the database
was checked.

## Out of scope

Workspaces, file editing and shell access. NUFI Works sells to departments, not
to engineering teams, and those need the sandbox work that is still unbuilt.
Built-in agents stay on the vendor harnesses until upstream's
`allowedAdapterTypes` includes `nufi_agent`.
