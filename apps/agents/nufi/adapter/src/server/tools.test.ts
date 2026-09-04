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

    await tools.run(call("create_child_issue", { description: "What the work is and what done looks like.", title: "Draft the negotiation letter" }));

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
      tasks: [{ clientKey: "t1", title: "Review the other vendor contracts", description: "Why this task exists." }],
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
    expect(tools.state).toEqual({ finalStatus: null, commented: false, blockers: [], children: [], asked: false });
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

describe("delegation that actually gets picked up", () => {
  /**
   * "Never look for unassigned work. No assignments = exit." — Paperclip's own
   * contract. A subtask with no assignee is inert: no agent will ever claim it,
   * and it sits at `todo` forever.
   *
   * Measured on a real onboarding run: the team lead broke "hire your first
   * engineer" into six subtasks, every one of them correct and every one of
   * them unassigned. The board looked like progress and nothing could move.
   */
  it("gives a subtask to the agent that made it when none is named", async () => {
    const { fn, calls } = http();
    const tools = buildTools(ctx(), fn);

    await tools.run(call("create_child_issue", { title: "Draft the job description", description: "Write the JD for the founding engineer role." }));

    expect(calls[0].body).toMatchObject({
      title: "Draft the job description",
      parentId: "issue_1",
      assigneeAgentId: "agent_1",
    });
  });

  it("honours another agent when one is named", async () => {
    const { fn, calls } = http();
    const tools = buildTools(ctx(), fn);

    await tools.run(call("create_child_issue", { description: "What the work is and what done looks like.", title: "Review it", assigneeAgentId: "agent_legal" }));

    expect(calls[0].body).toMatchObject({ assigneeAgentId: "agent_legal" });
  });

  /** "Always set parentId and goalId" — a subtask off the goal is off the plan. */
  it("carries the parent's goal onto the subtask", async () => {
    const { fn, calls } = http();
    const tools = buildTools(ctx({ goalId: "goal_7" }), fn);

    await tools.run(call("create_child_issue", { description: "What the work is and what done looks like.", title: "Anything" }));

    expect(calls[0].body).toMatchObject({ goalId: "goal_7" });
  });

  it("omits the goal when the parent has none", async () => {
    const { fn, calls } = http();
    const tools = buildTools(ctx(), fn);

    await tools.run(call("create_child_issue", { description: "What the work is and what done looks like.", title: "Anything" }));

    expect(calls[0].body).not.toHaveProperty("goalId");
  });
});

describe("list_agents", () => {
  /**
   * Delegating to the right desk requires knowing which desks exist. Without
   * this the only honest choice is self-assignment, which turns every company
   * into one agent doing everything.
   */
  it("lists the company's agents", async () => {
    const { fn, calls } = http();
    const tools = buildTools(ctx(), fn);

    const out = await tools.run(call("list_agents", {}));

    expect(out.ok).toBe(true);
    expect(calls[0].path).toBe("/api/companies/co_1/agents");
  });
});

