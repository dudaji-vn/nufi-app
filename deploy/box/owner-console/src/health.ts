// Health probing for the box's services. The owner console runs inside the
// `box` Docker network, so it reaches each service directly by container name
// and internal port over plain HTTP — not through Caddy's TLS ports. These are
// the same liveness endpoints `nufi-box doctor` checks (through Caddy); here we
// hit the container directly, which needs no certificate trust.

export type Probe = { name: string; url: string };
export type Health = { name: string; ok: boolean; status?: number; ms: number; error?: string };

const CORE: Probe[] = [
  { name: 'Chat', url: 'http://librechat:3080/health' },
  { name: 'Console', url: 'http://console:3000/_health' },
  { name: 'Admin panel', url: 'http://admin-panel:3000/' },
  { name: 'Gateway', url: 'http://litellm-proxy:4000/health/liveliness' },
  { name: 'Studio', url: 'http://studio:7860/health_check' },
];

// The Works profile adds one more service; it is only running when the box was
// installed with --with-works, surfaced here as NUFI_WORKS=1.
export function probesForEnv(env: Record<string, string | undefined> = process.env): Probe[] {
  const probes = [...CORE];
  if (env.NUFI_WORKS === '1') probes.push({ name: 'Works', url: 'http://works:3100/' });
  return probes;
}

// One probe. A non-2xx, a connection error, or a timeout all resolve to
// ok:false — never a throw — so one dead service cannot break the dashboard.
export async function probe(p: Probe, timeoutMs = 3000, fetchImpl: typeof fetch = fetch): Promise<Health> {
  const started = Date.now();
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const r = await fetchImpl(p.url, { signal: ctrl.signal, redirect: 'manual' });
    return { name: p.name, ok: r.ok, status: r.status, ms: Date.now() - started };
  } catch (e) {
    return { name: p.name, ok: false, ms: Date.now() - started, error: e instanceof Error ? e.name : 'error' };
  } finally {
    clearTimeout(timer);
  }
}

// Probe every service at once; order is preserved so the dashboard is stable.
export async function checkAll(
  probes: Probe[] = probesForEnv(),
  timeoutMs = 3000,
  fetchImpl: typeof fetch = fetch,
): Promise<Health[]> {
  return Promise.all(probes.map((p) => probe(p, timeoutMs, fetchImpl)));
}
