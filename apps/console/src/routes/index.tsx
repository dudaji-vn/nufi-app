import { useQuery } from '@tanstack/react-query';
import { createFileRoute, useNavigate } from '@tanstack/react-router';
import { useEffect } from 'react';
import { AvailableHero } from '@/components/available-hero';
import { LimitsBar } from '@/components/limits-bar';
import { SpendBreakdown } from '@/components/spend-breakdown';
import { TopKeysCard } from '@/components/top-keys-card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { UsageChart } from '@/components/usage-chart';
import { api, isUnauthorized } from '@/lib/orpc';

export const Route = createFileRoute('/')({
  component: HomePage,
});

function HomePage() {
  const me = useQuery(api.me.get.queryOptions());
  const usage = useQuery(api.usage.daily.queryOptions({ input: { days: 7 } }));
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
    <section className="space-y-6">
      <header>
        <h1 className="text-3xl font-semibold tracking-tight">Hi 👋</h1>
        <p className="mt-1 flex items-center gap-2 text-sm text-muted-foreground">
          <span className="font-mono">{identity}</span>
          <Badge variant="secondary">{me.data.role}</Badge>
        </p>
      </header>

      <AvailableHero
        spent={spend.total}
        maxBudget={limits.maxBudget}
        budgetDuration={limits.budgetDuration}
      />

      <UsageChart
        series={usage.data?.series ?? []}
        total={usage.data?.total ?? 0}
        requests={usage.data?.requests ?? 0}
        peak={usage.data?.peak ?? null}
        mostRecent={usage.data?.mostRecent ?? null}
        pending={usage.isPending}
      />

      <div className="grid gap-4 md:grid-cols-2">
        <SpendBreakdown chat={spend.chat} issuedKeys={spend.issuedKeys} />
        <TopKeysCard keys={topKeys} totalKeys={keysCount} />
      </div>

      <LimitsBar tpmLimit={limits.tpmLimit} rpmLimit={limits.rpmLimit} />
    </section>
  );
}

function ProfileSkeleton() {
  return (
    <section className="space-y-6">
      <div>
        <Skeleton className="h-9 w-40" />
        <Skeleton className="mt-2 h-4 w-56" />
      </div>
      <Skeleton className="h-32 w-full rounded-xl" />
      <Skeleton className="h-48 w-full" />
      <div className="grid gap-4 md:grid-cols-2">
        <Skeleton className="h-44 w-full" />
        <Skeleton className="h-44 w-full" />
      </div>
      <Skeleton className="h-24 w-full" />
    </section>
  );
}
