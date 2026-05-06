import { useQuery } from '@tanstack/react-query';
import { createFileRoute, useNavigate } from '@tanstack/react-router';
import { useEffect, useState } from 'react';
import { ByHardwareCard } from '@/components/by-hardware-card';
import { ByModelCard } from '@/components/by-model-card';
import { RecentRequestsTable } from '@/components/recent-requests-table';
import { StatCard } from '@/components/stat-card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { UsageChart } from '@/components/usage-chart';
import { formatUsd } from '@/lib/format';
import { api, isUnauthorized } from '@/lib/orpc';

const PERIODS = [
  { days: 7, label: '7 days' },
  { days: 30, label: '30 days' },
  { days: 90, label: '90 days' },
] as const;
type Days = (typeof PERIODS)[number]['days'];

export const Route = createFileRoute('/usage')({
  component: UsagePage,
});

function UsagePage() {
  const [days, setDays] = useState<Days>(7);
  const navigate = useNavigate();

  const summary = useQuery(api.usage.summary.queryOptions({ input: { days } }));
  const daily = useQuery(api.usage.daily.queryOptions({ input: { days } }));
  const byModel = useQuery(api.usage.byModel.queryOptions({ input: { days } }));
  const byHardware = useQuery(api.usage.byHardware.queryOptions({ input: { days } }));
  const recent = useQuery(api.usage.recent.queryOptions({ input: { limit: 50 } }));

  useEffect(() => {
    const err = summary.error ?? daily.error ?? byModel.error ?? byHardware.error ?? recent.error;
    if (err && isUnauthorized(err)) {
      navigate({ to: '/unauthorized' });
    }
  }, [summary.error, daily.error, byModel.error, byHardware.error, recent.error, navigate]);

  return (
    <section className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">Usage</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Tokens, cost, and recent requests across chat and your API keys.
          </p>
        </div>
        <PeriodSelector value={days} onChange={setDays} />
      </header>

      <SummaryCards data={summary.data} pending={summary.isPending} />

      <UsageChart
        series={daily.data?.series ?? []}
        total={daily.data?.total ?? 0}
        requests={daily.data?.requests ?? 0}
        peak={daily.data?.peak ?? null}
        mostRecent={daily.data?.mostRecent ?? null}
        pending={daily.isPending}
      />

      <div className="grid gap-4 md:grid-cols-2">
        <ByModelCard breakdown={byModel.data?.breakdown ?? []} pending={byModel.isPending} />
        <ByHardwareCard
          breakdown={byHardware.data?.breakdown ?? []}
          truncated={byHardware.data?.truncated ?? false}
          pending={byHardware.isPending}
        />
      </div>

      <RecentRequestsTable rows={recent.data?.rows ?? []} pending={recent.isPending} />
    </section>
  );
}

function PeriodSelector({ value, onChange }: { value: Days; onChange: (d: Days) => void }) {
  return (
    <div className="inline-flex rounded-md border bg-card p-0.5">
      {PERIODS.map((p) => (
        <Button
          key={p.days}
          size="sm"
          variant={value === p.days ? 'default' : 'ghost'}
          onClick={() => onChange(p.days)}
          className="h-7 px-3 text-xs"
        >
          {p.label}
        </Button>
      ))}
    </div>
  );
}

type SummaryData = {
  totalSpend: number;
  totalRequests: number;
  modelsUsed: number;
  primaryHardware: { hardwareId: string; backendType: string | null } | null;
};

function SummaryCards({ data, pending }: { data: SummaryData | undefined; pending: boolean }) {
  if (pending || !data) {
    return (
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }, (_, i) => (
          // biome-ignore lint/suspicious/noArrayIndexKey: skeleton placeholders
          <Skeleton key={i} className="h-24 rounded-lg" />
        ))}
      </div>
    );
  }

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <StatCard label="Total cost" value={formatUsd(data.totalSpend)} />
      <StatCard label="Requests" value={data.totalRequests.toLocaleString()} />
      <StatCard
        label="Models used"
        value={data.modelsUsed.toLocaleString()}
        hint={data.modelsUsed === 0 ? 'No traffic in this period' : undefined}
      />
      <StatCard
        label="Primary hardware"
        value={
          data.primaryHardware ? (
            <span className="font-mono text-base">{data.primaryHardware.hardwareId}</span>
          ) : (
            <span className="text-muted-foreground">—</span>
          )
        }
        hint={
          data.primaryHardware?.backendType ? (
            <Badge variant={data.primaryHardware.backendType === 'npu' ? 'default' : 'secondary'}>
              {data.primaryHardware.backendType}
            </Badge>
          ) : null
        }
      />
    </div>
  );
}
