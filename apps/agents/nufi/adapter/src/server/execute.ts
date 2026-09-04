import { runLoop, type LoopModel } from "./loop.js";
import { systemPrompt, wakeMessage } from "./prompt.js";
import { buildTools, type HttpFn, type NufiToolBox } from "./tools.js";

/**
 * Structural types matching `@paperclipai/adapter-utils`. Declared locally
 * rather than imported so this package builds and tests standalone, outside
 * Paperclip's pnpm workspace — which is where it has to live, because anything
 * under apps/agents/packages/ is vendored upstream and the fork guard rejects
 * additions there.
 *
 * Only the fields this adapter reads are declared. If the upstream contract
 * changes shape, `pnpm build` here still passes and the failure surfaces at
 * runtime — the trade for not coupling to an unpublished workspace package.
 */
export interface ExecutionContext {
  runId: string;
  agent: { id: string; companyId: string };
  config: Record<string, unknown>;
  context: Record<string, unknown>;
  authToken?: string;
  onLog: (stream: "stdout" | "stderr", chunk: string) => Promise<void>;
}

export interface ExecutionResult {
  exitCode: number | null;
  signal: string | null;
  timedOut: boolean;
  errorMessage?: string | null;
  summary?: string | null;
  model?: string | null;
}

export interface ExecuteDeps {
  http: HttpFn;
  model: LoopModel;
}

/** Statuses that mean somebody or something owns the next action. */
const TERMINAL = new Set(["done", "in_review", "blocked", "cancelled"]);

function readString(source: Record<string, unknown>, key: string): string | null {
  const value = source[key];
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

/**
 * Who the work belongs to, and therefore who reviews it.
 *
 * The control plane resolves this before dispatch and puts it in two places.
 * Read the run context first, then fall back to the claim on the run token — the
 * token is ours, minted by the server we are about to call, and this reads one
 * field out of it while verifying nothing. The server does the verifying.
 */
export function resolveResponsibleUser(ctx: ExecutionContext): string | null {
  const fromContext = readString(ctx.context, "responsibleUserId");
  if (fromContext) return fromContext;

  const parts = (ctx.authToken ?? "").split(".");
  if (parts.length !== 3) return null;
  try {
    const claims = JSON.parse(Buffer.from(parts[1], "base64url").toString("utf8")) as Record<string, unknown>;
    const sub = claims.responsible_user_id;
    return typeof sub === "string" && sub.trim() ? sub.trim() : null;
  } catch {
    return null;
  }
}

/**
 * One heartbeat.
 *
 * The contract has not changed since this adapter was a one-shot answerer: the
 * task is left in a state someone can act on, never untouched. What changed is
 * who does the leaving. The agent has tools now and is expected to use them;
 * `settle` steps in only when it did not.
 */
export async function runWith(deps: ExecuteDeps, ctx: ExecutionContext): Promise<ExecutionResult> {
  const issueId = readString(ctx.context, "taskId") ?? readString(ctx.context, "issueId");
  if (!issueId) {
    /**
     * An idle heartbeat is not a failure. Paperclip wakes an agent on a timer as
     * well as on assignment, and the contract is explicit: nothing assigned
     * means exit the heartbeat. Returning non-zero here marks every quiet tick
     * as a failed run and buries the real failures.
     */
    await ctx.onLog("stdout", "No task assigned; nothing to do this heartbeat.\n");
    return { exitCode: 0, signal: null, timedOut: false, summary: "Idle — no task assigned" };
  }

  const tools = buildTools(
    {
      apiUrl: "",
      runId: ctx.runId,
      agentId: ctx.agent.id,
      companyId: ctx.agent.companyId,
      issueId,
      responsibleUserId: resolveResponsibleUser(ctx),
      // Filled in once the heartbeat context is read, so subtasks inherit the
      // goal rather than falling off the plan.
      goalId: null,
    },
    deps.http,
  );

  try {
    /**
     * Work that is already answered is not work. Paperclip re-dispatches an
     * agent that still holds an assignment, and an agent that answers every time
     * it is asked will answer the same task forever. Measured before this guard
     * existed: one task collected four full answers in twenty seconds, and a
     * human could not close it — every attempt was undone within ten seconds.
     */
    const current = await deps.http({
      method: "GET",
      path: `/api/issues/${issueId}/heartbeat-context`,
      headers: { "X-Paperclip-Run-Id": ctx.runId },
    });
    if (current.status >= 400) {
      throw new Error(
        `heartbeat-context ${current.status}: ${JSON.stringify(current.body ?? {}).slice(0, 300)}`,
      );
    }
    /**
     * One read, used twice: the already-answered guard, and the task briefing
     * the agent wakes with. Fetching it here rather than letting the agent call
     * get_issue is what Paperclip's own wake payload does — and it keeps the
     * task text in a `user` span, where G1 requires two detectors to agree,
     * instead of the `untrusted` span where one is enough to refuse the request.
     */
    const heartbeat = current.body as {
      issue?: { status?: string; title?: string; description?: string; priority?: string; goalId?: string | null };
      goal?: { id?: string; title?: string } | null;
      project?: { name?: string } | null;
    } | null;
    const status = heartbeat?.issue?.status ?? "todo";
    tools.context.goalId = heartbeat?.goal?.id ?? heartbeat?.issue?.goalId ?? null;
    if (status === "in_review" || status === "done") {
      await ctx.onLog("stdout", "Already answered and awaiting a person; nothing to add.\n");
      return {
        exitCode: 0,
        signal: null,
        timedOut: false,
        summary: "Idle — already answered, waiting on review",
      };
    }

    const outcome = await runLoop({
      model: deps.model,
      tools,
      system: systemPrompt(),
      wake: wakeMessage({
        issueId,
        companyId: ctx.agent.companyId,
        agentId: ctx.agent.id,
        wakeReason: readString(ctx.context, "wakeReason"),
        wakeCommentId: readString(ctx.context, "wakeCommentId"),
        approvalId: readString(ctx.context, "approvalId"),
        issue: heartbeat?.issue?.title
          ? {
              title: heartbeat.issue.title,
              description: heartbeat.issue.description ?? "",
              status: heartbeat.issue.status ?? null,
              priority: heartbeat.issue.priority ?? null,
              goal: heartbeat.goal?.title ?? null,
              project: heartbeat.project?.name ?? null,
            }
          : null,
      }),
    });

    await ctx.onLog(
      "stdout",
      `${outcome.iterations} turn(s); tools used: ${outcome.toolsUsed.join(", ") || "none"}\n`,
    );

    const settled = await settle(tools, outcome.text, outcome.stopReason);
    await ctx.onLog("stdout", `[disposition: ${settled}]\n`);

    return {
      exitCode: 0,
      signal: null,
      timedOut: false,
      summary:
        settled === "blocked" ? "Blocked" : settled === "done" ? "Done" : "Answered, awaiting review",
    };
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);

    /**
     * A failed run still owes the task a disposition. Leaving it untouched is
     * what made Paperclip escalate and then stop dispatching during the spike,
     * so the comment and the status go out on the error path too — and if that
     * fails as well, the run reports non-zero rather than pretending.
     */
    try {
      await tools.run({
        id: "settle_error",
        name: "update_issue",
        arguments: {
          status: "blocked",
          comment: `The agent run failed and could not continue.\n\n\`\`\`\n${message}\n\`\`\``,
        },
      });
    } catch {
      // Reported through exitCode below; nothing further to try.
    }

    await ctx.onLog("stderr", `${message}\n`);
    return { exitCode: 1, signal: null, timedOut: false, errorMessage: message };
  }
}

