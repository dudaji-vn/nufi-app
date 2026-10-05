// Privileged exec handler. Argv is built ONLY by the shared exec-core allowlist
// (single source of truth, also used by the owner-console); no shell, no raw input.
import { Hono } from 'hono';

import { auditLine, BadRequest, BOX_SERVICE, buildBoxArgv, buildControlArgv, buildReadArgv } from '../../owner-console/src/exec-core';

export interface ExecDeps {
  spawn: typeof Bun.spawn;
  auditAppend: (line: string) => void; // must throw on failure: unaudited = not run
  now: () => Date;
}

const INFO = (cmd: string) =>
  `"${cmd}" runs from the box's command line (nufi-box ${cmd}); the in-console version ships with the hardening sidecar.\n`;

export function createApp(deps: ExecDeps): Hono {
  const app = new Hono();

  const body = async (c: { req: { json: () => Promise<unknown> } }): Promise<Record<string, unknown>> => {
    try {
      const b = await c.req.json();
      return b && typeof b === 'object' ? (b as Record<string, unknown>) : {};
    } catch {
      return {};
    }
  };

  // Audit BEFORE spawning; a failed audit write aborts (throws -> 500).
  const audit = (what: string, service?: string): string => {
    const line = auditLine(deps.now(), what, service);
    deps.auditAppend(line);
    return line;
  };

  app.onError((err, c) => {
    if (err instanceof BadRequest) return c.json({ error: err.message }, 400);
    return c.json({ error: 'exec failed' }, 500);
  });

  app.post('/control', async (c) => {
    const { action, service } = await body(c);
    const whole = service === undefined || service === null || service === BOX_SERVICE;
    const argv = whole ? buildBoxArgv(String(action)) : buildControlArgv(String(action), String(service)); // throws BadRequest
    const line = audit(String(action), whole ? BOX_SERVICE : String(service));
    const proc = deps.spawn({ cmd: argv, stdout: 'ignore', stderr: 'ignore' });
    const code = await proc.exited;
    return c.json({ ok: code === 0, audit: line });
  });

  app.post('/run', async (c) => {
    const { cmd } = await body(c);
    const name = String(cmd);
    const argv = buildReadArgv(name); // throws BadRequest
    audit(name);
    if (!argv) return new Response(INFO(name), { headers: { 'content-type': 'text/plain; charset=utf-8' } });
    const proc = deps.spawn({ cmd: argv, stdout: 'pipe', stderr: 'ignore' });
    const out = proc.stdout as ReadableStream<Uint8Array>;
    // Stream raw bytes; reap the process once the stream finishes.
    void proc.exited;
    return new Response(out, { headers: { 'content-type': 'text/plain; charset=utf-8', 'cache-control': 'no-store' } });
  });

  return app;
}
