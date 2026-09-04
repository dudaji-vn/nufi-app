import { describe, expect, it } from "bun:test";

import { runLoop, type LoopModel, type ModelTurn, type ToolBox } from "./loop";

/** A model that replays a fixed script of turns, and records what it was sent. */
function scriptedModel(turns: ModelTurn[]): LoopModel & { seen: unknown[][] } {
  const seen: unknown[][] = [];
  let i = 0;
  return {
    seen,
    async turn(messages) {
      seen.push([...messages]);
      return turns[Math.min(i++, turns.length - 1)];
    },
  };
}

function toolBox(
  handlers: Record<string, (args: unknown) => Promise<unknown> | unknown> = {},
): ToolBox & { calls: string[] } {
  const calls: string[] = [];
  return {
    calls,
    schemas: [{ name: "comment_on_issue", description: "", parameters: { type: "object" } }],
    async run(call) {
      calls.push(call.name);
      const handler = handlers[call.name];
      if (!handler) return { ok: false, result: `unknown tool ${call.name}` };
      return { ok: true, result: await handler(call.arguments) };
    },
  };
}

const text = (t: string): ModelTurn => ({ text: t, toolCalls: [] });
const callFor = (name: string, args: unknown = {}): ModelTurn => ({
  text: "",
  toolCalls: [{ id: `c_${name}`, name, arguments: args }],
});

describe("runLoop", () => {
  it("stops as soon as the model answers without calling a tool", async () => {
    const model = scriptedModel([text("Reviewed. Nothing further.")]);
    const tools = toolBox();

    const out = await runLoop({ model, tools, system: "sys", wake: "wake" });

    expect(out.stopReason).toBe("answered");
    expect(out.text).toBe("Reviewed. Nothing further.");
    expect(tools.calls).toEqual([]);
    expect(out.iterations).toBe(1);
  });

  it("runs a tool call and feeds the result back before the next turn", async () => {
    const model = scriptedModel([callFor("comment_on_issue", { body: "hi" }), text("Commented.")]);
    const tools = toolBox({ comment_on_issue: () => ({ id: "cmt_1" }) });

    const out = await runLoop({ model, tools, system: "sys", wake: "wake" });

    expect(tools.calls).toEqual(["comment_on_issue"]);
    expect(out.stopReason).toBe("answered");
    expect(out.iterations).toBe(2);

    // The second turn must carry the tool's result, or the model is guessing.
    const secondTurn = model.seen[1];
    expect(JSON.stringify(secondTurn)).toContain("cmt_1");
  });

  /**
   * A loop with no cap is a budget leak with a prompt attached. Measured before
   * this design existed: one task collected four full answers in twenty seconds
   * because nothing stopped the adapter re-answering.
   */
  it("stops at the iteration cap when the model never settles", async () => {
    const model = scriptedModel([callFor("comment_on_issue")]);
    const tools = toolBox({ comment_on_issue: () => ({}) });

    const out = await runLoop({ model, tools, system: "sys", wake: "wake", maxIterations: 4 });

    expect(out.stopReason).toBe("iteration_cap");
    expect(out.iterations).toBe(4);
    expect(tools.calls.length).toBe(4);
  });

  /**
   * The execution contract expects an agent to read a 403 or 429 and choose
   * another path. Throwing on the first tool failure takes that choice away and
   * turns a recoverable run into a failed one.
   */
  it("hands a failing tool back to the model instead of ending the run", async () => {
    const model = scriptedModel([callFor("comment_on_issue"), text("Blocked, and I said why.")]);
    const tools: ToolBox & { calls: string[] } = {
      calls: [],
      schemas: [],
      async run(call) {
        this.calls.push(call.name);
        return { ok: false, result: "403 deny_default" };
      },
    };

    const out = await runLoop({ model, tools, system: "sys", wake: "wake" });

    expect(out.stopReason).toBe("answered");
    expect(JSON.stringify(model.seen[1])).toContain("deny_default");
  });

  it("carries several tool calls from one turn", async () => {
    const model = scriptedModel([
      { text: "", toolCalls: [
        { id: "a", name: "comment_on_issue", arguments: {} },
        { id: "b", name: "comment_on_issue", arguments: {} },
      ] },
      text("done"),
    ]);
    const tools = toolBox({ comment_on_issue: () => ({}) });

    const out = await runLoop({ model, tools, system: "sys", wake: "wake" });

    expect(tools.calls).toEqual(["comment_on_issue", "comment_on_issue"]);
    expect(out.iterations).toBe(2);
  });

  it("opens with the system prompt and the wake message, in that order", async () => {
    const model = scriptedModel([text("ok")]);
    await runLoop({ model, tools: toolBox(), system: "SYSTEM_TEXT", wake: "WAKE_TEXT" });

    const first = model.seen[0] as { role: string; content: string }[];
    expect(first[0].role).toBe("system");
    expect(first[0].content).toBe("SYSTEM_TEXT");
    expect(first[1].role).toBe("user");
    expect(first[1].content).toBe("WAKE_TEXT");
  });

  /** Names every tool it touched, so a run can be audited without the transcript. */
  it("reports which tools ran", async () => {
    const model = scriptedModel([callFor("comment_on_issue"), text("done")]);
    const out = await runLoop({ model, tools: toolBox({ comment_on_issue: () => ({}) }), system: "s", wake: "w" });

    expect(out.toolsUsed).toEqual(["comment_on_issue"]);
  });
});
