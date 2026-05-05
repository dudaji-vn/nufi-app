import { createFileRoute, useNavigate } from '@tanstack/react-router';
import { useQuery } from '@tanstack/react-query';
import { useEffect } from 'react';
import { api, isUnauthorized } from '~/lib/orpc';

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

  if (me.isPending) {
    return <p className="text-muted-foreground">Loading…</p>;
  }
  if (me.isError && !isUnauthorized(me.error)) {
    return <p className="text-destructive">Error: {me.error.message}</p>;
  }
  if (!me.data) return null;

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
        <h2 className="mb-3 text-sm font-medium text-muted-foreground">Your LiteLLM account</h2>
        <dl className="grid grid-cols-2 gap-y-2 text-sm">
          <dt className="text-muted-foreground">Spend (period)</dt>
          <dd className="font-mono">${me.data.litellm.spend.toFixed(4)}</dd>

          <dt className="text-muted-foreground">Budget</dt>
          <dd className="font-mono">
            {me.data.litellm.maxBudget === null
              ? '—'
              : `$${me.data.litellm.maxBudget.toFixed(2)} / ${me.data.litellm.budgetDuration ?? '∞'}`}
          </dd>

          <dt className="text-muted-foreground">TPM limit</dt>
          <dd className="font-mono">{me.data.litellm.tpmLimit ?? '—'}</dd>

          <dt className="text-muted-foreground">RPM limit</dt>
          <dd className="font-mono">{me.data.litellm.rpmLimit ?? '—'}</dd>
        </dl>
      </div>

      <p className="text-xs text-muted-foreground">
        API keys + usage charts arrive in W3 Day 3 / W4.
      </p>
    </section>
  );
}
