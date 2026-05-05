import { ORPCError } from '@orpc/server';
import { z } from 'zod';
import { o } from '../orpc.ts';
import { spendLogsByEndUser } from '../lib/litellm.ts';

/**
 * usage.daily — bucket the user's spend by UTC day for the last N days.
 * Powers the "last N days" mini-chart on the profile page.
 *
 * We filter by `end_user_id` because that captures both chat (master key
 * + user field) and issued-key calls that include the user field. It's a
 * superset of `user_id` filtering and matches what users actually see.
 */
export const daily = o
  .input(
    z.object({
      days: z.number().int().min(1).max(90).default(7),
    }),
  )
  .handler(async ({ context, input }) => {
    if (!context.user) throw new ORPCError('UNAUTHORIZED');

    const today = new Date();
    today.setUTCHours(23, 59, 59, 999);

    const start = new Date(today);
    start.setUTCDate(today.getUTCDate() - (input.days - 1));
    start.setUTCHours(0, 0, 0, 0);

    const startDateStr = start.toISOString().slice(0, 10);
    const logs = await spendLogsByEndUser(context.user.id, startDateStr);

    // Pre-fill every day in range with $0 so the chart has a stable shape.
    const buckets = new Map<string, number>();
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