describe("suggested tasks land on someone too", () => {
  /**
   * The sibling of the `create_child_issue` bug, missed when that one was
   * fixed. Accepting a `suggest_tasks` card creates real issues from the
   * drafts, and a draft with no assignee produces exactly the same inert task:
   * `todo`, nobody on it, never picked up.
   *
   * Measured after the first fix shipped: a human accepted three proposals on
   * DAE-3 and got DAE-13, DAE-14 and DAE-15, all with `agent=NONE`. Fixing one
   * path and leaving its twin is how a bug survives being fixed.
   */
  it("fills in the proposing agent on drafts that name nobody", async () => {
    const { fn, calls } = http();
    const tools = buildTools(ctx(), fn);

    await tools.run(call("suggest_tasks", {
      tasks: [
        { clientKey: "t1", title: "Post the job on LinkedIn", description: "Why this task exists." },
        { clientKey: "t2", title: "Post the job on AngelList", description: "Why this task exists." },
      ],
    }));

    const tasks = (calls[0].body as { payload: { tasks: Array<Record<string, unknown>> } }).payload.tasks;
    expect(tasks).toHaveLength(2);
    for (const t of tasks) expect(t.assigneeAgentId).toBe("agent_1");
  });

  it("leaves a draft that names its own assignee alone", async () => {
    const { fn, calls } = http();
    const tools = buildTools(ctx(), fn);

    await tools.run(call("suggest_tasks", {
      tasks: [{ clientKey: "t1", title: "Legal review", assigneeAgentId: "agent_legal", description: "Why this task exists." }],
    }));

    const tasks = (calls[0].body as { payload: { tasks: Array<Record<string, unknown>> } }).payload.tasks;
    expect(tasks[0].assigneeAgentId).toBe("agent_legal");
  });

  /** A draft handed to a person is a person's job; do not take it back. */
  it("does not override a draft assigned to a person", async () => {
    const { fn, calls } = http();
    const tools = buildTools(ctx(), fn);

    await tools.run(call("suggest_tasks", {
      tasks: [{ clientKey: "t1", title: "Sign the offer", assigneeUserId: "user_boss", description: "Why this task exists." }],
    }));

    const tasks = (calls[0].body as { payload: { tasks: Array<Record<string, unknown>> } }).payload.tasks;
    expect(tasks[0].assigneeAgentId).toBeUndefined();
    expect(tasks[0].assigneeUserId).toBe("user_boss");
  });
});

describe("a task it creates must be workable", () => {
  /**
   * The agent was blocking on its own work.
   *
   * `create_child_issue` took a title and left the description optional, so the
   * agent produced title-only subtasks — then picked one up a heartbeat later
   * and blocked it, correctly, because a task with no description cannot be
   * worked without guessing. Measured on a real run: 7 of 16 blocked tasks were
   * blocked on descriptions the same agent had failed to write.
   *
   * Refusing at creation is the only place that loop can be cut. The agent
   * knows what it meant when it delegates; it does not a heartbeat later.
   */
  it("refuses to create a subtask with no description", async () => {
    const { fn, calls } = http();
    const tools = buildTools(ctx(), fn);

    const out = await tools.run(call("create_child_issue", { title: "Provision access" }));

    expect(out.ok).toBe(false);
    expect(String(out.result)).toMatch(/description/i);
    expect(calls).toHaveLength(0);
  });

  it("refuses a description that is only whitespace", async () => {
    const { fn, calls } = http();
    const tools = buildTools(ctx(), fn);

    const out = await tools.run(call("create_child_issue", { title: "X", description: "   " }));

    expect(out.ok).toBe(false);
    expect(calls).toHaveLength(0);
  });

  it("creates it when the description says what the work is", async () => {
    const { fn, calls } = http();
    const tools = buildTools(ctx(), fn);

    const out = await tools.run(call("create_child_issue", {
      title: "Provision repository access",
      description: "Grant the new engineer read/write on the two backend repos, and say which ones.",
    }));

    expect(out.ok).toBe(true);
    expect(calls[0].body).toMatchObject({ title: "Provision repository access" });
  });

  /** Same rule where the other half of the work is born. */
  it("refuses a suggested task with no description", async () => {
    const { fn, calls } = http();
    const tools = buildTools(ctx(), fn);

    const out = await tools.run(call("suggest_tasks", {
      tasks: [
        { clientKey: "t1", title: "Set up LinkedIn", description: "Post the role and say where." },
        { clientKey: "t2", title: "Set up AngelList" },
      ],
    }));

    expect(out.ok).toBe(false);
    expect(String(out.result)).toMatch(/Set up AngelList/);
    expect(calls).toHaveLength(0);
  });
});

