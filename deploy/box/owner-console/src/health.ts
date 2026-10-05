// Health probing for the box's services. The owner console runs inside the
// `box` Docker network, so it reaches each service directly by container name
// and internal port over plain HTTP — not through Caddy's TLS ports. These are
// the same liveness endpoints `nufi-box doctor` checks (through Caddy); here we
// hit the container directly, which needs no certificate trust.

// An HTTP probe (`url`) or a bare TCP connect (`tcp`) for services that don't
// speak HTTP (Postgres).
// `detail` is an optional best-effort enrichment: a JSON GET whose result is
// summarised into a short string. Any failure just leaves the card without it.
export type Detail = { url: string; parse: (json: any) => string | undefined };
export type Probe = { name: string; url: string; tcp?: { host: string; port: number }; detail?: Detail };
export type Health = { name: string; ok: boolean; status?: number; ms: number; error?: string; detail?: string };

const humanSize = (n: number): string => {
  const gb = n / 1e9;
  return gb >= 1 ? `${gb.toFixed(1)} GB` : `${Math.round(n / 1e6)} MB`;
};

export const parseChatVersion = (j: any): string | undefined => {
  const v = j?.version ?? j?.appVersion ?? j?.app_version;
  return typeof v === 'string' && v ? v : undefined;
};

export const parseOllamaModel = (j: any): string | undefined => {
  const m = j?.models?.[0];
  if (!m || typeof m.name !== 'string') return undefined;
  return typeof m.size === 'number' ? `${m.name} · ${humanSize(m.size)}` : m.name;
};

const CORE: Probe[] = [
  {
    name: 'Chat',
    url: 'http://librechat:3080/health',
    detail: { url: 'http://librechat:3080/api/config', parse: parseChatVersion },
  },
  { name: 'Console', url: 'http://console:3000/_health' },
  { name: 'Admin panel', url: 'http://admin-panel:3000/' },
  { name: 'Gateway', url: 'http://litellm-proxy:4000/health/liveliness' },
  { name: 'Studio', url: 'http://studio:7860/health_check' },
];

// The Works profile adds one more service; it is only running when the box was
// installed with --with-works, surfaced here as NUFI_WORKS=1.
export function probesForEnv(env: Record<string, string | undefined> = process.env): Probe[] {
  const probes = CORE.map((p) => ({ ...p }));
  if (env.CHAT_URL) {
    const chat = probes.find((p) => p.name === 'Chat')!;
    const base = env.CHAT_URL.replace(/\/+$/, '');
    chat.url = `${base}/health`;
    chat.detail = { url: `${base}/api/config`, parse: parseChatVersion };
  }
  if (env.NUFI_WORKS === '1') probes.push({ name: 'Works', url: 'http://works:3100/' });
  // Web Server, Database and AI model back three General-tab cards. Targets are env-configurable
  // so a box with different hostnames is a config change, not code.
  const caddy = (env.CADDY_URL || 'http://caddy/healthz').replace(/\/+$/, '');
  probes.push({ name: 'Web Server', url: caddy });
  const port = Number(env.PG_PORT);
  probes.push({
    name: 'Database',
    url: '',
    tcp: { host: env.PG_HOST || 'postgres', port: Number.isInteger(port) && port > 0 ? port : 5432 },
  });
  // litellm-proxy is the universal inference front (every profile), unlike the
  // ollama container, which only exists in the ollama-docker profile.
  const litellm = (env.LITELLM_URL || 'http://litellm-proxy:4000').replace(/\/+$/, '');
  const ollama = (env.OLLAMA_URL || 'http://ollama:11434').replace(/\/+$/, '');
  probes.push({
    name: 'AI model',
    url: `${litellm}/health/liveliness`,
    detail: { url: `${ollama}/api/tags`, parse: parseOllamaModel },
  });
  return probes;
}

// One probe. A non-2xx, a connection error, or a timeout all resolve to
// ok:false — never a throw — so one dead service cannot break the dashboard.
// Open (and immediately close) a TCP connection. Injectable for tests.
export type ConnectFn = (host: string, port: number) => Promise<{ end(): void }>;
const tcpConnect: ConnectFn = (hostname, port) =>
  Bun.connect({ hostname, port, socket: { data() {}, open() {}, close() {}, error() {} } });

async function tcpProbe(p: Probe, timeoutMs: number, connect: ConnectFn): Promise<Health> {
  const started = Date.now();
  const { host, port } = p.tcp!;
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    const pending = connect(host, port);
    const sock = await Promise.race([
      pending,
      new Promise<never>((_, reject) => {
        timer = setTimeout(() => {
          // A connect that lands after the deadline must not leak its socket.
          pending.then((s) => s.end(), () => {});
          reject(Object.assign(new Error('timeout'), { name: 'TimeoutError' }));
        }, timeoutMs);
      }),
    ]);
    sock.end();
    return { name: p.name, ok: true, ms: Date.now() - started };
  } catch (e) {
    return { name: p.name, ok: false, ms: Date.now() - started, error: e instanceof Error ? e.name || 'error' : 'error' };
  } finally {
    clearTimeout(timer);
  }
}

// Best-effort: never throws, resolves undefined on any failure.
async function readDetail(d: Detail, timeoutMs: number, fetchImpl: typeof fetch): Promise<string | undefined> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const r = await fetchImpl(d.url, { signal: ctrl.signal });
    if (!r.ok) return undefined;
    return d.parse(await r.json());
  } catch {
    return undefined;
  } finally {
    clearTimeout(timer);
  }
}

export async function probe(
  p: Probe,
  timeoutMs = 3000,
  fetchImpl: typeof fetch = fetch,
  connect: ConnectFn = tcpConnect,
): Promise<Health> {
  if (p.tcp) return tcpProbe(p, timeoutMs, connect);
  const started = Date.now();
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const r = await fetchImpl(p.url, { signal: ctrl.signal, redirect: 'manual' });
    const h: Health = { name: p.name, ok: r.ok, status: r.status, ms: Date.now() - started };
    if (r.ok && p.detail) {
      const d = await readDetail(p.detail, timeoutMs, fetchImpl);
      if (d) h.detail = d;
    }
    return h;
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
  connect: ConnectFn = tcpConnect,
): Promise<Health[]> {
  return Promise.all(probes.map((p) => probe(p, timeoutMs, fetchImpl, connect)));
}
