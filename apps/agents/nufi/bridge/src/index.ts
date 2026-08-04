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

const port = Number(process.env.PORT ?? 8099);
console.log(`nufi agents bridge on :${port}`);

export default { port, fetch: app.fetch };
