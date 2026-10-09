import { Hono } from 'hono';
import { applyConfig, BadRequest, readConfig } from '../exec';

// Injectable so the routes are tested without touching the sidecar/socket.
export interface ConfigDeps {
  readConfig: typeof readConfig;
  applyConfig: typeof applyConfig;
}

const real: ConfigDeps = { readConfig, applyConfig };

const message = (e: unknown): string => (e instanceof Error ? e.message : 'request failed');

// Mounted behind the /api/* owner-auth middleware. The validation + the writes
// live in the sidecar (exec-core allowlist); this is a thin pass-through.
export function configRoutes(deps: Partial<ConfigDeps> = {}): Hono {
  const d = { ...real, ...deps };
  const r = new Hono();

  r.get('/config', async (c) => {
    try {
      return c.json(await d.readConfig());
    } catch (e) {
      return c.json({ error: message(e) }, 500);
    }
  });

  r.post('/config', async (c) => {
    const patch = await c.req.json().catch(() => ({}));
    try {
      return c.json(await d.applyConfig(patch));
    } catch (e) {
      if (e instanceof BadRequest) return c.json({ error: e.message }, 400);
      return c.json({ error: message(e) }, 500);
    }
  });

  return r;
}
