import { describe, expect, it } from "bun:test";

import { runWith, type ExecutionContext } from "./execute";

function ctx(overrides: Partial<ExecutionContext> = {}): ExecutionContext {
  return {
    runId: "run_1",
    agent: { id: "agent_1", companyId: "co_1" },
    config: {},
    context: { taskId: "issue_1" },
    onLog: async () => {},
    ...overrides,
  };
}

function deps(overrides: Record<string, unknown> = {}) {
  const calls: string[] = [];
  return {
    calls,
    fetchIssue: async () => {
      calls.push("fetch");
      return { title: "Draft the approvals page", description: "Cover review gates.", goal: null, status: "todo", assigneeUserId: null };
    },
    complete: async () => {
      calls.push("complete");
      return "A review gate holds a run until a named role approves it.";
    },
    comment: async (_id: string, body: string) => {
      calls.push(`comment:${body.slice(0, 24)}`);
    },
    setStatus: async (_id: string, s: string, patch?: { assigneeUserId?: string }) => {
      calls.push(patch?.assigneeUserId ? `status:${s}+assignee:${patch.assigneeUserId}` : `status:${s}`);
    },
    lastComment: async () => null,
    ...overrides,
  };
}

describe("runWith", () => {
  it("answers, comments, and settles the issue in review", async () => {
    const d = deps();
    const result = await runWith(d, ctx());

    expect(result.exitCode).toBe(0);
    expect(d.calls).toEqual([
      "fetch",
      "complete",
      "comment:A review gate holds a ru",
      "status:in_review",
    ]);
  });

  it("blocks the issue when the model refuses, rather than leaving it open", async () => {
    const d = deps({ complete: async () => "I cannot answer this without the document." });
    const result = await runWith(d, ctx());

    expect(result.exitCode).toBe(0);
    expect(d.calls.at(-1)).toBe("status:blocked");
  });

  /**
   * The spike's finding, encoded: an issue left untouched is what made Paperclip
   * escalate to a recovery owner and then stop dispatching. A failed run still
   * owes a disposition.
   */
  it("still settles the issue when the model call throws", async () => {
    const d = deps({
      complete: async () => {
        throw new Error("gateway 503");
      },
    });
    const result = await runWith(d, ctx());

    expect(result.exitCode).toBe(1);
    expect(result.errorMessage).toBe("gateway 503");
    expect(d.calls).toContain("status:blocked");
  });

  /**
   * A task that cannot be worked on is a correct decision, not a failed run.
   * Reporting non-zero made Paperclip raise "run failed" toasts for the agent
   * getting it right, which looks like a crash to anyone watching.
   */
  /**
   * Paperclip re-dispatches while an assignment stands. Without this, one task
   * collected four answers in twenty seconds and could not be closed: every
   * approval was undone by the next run. The loop has no natural end and every
   * lap costs a model call.
   */
  it("does no work when the task is already answered and awaiting review", async () => {
    const d = deps({
      fetchIssue: async () => ({ title: "T", description: "D", goal: null, status: "in_review" }),
    });
    const result = await runWith(d, ctx());

    expect(result.exitCode).toBe(0);
    expect(result.summary).toContain("already answered");
    // No model call, no comment, no status write — the point is that a second
    // dispatch costs nothing.
    expect(d.calls).toEqual([]);
  });

  it("does no work on a task a person has already closed", async () => {
    const d = deps({
      fetchIssue: async () => ({ title: "T", description: "D", goal: null, status: "done" }),
    });
    await runWith(d, ctx());
    expect(d.calls).toEqual([]);
  });

  it("blocks an unworkable task WITHOUT reporting the run as failed", async () => {
    const d = deps({
      fetchIssue: async () => ({ title: "Do the thing", description: "", goal: null, status: "todo" }),
    });
    const result = await runWith(d, ctx());

    expect(result.exitCode).toBe(0);
    expect(result.summary).toContain("not workable");
    expect(d.calls).toContain("status:blocked");
  });

  it("still reports non-zero when the gateway genuinely fails", async () => {
    const d = deps({
      complete: async () => {
        throw new Error("gateway 503");
      },
    });
    const result = await runWith(d, ctx());

    expect(result.exitCode).toBe(1);
    expect(d.calls).toContain("status:blocked");
  });

  /**
   * Observed on a live server: a timer heartbeat with nothing assigned produced
   * `paperclip-run-unassigned-…` and reported `Status: failed` while the agent
   * was in fact working correctly on another issue. An idle tick must be a
   * clean exit, or every quiet heartbeat looks like a fault and buries the real
   * ones.
   */
  it("exits cleanly, not as a failure, when there is no task to work on", async () => {
    const d = deps();
    const result = await runWith(d, ctx({ context: {} }));

    expect(result.exitCode).toBe(0);
    expect(result.summary).toBe("Idle — no task assigned");
    expect(d.calls).toEqual([]);
  });

  /**
   * A rate-limited gateway made Paperclip retry, and every retry failed the
   * same way — producing ~20 identical `gateway 429` comments on one task. The
   * signal was in the first; the rest buried it.
   */
  it("does not repeat a failure comment that is already the latest one", async () => {
    const d = deps({
      complete: async () => {
        throw new Error("gateway 429");
      },
      lastComment: async () => "The agent run failed: gateway 429",
    });
    const result = await runWith(d, ctx());

    expect(result.exitCode).toBe(1);
    expect(d.calls.some((c) => c.startsWith("comment"))).toBe(false);
    expect(d.calls).toContain("status:blocked");
  });

  it("still comments when the latest comment is a different failure", async () => {
    const posted: string[] = [];
    const d = deps({
      complete: async () => {
        throw new Error("gateway 503");
      },
      comment: async (_id: string, body: string) => {
        posted.push(body);
      },
      lastComment: async () => "The agent run failed: gateway 429",
    });
    await runWith(d, ctx());

    expect(posted).toEqual(["The agent run failed: gateway 503"]);
  });

  it("does not mask the original failure when settling also fails", async () => {
    const d = deps({
      complete: async () => {
        throw new Error("gateway 503");
      },
      comment: async () => {
        throw new Error("api down");
      },
    });
    const result = await runWith(d, ctx());

    expect(result.exitCode).toBe(1);
    expect(result.errorMessage).toBe("gateway 503");
  });
});