describe("a child that blocks its parent actually blocks it", () => {
  /**
   * `blocksThisTask` was in the schema and nowhere else — accepted, then
   * silently dropped. So an agent could do everything right and still leave a
   * board that contradicts it.
   *
   * Measured on DAE-27: the agent created DAE-28 to gather the data it was
   * missing, wrote "This child issue is blocking the current task. I will now
   * set this task to blocked", and the board recorded `in_review`. The words
   * and the status disagreed, and only the status is machine-readable — so
   * nothing would ever wake it when DAE-28 finished.
   */
  it("records the new child as a blocker on the parent", async () => {
    const { fn, calls } = http({
      "POST /api/companies/co_1/issues": { status: 200, body: { id: "issue_new", identifier: "DAE-28" } },
    });
    const tools = buildTools(ctx(), fn);

    await tools.run(call("create_child_issue", {
      title: "Collect supplier performance data",
      description: "Pull the last 6 months of delivery and defect records per supplier.",
      blocksThisTask: true,
    }));

    const patch = calls.find((c) => c.method === "PATCH");
    expect(patch, "the parent should have been patched with the blocker").toBeDefined();
    expect(patch?.body).toMatchObject({ blockedByIssueIds: ["issue_new"] });
    expect(tools.state.blockers).toEqual(["issue_new"]);
  });

  it("leaves the parent alone when the child does not block it", async () => {
    const { fn, calls } = http();
    const tools = buildTools(ctx(), fn);

    await tools.run(call("create_child_issue", {
      title: "Nice to have",
      description: "Something that can happen later, in parallel.",
    }));

    expect(calls.filter((c) => c.method === "PATCH")).toHaveLength(0);
    expect(tools.state.blockers).toEqual([]);
  });
});

describe("blocked on what, exactly", () => {
  /**
   * An agent that creates subtasks and then blocks is blocked on those
   * subtasks. Saying so in the comment wakes nothing — only a recorded blocker
   * fires `issue_blockers_resolved`.
   *
   * Measured on the first run after #67, where `blocksThisTask` existed but the
   * model did not reach for it:
   *
   *   DAE-32  blocked  blockedBy=-  "Đã tạo các nhiệm vụ con… Nhiệm vụ này sẽ bị chặn"
   *   DAE-33  blocked  blockedBy=-  "Đã tạo subtask DAE-36… Nhiệm vụ này sẽ bị chặn"
   *
   * Both would have waited forever. The children created in the same run are
   * the only thing the block can mean, so they are what gets recorded.
   */
  it("blocks on the children this run created when the agent names none", async () => {
    const { fn, calls } = http({
      "POST /api/companies/co_1/issues": { status: 200, body: { id: "child_1" } },
    });
    const tools = buildTools(ctx(), fn);

    await tools.run(call("create_child_issue", { title: "Research suppliers", description: "Find three." }));
    await tools.run(call("update_issue", { status: "blocked", comment: "Blocked until the subtask lands." }));

    const patch = calls.filter((c) => c.method === "PATCH").pop();
    expect(patch?.body).toMatchObject({ status: "blocked", blockedByIssueIds: ["child_1"] });
  });

  it("does not overwrite blockers the agent named itself", async () => {
    const { fn, calls } = http({
      "POST /api/companies/co_1/issues": { status: 200, body: { id: "child_1" } },
    });
    const tools = buildTools(ctx(), fn);

    await tools.run(call("create_child_issue", { title: "Side work", description: "Runs in parallel." }));
    await tools.run(call("update_issue", { status: "blocked", blockedByIssueIds: ["other_issue"], comment: "x" }));

    const patch = calls.filter((c) => c.method === "PATCH").pop();
    expect(patch?.body).toMatchObject({ blockedByIssueIds: ["other_issue"] });
  });

  it("leaves a done update alone", async () => {
    const { fn, calls } = http({
      "POST /api/companies/co_1/issues": { status: 200, body: { id: "child_1" } },
    });
    const tools = buildTools(ctx(), fn);

    await tools.run(call("create_child_issue", { title: "Follow-up", description: "Later." }));
    await tools.run(call("update_issue", { status: "done", comment: "Finished." }));

    const patch = calls.filter((c) => c.method === "PATCH").pop();
    expect(patch?.body).not.toHaveProperty("blockedByIssueIds");
  });
});

