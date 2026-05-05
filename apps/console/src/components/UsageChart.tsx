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

      <div className="flex h-28 items-end gap-1">
        {series.map((d) => {
          const heightPct = max > 0 ? (d.spend / max) * 100 : 0;
          const isPeak = peak !== null && d.date === peak.date && d.spend > 0;
          return (
            <div key={d.date} className="group relative flex flex-1 flex-col items-center gap-2">
              <div className="flex h-full w-full items-end">
                <div
                  className={`w-full rounded-t-sm transition-all ${
                    isPeak ? 'bg-primary' : d.spend > 0 ? 'bg-primary/60' : 'bg-muted'
                  }`}
                  style={{ height: `${Math.max(heightPct, 2)}%` }}
                  aria-label={`${d.date}: ${formatUsd(d.spend)}`}
                />
              </div>
              {/* Tooltip-on-hover */}
              <div className="pointer-events-none absolute -top-9 hidden rounded bg-foreground px-2 py-1 text-xs text-background group-hover:block">
                {formatUsd(d.spend)}
              </div>
            </div>
          );
        })}
      </div>

      <div className="mt-2 flex justify-between text-[10px] text-muted-foreground">
        {series.map((d) => (
          <span key={d.date} className="flex-1 text-center">{dayLabel(d.date)}</span>
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
