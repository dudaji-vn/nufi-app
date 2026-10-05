import { describe, expect, test } from 'bun:test';
import { mkdtempSync, readFileSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import {
  BadRequest,
  READ_CMDS,
  SERVICES,
  controlService,
  runReadCommand,
  type ExecDeps,
} from '../src/exec';

const mk = (stdout = '', exitCode = 0) => {
  const dir = mkdtempSync(join(tmpdir(), 'exec-'));
  const calls: string[][] = [];
  const auditAtSpawn: (string | null)[] = [];
  const deps: ExecDeps = {
    stateDir: dir,
    now: () => new Date('2026-10-05T01:02:03.000Z'),
    spawn: ((opts: { cmd: string[] }) => {
      calls.push(opts.cmd);
      const f = join(dir, 'audit.log');
      auditAtSpawn.push(existsSync(f) ? readFileSync(f, 'utf8') : null);
      return {
        stdout: new Response(stdout).body,
        exited: Promise.resolve(exitCode),
      };
    }) as unknown as ExecDeps['spawn'],
  };
  return { deps, calls, auditAtSpawn, audit: () => (existsSync(join(dir, 'audit.log')) ? readFileSync(join(dir, 'audit.log'), 'utf8') : '') };
};
const drain = async (it: AsyncIterable<string>) => {
  const out: string[] = [];
  for await (const l of it) out.push(l);
  return out;
};

describe('controlService', () => {
  test('rejects an action not in the set', async () => {
    const m = mk();
    await expect(controlService('nuke' as any, 'caddy', m.deps)).rejects.toThrow(/action/);
    expect(m.calls).toEqual([]);
    expect(m.audit()).toBe('');
  });
  test('rejects a service not in the set', async () => {
    const m = mk();
    await expect(controlService('restart', 'sshd', m.deps)).rejects.toThrow(/service/);
    expect(m.calls).toEqual([]);
  });
  test.each(['caddy; rm -rf /', 'caddy && x', 'caddy ', ' caddy', 'caddy\n', '$(id)', '`id`', 'caddy|cat', '--help', '', 'CADDY', 'caddy\0'])(
    'rejects service %j without spawning',
    async (svc) => {
      const m = mk();
      const e = await controlService('restart', svc, m.deps).catch((x) => x);
      expect(e).toBeInstanceOf(BadRequest);
      expect(m.calls).toEqual([]);
      expect(m.audit()).toBe('');
    },
  );
  test.each(['restart; id', 'RESTART', 'down', 'rm', '', 'start ', 'toString', '__proto__', 'constructor'])(
    'rejects action %j',
    async (a) => {
      const m = mk();
      await expect(controlService(a as any, 'caddy', m.deps)).rejects.toBeInstanceOf(BadRequest);
      await expect(controlService('restart', a, m.deps)).rejects.toBeInstanceOf(BadRequest);
      expect(m.calls).toEqual([]);
    },
  );
  test.each(['start', 'restart', 'stop'] as const)('%s builds a plain argv', async (action) => {
    for (const svc of SERVICES) {
      const m = mk();
      const r = await controlService(action, svc, m.deps);
      expect(m.calls).toEqual([['docker', 'compose', '-p', 'nufi-box', action, svc]]);
      expect(r.ok).toBe(true);
      expect(m.calls[0]!.some((a) => /\b(sh|bash)\b|-c$/.test(a))).toBe(false);
    }
  });
  test('audit line is written BEFORE spawn', async () => {
    const m = mk();
    const r = await controlService('restart', 'caddy', m.deps);
    expect(m.auditAtSpawn[0]).toBe('2026-10-05T01:02:03.000Z · restart · caddy\n');
    expect(m.audit()).toBe('2026-10-05T01:02:03.000Z · restart · caddy\n');
    expect(r.audit).toBe('2026-10-05T01:02:03.000Z · restart · caddy');
  });
  test('nonzero exit => ok false', async () => {
    const m = mk('', 1);
    expect((await controlService('stop', 'ollama', m.deps)).ok).toBe(false);
  });
  test('audit failure prevents execution', async () => {
    const m = mk();
    m.deps.stateDir = '/dev/null/nope';
    await expect(controlService('stop', 'ollama', m.deps)).rejects.toThrow();
    expect(m.calls).toEqual([]);
  });
});

describe('runReadCommand', () => {
  test.each(['status; whoami', 'status && id', 'status ', 'logs librechat; x', 'logs caddy', 'logs  librechat', 'STATUS', '', 'status\nid', 'logs --tail=1'])(
    'rejects %j without spawning',
    async (c) => {
      const m = mk();
      await expect(drain(runReadCommand(c, m.deps))).rejects.toThrow(/command/);
      await expect(drain(runReadCommand(c, m.deps))).rejects.toBeInstanceOf(BadRequest);
      expect(m.calls).toEqual([]);
      expect(m.audit()).toBe('');
    },
  );
  test('status argv', async () => {
    const m = mk('a\nb\n');
    expect(await drain(runReadCommand('status', m.deps))).toEqual(['a', 'b']);
    expect(m.calls).toEqual([['docker', 'compose', '-p', 'nufi-box', 'ps']]);
    expect(m.audit()).toBe('2026-10-05T01:02:03.000Z · status\n');
    expect(m.auditAtSpawn[0]).toContain('· status');
  });
  test('logs argv', async () => {
    const m = mk('x');
    expect(await drain(runReadCommand('logs', m.deps))).toEqual(['x']);
    expect(m.calls).toEqual([['docker', 'compose', '-p', 'nufi-box', 'logs', '--no-color', '--tail=200']]);
  });
  test('logs librechat argv', async () => {
    const m = mk();
    await drain(runReadCommand('logs librechat', m.deps));
    expect(m.calls).toEqual([['docker', 'compose', '-p', 'nufi-box', 'logs', '--no-color', '--tail=200', 'librechat']]);
    expect(m.audit()).toContain('· logs librechat\n');
  });
  test.each(['doctor', 'support'])('%s does not exec, yields info line', async (c) => {
    const m = mk();
    const lines = await drain(runReadCommand(c, m.deps));
    expect(m.calls).toEqual([]);
    expect(lines).toHaveLength(1);
    expect(lines[0]).toContain(`nufi-box ${c}`);
    expect(lines[0]).toContain('hardening sidecar');
  });
  test('allowlists are exact', () => {
    expect([...READ_CMDS]).toEqual(['status', 'logs', 'logs librechat', 'doctor', 'support']);
    expect([...SERVICES]).toEqual(['librechat', 'litellm-proxy', 'rag_api', 'ollama', 'caddy', 'mongodb', 'postgres', 'studio']);
  });
});
