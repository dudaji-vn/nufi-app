// Allowlisted, audited exec layer. The ONLY place the console runs host commands.
// Security model: every command is an argv array handed to Bun.spawn (no shell),
// and every variable part (action, service, cmd) must be an EXACT member of a
// constant allowlist before anything is built or run.
import { appendFileSync, mkdirSync } from 'node:fs';
import { join } from 'node:path';

export const SERVICES = ['librechat', 'litellm-proxy', 'rag_api', 'ollama', 'caddy', 'mongodb', 'postgres', 'studio'] as const;
export const READ_CMDS = ['status', 'logs', 'logs librechat', 'doctor', 'support'] as const;
const ACTIONS = ['start', 'restart', 'stop'] as const;

export type Action = (typeof ACTIONS)[number];

export class BadRequest extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'BadRequest';
  }
}

export interface ExecDeps {
  spawn: typeof Bun.spawn;
  stateDir: string;
  now: () => Date;
}

const defaultDeps = (): ExecDeps => ({
  spawn: Bun.spawn,
  stateDir: process.env.NUFI_STATE_DIR || '/state',
  now: () => new Date(),
});

const COMPOSE = ['docker', 'compose', '-p', 'nufi-box'] as const;

const isIn = <T extends readonly string[]>(set: T, v: unknown): v is T[number] =>
  typeof v === 'string' && set.includes(v);

// Appends and throws on failure: an action that cannot be audited is not run.
function audit(deps: ExecDeps, what: string, service?: string): string {
  const line = [deps.now().toISOString(), what, ...(service ? [service] : [])].join(' · ');
  mkdirSync(deps.stateDir, { recursive: true });
  appendFileSync(join(deps.stateDir, 'audit.log'), line + '\n');
  return line;
}

export function buildControlArgv(action: string, service: string): string[] {
  if (!isIn(ACTIONS, action)) throw new BadRequest('invalid action');
  if (!isIn(SERVICES, service)) throw new BadRequest('invalid service');
  return [...COMPOSE, action, service];
}

export function buildReadArgv(cmd: string): string[] | null {
  if (!isIn(READ_CMDS, cmd)) throw new BadRequest('invalid command');
  switch (cmd) {
    case 'status':
      return [...COMPOSE, 'ps'];
    case 'logs':
      return [...COMPOSE, 'logs', '--no-color', '--tail=200'];
    case 'logs librechat':
      return [...COMPOSE, 'logs', '--no-color', '--tail=200', 'librechat'];
    default:
      return null; // doctor / support: informational only, never executed
  }
}

export async function controlService(
  action: Action,
  service: string,
  deps: ExecDeps = defaultDeps(),
): Promise<{ ok: boolean; audit: string }> {
  const argv = buildControlArgv(action, service); // validates first
  const line = audit(deps, action, service); // audited before execution
  const proc = deps.spawn({ cmd: argv, stdout: 'ignore', stderr: 'ignore' });
  const code = await proc.exited;
  return { ok: code === 0, audit: line };
}

export async function* runReadCommand(cmd: string, deps: ExecDeps = defaultDeps()): AsyncGenerator<string> {
  const argv = buildReadArgv(cmd); // validates the WHOLE string first
  audit(deps, cmd);
  if (!argv) {
    yield `"${cmd}" runs from the box's command line (nufi-box ${cmd}); the in-console version ships with the hardening sidecar.`;
    return;
  }
  const proc = deps.spawn({ cmd: argv, stdout: 'pipe', stderr: 'ignore' });
  const reader = (proc.stdout as ReadableStream<Uint8Array>).getReader();
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
    await proc.exited;
  }
}
