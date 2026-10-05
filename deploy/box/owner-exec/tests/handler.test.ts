import { describe, expect, test } from 'bun:test';

import { createApp, type ExecDeps } from '../src/handler';

function setup(opts: { auditThrows?: boolean; stdout?: string } = {}) {
  const spawned: string[][] = [];
  const audits: string[] = [];
  const deps: ExecDeps = {
    now: () => new Date('2026-10-05T00:00:00Z'),
    auditAppend: (line) => {
      if (opts.auditThrows) throw new Error('disk full');
      audits.push(line);
    },
    spawn: ((o: { cmd: string[] }) => {
      spawned.push(o.cmd);
      return {
        exited: Promise.resolve(0),
        stdout: new Response(opts.stdout ?? 'line1\nline2\n').body,
      };
    }) as unknown as ExecDeps['spawn'],
  };
  const app = createApp(deps);
  const post = (path: string, body: unknown) =>
    app.request(path, { method: 'POST', body: JSON.stringify(body), headers: { 'content-type': 'application/json' } });
  return { spawned, audits, post };
}

describe('POST /control', () => {
  test('restart caddy spawns the exact argv, audited first', async () => {
    const { spawned, audits, post } = setup();
    const res = await post('/control', { action: 'restart', service: 'caddy' });
    expect(res.status).toBe(200);
    const j = (await res.json()) as { ok: boolean; audit: string };
    expect(j.ok).toBe(true);
    expect(j.audit).toBe(audits[0]);
    expect(spawned).toEqual([['docker', 'compose', '-p', 'nufi-box', 'restart', 'caddy']]);
  });
  test('off-list action or service -> 400, no spawn', async () => {
    const { spawned, post } = setup();
    expect((await post('/control', { action: 'down', service: 'caddy' })).status).toBe(400);
    expect((await post('/control', { action: 'restart', service: 'evil; rm' })).status).toBe(400);
    expect((await post('/control', {})).status).toBe(400);
    expect(spawned).toEqual([]);
  });
  test('audit failure -> no spawn', async () => {
    const { spawned, post } = setup({ auditThrows: true });
    const res = await post('/control', { action: 'stop', service: 'ollama' });
    expect(res.status).toBe(500);
    expect(spawned).toEqual([]);
  });
});

describe('POST /run', () => {
  test('status streams ps output', async () => {
    const { spawned, audits, post } = setup({ stdout: 'a\nb\n' });
    const res = await post('/run', { cmd: 'status' });
    expect(res.status).toBe(200);
    expect(await res.text()).toBe('a\nb\n');
    expect(spawned).toEqual([['docker', 'compose', '-p', 'nufi-box', 'ps']]);
    expect(audits.length).toBe(1);
  });
  test('logs librechat argv', async () => {
    const { spawned, post } = setup();
    await (await post('/run', { cmd: 'logs librechat' })).text();
    expect(spawned[0]).toEqual(['docker', 'compose', '-p', 'nufi-box', 'logs', '--no-color', '--tail=200', 'librechat']);
  });
  test.each(['down', 'logs; rm -rf', 'logs badsvc', ''])('rejects %p', async (cmd) => {
    const { spawned, post } = setup();
    expect((await post('/run', { cmd })).status).toBe(400);
    expect(spawned).toEqual([]);
  });
  test.each(['doctor', 'support'])('%s is informational, no spawn', async (cmd) => {
    const { spawned, post } = setup();
    const res = await post('/run', { cmd });
    expect(res.status).toBe(200);
    expect(await res.text()).toContain(`nufi-box ${cmd}`);
    expect(spawned).toEqual([]);
  });
  test('audit failure -> no spawn', async () => {
    const { spawned, post } = setup({ auditThrows: true });
    expect((await post('/run', { cmd: 'status' })).status).toBe(500);
    expect(spawned).toEqual([]);
  });
});