describe("the shape of a question", () => {
  /**
   * `payload: { type: "object" }` told the model nothing, so it had to guess a
   * shape the server validates strictly — and when it guessed wrong it gave up
   * on asking at all.
   *
   * Measured on the live board, on a task that said in as many words "ask the
   * person what you need to know":
   *
   *   "Bị chặn: Không thể thu thập thông tin dạng văn bản tự do bằng công cụ
   *    ask_user_questions. Vui lòng cung cấp ... trực tiếp trong phần bình luận."
   *
   * The agent was half right — every question does need options — and half
   * wrong: an empty `options` array plus `otherText` is exactly how the card
   * takes free text, which the server accepts and the UI renders. It could not
   * know that from a schema that described nothing.
   */
  it("describes the questions a person will actually see", () => {
    const tools = buildTools(ctx(), http().fn);
    const schema = tools.schemas.find((s) => s.name === "ask_user_questions");
    const payload = (schema?.parameters as any).properties.payload;

    expect(payload.properties.questions).toBeDefined();
    const question = payload.properties.questions.items;
    expect(Object.keys(question.properties)).toEqual(
      expect.arrayContaining(["id", "prompt", "selectionMode", "options"]),
    );
    expect(question.required).toEqual(expect.arrayContaining(["id", "prompt", "selectionMode", "options"]));
  });

  it("says how a person answers something nobody listed", () => {
    const tools = buildTools(ctx(), http().fn);
    const schema = JSON.stringify(tools.schemas.find((s) => s.name === "ask_user_questions"));

    expect(schema).toMatch(/Other/);
    expect(schema).toMatch(/otherText/);
  });

  it("describes what a confirmation actually needs", () => {
    const tools = buildTools(ctx(), http().fn);
    const schema = tools.schemas.find((s) => s.name === "request_confirmation");
    const payload = (schema?.parameters as any).properties.payload;

    expect(payload.properties.prompt).toBeDefined();
    expect(payload.required).toEqual(expect.arrayContaining(["version", "prompt"]));
  });
});

describe("what the free-text case actually is", () => {
  /**
   * The previous fix wrote something false into the schema: "use empty options
   * for a free-text question". The server rejects that outright —
   *
   *   400 {"code":"too_small","minimum":1,"path":["payload","questions",0,"options"]}
   *
   * — so the model followed the instruction and got a 400, then gave up on
   * asking and blocked with a comment, which is the exact behaviour that fix
   * existed to prevent. Measured on LEG-15 after it shipped.
   *
   * The real shape, verified against the live server: at least one option, and
   * the card always renders an "Other" button (OTHER_ANSWER_ID in
   * IssueThreadInteractionCard) so a person can type an answer nobody listed.
   * Free text is never the absence of options; it rides alongside them.
   */
  it("tells the model options are never empty", () => {
    const tools = buildTools(ctx(), http().fn);
    const schema = JSON.stringify(tools.schemas.find((s) => s.name === "ask_user_questions"));

    expect(schema).not.toMatch(/empty options/i);
    expect(schema).toMatch(/Other/);
  });

  it("refuses an empty options array before the server does", async () => {
    const { fn, calls } = http();
    const tools = buildTools(ctx(), fn);

    const out = await tools.run(call("ask_user_questions", {
      payload: { version: 1, questions: [{ id: "q1", prompt: "How long?", selectionMode: "single", options: [] }] },
    }));

    expect(out.ok).toBe(false);
    expect(String(out.result)).toMatch(/at least one/i);
    expect(String(out.result)).toMatch(/Other/);
    expect(calls).toHaveLength(0);
  });

  it("sends a question that names its options", async () => {
    const { fn, calls } = http();
    const tools = buildTools(ctx(), fn);

    const out = await tools.run(call("ask_user_questions", {
      payload: {
        version: 1,
        questions: [
          { id: "term", prompt: "How long?", selectionMode: "single", options: [{ id: "3y", label: "3 years" }] },
        ],
      },
    }));

    expect(out.ok).toBe(true);
    expect(calls).toHaveLength(1);
  });
});
