import { Link } from '@tanstack/react-router';
import { formatUsd, maskKey } from '@/lib/format';
import { Button } from './ui/button';

type Key = {
  alias: string | null;
  token: string;
  spend: number;
  maxBudget: number | null;
};

type Props = {
  keys: Key[];
  totalKeys: number;
};

export function TopKeysCard({ keys, totalKeys }: Props) {
  const max = keys[0]?.spend ?? 0;

  return (
    <div className="rounded-lg border bg-card p-5 text-card-foreground">
      <div className="mb-3 flex items-baseline justify-between">
        <h3 className="text-sm font-medium">Your keys</h3>
        <Link to="/keys">
          <Button variant="link" size="sm" className="h-auto p-0">
            View all ({totalKeys}) →
          </Button>
        </Link>
      </div>

      {keys.length === 0 ? (
        <div className="py-4 text-center text-sm text-muted-foreground">
          You don’t have any API keys yet.{' '}
          <Link
            to="/keys"
            className="font-medium text-foreground underline-offset-4 hover:underline"
          >
            Generate one
          </Link>
          .
        </div>
      ) : (
        <ul className="space-y-3">
          {keys.map((k) => {
            const pct = max > 0 ? (k.spend / max) * 100 : 0;
            return (
              <li key={k.token} className="space-y-1">
                <div className="flex items-baseline justify-between gap-3">
                  <span className="truncate text-sm font-medium">
                    {k.alias ?? <span className="text-muted-foreground">unnamed</span>}
                  </span>
                  <span className="font-mono text-xs text-muted-foreground">
                    {maskKey(k.token)}
                  </span>
                  <span className="font-mono text-sm tabular-nums">{formatUsd(k.spend)}</span>
                </div>
                <div className="h-1 w-full overflow-hidden rounded-full bg-muted">
                  <div className="h-full bg-blue-500" style={{ width: `${pct}%` }} />
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
