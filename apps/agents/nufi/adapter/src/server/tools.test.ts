import { describe, expect, it } from "bun:test";

import { buildTools, type HttpCall, type HttpFn, type ToolContext } from "./tools";

function ctx(overrides: Partial<ToolContext> = {}): ToolContext {
  return {
    apiUrl: "http://api",
    runId: "run_1",
    agentId: "agent_1",
    companyId: "co_1",
    issueId: "issue_1",
    responsibleUserId: "user_9",
    ...overrides,
  };
}

/** Records every call and replays canned responses keyed by "METHOD path". */
function http(responses: Record<string, { status: number; body?: unknown }> = {}) {
  const calls: HttpCall[] = [];
  const fn: HttpFn = async (call) => {
    calls.push(call);
    const canned = responses[`${call.method} ${call.path}`];
    return canned ?? { status: 200, body: { ok: true } };
  };
  return { fn, calls };
}

const call = (name: string, args: unknown) => ({ id: "c1", name, arguments: args });

describe("update_issue", () => {
  /**
   * Two 422s, both learned in production on the same afternoon:
   *
   *   invalid_issue_disposition — an agent moving an issue to in_review must
   *   name a review path, or nobody owns the next action.
   *
   *   Issue can only have one assignee — so naming a person is a HANDOVER: the
   *   agent steps off as the person steps on.
   *
   * The model is not asked to know either rule. The tool applies them.
   */
  it("hands the issue to the responsible user when moving to in_review", async () => {
    const { fn, calls } = http();
    const tools = buildTools(ctx(), fn);

    const out = await tools.run(call("update_issue", { status: "in_review", comment: "Answered." }));

    expect(out.ok).toBe(true);
    expect(calls[0].method).toBe("PATCH");
    expect(calls[0].body).toMatchObject({
      status: "in_review",
      comment: "Answered.",
      assigneeUserId: "user_9",
      assigneeAgentId: null,
    });
  });

  it("leaves an assignee the model named alone", async () => {
    const { fn, calls } = http();
    const tools = buildTools(ctx(), fn);

    await tools.run(call("update_issue", { status: "in_review", assigneeUserId: "user_other" }));

    expect(calls[0].body).toMatchObject({ assigneeUserId: "user_other", assigneeAgentId: null });
  });

  /** blocked and done own their next action already; a handover would be wrong. */
  it("does not hand over for any status but in_review", async () => {
    const { fn, calls } = http();
    const tools = buildTools(ctx(), fn);

    await tools.run(call("update_issue", { status: "blocked", comment: "Waiting on Legal." }));

    expect(calls[0].body).not.toHaveProperty("assigneeUserId");
    expect(calls[0].body).not.toHaveProperty("assigneeAgentId");
  });

  /** With nobody to hand to, keep the agent rather than orphaning the issue. */
  it("skips the handover when there is no responsible user", async () => {
    const { fn, calls } = http();
    const tools = buildTools(ctx({ responsibleUserId: null }), fn);

    await tools.run(call("update_issue", { status: "in_review" }));

    expect(calls[0].body).not.toHaveProperty("assigneeUserId");
  });
});

describe("the run audit trail", () => {
  /** "You MUST include X-Paperclip-Run-Id on ALL requests that modify issues." */
  it("stamps the run id on every mutating call", async () => {
    const { fn, calls } = http();
    const tools = buildTools(ctx(), fn);

    await tools.run(call("add_comment", { body: "progress" }));
    await tools.run(call("update_issue", { status: "blocked" }));
    await tools.run(call("checkout_issue", {}));

    for (const c of calls) {
      expect(c.headers["X-Paperclip-Run-Id"]).toBe("run_1");
    }
  });
});

