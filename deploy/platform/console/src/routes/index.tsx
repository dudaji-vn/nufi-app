import { createFileRoute, useNavigate } from '@tanstack/react-router';
import { useQuery } from '@tanstack/react-query';
import { useEffect } from 'react';
import { api, isUnauthorized } from '~/lib/orpc';
import { formatUsd } from '~/lib/format';

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

  if (me.isPending) return <p className="text-muted-foreground">Loading…</p>;
  if (me.isError && !isUnauthorized(me.error)) {
    return <p className="text-destructive">Error: {me.error.message}</p>;
  }
  if (!me.data) return null;

  const { spend, limits } = me.data;

  return (
    <section className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Welcome</h1>
        <p className="text-muted-foreground">
          Signed in as <span className="font-mono">{me.data.email ?? me.data.id}</span> ·{' '}
          <span className="rounded bg-muted px-2 py-0.5 text-xs">{me.data.role}</span>
        </p>
      </div>

      <div className="rounded-lg border bg-card p-4 text-card-foreground">
        <h2 className="mb-3 text-sm font-medium text-muted-foreground">This period</h2>
        <dl className="grid grid-cols-2 gap-y-2 text-sm">
          <dt className="text-muted-foreground">Total spend</dt>
          <dd className="font-mono">{formatUsd(spend.total)}</dd>

          <dt className="pl-3 text-xs text-muted-foreground">— Chat (LibreChat)</dt>
          <dd className="font-mono text-xs text-muted-foreground">{formatUsd(spend.chat)}</dd>

          <dt className="pl-3 text-xs text-muted-foreground">— Issued API keys</dt>
          <dd className="font-mono text-xs text-muted-foreground">{formatUsd(spend.issuedKeys)}</dd>

          <dt className="text-muted-foreground">Budget</dt>
          <dd className="font-mono">
            {limits.maxBudget === null
              ? '—'
              : `${formatUsd(limits.maxBudget)} / ${limits.budgetDuration ?? '∞'}`}
          </dd>

          <dt className="text-muted-foreground">TPM limit</dt>
          <dd className="font-mono">{limits.tpmLimit ?? '—'}</dd>

          <dt className="text-muted-foreground">RPM limit</dt>
          <dd className="font-mono">{limits.rpmLimit ?? '—'}</dd>
        </dl>
        <p className="mt-4 text-xs text-muted-foreground">
          Chat usage flows through the master key with your id as <code>end_user</code>. Issued-key
          usage is attributed directly. The LiteLLM admin "Users" tab only shows the latter; this
          card sums both.
        </p>
      </div>
    </section>
  );
}