describe("naming a reviewer", () => {
  /**
   * Paperclip refuses an agent-authored move to in_review that leaves nobody
   * owning the next action — 422 `invalid_issue_disposition`. Observed in
   * production: the answer comment landed, the status update was rejected, and
   * the adapter's own error path then overwrote a good run with "failed" and
   * pushed the issue to blocked.
   *
   * So when the issue has no human assignee, hand it to the person the run
   * belongs to. That IS the review path — the member who asked gets the answer.
   */
  it("assigns the responsible user when the issue has none", async () => {
    const d = deps();
    await runWith(d, ctx({ context: { taskId: "issue_1", responsibleUserId: "user_9" } }));

    expect(d.calls).toContain("status:in_review+assignee:user_9");
  });

  /**
   * An issue that already has a human assignee satisfies the guard on its own.
   * Reassigning it would silently take the work off whoever it was given to.
   */
  it("leaves an existing assignee alone", async () => {
    const d = deps({
      fetchIssue: async () => ({
        title: "Draft the approvals page",
        description: "Cover review gates.",
        goal: null,
        status: "todo",
        assigneeUserId: "user_owner",
      }),
    });
    await runWith(d, ctx({ context: { taskId: "issue_1", responsibleUserId: "user_9" } }));

    expect(d.calls).toContain("status:in_review");
    expect(d.calls.join()).not.toContain("assignee:");
  });

  /** Blocked needs no reviewer — the guard only covers in_review. */
  it("does not name a reviewer when blocking", async () => {
    const d = deps({ complete: async () => "I cannot answer this without the contract." });
    await runWith(d, ctx({ context: { taskId: "issue_1", responsibleUserId: "user_9" } }));

    expect(d.calls).toContain("status:blocked");
    expect(d.calls.join()).not.toContain("assignee:");
  });
});
