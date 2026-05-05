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

const CHART_HEIGHT_PX = 176; // h-44 — keeps small bars (>=15%) clearly visible
const MIN_BAR_PCT = 15;       // any non-zero day gets at least this much height

/**
 * Square-root scaling so a $0.0001 day is visible next to a $0.012 peak,
 * floored at 15% so even the smallest non-zero day reads as "yes, there
 * was activity here", clearly different from a $0 day.
 */
function barHeightPct(value: number, max: number): number {
  if (max <= 0 || value <= 0) return 0;
  const norm = Math.sqrt(value / max);
  return Math.max(MIN_BAR_PCT, Math.round(norm * 100));
}

export function UsageChart({ series, total, requests, peak, mostRecent, pending }: Props) {
  if (pending) {
    return (
      <div className="rounded-lg border bg-card p-5">
        <Skeleton className="h-4 w-32" />
        <Skeleton className="mt-4 h-44 w-full" />
        <Skeleton className="mt-3 h-3 w-48" />
      </div>
    );
  }

  const max = Math.max(...series.map((d) => d.spend), 0);
  const days = series.length;
  const gridStyle = { gridTemplateColumns: `repeat(${days}, minmax(0, 1fr))` };

  return (
    <div className="rounded-lg border bg-card p-5 text-card-foreground">
      <div className="mb-4 flex items-baseline justify-between">
        <h3 className="text-sm font-medium">Last {days} days</h3>
        <span className="text-xs text-muted-foreground">
          {requests.toLocaleString()} request{requests === 1 ? '' : 's'} · {formatUsd(total)}
        </span>
      </div>

      {/* Chart area — explicit pixel height so % bar heights resolve correctly */}
      <div
        className="grid gap-2 border-b border-border/50"
        style={{ height: `${CHART_HEIGHT_PX}px`, ...gridStyle }}
      >
        {series.map((d) => {
          const pct = barHeightPct(d.spend, max);
          const isPeak = peak !== null && d.date === peak.date && d.spend > 0;
          const hasSpend = d.spend > 0;

          return (
            <div key={d.date} className="relative flex h-full flex-col items-center justify-end">
              {/* Value label — sits right above the bar */}
              <span
                className={`mb-1 font-mono text-[10px] tabular-nums leading-none ${
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
                  hasSpend ? (isPeak ? 'bg-primary' : 'bg-primary/55') : 'bg-muted'
                }`}
                style={{ height: hasSpend ? `${pct}%` : '4px' }}
                aria-label={`${d.date}: ${formatUsd(d.spend)}`}
              />
            </div>
          );
        })}
      </div>

      {/* Day labels */}
      <div className="mt-2 grid gap-2" style={gridStyle}>
        {series.map((d) => (
          <span key={d.date} className="text-center text-[11px] text-muted-foreground">
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
