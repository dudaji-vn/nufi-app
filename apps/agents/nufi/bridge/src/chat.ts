const CHAT_URL = process.env.NUFI_CHAT_URL ?? "http://localhost:3080";
const CHAT_KEY = process.env.NUFI_CHAT_API_KEY ?? "";
const AGENT_ID = process.env.NUFI_CHAT_AGENT_ID ?? "";

/**
 * apps/chat exposes an OpenAI-compatible agent endpoint, so the NuFi agent is
 * addressed as `model`. The call goes to our own service, which routes to the
 * LiteLLM gateway — the whole reason this bridge exists rather than pointing
 * Paperclip at a vendor.
 */
export const chat = {
  async complete(prompt: string) {
    if (!CHAT_KEY) throw new Error("NUFI_CHAT_API_KEY is not set");
    if (!AGENT_ID) throw new Error("NUFI_CHAT_AGENT_ID is not set");

    const res = await fetch(`${CHAT_URL}/api/agents/chat/completions`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        authorization: `Bearer ${CHAT_KEY}`,
      },
      body: JSON.stringify({
        model: AGENT_ID,
        messages: [{ role: "user", content: prompt }],
        stream: false,
      }),
    });
    if (!res.ok) throw new Error(`chat ${res.status}: ${await res.text()}`);

    const data = (await res.json()) as { choices?: { message?: { content?: string } }[] };
    const content = data.choices?.[0]?.message?.content;
    if (!content) throw new Error("chat returned no content");
    return content;
  },
};
