/**
 * The model client. Two targets, same OpenAI-compatible shape.
 *
 *   NUFI_TARGET=gateway  → the LiteLLM gateway directly (default)
 *   NUFI_TARGET=chat     → apps/chat's agent endpoint
 *
 * The spike defaults to the gateway because that is the smaller dependency:
 * it needs one key, where the chat route needs the whole chat stack running
 * (MongoDB, Meilisearch, an agent already created).
 *
 * WHAT THAT COSTS: pointing at the gateway tests Paperclip's product model —
 * whether goals, tasks, checkout and approvals suit the way NuFi's users work.
 * It does NOT test a NuFi chat agent's own capabilities: no RAG over company
 * documents, no tools, no MCP. Those ride on the chat route. Read the spike
 * findings with that limit in mind; a good result here means the management
 * model fits, not that the agent is good.
 *
 * Either way the call lands on api.codechi.me, so the guardrails see it.
 */

type Target = "gateway" | "chat";

const TARGET = (process.env.NUFI_TARGET ?? "gateway") as Target;

const GATEWAY_URL = process.env.NUFI_GATEWAY_URL ?? "https://api.codechi.me/v1";
const GATEWAY_MODEL = process.env.NUFI_GATEWAY_MODEL ?? "gemini";

const CHAT_URL = process.env.NUFI_CHAT_URL ?? "http://localhost:3080";
const CHAT_AGENT_ID = process.env.NUFI_CHAT_AGENT_ID ?? "";

const KEY = process.env.NUFI_MODEL_API_KEY ?? "";

/**
 * Generous by default. Gemini spends its reasoning budget before emitting any
 * text — measured, a 20-token cap returned `content: ""` with 15 of those
 * tokens going to reasoning, and no error. A too-small cap looks like an empty
 * answer rather than a truncation, which is the worst way for this to fail.
 */
const MAX_TOKENS = Number(process.env.NUFI_MAX_TOKENS ?? 4096);

function endpoint() {
  return TARGET === "chat"
    ? `${CHAT_URL}/api/agents/chat/completions`
    : `${GATEWAY_URL}/chat/completions`;
}

function model() {
  return TARGET === "chat" ? CHAT_AGENT_ID : GATEWAY_MODEL;
}

export const chat = {
  async complete(prompt: string) {
    if (!KEY) throw new Error("NUFI_MODEL_API_KEY is not set");
    if (TARGET === "chat" && !CHAT_AGENT_ID) {
      throw new Error("NUFI_TARGET=chat requires NUFI_CHAT_AGENT_ID");
    }

    const res = await fetch(endpoint(), {
      method: "POST",
      headers: {
        "content-type": "application/json",
        authorization: `Bearer ${KEY}`,
      },
      body: JSON.stringify({
        model: model(),
        messages: [{ role: "user", content: prompt }],
        max_tokens: MAX_TOKENS,
        stream: false,
      }),
    });
    if (!res.ok) throw new Error(`${TARGET} ${res.status}: ${(await res.text()).slice(0, 300)}`);

    const data = (await res.json()) as { choices?: { message?: { content?: string } }[] };
    const content = data.choices?.[0]?.message?.content;
    if (!content) {
      throw new Error(
        `${TARGET} returned no content — if max_tokens is small the reasoning budget can consume it all`,
      );
    }
    return content;
  },
};
