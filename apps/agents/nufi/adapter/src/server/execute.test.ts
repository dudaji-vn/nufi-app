import { describe, expect, it } from "bun:test";

import { resolveResponsibleUser, runWith, type ExecutionContext } from "./execute";
import type { ModelTurn } from "./loop";
import type { HttpCall } from "./tools";

function ctx(overrides: Partial<ExecutionContext> = {}): ExecutionContext {
  return {
    runId: "run_1",
    agent: { id: "agent_1", companyId: "co_1" },
    config: {},
    context: { taskId: "issue_1", responsibleUserId: "user_9" },
    onLog: async () => {},
    ...overrides,
  };
}

/** Serves heartbeat-context and records every mutation the run makes. */
function api(opts: { status?: string; responses?: Record<string, { status: number; body?: unknown }> } = {}) {
  const calls: HttpCall[] = [];
  const fn = async (call: HttpCall) => {
    calls.push(call);
    const canned = opts.responses?.[`${call.method} ${call.path}`];
    if (canned) return canned;
    if (call.path.endsWith("/heartbeat-context")) {
      return { status: 200, body: { issue: { status: opts.status ?? "todo", title: "T", description: "D" } } };
    }
    return { status: 200, body: { ok: true } };
  };
  const patches = () => calls.filter((c) => c.method === "PATCH").map((c) => c.body as Record<string, unknown>);
  return { fn, calls, patches };
}

function model(turns: ModelTurn[]) {
  let i = 0;
  return { async turn() { return turns[Math.min(i++, turns.length - 1)]; } };
}

const say = (t: string): ModelTurn => ({ text: t, toolCalls: [] });
const use = (name: string, args: unknown = {}): ModelTurn => ({
  text: "",
  toolCalls: [{ id: "c1", name, arguments: args }],
});

describe("runWith", () => {
  it("exits idle when nothing is assigned", async () => {
    const { fn, calls } = api();
    const out = await runWith({ http: fn, model: model([say("hi")]) }, ctx({ context: {} }));

    expect(out.exitCode).toBe(0);
    expect(out.summary).toMatch(/Idle/);
    expect(calls).toHaveLength(0);
  });

  /**
   * Paperclip re-dispatches an agent that still holds an assignment. Measured
   * before this guard: one task collected four full answers in twenty seconds
   * and a human could not close it.
   */
  it("does not re-answer a task already waiting on a person", async () => {
    const { fn, patches } = api({ status: "in_review" });
    const out = await runWith({ http: fn, model: model([say("more thoughts")]) }, ctx());

    expect(out.summary).toMatch(/already answered/i);
    expect(patches()).toHaveLength(0);
  });

  it("lets the agent set its own final state and does not second-guess it", async () => {
    const { fn, patches } = api();
    const out = await runWith(
      {
        http: fn,
        model: model([use("update_issue", { status: "done", comment: "Filed." }), say("Done.")]),
      },
      ctx(),
    );

    expect(out.summary).toBe("Done");
    expect(patches()).toHaveLength(1);
    expect(patches()[0]).toMatchObject({ status: "done" });
  });

  /**
   * The backstop. Three consecutive runs that leave no disposition make
   * Paperclip escalate to a recovery owner and stop dispatching the agent.
   */
  it("settles a task the agent talked about but never touched", async () => {
    const { fn, patches } = api();
    const out = await runWith({ http: fn, model: model([say("Here is my answer.")]) }, ctx());

    expect(out.summary).toMatch(/awaiting review/i);
    expect(patches()[0]).toMatchObject({ status: "in_review", comment: "Here is my answer." });
  });

  /** A run that spends its whole budget mid-thought is blocked, not "in review". */
  it("blocks when the turn budget runs out", async () => {
    const { fn, patches } = api();
    const out = await runWith({ http: fn, model: model([use("get_issue")]) }, ctx());

    expect(out.summary).toBe("Blocked");
    expect(patches()[0]).toMatchObject({ status: "blocked" });
    expect(String(patches()[0].comment)).toMatch(/turn budget/i);
  });

  /**
   * The settle must not believe the model. A model that will narrate creating a
   * task will narrate closing one, so the backstop reads what the tools
   * recorded — and a rejected PATCH recorded nothing.
   */
  it("still settles when the agent's own status update was refused", async () => {
    const { fn, patches } = api({
      responses: { "PATCH /api/issues/issue_1": { status: 422, body: { error: "invalid_issue_disposition" } } },
    });
    await runWith(
      { http: fn, model: model([use("update_issue", { status: "done" }), say("All finished!")]) },
      ctx(),
    );

    // Its own attempt, then the backstop's — the run never claims success on a 422.
    expect(patches()).toHaveLength(2);
  });

  it("blocks the task and reports non-zero when the control plane is unreachable", async () => {
    const { fn, patches } = api({
      responses: { "GET /api/issues/issue_1/heartbeat-context": { status: 404, body: { error: "Issue not found" } } },
    });
    const out = await runWith({ http: fn, model: model([say("never runs")]) }, ctx());

    expect(out.exitCode).toBe(1);
    expect(out.errorMessage).toContain("heartbeat-context 404");
    expect(patches()[0]).toMatchObject({ status: "blocked" });
  });

  it("passes the wake reason through to the agent", async () => {
    const { fn } = api();
    let seen = "";
    const spy = {
      async turn(messages: { role: string; content: string }[]) {
        seen = messages.map((m) => m.content).join("\n");
        return say("ok");
      },
    };
    await runWith(
      { http: fn, model: spy },
      ctx({ context: { taskId: "issue_1", wakeReason: "issue_commented", wakeCommentId: "cmt_7" } }),
    );

    expect(seen).toContain("issue_commented");
    expect(seen).toContain("cmt_7");
  });
});

describe("resolveResponsibleUser", () => {
  it("prefers the run context", () => {
    expect(resolveResponsibleUser(ctx())).toBe("user_9");
  });

  /** The token is ours; this reads one claim and verifies nothing. */
  it("falls back to the run token's claim", () => {
    const claims = Buffer.from(JSON.stringify({ responsible_user_id: "user_jwt" })).toString("base64url");
    const withToken = ctx({ context: { taskId: "issue_1" }, authToken: `h.${claims}.sig` });

    expect(resolveResponsibleUser(withToken)).toBe("user_jwt");
  });

  it("returns null rather than throwing on a malformed token", () => {
    expect(resolveResponsibleUser(ctx({ context: { taskId: "i" }, authToken: "not-a-jwt" }))).toBeNull();
    expect(resolveResponsibleUser(ctx({ context: { taskId: "i" }, authToken: "a.!!!.c" }))).toBeNull();
  });
});
