import { KeyRound, DollarSign, Clock, ShieldAlert } from 'lucide-react';
import { compactNumber, formatUsd } from '~/lib/format';

type Key = {
  spend: number;
  maxBudget: number | null;
  expires: string | null;
};

type Props = {
  keys: Key[];
};

export function KeysSummary({ keys }: Props) {
  const total = keys.length;
  const spent = keys.reduce((s, k) => s + k.spend, 0);
  const budget = keys.reduce((s, k) => s + (k.maxBudget ?? 0), 0);

  const expiringSoon = keys.filter((k) => {
    if (!k.expires) return false;
    const ms = new Date(k.expires).getTime() - Date.now();
    return ms > 0 && ms < 7 * 24 * 3600 * 1000;
  }).length;

  return (
    <div className="grid gap-3 sm:grid-cols-2 md:grid-cols-4">
      <Stat icon={<KeyRound className="size-4" />} label="Active keys" value={compactNumber(total)} />
      <Stat
        icon={<DollarSign className="size-4" />}
        label="Used across keys"
        value={formatUsd(spent)}
      />
      <Stat
        icon={<Clock className="size-4" />}
        label="Total budget"
        value={budget > 0 ? formatUsd(budget) : '—'}
        hint={budget > 0 ? `${formatUsd(spent)} of ${formatUsd(budget)}` : 'No caps set'}
      />
      <Stat
        icon={<ShieldAlert className="size-4" />}
        label="Expiring this week"
        value={expiringSoon.toString()}
        tone={expiringSoon > 0 ? 'warn' : undefined}
      />
    </div>
  );
}

function Stat({
  icon,
  label,
  value,
  hint,
  tone,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  hint?: string;
  tone?: 'warn';
}) {
  const valueClass = tone === 'warn' ? 'text-amber-600' : '';
  return (
    <div className="rounded-lg border bg-card p-4 text-card-foreground">
      <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">
        {icon}
        {label}
      </div>
      <p className={`mt-2 font-mono text-xl font-semibold tracking-tight ${valueClass}`}>
        {value}
      </p>
      {hint && <p className="mt-1 text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}