describe("checkout_issue", () => {
  it("sends the agent id and the statuses it expects to claim", async () => {
    const { fn, calls } = http();
    const tools = buildTools(ctx(), fn);

    await tools.run(call("checkout_issue", {}));

    expect(calls[0].path).toBe("/api/issues/issue_1/checkout");
    expect(calls[0].body).toMatchObject({ agentId: "agent_1" });
    expect((calls[0].body as { expectedStatuses: string[] }).expectedStatuses).toContain("todo");
  });

  /**
   * "Never retry a 409. The task belongs to someone else." A bare status code
   * invites a retry; the message has to carry the rule.
   */
  it("turns a 409 into an instruction not to retry", async () => {
    const { fn } = http({ "POST /api/issues/issue_1/checkout": { status: 409, body: { error: "conflict" } } });
    const tools = buildTools(ctx(), fn);

    const out = await tools.run(call("checkout_issue", {}));

    expect(out.ok).toBe(false);
    expect(String(out.result)).toMatch(/another agent/i);
    expect(String(out.result)).toMatch(/do not retry/i);
  });
});

describe("failures reach the model", () => {
  /**
   * The execution contract expects an agent to read a refusal and pick another
   * path. Throwing takes that choice away and fails a run that could recover.
   */
  it("returns the server's body, not just the status code", async () => {
    const { fn } = http({
      "PATCH /api/issues/issue_1": {
        status: 422,
        body: { error: "invalid_issue_disposition: needs a real review path" },
      },
    });
    const tools = buildTools(ctx(), fn);

    const out = await tools.run(call("update_issue", { status: "in_review" }));

    expect(out.ok).toBe(false);
    expect(String(out.result)).toContain("invalid_issue_disposition");
  });

  it("reports an unknown tool instead of throwing", async () => {
    const { fn } = http();
    const tools = buildTools(ctx(), fn);

    const out = await tools.run(call("delete_everything", {}));

    expect(out.ok).toBe(false);
    expect(String(out.result)).toMatch(/unknown tool/i);
  });
});

describe("delegation and interactions", () => {
  it("creates a child issue under the current one", async () => {
    const { fn, calls } = http();
    const tools = buildTools(ctx(), fn);

    await tools.run(call("create_child_issue", { title: "Draft the negotiation letter" }));

    expect(calls[0].path).toBe("/api/companies/co_1/issues");
    expect(calls[0].body).toMatchObject({ title: "Draft the negotiation letter", parentId: "issue_1" });
  });

  /**
   * `request_confirmation` defaults to `continuationPolicy: none`, which never
   * wakes the agent — the issue would sit answered forever. Every interaction
   * this adapter creates is one it intends to come back to.
   */
  it("always asks to be woken when the person responds", async () => {
    const { fn, calls } = http();
    const tools = buildTools(ctx(), fn);

    await tools.run(call("ask_user_questions", {
      title: "Which entity signs?",
      payload: { version: 1, questions: [] },
    }));

    expect(calls[0].path).toBe("/api/issues/issue_1/interactions");
    expect(calls[0].body).toMatchObject({ kind: "ask_user_questions", continuationPolicy: "wake_assignee" });
  });

  it("proposes tasks for a person to accept", async () => {
    const { fn, calls } = http();
    const tools = buildTools(ctx(), fn);

    await tools.run(call("suggest_tasks", {
      tasks: [{ clientKey: "t1", title: "Review the other vendor contracts" }],
    }));

    expect(calls[0].body).toMatchObject({ kind: "suggest_tasks", continuationPolicy: "wake_assignee" });
    const payload = (calls[0].body as { payload: { version: number; tasks: unknown[] } }).payload;
    expect(payload.version).toBe(1);
    expect(payload.tasks).toHaveLength(1);
  });
});

describe("the escape hatch", () => {
  it("passes an arbitrary call through with the run id attached", async () => {
    const { fn, calls } = http();
    const tools = buildTools(ctx(), fn);

    await tools.run(call("paperclip_api", { method: "GET", path: "/api/agents/me" }));

    expect(calls[0]).toMatchObject({ method: "GET", path: "/api/agents/me" });
    expect(calls[0].headers["X-Paperclip-Run-Id"]).toBe("run_1");
  });

  it("refuses a path outside the API", async () => {
    const { fn, calls } = http();
    const tools = buildTools(ctx(), fn);

    const out = await tools.run(call("paperclip_api", { method: "GET", path: "https://elsewhere.example/steal" }));

    expect(out.ok).toBe(false);
    expect(calls).toHaveLength(0);
  });
});

