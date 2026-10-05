import { describe, expect, test } from 'bun:test';
import { createServer } from 'node:net';
import { checkAll, parseChatVersion, parseOllamaModel, probe, probesForEnv, type Probe } from '../src/health';
import { makeApp, ownerCookie } from './helpers';

// A fetch that never resolves until the AbortController fires — used to prove
// the timeout path returns ok:false without throwing out of probe().
const hangingFetch = ((_url: string, init: { signal: AbortSignal }) =>
  new Promise((_resolve, reject) => {
    init.signal.addEventListener('abort', () =>
      reject(Object.assign(new Error('aborted'), { name: 'AbortError' })),
    );
  })) as unknown as typeof fetch;

// A fetch driven by a url -> status map; a url not in the map throws (like a
// connection refused), which probe() must render as ok:false, not a throw.
const mapFetch = (statuses: Record<string, number>) =>
  (async (url: string) => {
    if (!(url in statuses)) throw new Error('ECONNREFUSED');
    return new Response('', { status: statuses[url] });
  }) as unknown as typeof fetch;

describe('probe', () => {
  test('a 2xx is healthy', async () => {
    const r = await probe({ name: 'Chat', url: 'http://x/health' }, 1000, mapFetch({ 'http://x/health': 200 }));
    expect(r.ok).toBe(true);
    expect(r.status).toBe(200);
    expect(typeof r.ms).toBe('number');
  });

  test('a non-2xx is unhealthy but does not throw', async () => {
    const r = await probe({ name: 'Chat', url: 'http://x/health' }, 1000, mapFetch({ 'http://x/health': 503 }));
    expect(r.ok).toBe(false);
    expect(r.status).toBe(503);
  });

  test('a connection error is unhealthy, not a throw', async () => {
    const r = await probe({ name: 'Chat', url: 'http://down/health' }, 1000, mapFetch({}));
    expect(r.ok).toBe(false);
    expect(r.error).toBeTruthy();
  });

  test('a hang aborts at the timeout and is unhealthy', async () => {
    const r = await probe({ name: 'Chat', url: 'http://slow/health' }, 20, hangingFetch);
    expect(r.ok).toBe(false);
    expect(r.error).toBe('AbortError');
  });
});

describe('probesForEnv', () => {
  test('the five core services plus Web Server, Database and AI model are always probed', () => {
    const names = probesForEnv({}).map((p) => p.name);
    expect(names).toEqual(['Chat', 'Console', 'Admin panel', 'Gateway', 'Studio', 'Web Server', 'Database', 'AI model']);
  });

  test('Works is added only when the works profile is on', () => {
    expect(probesForEnv({ NUFI_WORKS: '1' }).some((p) => p.name === 'Works')).toBe(true);
    expect(probesForEnv({ NUFI_WORKS: '0' }).some((p) => p.name === 'Works')).toBe(false);
  });

  test('probes target container names on internal ports over http', () => {
    const byName = Object.fromEntries(probesForEnv({}).map((p) => [p.name, p.url]));
    expect(byName['AI model']).toBe('http://litellm-proxy:4000/health/liveliness');
    expect(byName['Web Server']).toBe('http://caddy/healthz');
    expect(byName['Chat']).toBe('http://librechat:3080/health');
    expect(byName['Console']).toBe('http://console:3000/_health');
    expect(byName['Admin panel']).toBe('http://admin-panel:3000/');
    expect(byName['Gateway']).toBe('http://litellm-proxy:4000/health/liveliness');
    expect(byName['Studio']).toBe('http://studio:7860/health_check');
  });
});

describe('checkAll', () => {
  test('probes every service and preserves order', async () => {
    const probes = probesForEnv({});
    const f = mapFetch(Object.fromEntries(probes.map((p) => [p.url, 200])));
    const results = await checkAll(probes, 1000, f, async () => ({ end() {} }));
    expect(results.map((r) => r.name)).toEqual(probes.map((p) => p.name));
    expect(results.every((r) => r.ok)).toBe(true);
  });
});

