import { ORPCError } from '@orpc/server';
import { z } from 'zod';
import { spendLogsForUser } from '../lib/litellm.ts';
import { o } from '../orpc.ts';

const PeriodInput = z.object({
  days: z.number().int().min(1).max(90).default(7),
});

function periodStartDate(days: number): string {
  const today = new Date();
  today.setUTCHours(23, 59, 59, 999);
  const start = new Date(today);
  start.setUTCDate(today.getUTCDate() - (days - 1));
  start.setUTCHours(0, 0, 0, 0);
  return start.toISOString().slice(0, 10);
}

/**
 * LiteLLM logs the same model under two names depending on path:
 * the configured alias (`qwen2.5-3b`) for direct admin-API traffic and the
 * upstream id with provider prefix (`openai/qwen2.5:3b`) for chat traffic.
 * Strip the provider prefix so the two collapse visually; the alias-vs-id
 * shape difference (`-` vs `:`) is harder to fix without round-tripping
 * through /model/info, so leave it for a future Langfuse-backed view.
 */
function normalizeModel(model: string | null | undefined): string {
  if (!model) return 'unknown';
  return model.replace(/^openai\//, '');
}

/**
 * usage.daily — bucket the current user's spend by UTC day for the last N
 * days. Powers the "last N days" chart on the profile page and `/usage`.
 *
 * Filters logs to ones that belong to *this* user only (matched on either
 * end_user OR metadata.user_api_key_user_id — the LiteLLM query-param
 * filters silently no-op on this version, so we filter server-side here).
 */
export const daily = o.input(PeriodInput).handler(async ({ context, input }) => {
  if (!context.user) throw new ORPCError('UNAUTHORIZED');

  const startDateStr = periodStartDate(input.days);
  const logs = await spendLogsForUser(context.user.id, startDateStr);

  // Pre-fill every day in range with $0 so the chart has a stable shape.
  const buckets = new Map<string, number>();
  const start = new Date(`${startDateStr}T00:00:00Z`);
  for (let i = 0; i < input.days; i++) {
    const d = new Date(start);
    d.setUTCDate(start.getUTCDate() + i);
    buckets.set(d.toISOString().slice(0, 10), 0);
  }

  let total = 0;
  let mostRecent: string | null = null;
  for (const log of logs) {
    const day = log.startTime.slice(0, 10);
    if (buckets.has(day)) {
      buckets.set(day, (buckets.get(day) ?? 0) + (log.spend ?? 0));
    }
    total += log.spend ?? 0;
    if (!mostRecent || log.startTime > mostRecent) mostRecent = log.startTime;
  }

  const series = Array.from(buckets.entries()).map(([date, spend]) => ({ date, spend }));
  const peak = series.reduce((p, d) => (d.spend > p.spend ? d : p), { date: '', spend: 0 });

  return {
    days: input.days,
    total,
    series,
    peak: peak.spend > 0 ? peak : null,
    mostRecent,
    requests: logs.length,
  };
});

/**
 * usage.byModel — per-model spend + request count over the last N days.
 * Re-aggregates the same `spendLogsForUser` data the `daily` procedure
 * uses; no extra LiteLLM round-trip needed.
 */
export const byModel = o.input(PeriodInput).handler(async ({ context, input }) => {
  if (!context.user) throw new ORPCError('UNAUTHORIZED');

  const logs = await spendLogsForUser(context.user.id, periodStartDate(input.days));

  const buckets = new Map<string, { spend: number; requests: number }>();
  for (const log of logs) {
    const model = normalizeModel(log.model);
    const b = buckets.get(model) ?? { spend: 0, requests: 0 };
    b.spend += log.spend ?? 0;
    b.requests += 1;
    buckets.set(model, b);
  }

  const breakdown = Array.from(buckets.entries())
    .map(([model, b]) => ({ model, spend: b.spend, requests: b.requests }))
    .sort((a, b) => b.spend - a.spend);

  return { days: input.days, breakdown };
});

/**
 * usage.recent — last N spend logs for the current user, newest first.
 * The shape is deliberately narrow: only the columns the table needs.
 */
export const recent = o
  .input(
    z.object({
      limit: z.number().int().min(1).max(200).default(50),
    }),
  )
  .handler(async ({ context, input }) => {
    if (!context.user) throw new ORPCError('UNAUTHORIZED');

    // 30 days back is enough for the recent-requests view; if a user has
    // not used the platform in a month the table will be empty, which is
    // the right signal.
    const logs = await spendLogsForUser(context.user.id, periodStartDate(30));
    const sorted = logs
      .slice()
      .sort((a, b) => (a.startTime < b.startTime ? 1 : a.startTime > b.startTime ? -1 : 0))
      .slice(0, input.limit);

    return {
      rows: sorted.map((log) => ({
        startTime: log.startTime,
        model: normalizeModel(log.model),
        spend: log.spend ?? 0,
        keyAlias: log.metadata?.user_api_key_alias ?? null,
        // `via` distinguishes "chat traffic" (no key, end_user matches us)
        // from "issued-key traffic" (a key we created was used).
        via: log.metadata?.user_api_key_user_id === context.user.id ? 'key' : 'chat',
      })),
    };
  });