describe("the schemas the model sees", () => {
  it("describes every tool it can run, and runs every tool it describes", async () => {
    const tools = buildTools(ctx(), http().fn);
    const names = tools.schemas.map((s) => s.name);

    expect(names).toContain("update_issue");
    expect(names).toContain("suggest_tasks");
    expect(names).toContain("paperclip_api");

    for (const schema of tools.schemas) {
      expect(schema.description.length).toBeGreaterThan(10);
      const out = await tools.run(call(schema.name, {}));
      expect(String(out.result)).not.toMatch(/unknown tool/i);
    }
  });
});

describe("what the run recorded", () => {
  /**
   * `execute` must know whether the task was really left in a final state. It
   * asks the tools, never the model — a model that will narrate creating a task
   * will just as happily narrate closing one.
   */
  it("records the status only when the call succeeded", async () => {
    const { fn } = http({ "PATCH /api/issues/issue_1": { status: 422, body: { error: "nope" } } });
    const tools = buildTools(ctx(), fn);

    await tools.run(call("update_issue", { status: "done" }));

    expect(tools.state.finalStatus).toBeNull();
  });

  it("records the status and the comment on success", async () => {
    const { fn } = http();
    const tools = buildTools(ctx(), fn);

    await tools.run(call("update_issue", { status: "blocked", comment: "Waiting on Legal." }));

    expect(tools.state.finalStatus).toBe("blocked");
    expect(tools.state.commented).toBe(true);
  });

  it("starts with nothing recorded", () => {
    const tools = buildTools(ctx(), http().fn);
    expect(tools.state).toEqual({ finalStatus: null, commented: false });
  });
});

describe("what a mutation hands back", () => {
  /**
   * A tool result returns as `role: "tool"`, which the gateway's G1 control
   * classifies as `untrusted` — the one span class that blocks on a single
   * detector. The server echoes the whole issue back from a checkout or a
   * status update, so the task description made a round trip and came back
   * through the strictest channel there is. Measured on HAN-4:
   *
   *     injection  source=untrusted  0–2202  score=0.99997   -> blocked
   *
   * The agent does not need the echo. It was handed the task in the wake. So a
   * mutation confirms what changed and nothing else.
   */
  it("confirms the change without echoing the task back", async () => {
    const { fn } = http({
      "PATCH /api/issues/issue_1": {
        status: 200,
        body: {
          id: "issue_1",
          identifier: "HAN-4",
          status: "blocked",
          title: "printer",
          description: "A long description that must not travel back through an untrusted span.",
        },
      },
    });
    const tools = buildTools(ctx(), fn);

    const out = await tools.run(call("update_issue", { status: "blocked", comment: "No description." }));

    expect(out.ok).toBe(true);
    const text = JSON.stringify(out.result);
    expect(text).toContain("blocked");
    expect(text).toContain("HAN-4");
    expect(text).not.toContain("untrusted span");
  });

  it("keeps a checkout's answer to what the agent asked", async () => {
    const { fn } = http({
      "POST /api/issues/issue_1/checkout": {
        status: 200,
        body: { id: "issue_1", identifier: "HAN-1", status: "in_progress", description: "Meridian NDA clause 7." },
      },
    });
    const tools = buildTools(ctx(), fn);

    const out = await tools.run(call("checkout_issue", {}));

    expect(JSON.stringify(out.result)).not.toContain("Meridian");
    expect(JSON.stringify(out.result)).toContain("in_progress");
  });

  /** Reads are different: their content is the answer, so it comes back whole. */
  it("leaves a read alone", async () => {
    const { fn } = http({
      "GET /api/issues/issue_1/heartbeat-context": {
        status: 200,
        body: { issue: { title: "T", description: "The clause the agent asked to re-read." } },
      },
    });
    const tools = buildTools(ctx(), fn);

    const out = await tools.run(call("get_issue", {}));

    expect(JSON.stringify(out.result)).toContain("re-read");
  });
});
