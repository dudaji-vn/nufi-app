import { createFileRoute, useNavigate } from '@tanstack/react-router';
import { useQuery } from '@tanstack/react-query';
import { useEffect } from 'react';
import { Activity, Gauge, KeyRound } from 'lucide-react';
import { api, isUnauthorized } from '~/lib/orpc';
import { formatUsd } from '~/lib/format';
import { Skeleton } from '~/components/ui/skeleton';
import { Badge } from '~/components/ui/badge';
import { StatCard } from '~/components/StatCard';
import { BudgetCard } from '~/components/BudgetCard';
import { SpendBreakdown } from '~/components/SpendBreakdown';
import { TopKeysCard } from '~/components/TopKeysCard';

export const Route = createFileRoute('/')({
  component: HomePage,
});

function HomePage() {
  const me = useQuery(api.me.get.queryOptions());
  const navigate = useNavigate();

  useEffect(() => {
    if (me.isError && isUnauthorized(me.error)) {
      navigate({ to: '/unauthorized' });
    }
  }, [me.isError, me.error, navigate]);

  if (me.isPending) return <ProfileSkeleton />;
  if (me.isError && !isUnauthorized(me.error)) {
    return <p className="text-destructive">Error: {me.error.message}</p>;
  }
  if (!me.data) return null;

  const { spend, limits, keysCount, topKeys } = me.data;
  const identity = me.data.email ?? me.data.id;

  return (
    <section className="space-y-8">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">Welcome</h1>
          <p className="mt-1 flex items-center gap-2 text-sm text-muted-foreground">
            <span className="font-mono">{identity}</span>
            <Badge variant="secondary">{me.data.role}</Badge>
          </p>
        </div>
      </header>

      <div className="grid gap-4 md:grid-cols-3">
        <StatCard
          label="Total spend"
          value={formatUsd(spend.total)}
          hint={
            <span className="inline-flex items-center gap-1">
              <Activity className="size-3" /> this period
            </span>
          }
        />
        <BudgetCard
          spent={spend.total}
          maxBudget={limits.maxBudget}
          budgetDuration={limits.budgetDuration}
        />
        <StatCard
          label="Rate limits"
          value={
            <span className="text-base">
              <span className="font-semibold">{limits.tpmLimit?.toLocaleString() ?? '∞'}</span>
              <span className="ml-1 text-xs text-muted-foreground">tpm</span>
              <span className="mx-2 text-muted-foreground">·</span>
              <span className="font-semibold">{limits.rpmLimit?.toLocaleString() ?? '∞'}</span>
              <span className="ml-1 text-xs text-muted-foreground">rpm</span>
            </span>
          }
          hint={
            <span className="inline-flex items-center gap-1">
              <Gauge className="size-3" /> per-account caps
            </span>
          }
        />
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <SpendBreakdown chat={spend.chat} issuedKeys={spend.issuedKeys} />
        <TopKeysCard keys={topKeys} totalKeys={keysCount} />
      </div>

      <p className="rounded-md border bg-muted/40 p-3 text-xs text-muted-foreground">
        <KeyRound className="mr-1 inline size-3" />
        Chat traffic flows through the master key with your id as <code>end_user</code>;
        issued-key traffic is attributed directly. The LiteLLM admin <em>Users</em> tab only
        sums issued-key spend that LiteLLM tracks against the user record — this card
        sums spend across all your keys plus end-user (chat) spend, so it can be higher
        than what that tab shows.
      </p>
    </section>
  );
}

function ProfileSkeleton() {
  return (
    <section className="space-y-8">
      <div>
        <Skeleton className="h-9 w-48" />
        <Skeleton className="mt-2 h-4 w-64" />
      </div>
      <div className="grid gap-4 md:grid-cols-3">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-28 w-full" />
        ))}
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <Skeleton className="h-40 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    </section>
  );
}
