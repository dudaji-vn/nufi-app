import { describe, expect, test } from 'bun:test';
import { BadRequest, READ_CMDS, SERVICES, controlService, runReadCommand, type ExecDeps } from '../src/exec';

const mk = (res: () => Response) => {
  const calls: { url: string; init: any }[] = [];
  const deps: ExecDeps = {
    sock: '/test.sock',
    fetchImpl: (async (url: string, init: any) => {
      calls.push({ url, init });
      return res();
    }) as ExecDeps['fetchImpl'],
  };
  return { deps, calls };
};
const json = (b: unknown, status = 200) => () =>
  new Response(JSON.stringify(b), { status, headers: { 'content-type': 'application/json' } });
const drain = async (it: AsyncIterable<string>) => {
  const out: string[] = [];
  for await (const l of it) out.push(l);
  return out;
};

describe('controlService (sidecar client)', () => {
  test('POSTs /control over the socket and returns the sidecar result', async () => {
    const m = mk(json({ ok: true, audit: 'a · restart · caddy' }));
    const r = await controlService('restart', 'caddy', m.deps);
    expect(r).toEqual({ ok: true, audit: 'a · restart · caddy' });
    expect(m.calls).toHaveLength(1);
    expect(m.calls[0]!.url).toBe('http://x/control');
    expect(m.calls[0]!.init.unix).toBe('/test.sock');
    expect(JSON.parse(m.calls[0]!.init.body)).toEqual({ action: 'restart', service: 'caddy' });
  });
  test('sidecar 400 -> BadRequest; 500 -> Error', async () => {
    await expect(controlService('restart', 'caddy', mk(json({ error: 'nope' }, 400)).deps)).rejects.toBeInstanceOf(BadRequest);
    const e = await controlService('restart', 'caddy', mk(json({ error: 'audit failed' }, 500)).deps).catch((x) => x);
    expect(e).toBeInstanceOf(Error);
    expect(e).not.toBeInstanceOf(BadRequest);
    expect(e.message).toContain('audit failed');
  });
  test.each([['nuke', 'caddy'], ['restart', 'sshd'], ['restart', 'caddy; rm'], ['', 'caddy'], ['toString', 'caddy']])(
    'off-list %j %j -> BadRequest before any fetch',
    async (a, s) => {
      const m = mk(json({ ok: true, audit: '' }));
      await expect(controlService(a as any, s, m.deps)).rejects.toBeInstanceOf(BadRequest);
      expect(m.calls).toEqual([]);
    },
  );
  test('every service accepted', async () => {
    for (const svc of SERVICES) {
      const m = mk(json({ ok: true, audit: 'x' }));
      expect((await controlService('stop', svc, m.deps)).ok).toBe(true);
    }
  });
});

describe('runReadCommand (sidecar client)', () => {
  test('status POSTs /run and yields streamed lines', async () => {
    const stream = new ReadableStream<Uint8Array>({
      start(c) {
        const e = new TextEncoder();
        c.enqueue(e.encode('a\nb'));
        c.enqueue(e.encode('c\nd\n'));
        c.close();
      },
    });
    const m = mk(() => new Response(stream, { headers: { 'content-type': 'text/plain' } }));
    expect(await drain(runReadCommand('status', m.deps))).toEqual(['a', 'bc', 'd']);
    expect(m.calls[0]!.url).toBe('http://x/run');
    expect(m.calls[0]!.init.unix).toBe('/test.sock');
    expect(JSON.parse(m.calls[0]!.init.body)).toEqual({ cmd: 'status' });
  });
  test('logs <service> is sent', async () => {
    const m = mk(() => new Response('x'));
    expect(await drain(runReadCommand('logs ollama', m.deps))).toEqual(['x']);
    expect(JSON.parse(m.calls[0]!.init.body)).toEqual({ cmd: 'logs ollama' });
  });
  test('doctor yields the sidecar info line', async () => {
    const m = mk(() => new Response('info line\n'));
    expect(await drain(runReadCommand('doctor', m.deps))).toEqual(['info line']);
  });
  test.each(['down', 'restore', 'logs; rm', 'status && x', 'logs badsvc', 'STATUS', ''])('%j -> BadRequest before fetch', async (c) => {
    const m = mk(() => new Response(''));
    await expect(drain(runReadCommand(c, m.deps))).rejects.toBeInstanceOf(BadRequest);
    expect(m.calls).toEqual([]);
  });
  test('sidecar 400 -> BadRequest', async () => {
    await expect(drain(runReadCommand('status', mk(json({ error: 'x' }, 400)).deps))).rejects.toBeInstanceOf(BadRequest);
  });
  test('allowlists are exact', () => {
    expect([...READ_CMDS]).toEqual(['status', 'logs', 'doctor', 'support']);
  });
});
