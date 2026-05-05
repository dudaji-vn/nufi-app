import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';

type Props = {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  className?: string;
};

export function StatCard({ label, value, hint, className }: Props) {
  return (
    <div className={cn('rounded-lg border bg-card p-5 text-card-foreground', className)}>
      <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">{label}</p>
      <p className="mt-2 font-mono text-2xl font-semibold tracking-tight">{value}</p>
      {hint && <div className="mt-2 text-xs text-muted-foreground">{hint}</div>}
    </div>
  );
}