describe('Database (Postgres TCP) probe', () => {
  const dbProbe = (port: number): Probe => ({ name: 'Database', url: '', tcp: { host: '127.0.0.1', port } });

  test('defaults to postgres:5432 and honours PG_HOST / PG_PORT', () => {
    expect(probesForEnv({}).find((p) => p.name === 'Database')!.tcp).toEqual({ host: 'postgres', port: 5432 });
    expect(probesForEnv({ PG_HOST: 'db', PG_PORT: '6543' }).find((p) => p.name === 'Database')!.tcp).toEqual({ host: 'db', port: 6543 });
  });

  test('is ok when the port accepts a connection', async () => {
    const srv = createServer((s) => s.end());
    await new Promise<void>((r) => srv.listen(0, '127.0.0.1', r));
    const port = (srv.address() as { port: number }).port;
    try {
      const r = await probe(dbProbe(port), 1000);
      expect(r.ok).toBe(true);
      expect(r.name).toBe('Database');
    } finally {
      srv.close();
    }
  });

  test('is not ok, with an error, when nothing listens (never throws)', async () => {
    const srv = createServer();
    await new Promise<void>((r) => srv.listen(0, '127.0.0.1', r));
    const port = (srv.address() as { port: number }).port;
    await new Promise((r) => srv.close(r)); // port is now closed
    const r = await probe(dbProbe(port), 1000);
    expect(r.ok).toBe(false);
    expect(r.error).toBeTruthy();
  });

  test('a hanging connect times out as not ok', async () => {
    const hang = () => new Promise<{ end(): void }>(() => {});
    const r = await probe(dbProbe(1), 20, fetch, hang);
    expect(r.ok).toBe(false);
    expect(r.error).toBe('TimeoutError');
  });
});

describe('AI model (litellm-proxy) + Web Server (caddy) probes', () => {
  const ai = (env = {}) => probesForEnv(env).find((p) => p.name === 'AI model')!;

  const web = (env = {}) => probesForEnv(env).find((p) => p.name === 'Web Server')!;

  test('LITELLM_URL and CADDY_URL are configurable', () => {
    expect(ai({ LITELLM_URL: 'http://gw:1234/' }).url).toBe('http://gw:1234/health/liveliness');
    expect(web({ CADDY_URL: 'http://c:81/healthz' }).url).toBe('http://c:81/healthz');
  });

  test('caddy: ok on 200, not ok when down', async () => {
    expect((await probe(web(), 1000, mapFetch({ 'http://caddy/healthz': 200 }))).ok).toBe(true);
    const down = await probe(web(), 1000, mapFetch({}));
    expect(down.ok).toBe(false);
    expect(down.error).toBeTruthy();
  });

  test('ok on 200, not ok when unreachable', async () => {
    const up = await probe(ai(), 1000, mapFetch({ 'http://litellm-proxy:4000/health/liveliness': 200 }));
    expect(up.ok).toBe(true);
    const down = await probe(ai(), 1000, mapFetch({}));
    expect(down.ok).toBe(false);
    expect(down.error).toBeTruthy();
  });
});

describe('GET /api/status with real probes down', () => {
  test('still returns 200 with every probe present when services are unreachable', async () => {
    // Real checkAll with no injected checkHealth: every default target is
    // unresolvable here, so each probe fails — the route must not.
    const app = makeApp({ PG_HOST: '127.0.0.1', PG_PORT: '1', LITELLM_URL: 'http://127.0.0.1:1', CADDY_URL: 'http://127.0.0.1:1/healthz' });
    const r = await app.request('/api/status', { headers: { cookie: ownerCookie() } });
    expect(r.status).toBe(200);
    const { services } = await r.json();
    const names = services.map((s: { name: string }) => s.name);
    expect(names).toContain('Database');
    expect(names).toContain('AI model');
    expect(names).toContain('Web Server');
    expect(services.find((s: { name: string }) => s.name === 'Database').ok).toBe(false);
  });
});

describe('probe detail', () => {
  const p: Probe = { name: 'AI model', url: 'http://l/h', detail: { url: 'http://o/tags', parse: parseOllamaModel } };
  const f = (detail: () => Response) =>
    (async (url: string) => (url === 'http://l/h' ? new Response('', { status: 200 }) : detail())) as unknown as typeof fetch;
  test('detail appears when the detail fetch succeeds', async () => {
    const r = await probe(p, 1000, f(() => new Response(JSON.stringify({ models: [{ name: 'qwen3', size: 4_500_000_000 }] }))));
    expect(r.ok).toBe(true);
    expect(r.detail).toBe('qwen3 · 4.5 GB');
  });
  test('detail absent when the detail fetch fails; card stays ok', async () => {
    for (const d of [() => new Response('', { status: 500 }), () => { throw new Error('x'); }, () => new Response('not json')]) {
      const r = await probe(p, 1000, f(d));
      expect(r.ok).toBe(true);
      expect(r.detail).toBeUndefined();
    }
  });
  test('chat version parsed; probesForEnv wires details', () => {
    expect(parseChatVersion({ version: 'v0.8.6' })).toBe('v0.8.6');
    expect(parseChatVersion({})).toBeUndefined();
    const ps = probesForEnv({ CHAT_URL: 'http://c:1/', OLLAMA_URL: 'http://o:2' });
    expect(ps.find((x) => x.name === 'Chat')!.detail!.url).toBe('http://c:1/api/config');
    expect(ps.find((x) => x.name === 'AI model')!.detail!.url).toBe('http://o:2/api/tags');
  });
});
