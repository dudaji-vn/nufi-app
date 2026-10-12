// Thin client of the owner-exec sidecar. The console no longer spawns anything:
// it pre-validates against the shared allowlist (defense in depth; the sidecar
// re-validates and owns spawn + audit) and calls the sidecar over a unix socket.
import {
  type Action,
  type ConfigView,
  BadRequest,
  BOX_SERVICE,
  buildBoxArgv,
  buildControlArgv,
  buildReadArgv,
  buildRemoteWorkArgv,
  validateConfigPatch,
} from './exec-core';

export * from './exec-core';

type FetchImpl = (url: string, init?: Record<string, unknown>) => Promise<Response>;

export interface ExecDeps {
  fetchImpl: FetchImpl;
  sock: string;
}

const defaultDeps = (): ExecDeps => ({
  fetchImpl: fetch as unknown as FetchImpl,
  sock: process.env.EXEC_SOCK || '/sock/exec.sock',
});

async function call(deps: ExecDeps, path: string, body: unknown): Promise<Response> {
  const res = await deps.fetchImpl(`http://x${path}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
    unix: deps.sock,
  });
  if (res.status === 400) {
    const j = (await res.json().catch(() => ({}))) as { error?: string };
    throw new BadRequest(j.error || 'bad request');
  }
  if (!res.ok) {
    const j = (await res.json().catch(() => ({}))) as { error?: string };
    throw new Error(j.error || `exec sidecar error (${res.status})`);
  }
  return res;
}

export async function controlService(
  action: Action,
  service: string,
  deps: ExecDeps = defaultDeps(),
): Promise<{ ok: boolean; audit: string }> {
  if (service === BOX_SERVICE) return controlBox(action, deps);
  buildControlArgv(action, service); // pre-validate; throws BadRequest before any fetch
  const res = await call(deps, '/control', { action, service });
  return (await res.json()) as { ok: boolean; audit: string };
}

export async function controlBox(
  action: Action | string,
  deps: ExecDeps = defaultDeps(),
): Promise<{ ok: boolean; audit: string }> {
  buildBoxArgv(action); // pre-validate; throws BadRequest before any fetch
  const res = await call(deps, '/control', { action, service: BOX_SERVICE });
  return (await res.json()) as { ok: boolean; audit: string };
}

// "Allow remote work" toggle: start/stop the box's tailscale (mesh) container.
export async function setRemoteWork(
  on: boolean,
  deps: ExecDeps = defaultDeps(),
): Promise<{ ok: boolean; audit: string }> {
  buildRemoteWorkArgv(on); // pre-validate; throws BadRequest before any fetch
  const res = await call(deps, '/remote-work', { on });
  return (await res.json()) as { ok: boolean; audit: string };
}

// The real remote-work state (is the mesh container running), read from the
// sidecar — unlike mesh.joined, which is only what .env held at container start.
export async function readRemoteWork(deps: ExecDeps = defaultDeps()): Promise<{ on: boolean }> {
  const res = await deps.fetchImpl('http://x/remote-work', { method: 'GET', unix: deps.sock });
  if (!res.ok) throw new Error(`exec sidecar error (${res.status})`);
  return (await res.json()) as { on: boolean };
}

export async function readConfig(deps: ExecDeps = defaultDeps()): Promise<ConfigView> {
  const res = await deps.fetchImpl('http://x/config', { method: 'GET', unix: deps.sock });
  if (!res.ok) throw new Error(`exec sidecar error (${res.status})`);
  return (await res.json()) as ConfigView;
}

export async function applyConfig(
  patch: unknown,
  deps: ExecDeps = defaultDeps(),
): Promise<{ ok: boolean; audit: string }> {
  const validated = validateConfigPatch(patch); // pre-validate; throws BadRequest before any fetch
  const res = await call(deps, '/reconfigure', validated);
  return (await res.json()) as { ok: boolean; audit: string };
}

export async function* runReadCommand(cmd: string, deps: ExecDeps = defaultDeps()): AsyncGenerator<string> {
  buildReadArgv(cmd); // pre-validate the WHOLE string
  const res = await call(deps, '/run', { cmd });
  if (!res.body) return;
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = '';
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      const parts = buf.split('\n');
      buf = parts.pop() ?? '';
      for (const p of parts) yield p;
    }
    buf += dec.decode();
    if (buf) yield buf;
  } finally {
    reader.releaseLock();
  }
}
