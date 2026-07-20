import { timingSafeEqual } from 'crypto';
import client, { register } from 'prom-client';

client.collectDefaultMetrics();

export const httpRequestsTotal = new client.Counter({
  name: 'admin_http_requests_total',
  help: 'Total number of HTTP requests',
  labelNames: ['method', 'path', 'status_code'] as const,
});

export const httpRequestDurationSeconds = new client.Histogram({
  name: 'admin_http_request_duration_seconds',
  help: 'Duration of HTTP requests in seconds',
  labelNames: ['method', 'path', 'status_code'] as const,
  buckets: [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10],
});

export async function metricsResponse(req: Request): Promise<Response> {
  const secret = process.env.ADMIN_PANEL_METRICS_SECRET;
  const auth = req.headers.get('authorization');
  if (!secret || !auth) return new Response(null, { status: 401 });

  const token = auth.replace(/^bearer\s+/i, '');
  const encode = (s: string) => new TextEncoder().encode(s);
  const expected = encode(secret);
  const actual = encode(token);
  const maxLen = Math.max(expected.byteLength, actual.byteLength);
  const paddedExpected = new Uint8Array(maxLen);
  const paddedActual = new Uint8Array(maxLen);
  paddedExpected.set(expected);
  paddedActual.set(actual);
  const lengthMatch = expected.byteLength === actual.byteLength;
  if (!timingSafeEqual(paddedExpected, paddedActual) || !lengthMatch) {
    return new Response(null, { status: 401 });
  }

  try {
    const data = await register.metrics();
    return new Response(data, { headers: { 'Content-Type': register.contentType } });
  } catch {
    return new Response(null, { status: 500 });
  }
}
