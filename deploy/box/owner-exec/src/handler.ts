// Privileged exec handler. Argv is built ONLY by the shared exec-core allowlist
// (single source of truth, also used by the owner-console); no shell, no raw input.
import { Hono } from 'hono';

import {
  applyConfigToYaml,
  auditLine,
  BadRequest,
  BOX_SERVICE,
  buildBoxContainerArgv,
  buildControlArgv,
  buildListContainersArgv,
  buildReadArgv,
  buildReconfigureArgv,
  buildRemoteWorkArgv,
  buildRemoteWorkStatusArgv,
  configViewFromYaml,
  validateConfigPatch,
} from '../../owner-console/src/exec-core';

export interface ExecDeps {
  spawn: typeof Bun.spawn;
  auditAppend: (line: string) => void; // must throw on failure: unaudited = not run
  now: () => Date;
  // litellm/config.yaml, bind-mounted read-WRITE at its OWN path (NOT nested
  // under the read-only /box mount — a RW file inside a RO bind mount is EROFS).
  // It is the ONLY file this layer writes; .env holds the box's secrets and is
  // mounted nowhere.
  configPath: string;
  readFile: (path: string) => string;
  writeFile: (path: string, data: string) => void;
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
    const a = String(action);

    // Whole-box: act on the project's containers directly, so a STOP/RESTART
    // keeps the console plane (caddy + owner-console + owner-exec) running and
    // the UI can still turn the box back on. START brings everything back.
    if (service === BOX_SERVICE) {
      const listProc = deps.spawn({ cmd: buildListContainersArgv(a !== 'start'), stdout: 'pipe', stderr: 'ignore' });
      const names = (await new Response(listProc.stdout as ReadableStream<Uint8Array>).text().catch(() => '')).split('\n');
      await listProc.exited;
      const argv = buildBoxContainerArgv(a, names); // throws BadRequest on a bad action
      const line = audit(a, BOX_SERVICE);
      if (argv.length <= 2) return c.json({ ok: true, audit: line }); // nothing to act on
      const proc = deps.spawn({ cmd: argv, stdout: 'ignore', stderr: 'ignore' });
      const code = await proc.exited;
      return c.json({ ok: code === 0, audit: line });
    }

    const argv = buildControlArgv(a, String(service)); // throws BadRequest
    const line = audit(a, String(service));
    const proc = deps.spawn({ cmd: argv, stdout: 'ignore', stderr: 'ignore' });
    const code = await proc.exited;
    return c.json({ ok: code === 0, audit: line });
  });

  // The real remote-work state: is the tailscale container running? (Read-only.)
  app.get('/remote-work', async (c) => {
    const proc = deps.spawn({ cmd: buildRemoteWorkStatusArgv(), stdout: 'pipe', stderr: 'ignore' });
    const out = await new Response(proc.stdout as ReadableStream<Uint8Array>).text().catch(() => '');
    const code = await proc.exited;
    return c.json({ on: code === 0 && out.trim() === 'true' });
  });

  // "Allow remote work" toggle: start/stop the tailscale (mesh) container by
  // name. No shell, no input beyond a boolean; the argv is fixed by exec-core.
  app.post('/remote-work', async (c) => {
    const { on } = await body(c);
    const argv = buildRemoteWorkArgv(on === true); // throws BadRequest if not boolean-ish → here always boolean
    const line = audit(on === true ? 'remote-work on' : 'remote-work off');
    const proc = deps.spawn({ cmd: argv, stdout: 'ignore', stderr: 'ignore' });
    const code = await proc.exited;
    return c.json({ ok: code === 0, audit: line });
  });

  // Read the live model endpoint (AI Base Location + Model Name) from the one
  // box config file that is not .env: litellm/config.yaml.
  app.get('/config', (c) => {
    const yaml = deps.readFile(deps.configPath);
    return c.json(configViewFromYaml(yaml));
  });

  // Apply the Config modal: rewrite the model + api_base in litellm/config.yaml
  // and restart litellm-proxy so it re-reads the mounted file. .env is never
  // touched (it is mounted into nothing).
  app.post('/reconfigure', async (c) => {
    const patch = validateConfigPatch(await body(c)); // throws BadRequest
    const updated = applyConfigToYaml(deps.readFile(deps.configPath), patch); // throws BadRequest if unrecognised
    const line = audit('reconfigure');
    deps.writeFile(deps.configPath, updated);
    const proc = deps.spawn({ cmd: buildReconfigureArgv(), stdout: 'ignore', stderr: 'ignore' });
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
