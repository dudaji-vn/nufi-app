import { describe, expect, it } from "bun:test";

import { resolveResponsibleUser, runWith, settle, type ExecutionContext } from "./execute";
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

describe("the task briefing", () => {
  /**
   * The heartbeat context is fetched once and used twice — the already-answered
   * guard, and the wake. Letting the agent fetch it instead puts the task text
   * in an `untrusted` span, which G1 refuses on a single detector; LEG-8 died
   * that way, on an ordinary HR leave policy.
   */
  it("hands the agent the task instead of making it fetch one", async () => {
    const calls: HttpCall[] = [];
    const fn = async (call: HttpCall) => {
      calls.push(call);
      if (call.path.endsWith("/heartbeat-context")) {
        return {
          status: 200,
          body: {
            issue: { status: "todo", title: "Review clause 12.2", description: "It voids termination." },
            goal: { title: "Cut vendor risk" },
          },
        };
      }
      return { status: 200, body: {} };
    };

    let seen = "";
    const spy = {
      async turn(messages: { role: string; content: string }[]) {
        seen = messages.map((m) => m.content).join("\n");
        return say("ok");
      },
    };
    await runWith({ http: fn, model: spy }, ctx());

    expect(seen).toContain("Review clause 12.2");
    expect(seen).toContain("It voids termination.");
    expect(seen).toContain("Cut vendor risk");
    // Fetched once for both purposes, not once per purpose.
    expect(calls.filter((c) => c.path.endsWith("/heartbeat-context"))).toHaveLength(1);
  });
});

describe("settling honestly when the model just stops", () => {
  const toolbox = (state: Partial<import("./tools.js").ToolState>) => {
    const seen: any[] = [];
    return {
      seen,
      box: {
        state: { finalStatus: null, commented: false, blockers: [], children: [], ...state },
        run: async (c: any) => { seen.push(c); return { ok: true, result: {} }; },
      } as any,
    };
  };

  /**
   * `in_review` claims a reviewer. When the agent blocked itself behind work it
   * just created, there is no reviewer — there is a dependency, and saying
   * "review" means nothing wakes this task when that dependency lands.
   */
  it("blocks on the children it created rather than claiming a review", async () => {
    const { box, seen } = toolbox({ blockers: ["child_a", "child_b"] });

    const out = await settle(box, "I created a subtask to gather the data.", "completed");

    expect(out).toBe("blocked");
    expect(seen[0].arguments.status).toBe("blocked");
    expect(seen[0].arguments.blockedByIssueIds).toEqual(["child_a", "child_b"]);
  });

  /**
   * A task with nothing written on it is not awaiting review; nobody can review
   * an empty result. Saying so puts it in front of a person instead of parking
   * it in a queue that looks healthy.
   */
  it("does not send an empty result to review", async () => {
    const { box, seen } = toolbox({});

    const out = await settle(box, "   ", "completed");

    expect(out).toBe("blocked");
    expect(String(seen[0].arguments.comment)).toMatch(/without leaving a written result/);
  });

  it("still sends a real written answer to review", async () => {
    const { box, seen } = toolbox({});

    const out = await settle(box, "Here are the four suppliers at risk, and why.", "completed");

    expect(out).toBe("in_review");
    expect(seen[0].arguments.status).toBe("in_review");
  });
});

describe("a run that delegated and stopped is waiting on the delegate", () => {
  const toolbox = (state: Partial<import("./tools.js").ToolState>) => {
    const seen: any[] = [];
    return {
      seen,
      box: {
        state: { finalStatus: null, commented: false, blockers: [], children: [], ...state },
        run: async (c: any) => { seen.push(c); return { ok: true, result: {} }; },
      } as any,
    };
  };

  /**
   * Measured on DAE-30: "Task claimed. Created subtask DAE-33 to research
   * alternative steel suppliers" — and the board said `in_review`, with nobody
   * reviewing and no blocker. The child it just created is the thing it is
   * waiting for, whether or not it thought to say so.
   */
  it("blocks on children it created rather than claiming a review", async () => {
    const { box, seen } = toolbox({ children: ["child_1"] });

    const out = await settle(box, "Created a subtask to research suppliers.", "completed");

    expect(out).toBe("blocked");
    expect(seen[0].arguments.blockedByIssueIds).toEqual(["child_1"]);
  });

  it("still reviews a written answer that delegated nothing", async () => {
    const { box } = toolbox({});
    expect(await settle(box, "Here is the answer.", "completed")).toBe("in_review");
  });
});

