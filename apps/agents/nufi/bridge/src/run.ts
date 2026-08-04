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
    checkout(
      issueId: string,
      agentId: string,
      runId: string,
    ): Promise<{ ok: boolean; conflict?: boolean }>;
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
 * the correct response is to stop, never to retry (.claude/skills/paperclip,
 * Step 5). Commenting on an issue we do not own would be worse than doing
 * nothing: it looks like progress to whoever does own it.
 */
export async function handleRun(deps: RunDeps, payload: RunPayload): Promise<RunOutcome> {
  const { taskId } = payload.context;

  const claim = await deps.paperclip.checkout(taskId, payload.agentId, payload.runId);
  if (!claim.ok) {
    return {
      status: "skipped",
      detail: claim.conflict ? "owned by another agent" : "checkout refused",
    };
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
