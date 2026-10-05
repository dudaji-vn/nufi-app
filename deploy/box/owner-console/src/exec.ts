// Allowlisted, audited exec layer. The ONLY place the console runs host commands.
// Security model: every command is an argv array handed to Bun.spawn (no shell),
// and every variable part (action, service, cmd) must be an EXACT member of a
// constant allowlist before anything is built or run.
import { appendFileSync, mkdirSync } from 'node:fs';
import { join } from 'node:path';

import { type Action, auditLine, buildControlArgv, buildReadArgv } from './exec-core';

export * from './exec-core';

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

// Appends and throws on failure: an action that cannot be audited is not run.
function audit(deps: ExecDeps, what: string, service?: string): string {
  const line = auditLine(deps.now(), what, service);
  mkdirSync(deps.stateDir, { recursive: true });
  appendFileSync(join(deps.stateDir, 'audit.log'), line + '\n');
  return line;
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