describe("a person answering is new work, even mid-review", () => {
  /**
   * The guard that stops an agent re-answering a task it already answered was
   * unconditional on `in_review` — and that is exactly the status a task sits
   * in while it waits for a person.
   *
   * So the headline flow died silently: the agent asks a question, the person
   * answers, the server wakes the assignee with `reason: "issue_commented"`
   * (routes/issues.ts, on every interaction response), and the adapter replied
   * "Idle — already answered, waiting on review". The answer was dropped.
   *
   * Paperclip's own contract says the opposite: "issue_commented with
   * PAPERCLIP_WAKE_COMMENT_ID → read the comment, then checkout and address the
   * feedback (applies to in_review too)".
   *
   * The guard still holds for what it was built for: a plain re-dispatch of a
   * task nobody has touched.
   */
  it("works a reviewed task when a comment triggered the wake", async () => {
    const { fn, patches } = api({ status: "in_review" });

    const out = await runWith(
      { http: fn, model: model([use("update_issue", { status: "done", comment: "Thanks — done." })]) },
      ctx({ context: { taskId: "issue_1", wakeReason: "issue_commented", wakeCommentId: "comment_9" } }),
    );

    expect(out.summary).not.toMatch(/already answered/i);
    expect(patches()[0]).toMatchObject({ status: "done" });
  });

  it("works a reviewed task when an approval triggered the wake", async () => {
    const { fn, patches } = api({ status: "in_review" });

    const out = await runWith(
      { http: fn, model: model([use("update_issue", { status: "done", comment: "Approved — proceeding." })]) },
      ctx({ context: { taskId: "issue_1", wakeReason: "issue_commented", approvalId: "appr_1" } }),
    );

    expect(patches()[0]).toMatchObject({ status: "done" });
  });

  it("still refuses a plain re-dispatch of a task nobody touched", async () => {
    const { fn, patches } = api({ status: "in_review" });

    const out = await runWith(
      { http: fn, model: model([say("more thoughts")]) },
      ctx({ context: { taskId: "issue_1", wakeReason: "heartbeat_timer" } }),
    );

    expect(out.summary).toMatch(/already answered/i);
    expect(patches()).toHaveLength(0);
  });
});

describe("waking on a person's answer", () => {
  /**
   * The wake payload names the interaction (`interactionId` in the context
   * snapshot, set by routes/issues.ts on every response) but carries neither
   * the question nor the answer. Reading it here is what closes
   * "ask → answer → continue": without it the agent wakes, finds no comment,
   * and asks again.
   */
  it("reads the interaction named by the wake and briefs the agent with it", async () => {
    const seen: string[] = [];
    const fn = async (call: any) => {
      seen.push(`${call.method} ${call.path}`);
      if (call.path.endsWith("/heartbeat-context")) {
        return { status: 200, body: { issue: { status: "in_review", title: "Buy the laptop", description: "" } } };
      }
      if (call.path.endsWith("/interactions")) {
        return {
          status: 200,
          body: [
            { id: "other", kind: "suggest_tasks", status: "pending", result: null },
            {
              id: "int_1",
              kind: "ask_user_questions",
              status: "answered",
              title: "Procurement details needed",
              result: { laptop: "MacBook Pro 14" },
            },
          ],
        };
      }
      return { status: 200, body: { ok: true } };
    };

    let wakeText = "";
    await runWith(
      {
        http: fn,
        model: {
          async turn(messages: any) {
            wakeText = JSON.stringify(messages);
            return { text: "done", toolCalls: [] };
          },
        } as any,
      },
      ctx({ context: { taskId: "issue_1", wakeReason: "issue_commented", interactionId: "int_1" } }),
    );

    expect(seen).toContain("GET /api/issues/issue_1/interactions");
    expect(wakeText).toContain("MacBook Pro 14");
    expect(wakeText).toContain("Procurement details needed");
  });

  it("does not fetch interactions when the wake names none", async () => {
    const seen: string[] = [];
    const { fn } = api();
    const wrapped = async (call: any) => { seen.push(call.path); return fn(call); };

    await runWith({ http: wrapped, model: model([say("ok")]) }, ctx());

    expect(seen.some((p) => p.endsWith("/interactions"))).toBe(false);
  });
});

describe("a question waiting on a person is a review path", () => {
  const toolbox = (state: Partial<import("./tools.js").ToolState>) => {
    const seen: any[] = [];
    return {
      seen,
      box: {
        state: { finalStatus: null, commented: false, blockers: [], children: [], asked: false, ...state },
        run: async (c: any) => { seen.push(c); return { ok: true, result: {} }; },
      } as any,
    };
  };

  /**
   * Paperclip is explicit: "If your heartbeat creates a pending board/user
   * interaction ... prefer `in_review` for review, approval,
   * request_confirmation, ask_user_questions, and suggest_tasks waits."
   *
   * The empty-result rule from the previous fix would otherwise block a
   * heartbeat whose whole point was to put a question in front of a person —
   * the card sits pending while the task reads as stuck.
   */
  it("reviews when it left a question pending, even with nothing written", async () => {
    const { box, seen } = toolbox({ asked: true });

    const out = await settle(box, "   ", "completed");

    expect(out).toBe("in_review");
    expect(seen[0].arguments.status).toBe("in_review");
  });

  it("still blocks an empty run that asked nobody anything", async () => {
    const { box } = toolbox({});
    expect(await settle(box, "  ", "completed")).toBe("blocked");
  });

  it("a delegated blocker still outranks a pending question", async () => {
    const { box } = toolbox({ asked: true, children: ["child_1"] });
    expect(await settle(box, "", "completed")).toBe("blocked");
  });
});
