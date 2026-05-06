import { Cpu } from 'lucide-react';
import { formatUsd } from '@/lib/format';
import { Badge } from './ui/badge';
import { Skeleton } from './ui/skeleton';

type Row = {
  hardwareId: string;
  backendType: string | null;
  spend: number;
  requests: number;
};

type Props = {
  breakdown: Row[];
  truncated?: boolean;
  pending?: boolean;
};

export function ByHardwareCard({ breakdown, truncated, pending }: Props) {
  if (pending) {
    return (
      <div className="rounded-lg border bg-card p-5">
        <Skeleton className="h-4 w-32" />
        <Skeleton className="mt-4 h-24 w-full" />
      </div>
    );
  }

  if (breakdown.length === 0) {
    return null;
  }

  const max = Math.max(...breakdown.map((r) => r.spend), 0);

  return (
    <div className="rounded-lg border bg-card p-5 text-card-foreground">
      <div className="mb-4 flex items-baseline justify-between gap-3">
        <h3 className="flex items-center gap-2 text-sm font-medium">
          <Cpu className="size-4 text-muted-foreground" />
          By hardware
        </h3>
        {truncated && (
          <span className="text-xs text-muted-foreground">
            (recent traces only — ask for older with a longer period)
          </span>
        )}
      </div>
      <ul className="space-y-3">
        {breakdown.map((row) => {
          const pct = max > 0 ? Math.max(2, Math.round((row.spend / max) * 100)) : 0;
          return (
            <li key={row.hardwareId} className="space-y-1">
              <div className="flex items-baseline justify-between gap-2 text-sm">
                <span className="flex items-center gap-2 truncate">
                  <span className="font-mono">{row.hardwareId}</span>
                  {row.backendType && (
                    <Badge variant={row.backendType === 'npu' ? 'default' : 'secondary'}>
                      {row.backendType}
                    </Badge>
                  )}
                </span>
                <span className="shrink-0 font-mono tabular-nums text-muted-foreground">
                  {formatUsd(row.spend)}{' '}
                  <span className="text-xs">
                    · {row.requests} req{row.requests === 1 ? '' : 's'}
                  </span>
                </span>
              </div>
              <div className="h-2 w-full rounded-full bg-muted">
                <div
                  className={`h-2 rounded-full ${
                    row.backendType === 'npu' ? 'bg-primary' : 'bg-primary/55'
                  }`}
                  style={{ width: `${pct}%` }}
                  title={`${row.hardwareId}: ${formatUsd(row.spend)} (${row.requests} requests)`}
                />
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
