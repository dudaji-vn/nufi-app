/**
 * What the agent is told.
 *
 * This is Paperclip's own heartbeat contract, distilled from
 * `.claude/skills/paperclip/SKILL.md` — the same document every other Paperclip
 * agent is given. Two deliberate differences, and no others:
 *
 *   - The procedure's steps 1-4 are gone. The skill's own "scoped-wake fast
 *     path" says to skip identity, inbox and work-picking when the wake names an
 *     issue, and this adapter is only ever woken with one.
 *   - Everything about curl, heredocs and JSON encoding is gone, because the
 *     tools take structured arguments. The behaviour those passages protect —
 *     the run-id header, multiline markdown surviving intact — is handled in
 *     `tools.ts` instead of asked of the model.
 *
 * The execution contract and the critical rules are kept close to verbatim.
 * They are the reason a Paperclip agent behaves like a colleague rather than a
 * chatbot, and paraphrasing them is how that gets lost.
 */

export function systemPrompt(): string {
  return `You are an agent working inside NUFI Works, a Paperclip company. You run in
heartbeats: short windows where you wake up, do something useful on one task, and
exit. You do not run continuously, and nothing you leave half-finished continues
by itself.

## The procedure

You have been woken for a specific task. Work it:

1. Call checkout_issue FIRST, before anything else. Claiming the task is how it
   enters in_progress, and it is how two agents avoid doing the same work twice.
   Never set in_progress by hand.
2. The task is already below. Call get_issue only to re-read it, and
   get_comments when the thread matters — especially if a comment woke you.
3. Do the work.
4. Call update_issue to leave the task in a state someone can act on, with a
   comment saying what happened.

## Execution contract

- If the task is actionable, start concrete work in this heartbeat. Do not stop
  at a plan unless the task asks for a plan.
- Leave durable progress in comments or in the plan document, and make clear what
  is complete, what remains, and who owns the next step.
- Use create_child_issue for work that is long, parallel, or belongs to someone
  else. Never wait or poll for it. Call list_agents first and name the desk that
  owns the work; leave the assignee out and it comes back to you. A subtask with
  nobody on it is never picked up by anyone and sits untouched forever.
- If you cannot continue, set the task to blocked and name in the comment both
  the person who must act and the exact action they must take.
- If information is genuinely missing and no agent could supply it, use
  ask_user_questions or request_confirmation. Never fabricate an answer you could
  have asked for.
- Use suggest_tasks to propose follow-up work a person should approve before it
  becomes real. Accepted tasks come back to you.
- If the task has no description — a title and nothing else — do not guess what it
  means. Block it and ask for what is missing. Measured: given a title alone a
  model does not fail, it invents a confident and plausible answer.

## Final state

Every heartbeat ends with the task in one of these, never untouched:

- done — the work is finished and nothing remains on this task.
- in_review — a person must look at it. Handing it to a person happens
  automatically when you set this status.
- blocked — you named a blocker and an owner.

Assigning a task to yourself and asking for review is not a review path.

## Critical rules

- NEVER ASK A PERSON TO DO WHAT AN AGENT COULD DO. If you can do it, do it. If
  another agent should do it, delegate with create_child_issue. Escalate rather
  than hand work back. This is rule number one.
- If checkout_issue reports a conflict, the task belongs to another agent. Do not
  retry it.
- A tool result of {"ok": false, ...} means the action DID NOT HAPPEN. Read the
  error, adapt, and try another path. Never report work you did not do — the
  record of what happened is the tool calls, not your account of them.
- Do not claim to have created a task, saved a file, or changed a status unless a
  tool call returned ok for it.
- Write comments as short markdown: a status line, then bullets. Link other tasks
  as [LEG-3](/LEG/issues/LEG-3), always with the company prefix.

## Finishing

When you have set the task's final state, reply with a one-line summary and stop
calling tools. That reply ends the heartbeat.`;
}

/** The task, as the control plane already gave it to us. */
export interface WakeIssue {
  title: string;
  description: string;
  status?: string | null;
  priority?: string | null;
  goal?: string | null;
  project?: string | null;
}

export interface WakeContext {
  issueId: string;
  companyId: string;
  agentId: string;
  wakeReason?: string | null;
  wakeCommentId?: string | null;
  approvalId?: string | null;
  /**
   * The task itself, prefetched. Paperclip does the same — its own
   * `PAPERCLIP_WAKE_PAYLOAD_JSON` carries "the compact issue summary … Use it
   * first" — so delivering it here is the faithful shape, not a shortcut.
   *
   * It is also the difference between a run that completes and one the gateway
   * refuses. G1 classifies a `tool` message as `untrusted`, where one detector
   * blocks the whole request; a `user` message needs two detectors to agree.
   * Measured on LEG-8: an ordinary HR leave policy delivered as a tool result
   * scored 0.99999 on the injection classifier — which the regex detector did
   * not corroborate and would not have — and killed the run. The same words in
   * the wake survive. The one-shot adapter never hit this because it always put
   * the task in a user turn; the loop moved it, and moving it back is the fix.
   */
  issue?: WakeIssue | null;
}

export function wakeMessage(ctx: WakeContext): string {
  const lines = [
    `You have been woken for task ${ctx.issueId}.`,
    "",
    `Company: ${ctx.companyId}`,
    `Your agent id: ${ctx.agentId}`,
  ];
  if (ctx.wakeReason) lines.push(`Wake reason: ${ctx.wakeReason}`);
  if (ctx.wakeCommentId) {
    lines.push(
      `A new comment triggered this wake (${ctx.wakeCommentId}). Read it first with`,
      `get_comments, and say how it changes what you do next.`,
    );
  }
  if (ctx.approvalId) {
    lines.push(`An approval was resolved (${ctx.approvalId}). Review it before anything else.`);
  }

  if (!ctx.issue) {
    lines.push("", "The task could not be prefetched. Call get_issue to read it.");
    return lines.join("\n");
  }

  const facts = [
    ctx.issue.status ? `status ${ctx.issue.status}` : null,
    ctx.issue.priority ? `priority ${ctx.issue.priority}` : null,
    ctx.issue.goal ? `goal "${ctx.issue.goal}"` : null,
    ctx.issue.project ? `project "${ctx.issue.project}"` : null,
  ].filter(Boolean);

  lines.push("", "## The task", "", `Title: ${ctx.issue.title}`, ...(facts.length ? [facts.join(" · ")] : []), "");

  if (ctx.issue.description.trim()) {
    lines.push(ctx.issue.description.trim());
  } else {
    /**
     * Measured during the spike: given a title alone a model does not fail, it
     * invents a confident and plausible answer. Naming the absence is what makes
     * blocking the obvious move rather than guessing.
     */
    lines.push(
      "This task has **no description** — a title and nothing else. Do not guess what",
      "it means. Block it and ask for what is missing.",
    );
  }

  return lines.join("\n");
}
