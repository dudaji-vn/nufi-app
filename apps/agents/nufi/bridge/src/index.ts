import { Hono } from "hono";

import { chat } from "./chat";
import { paperclip } from "./paperclip";
import { handleRun, type RunPayload } from "./run";

const app = new Hono();

app.get("/health", (c) => c.json({ ok: true }));

app.post("/run", async (c) => {
  const payload = (await c.req.json()) as RunPayload;
  const outcome = await handleRun({ paperclip, chat }, payload);
  return c.json(outcome, outcome.status === "failed" ? 500 : 200);
});

/**
 * Deliberately NOT `PORT`. The bridge is run with apps/agents/.env sourced so it
 * can share PAPERCLIP_API_URL and the model key, and that file sets PORT=3100 —
 * the Paperclip server's own port. Reading PORT here makes the bridge try to
 * bind the port the server already holds.
 */
const port = Number(process.env.BRIDGE_PORT ?? 8099);
console.log(`nufi agents bridge on :${port}`);

export default { port, fetch: app.fetch };
