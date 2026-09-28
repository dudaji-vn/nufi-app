import { describe, expect, test } from 'bun:test';
import { checkAll, probe, probesForEnv } from '../src/health';

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
  test('the five core services are always probed', () => {
    const names = probesForEnv({}).map((p) => p.name);
    expect(names).toEqual(['Chat', 'Console', 'Admin panel', 'Gateway', 'Studio']);
  });

  test('Works is added only when the works profile is on', () => {
    expect(probesForEnv({ NUFI_WORKS: '1' }).some((p) => p.name === 'Works')).toBe(true);
    expect(probesForEnv({ NUFI_WORKS: '0' }).some((p) => p.name === 'Works')).toBe(false);
  });

  test('probes target container names on internal ports over http', () => {
    const byName = Object.fromEntries(probesForEnv({}).map((p) => [p.name, p.url]));
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
    const results = await checkAll(probes, 1000, f);
    expect(results.map((r) => r.name)).toEqual(probes.map((p) => p.name));
    expect(results.every((r) => r.ok)).toBe(true);
  });
});
