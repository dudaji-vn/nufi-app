/**
 * The tools a NUFI agent can actually use.
 *
 * Paperclip hands its agents a REST API and a procedure, not a tool list — the
 * vendor harnesses reach it with `bash` and `curl`. This adapter has no shell,
 * so the same endpoints are exposed as typed tools.
 *
 * That is a deliberate translation, not a smaller product. What typed tools buy
 * is truthfulness: measured on a real issue, a harness driving a mid-tier model
 * announced "I'll create a task", "saved it to cloudflow_agreement_brief.md" and
 * "I will mark the task as completed" — and the database held none of it. A tool
 * that is not called leaves no record; a tool that is called leaves one. Narrated
 * work stops being possible.
 *
 * Two rules the model is never asked to remember, because both were learned from
 * a 422 in production and neither is discoverable from the API surface:
 *   - moving to `in_review` must name a review path
 *   - naming a person is a handover, since an issue can hold one assignee
 */

import type { ToolBox, ToolCall, ToolSchema } from "./loop.js";

export interface ToolContext {
  apiUrl: string;
  runId: string;
  agentId: string;
  companyId: string;
  issueId: string;
  /** The person this run belongs to. The reviewer, when work goes back for review. */
  responsibleUserId: string | null;
  /** The goal this task hangs off, so subtasks stay on the same plan. */
  goalId?: string | null;
}

export interface HttpCall {
  method: string;
  path: string;
  headers: Record<string, string>;
  body?: unknown;
}

export type HttpFn = (call: HttpCall) => Promise<{ status: number; body?: unknown }>;

/**
 * What the run did, as recorded by the tools rather than claimed by the model.
 *
 * `execute` needs to know whether the agent actually left the task somewhere
 * final. Asking the model would reintroduce exactly the failure this design
 * exists to prevent, so the answer comes from the tool that succeeded.
 */
export interface ToolState {
  /** The last status a successful update_issue call set. */
  finalStatus: string | null;
  /** True once anything durable was written, so a settle knows not to duplicate. */
  commented: boolean;
}

export type NufiToolBox = ToolBox & {
  state: ToolState;
  /**
   * The context these tools run against, exposed so `execute` can fill in what
   * it only learns after the first read — the goal a subtask should inherit.
   */
  context: ToolContext;
};

type Args = Record<string, unknown>;

function args(value: unknown): Args {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Args) : {};
}