/**
 * Guarantee a disposition.
 *
 * The agent is expected to set its own final state — that is what the tools and
 * the contract are for. This is the backstop for the run that talked itself out
 * without acting, and for the one that spent its whole turn budget mid-thought.
 * Three consecutive dispositionless runs make Paperclip escalate to a recovery
 * owner and stop dispatching the agent at all.
 *
 * It reads `tools.state`, never the model's closing text: a model that will
 * narrate creating a task will just as happily narrate closing one.
 */
export async function settle(tools: NufiToolBox, text: string, stopReason: string): Promise<string> {
  if (tools.state.finalStatus && TERMINAL.has(tools.state.finalStatus)) {
    return tools.state.finalStatus;
  }

  const ranOutOfTurns = stopReason === "iteration_cap";
  const written = text.trim();
  /**
   * `in_review` is a claim that somebody will review this, and Paperclip treats
   * it as a healthy waiting path. Two endings do not earn it.
   *
   * A run that delegated its own blocker is waiting on a dependency, not a
   * person — and only a recorded blocker will wake it when that dependency
   * lands. Measured on DAE-27: the agent created the child, wrote "I will now
   * set this task to blocked", and the board said `in_review`.
   *
   * A run that wrote nothing has nothing to review. Parking it in a reviewer's
   * queue makes an empty result look like progress; `blocked` puts it in front
   * of a person, which is what the message has always said it needs.
   */
  const blockedOnChildren = tools.state.blockers.length > 0;
  const status = ranOutOfTurns || blockedOnChildren || !written ? "blocked" : "in_review";

  const comment = ranOutOfTurns
    ? "The agent used its whole turn budget without reaching a conclusion, so this task is " +
      "blocked rather than left looking active. A person should decide whether it is " +
      "answerable as written.\n\n" +
      (written ? `Its last words:\n\n${written}` : "It produced no closing summary.")
    : written ||
      "The agent finished without leaving a written result. A person should decide whether " +
        "this task is answerable as written.";

  await tools.run({
    id: "settle",
    name: "update_issue",
    arguments: {
      status,
      comment,
      ...(blockedOnChildren ? { blockedByIssueIds: [...tools.state.blockers] } : {}),
    },
  });
  return status;
}
