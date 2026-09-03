/**
 * The heartbeat loop.
 *
 * Paperclip agents are not one-shot answerers. They wake into a short execution
 * window, work the procedure, and exit having left the issue somewhere a person
 * or another agent can pick up. This module is that window: model turn, tool
 * calls, model turn, until the model stops asking for tools.
 *
 * Everything here is injected. The loop never opens a socket, never reads the
 * clock, and never knows which model it is driving — which is what lets the
 * tests drive it with a scripted model and assert on what the model was shown.
 */

/** One tool the model may call. JSON Schema, as both gateway shapes expect. */
export interface ToolSchema {
  name: string;
  description: string;
  parameters: Record<string, unknown>;
}

export interface ToolCall {
  /** Correlation id from the model. Tool results must quote it back. */
  id: string;
  name: string;
  arguments: unknown;
}

export interface ModelTurn {
  text: string;
  toolCalls: ToolCall[];
}

export interface Message {
  role: "system" | "user" | "assistant" | "tool";
  content: string;
  tool_calls?: { id: string; type: "function"; function: { name: string; arguments: string } }[];
  tool_call_id?: string;
}

export interface LoopModel {
  turn(messages: Message[], tools: ToolSchema[]): Promise<ModelTurn>;
}

export interface ToolBox {
  schemas: ToolSchema[];
  /**
   * Never throws for a tool-level failure. A 403 or a 429 is information the
   * agent is expected to act on — the execution contract says read it and take
   * another path — so it comes back as a result the model can see.
   */
  run(call: ToolCall): Promise<{ ok: boolean; result: unknown }>;
}

export type StopReason = "answered" | "iteration_cap";

export interface LoopOutcome {
  text: string;
  stopReason: StopReason;
  iterations: number;
  /** Distinct tool names touched, so a run is auditable without the transcript. */
  toolsUsed: string[];
  messages: Message[];
}

/**
 * Twelve is not a magic number, it is a budget.
 *
 * An unbounded loop is a budget leak with a prompt attached. Before any of this
 * existed, an adapter with no stop condition let one task collect four full
 * answers in twenty seconds, and a human could not close it — every attempt was
 * undone by the next run within ten seconds. Twelve is enough for
 * checkout → context → work → comment → status → delegate with room to recover
 * from a couple of tool errors, and short enough that a confused model costs
 * cents rather than the month's budget.
 */
const DEFAULT_MAX_ITERATIONS = 12;

function serialise(value: unknown): string {
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value ?? null);
  } catch {
    return String(value);
  }
}

export async function runLoop(input: {
  model: LoopModel;
  tools: ToolBox;
  system: string;
  wake: string;
  maxIterations?: number;
}): Promise<LoopOutcome> {
  const maxIterations = input.maxIterations ?? DEFAULT_MAX_ITERATIONS;
  const messages: Message[] = [
    { role: "system", content: input.system },
    { role: "user", content: input.wake },
  ];
  const toolsUsed: string[] = [];
  let iterations = 0;
  let text = "";

  while (iterations < maxIterations) {
    iterations += 1;
    const turn = await input.model.turn(messages, input.tools.schemas);
    text = turn.text || text;

    if (turn.toolCalls.length === 0) {
      messages.push({ role: "assistant", content: turn.text });
      return { text, stopReason: "answered", iterations, toolsUsed, messages };
    }

    messages.push({
      role: "assistant",
      content: turn.text,
      tool_calls: turn.toolCalls.map((call) => ({
        id: call.id,
        type: "function" as const,
        function: { name: call.name, arguments: serialise(call.arguments) },
      })),
    });

    for (const call of turn.toolCalls) {
      if (!toolsUsed.includes(call.name)) toolsUsed.push(call.name);
      const outcome = await input.tools.run(call);
      /**
       * The result is tagged rather than just serialised. A model that cannot
       * tell a refusal from an empty success will happily report the work as
       * done — which is the exact failure this whole design exists to prevent.
       */
      messages.push({
        role: "tool",
        tool_call_id: call.id,
        content: serialise(
          outcome.ok ? { ok: true, result: outcome.result } : { ok: false, error: outcome.result },
        ),
      });
    }
  }

  return { text, stopReason: "iteration_cap", iterations, toolsUsed, messages };
}
