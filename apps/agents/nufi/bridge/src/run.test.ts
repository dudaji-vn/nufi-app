import { describe, expect, it } from "bun:test";

import { handleRun } from "./run";

const payload = {
  runId: "run_1",
  agentId: "agent_1",
  companyId: "co_1",
  context: { taskId: "issue_1", wakeReason: "issue_assigned" },
};

function deps(overrides: Record<string, unknown> = {}) {
  const calls: string[] = [];
  const paperclip = {
    checkout: async () => {
      calls.push("checkout");
      return { ok: true };
    },
    heartbeatContext: async () => {
      calls.push("context");
      return { title: "Translate the login screen", description: "Vietnamese to English.", goal: null };
    },
    comment: async (_id: string, body: string) => {
      calls.push(`comment:${body}`);
    },
    setStatus: async (_id: string, s: string) => {
      calls.push(`status:${s}`);
    },
  };
  const chat = {
    complete: async () => {
      calls.push("chat");
      return "Done — 14 strings translated.";
    },
  };
  return { calls, paperclip, chat, ...overrides };
}

describe("handleRun", () => {
  it("checks out, reads context, asks chat, then reports back", async () => {
    const d = deps();
    const outcome = await handleRun(d as never, payload);

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
    const base = deps();
    const d = deps({
      paperclip: { ...base.paperclip, checkout: async () => ({ ok: false, conflict: true }) },
    });
    const outcome = await handleRun(d as never, payload);

    expect(outcome.status).toBe("skipped");
    expect(d.calls.some((c) => c.startsWith("comment"))).toBe(false);
  });

  it("reports the failure as a comment and leaves the task open", async () => {
    const d = deps({
      chat: {
        complete: async () => {
          throw new Error("gateway 503");
        },
      },
    });
    const outcome = await handleRun(d as never, payload);

    expect(outcome.status).toBe("failed");
    expect(d.calls.at(-1)).toBe("comment:Run failed: gateway 503");
  });
});