function str(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

/** Statuses a heartbeat may legitimately claim. `in_progress` is entered by checkout. */
const CLAIMABLE = ["todo", "backlog", "blocked", "in_review"] as const;

const OBJECT = (properties: Record<string, unknown>, required: string[] = []) => ({
  type: "object",
  properties,
  ...(required.length ? { required } : {}),
});

const S = { type: "string" } as const;

/**
 * What a mutation hands back to the model.
 *
 * A tool result returns as `role: "tool"`, which the gateway's G1 control
 * classifies as `untrusted` — the one span class that blocks on a single
 * detector rather than requiring two to agree. The server echoes the whole
 * issue back from a checkout or a status update, so the task description made a
 * round trip and came back through the strictest channel there is. Measured on
 * HAN-4: `injection source=untrusted 0–2202 score=0.99997`, and the run died.
 *
 * The agent does not need the echo — it was handed the task in the wake. So a
 * mutation confirms what changed and nothing more. Reads are untouched: their
 * content is the answer the agent asked for.
 */
/**
 * Give every proposed task an owner before it can become a real one.
 *
 * Accepting a `suggest_tasks` card turns each draft into an issue, and a draft
 * naming nobody produces exactly the inert task that `create_child_issue` was
 * fixed for: `todo`, no assignee, never picked up. Fixing one path and leaving
 * its twin is how a bug survives being fixed — measured right after that fix
 * shipped, when accepting three proposals produced three orphans.
 *
 * A draft already handed to a person is left alone; that is a person's job, not
 * something to take back.
 */
export function withOwners(tasks: unknown, agentId: string): unknown[] {
  if (!Array.isArray(tasks)) return [];
  return tasks.map((task) => {
    if (!task || typeof task !== "object" || Array.isArray(task)) return task;
    const draft = task as Record<string, unknown>;
    if (str(draft.assigneeAgentId) || str(draft.assigneeUserId)) return draft;
    return { ...draft, assigneeAgentId: agentId };
  });
}

function confirm(body: unknown): unknown {
  if (!body || typeof body !== "object" || Array.isArray(body)) return { ok: true };
  const row = body as Record<string, unknown>;
  const kept: Record<string, unknown> = { ok: true };
  for (const key of ["id", "identifier", "status", "assigneeUserId", "assigneeAgentId"]) {
    if (row[key] !== undefined) kept[key] = row[key];
  }
  return kept;
}

export function buildTools(ctx: ToolContext, http: HttpFn): NufiToolBox {
  const state: ToolState = { finalStatus: null, commented: false };
  const headers = {
    "content-type": "application/json",
    "X-Paperclip-Run-Id": ctx.runId,
  };

  const send = async (method: string, path: string, body?: unknown) =>
    http({ method, path, headers, body });

  /** A non-2xx is information, not an exception — the contract expects the agent to read it. */
  const result = (
    res: { status: number; body?: unknown },
    onError?: (status: number) => string | undefined,
    shape: (body: unknown) => unknown = (body) => body ?? null,
  ) => {
    if (res.status >= 200 && res.status < 300) return { ok: true, result: shape(res.body) };
    const custom = onError?.(res.status);
    const detail = typeof res.body === "string" ? res.body : JSON.stringify(res.body ?? {});
    return { ok: false, result: custom ? `${custom} (HTTP ${res.status}: ${detail})` : `HTTP ${res.status}: ${detail}` };
  };

  const interaction = async (kind: string, a: Args) => {
    const res = await send("POST", `/api/issues/${ctx.issueId}/interactions`, {
      kind,
      title: str(a.title) ?? null,
      summary: str(a.summary) ?? null,
      // request_confirmation defaults to `none`, which never wakes anyone. Every
      // interaction this adapter opens is one it means to come back to.
      continuationPolicy: str(a.continuationPolicy) ?? "wake_assignee",
      ...(str(a.idempotencyKey) ? { idempotencyKey: str(a.idempotencyKey) } : {}),
      payload: a.payload ?? { version: 1 },
    });
    return result(res, undefined, confirm);
  };

  const handlers: Record<string, { schema: ToolSchema; run: (a: Args) => Promise<{ ok: boolean; result: unknown }> }> = {
    get_issue: {
      schema: {
        name: "get_issue",
        description:
          "Read the current task: title, description, status, the goal and project it belongs to, ancestors, and blockers. Call this before doing the work.",
        parameters: OBJECT({}),
      },
      run: async () => result(await send("GET", `/api/issues/${ctx.issueId}/heartbeat-context`)),
    },

    get_comments: {
      schema: {
        name: "get_comments",
        description:
          "Read the task's comment thread, oldest first. Pass `after` with a comment id to fetch only what is new since then.",
        parameters: OBJECT({ after: S }),
      },
      run: async (a) => {
        const after = str(a.after);
        const query = `?order=asc&limit=50${after ? `&after=${encodeURIComponent(after)}` : ""}`;
        return result(await send("GET", `/api/issues/${ctx.issueId}/comments${query}`));
      },
    },

    checkout_issue: {
      schema: {
        name: "checkout_issue",
        description:
          "Claim this task before working on it. This is how a task enters in_progress — never set that status by hand. If another agent holds it you get a conflict; pick different work rather than retrying.",
        parameters: OBJECT({}),
      },
      run: async () =>
        result(
          await send("POST", `/api/issues/${ctx.issueId}/checkout`, {
            agentId: ctx.agentId,
            expectedStatuses: [...CLAIMABLE],
          }),
          (status) =>
            status === 409
              ? "This task is checked out by another agent. Do not retry; work on something else or report that it is taken."
              : undefined,
          confirm,
        ),
    },

    add_comment: {
      schema: {
        name: "add_comment",
        description:
          "Post markdown progress on the task. Say what is done, what remains, and who owns the next step. Reference other tasks as links like [LEG-3](/LEG/issues/LEG-3).",
        parameters: OBJECT({ body: S }, ["body"]),
      },
      run: async (a) => {
        const out = result(await send("POST", `/api/issues/${ctx.issueId}/comments`, { body: str(a.body) ?? "" }), undefined, confirm);
        if (out.ok) state.commented = true;
        return out;
      },
    },

    update_issue: {
      schema: {
        name: "update_issue",
        description:
          "Set the task's final state for this heartbeat, with an optional comment in the same call. Use 'done' when the work is finished, 'in_review' when a person must look at it, 'blocked' when you cannot continue — and when blocked, say in the comment who must act and what they must do.",
        parameters: OBJECT(
          {
            status: { type: "string", enum: ["backlog", "todo", "in_progress", "in_review", "done", "blocked", "cancelled"] },
            comment: S,
            priority: { type: "string", enum: ["critical", "high", "medium", "low"] },
            assigneeUserId: S,
            blockedByIssueIds: { type: "array", items: S },
          },
          [],
        ),
      },
      run: async (a) => {
        const status = str(a.status);
        const body: Args = {};
        if (status) body.status = status;
        if (str(a.comment)) body.comment = str(a.comment);
        if (str(a.priority)) body.priority = str(a.priority);
        if (Array.isArray(a.blockedByIssueIds)) body.blockedByIssueIds = a.blockedByIssueIds;

        /**
         * The handover. `in_review` needs someone owning the next action, and an
         * issue holds one assignee — so the agent steps off as the person steps
         * on. Skipped entirely when there is nobody to hand to, because an issue
         * with no owner at all is worse than one still held by its agent.
         */
        const namedAssignee = str(a.assigneeUserId);
        const reviewer = status === "in_review" ? namedAssignee ?? ctx.responsibleUserId : namedAssignee;
        if (reviewer) {
          body.assigneeUserId = reviewer;
          body.assigneeAgentId = null;
        }

        const out = result(await send("PATCH", `/api/issues/${ctx.issueId}`, body), undefined, confirm);
        if (out.ok) {
          if (status) state.finalStatus = status;
          if (body.comment) state.commented = true;
        }
        return out;
      },
    },

    create_child_issue: {
      schema: {
        name: "create_child_issue",
        description:
          "Delegate work that does not fit this heartbeat by creating a subtask. Prefer this over waiting or polling. " +
          "Name assigneeAgentId to hand it to another agent — call list_agents to see who there is. " +
          "Leave it out and the subtask comes back to you: an unassigned task is never picked up by anyone.",
        parameters: OBJECT(
          {
            title: S,
            description: S,
            priority: { type: "string", enum: ["critical", "high", "medium", "low"] },
            assigneeAgentId: S,
            blocksThisTask: { type: "boolean" },
          },
          ["title"],
        ),
      },
      run: async (a) =>
        result(
          await send("POST", `/api/companies/${ctx.companyId}/issues`, {
            title: str(a.title) ?? "",
            description: str(a.description) ?? null,
            status: "todo",
            priority: str(a.priority) ?? "medium",
            parentId: ctx.issueId,
            /**
             * Never unassigned. "Never look for unassigned work. No assignments
             * = exit" is Paperclip's contract, so a subtask with nobody on it
             * is inert — it sits at `todo` and no agent will ever claim it.
             * Measured on a real onboarding run: a team lead split its task into
             * six correct subtasks, all unassigned, and the board looked like
             * progress while nothing could move.
             *
             * An unnamed assignee means "I will do it", which is also the
             * honest reading of an agent breaking its own work into steps.
             */
            assigneeAgentId: str(a.assigneeAgentId) ?? ctx.agentId,
            // "Always set parentId and goalId" — a subtask off the goal is off
            // the plan, and drops out of every goal-scoped view.
            ...(ctx.goalId ? { goalId: ctx.goalId } : {}),
          }),
          undefined,
          confirm,
        ),
    },

    list_agents: {
      schema: {
        name: "list_agents",
        description:
          "List the agents in this company, with their names and what they do. Use it before delegating, so a subtask goes to the desk that owns the work rather than back to you.",
        parameters: OBJECT({}),
      },
      run: async () => result(await send("GET", `/api/companies/${ctx.companyId}/agents`)),
    },

    put_plan: {
      schema: {
        name: "put_plan",
        description:
          "Write or revise this task's plan document. Plans live here, never in the task description and never as a repo file. Mention in a comment that you updated it.",
        parameters: OBJECT({ body: S, baseRevisionId: S }, ["body"]),
      },
      run: async (a) =>
        result(
          await send("PUT", `/api/issues/${ctx.issueId}/documents/plan`, {
            title: "Plan",
            format: "markdown",
            body: str(a.body) ?? "",
            baseRevisionId: str(a.baseRevisionId) ?? null,
          }),
        ),
    },

    suggest_tasks: {
      schema: {
        name: "suggest_tasks",
        description:
          "Propose concrete follow-up tasks for a person to accept. Accepted ones become real subtasks and wake you to work them. Each task needs a unique clientKey and a title.",
        parameters: OBJECT(
          {
            title: S,
            summary: S,
            tasks: {
              type: "array",
              items: OBJECT({ clientKey: S, title: S, description: S }, ["clientKey", "title"]),
            },
          },
          ["tasks"],
        ),
      },
      run: async (a) =>
        interaction("suggest_tasks", {
          ...a,
          payload: { version: 1, tasks: withOwners(a.tasks, ctx.agentId) },
        }),
    },

    ask_user_questions: {
      schema: {
        name: "ask_user_questions",
        description:
          "Ask a person a short set of structured questions when information is genuinely missing and no agent could supply it. Never invent an answer you could have asked for.",
        parameters: OBJECT({ title: S, summary: S, payload: { type: "object" } }, ["payload"]),
      },
      run: async (a) => interaction("ask_user_questions", a),
    },

    request_confirmation: {
      schema: {
        name: "request_confirmation",
        description:
          "Ask a person for a single yes/no decision before doing something consequential. Use for one decision; use suggest_tasks to propose work and ask_user_questions to gather facts.",
        parameters: OBJECT({ title: S, summary: S, payload: { type: "object" } }, ["payload"]),
      },
      run: async (a) => interaction("request_confirmation", a),
    },

    paperclip_api: {
      schema: {
        name: "paperclip_api",
        description:
          "Call any other Paperclip API endpoint directly when no tool above fits. Paths must start with /api/.",
        parameters: OBJECT({ method: S, path: S, body: { type: "object" } }, ["method", "path"]),
      },
      run: async (a) => {
        const path = str(a.path) ?? "";
        /**
         * The run token is a bearer credential. Left unchecked, this tool would
         * happily send it to any host the model names — which turns one confused
         * turn into credential exfiltration.
         */
        if (!path.startsWith("/api/")) {
          return { ok: false, result: `Refused: path must start with /api/ and stay on this server. Got "${path}".` };
        }
        return result(await send(str(a.method)?.toUpperCase() ?? "GET", path, a.body));
      },
    },
  };

  return {
    state,
    context: ctx,
    schemas: Object.values(handlers).map((h) => h.schema),
    async run(call: ToolCall) {
      const handler = handlers[call.name];
      if (!handler) {
        return { ok: false, result: `Unknown tool "${call.name}". Use one of: ${Object.keys(handlers).join(", ")}.` };
      }
      try {
        return await handler.run(args(call.arguments));
      } catch (err) {
        return { ok: false, result: `Tool "${call.name}" failed: ${err instanceof Error ? err.message : String(err)}` };
      }
    },
  };
}
