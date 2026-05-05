import { dayLabel, formatRelative, formatUsd } from '~/lib/format';
import { Skeleton } from './ui/skeleton';

type Point = { date: string; spend: number };

type Props = {
  series: Point[];
  total: number;
  requests: number;
  peak: { date: string; spend: number } | null;
  mostRecent: string | null;
  pending?: boolean;
};

/**
 * Square-root scaling so that days with $0.0001 are still clearly visible
 * next to a $0.012 peak, instead of being crushed to a 0.8 % sliver.
 * Linear:  $0.0001 / $0.012 → 0.8% bar (invisible)
 * sqrt:    sqrt(0.008) / sqrt(1) → 9% bar (clearly there)
 */
function scaledHeight(value: number, max: number): number {
  if (max <= 0 || value <= 0) return 0;
  const norm = Math.sqrt(value / max);
  return Math.max(8, norm * 100); // floor at 8% so any non-zero day is unambiguous
}

export function UsageChart({ series, total, requests, peak, mostRecent, pending }: Props) {
  if (pending) {
    return (
      <div className="rounded-lg border bg-card p-5">
        <Skeleton className="h-4 w-32" />
        <Skeleton className="mt-4 h-32 w-full" />
        <Skeleton className="mt-3 h-3 w-48" />
      </div>
    );
  }

  const max = Math.max(...series.map((d) => d.spend), 0);
  const days = series.length;

  return (
    <div className="rounded-lg border bg-card p-5 text-card-foreground">
      <div className="mb-4 flex items-baseline justify-between">
        <h3 className="text-sm font-medium">Last {days} days</h3>
        <span className="text-xs text-muted-foreground">
          {requests.toLocaleString()} request{requests === 1 ? '' : 's'} · {formatUsd(total)}
        </span>
      </div>

      <div className="flex h-36 items-end gap-2">
        {series.map((d) => {
          const heightPct = scaledHeight(d.spend, max);
          const isPeak = peak !== null && d.date === peak.date && d.spend > 0;
          const hasSpend = d.spend > 0;

          return (
            <div key={d.date} className="group relative flex flex-1 flex-col items-center justify-end">
              {/* Always-visible value label above each bar */}
              <span
                className={`mb-1 font-mono text-[10px] tabular-nums ${
                  hasSpend
                    ? isPeak
                      ? 'font-semibold text-foreground'
                      : 'text-muted-foreground'
                    : 'text-muted-foreground/40'
                }`}
              >
                {hasSpend ? formatUsd(d.spend) : '—'}
              </span>
              <div
                className={`w-full rounded-t-sm transition-all ${
                  isPeak ? 'bg-primary' : hasSpend ? 'bg-primary/50' : 'bg-muted'
                }`}
                style={{ height: `${Math.max(heightPct, 2)}%` }}
                aria-label={`${d.date}: ${formatUsd(d.spend)}`}
              />
            </div>
          );
        })}
      </div>

      <div className="mt-2 flex justify-between text-[11px] text-muted-foreground">
        {series.map((d) => (
          <span key={d.date} className="flex-1 text-center">
            {dayLabel(d.date)}
          </span>
        ))}
      </div>

      <div className="mt-4 flex flex-wrap gap-x-6 gap-y-1 text-xs text-muted-foreground">
        {peak && (
          <span>
            Peak day:{' '}
            <span className="text-foreground">
              {dayLabel(peak.date)} · {formatUsd(peak.spend)}
            </span>
          </span>
        )}
        {mostRecent && (
          <span>
            Last request: <span className="text-foreground">{formatRelative(mostRecent)}</span>
          </span>
        )}
      </div>
    </div>
  );
}
