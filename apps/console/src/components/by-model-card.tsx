import { formatUsd } from '@/lib/format';
import { Skeleton } from './ui/skeleton';

type Row = { model: string; spend: number; requests: number };

type Props = {
  breakdown: Row[];
  pending?: boolean;
};

export function ByModelCard({ breakdown, pending }: Props) {
  if (pending) {
    return (
      <div className="rounded-lg border bg-card p-5">
        <Skeleton className="h-4 w-32" />
        <Skeleton className="mt-4 h-32 w-full" />
      </div>
    );
  }

  if (breakdown.length === 0) {
    return (
      <div className="rounded-lg border bg-card p-5">
        <h3 className="text-sm font-medium">By model</h3>
        <p className="mt-3 text-sm text-muted-foreground">No usage in this period.</p>
      </div>
    );
  }

  const max = Math.max(...breakdown.map((r) => r.spend), 0);

  return (
    <div className="rounded-lg border bg-card p-5 text-card-foreground">
      <h3 className="mb-4 text-sm font-medium">By model</h3>
      <ul className="space-y-3">
        {breakdown.map((row) => {
          const pct = max > 0 ? Math.max(2, Math.round((row.spend / max) * 100)) : 0;
          return (
            <li key={row.model} className="space-y-1">
              <div className="flex items-baseline justify-between gap-2 text-sm">
                <span className="truncate font-mono">{row.model}</span>
                <span className="shrink-0 font-mono tabular-nums text-muted-foreground">
                  {formatUsd(row.spend)}{' '}
                  <span className="text-xs">
                    · {row.requests} req{row.requests === 1 ? '' : 's'}
                  </span>
                </span>
              </div>
              <div className="h-2 w-full rounded-full bg-muted">
                <div
                  className="h-2 rounded-full bg-primary/70"
                  style={{ width: `${pct}%` }}
                  title={`${row.model}: ${formatUsd(row.spend)} (${row.requests} requests)`}
                />
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
