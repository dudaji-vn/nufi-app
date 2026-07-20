/**
 * Thin wrapper around the Langfuse public API. Used by `usage.byHardware`
 * to aggregate spend per `hardware_id` — LiteLLM's /spend/logs doesn't
 * carry hardware metadata, but every trace does (via the W2.5 pre-call
 * hook in litellm/callbacks/hardware_metadata.py).
 *
 * Public + secret keys are passed via Basic auth, server-side only.
 */

const HOST = process.env.LANGFUSE_HOST ?? 'http://langfuse-web:3000';
const PUBLIC_KEY = process.env.LANGFUSE_PUBLIC_KEY ?? '';
const SECRET_KEY = process.env.LANGFUSE_SECRET_KEY ?? '';

export class LangfuseError extends Error {
  constructor(
    public status: number,
    public bodyText: string,
  ) {
    super(`Langfuse ${status}: ${bodyText.slice(0, 200)}`);
  }
}

export type LangfuseTrace = {
  id: string;
  userId: string | null;
  timestamp: string;
  totalCost: number | null;
  tags: string[];
  metadata: Record<string, unknown> | null;
};

type TraceListResponse = {
  data: LangfuseTrace[];
  meta: { page: number; limit: number; totalItems: number; totalPages: number };
};

// Per-page limit accepted by Langfuse public API; 100 is the documented max.
const PAGE_LIMIT = 100;
// Hard cap on pages we'll fetch in one procedure call. 5 × 100 = 500 traces
// per period — enough at current scale; if a user grows past that we'll
// switch to Langfuse's `/api/public/metrics` aggregations.
const MAX_PAGES = 5;

async function call<T>(path: string): Promise<T> {
  if (!PUBLIC_KEY || !SECRET_KEY) {
    throw new Error('LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY not configured');
  }
  const auth = Buffer.from(`${PUBLIC_KEY}:${SECRET_KEY}`).toString('base64');
  const res = await fetch(`${HOST}${path}`, {
    headers: { Authorization: `Basic ${auth}`, Accept: 'application/json' },
  });
  const text = await res.text();
  if (!res.ok) throw new LangfuseError(res.status, text);
  return text ? (JSON.parse(text) as T) : (undefined as T);
}

// 60s TTL keeps the dashboard's 30s polling tick cheap without pinning
// stale data for long. Sized for one entry per (userId, fromIso) — fine
// at current scale; if a single console grows past a few thousand active
// users this turns into an LRU.
const TRACE_CACHE_TTL_MS = 60_000;
const traceCache = new Map<
  string,
  { at: number; value: { traces: LangfuseTrace[]; truncated: boolean } }
>();

/**
 * Fetch up to MAX_PAGES × PAGE_LIMIT traces for a user since `fromIso`,
 * newest first. Returns whatever's available — the `truncated` flag tells
 * the caller whether the cap was hit. Result is cached per (userId, fromIso)
 * for TRACE_CACHE_TTL_MS so concurrent procedures (byHardware + future
 * summary card) share one Langfuse round-trip.
 */
export async function tracesForUser(
  userId: string,
  fromIso: string,
): Promise<{ traces: LangfuseTrace[]; truncated: boolean }> {
  const key = `${userId}\0${fromIso}`;
  const hit = traceCache.get(key);
  if (hit && Date.now() - hit.at < TRACE_CACHE_TTL_MS) return hit.value;

  const traces: LangfuseTrace[] = [];
  let truncated = false;

  for (let page = 1; page <= MAX_PAGES; page++) {
    const params = new URLSearchParams({
      userId,
      fromTimestamp: fromIso,
      orderBy: 'timestamp.desc',
      limit: String(PAGE_LIMIT),
      page: String(page),
    });
    const res = await call<TraceListResponse>(`/api/public/traces?${params}`);
    traces.push(...res.data);
    if (page >= res.meta.totalPages) break;
    if (page === MAX_PAGES) truncated = true;
  }

  const value = { traces, truncated };
  traceCache.set(key, { at: Date.now(), value });
  return value;
}

/**
 * Extract a tag's value from the `key:value` strings the W2.5 hook
 * stamps on every trace. Returns null if the tag isn't present.
 */
export function tagValue(trace: LangfuseTrace, key: string): string | null {
  const prefix = `${key}:`;
  for (const t of trace.tags) {
    if (t.startsWith(prefix)) return t.slice(prefix.length);
  }
  return null;
}
