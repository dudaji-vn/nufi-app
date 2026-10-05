import { Hono } from 'hono';
import { streamSSE } from 'hono/streaming';
import { BadRequest, BOX_SERVICE, controlService, runReadCommand } from '../exec';

// Injectable so the routes are tested without touching docker.
export interface ControlDeps {
  controlService: typeof controlService;
  runReadCommand: typeof runReadCommand;
}

const real: ControlDeps = { controlService, runReadCommand };

const message = (e: unknown): string => (e instanceof Error ? e.message : 'command failed');

// Mounted behind the /api/* owner-auth middleware; allowlisting lives in exec.ts.
export function controlRoutes(deps: Partial<ControlDeps> = {}): Hono {
  const d = { ...real, ...deps };
  const r = new Hono();

  r.post('/control', async (c) => {
    const body = (await c.req.json().catch(() => ({}))) as { action?: unknown; service?: unknown; scope?: unknown };
    try {
      const service = body.scope === 'box' ? BOX_SERVICE : (body.service as string);
      const res = await d.controlService(body.action as never, service);
      return c.json(res);
    } catch (e) {
      if (e instanceof BadRequest) return c.json({ error: e.message }, 400);
      return c.json({ error: message(e) }, 500);
    }
  });

  r.post('/console', async (c) => {
    const body = (await c.req.json().catch(() => ({}))) as { cmd?: unknown };
    const gen = d.runReadCommand(String(body.cmd ?? ''));
    // Pull the first line before opening the stream so a bad cmd is a real 400.
    let first: IteratorResult<string>;
    try {
      first = await gen.next();
    } catch (e) {
      if (e instanceof BadRequest) return c.json({ error: e.message }, 400);
      return c.json({ error: message(e) }, 500);
    }
    return streamSSE(c, async (stream) => {
      try {
        let cur = first;
        while (!cur.done) {
          await stream.writeSSE({ data: cur.value });
          cur = await gen.next();
        }
      } catch (e) {
        await stream.writeSSE({ event: 'error', data: message(e) });
      }
    });
  });

  return r;
}
