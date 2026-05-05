import { formatUsd, pctSpent } from "@/lib/format";

type Props = {
  spent: number;
  maxBudget: number | null;
  budgetDuration: string | null;
};

const PERIOD_LABEL: Record<string, string> = {
  "24h": "24 hours",
  "7d": "7 days",
  "30d": "30 days",
};

export function AvailableHero({ spent, maxBudget, budgetDuration }: Props) {
  const period = PERIOD_LABEL[budgetDuration ?? ""] ?? budgetDuration ?? "this period";

  if (maxBudget === null) {
    return (
      <div className="rounded-xl border bg-card p-5 text-card-foreground sm:p-6">
        <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground sm:text-sm">
          You have unlimited usage
        </p>
        <p className="mt-2 font-mono text-3xl font-semibold tracking-tight sm:text-4xl">{formatUsd(spent)}</p>
        <p className="mt-2 text-sm text-muted-foreground">used so far</p>
      </div>
    );
  }

  const remaining = Math.max(0, maxBudget - spent);
  const pct = pctSpent(spent, maxBudget);
  const tone = pct >= 90 ? "bg-destructive" : pct >= 70 ? "bg-amber-500" : "bg-primary";
  const status = pct >= 90 ? "Almost out" : pct >= 70 ? "Running low" : "Healthy";

  return (
    <div className="rounded-xl border bg-card p-5 text-card-foreground sm:p-6">
      <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground sm:text-sm">
        Available · next {period}
      </p>
      <div className="mt-2 flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <p className="font-mono text-3xl font-semibold tracking-tight sm:text-4xl">{formatUsd(remaining)}</p>
        <span className="text-sm text-muted-foreground">of {formatUsd(maxBudget)}</span>
      </div>

      <div className="mt-4 h-2 w-full overflow-hidden rounded-full bg-muted">
        <div className={`h-full transition-all ${tone}`} style={{ width: `${pct}%` }} />
      </div>

      <div className="mt-2 flex justify-between text-xs">
        <span className="text-muted-foreground">
          {formatUsd(spent)} used ({pct}%)
        </span>
        <span className={pct >= 90 ? "text-destructive" : pct >= 70 ? "text-amber-600" : "text-muted-foreground"}>{status}</span>
      </div>
    </div>
  );
}
