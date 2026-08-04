import { buildPrompt, resolveDisposition } from "./disposition.js";

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
  fetchIssue(issueId: string): Promise<{ title: string; description: string; goal: string | null }>;
  complete(prompt: string): Promise<string>;
  comment(issueId: string, body: string): Promise<void>;
  setStatus(issueId: string, status: string): Promise<void>;
}

/**
 * One run. The contract this adapter holds itself to is that the issue is left
 * in a state someone can act on — `in_review` or `blocked`, never untouched.
 * See disposition.ts for why.
 */
export async function runWith(
  deps: ExecuteDeps,
  ctx: ExecutionContext,
): Promise<ExecutionResult> {
  const issueId = String(ctx.context.taskId ?? "");
  if (!issueId) {
    /**
     * An idle heartbeat is not a failure. Paperclip wakes an agent on a timer
     * as well as on assignment, and the control-plane contract is explicit:
     * nothing assigned means exit the heartbeat. Returning non-zero here marks
     * every quiet tick as a failed run, which buries the real failures —
     * observed directly: a run with nothing to do produced
     * `paperclip-run-unassigned-…` and `Status: failed` while the agent was
     * working correctly on another issue.
     */
    await ctx.onLog("stdout", "No task assigned; nothing to do this heartbeat.\n");
    return { exitCode: 0, signal: null, timedOut: false, summary: "Idle — no task assigned" };
  }

  try {
    const issue = await deps.fetchIssue(issueId);
    const prompt = buildPrompt(issue);

    await ctx.onLog("stdout", `> ${issue.title}\n`);
    const answer = await deps.complete(prompt);

    const disposition = resolveDisposition(answer);
    await deps.comment(issueId, disposition.comment);
    await deps.setStatus(issueId, disposition.status);

    await ctx.onLog("stdout", `\n[disposition: ${disposition.status}]\n`);

    return {
      exitCode: 0,
      signal: null,
      timedOut: false,
      summary: disposition.status === "in_review" ? "Answered, awaiting review" : "Blocked",
    };
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);

    /**
     * A failure still owes the issue a disposition. Leaving it untouched is the
     * exact behaviour that made Paperclip escalate and then stop dispatching
     * during the spike, so the comment and the status go out even on the error
     * path — and if THAT fails too, the run reports non-zero rather than
     * pretending.
     */
    try {
      await deps.comment(issueId, `The agent run failed: ${message}`);
      await deps.setStatus(issueId, "blocked");
    } catch {
      // Reported through exitCode below; nothing further to try.
    }

    await ctx.onLog("stderr", `${message}\n`);
    return { exitCode: 1, signal: null, timedOut: false, errorMessage: message };
  }
}
