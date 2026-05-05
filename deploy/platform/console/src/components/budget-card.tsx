import { formatUsd, pctSpent } from '@/lib/format';
import { StatCard } from './stat-card';

type Props = {
  spent: number;
  maxBudget: number | null;
  budgetDuration: string | null;
};

export function BudgetCard({ spent, maxBudget, budgetDuration }: Props) {
  if (maxBudget === null) {
    return <StatCard label="Budget" value="Unlimited" hint="No cap set on your account." />;
  }

  const pct = pctSpent(spent, maxBudget);
  const remaining = Math.max(0, maxBudget - spent);
  const tone = pct >= 90 ? 'bg-destructive' : pct >= 70 ? 'bg-amber-500' : 'bg-primary';

  return (
    <div className="rounded-lg border bg-card p-5 text-card-foreground">
      <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">Budget</p>
      <div className="mt-2 flex items-baseline justify-between">
        <p className="font-mono text-2xl font-semibold tracking-tight">{formatUsd(spent)}</p>
        <p className="font-mono text-sm text-muted-foreground">
          / {formatUsd(maxBudget)}
          {budgetDuration && ` · ${budgetDuration}`}
        </p>
      </div>
      <div
        className="mt-3 h-2 w-full overflow-hidden rounded-full bg-muted"
        role="progressbar"
        aria-label="Budget used"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div className={`h-full transition-all ${tone}`} style={{ width: `${pct}%` }} />
      </div>
      <p className="mt-2 text-xs text-muted-foreground">
        {formatUsd(remaining)} remaining ({100 - pct}%)
      </p>
    </div>
  );
}
