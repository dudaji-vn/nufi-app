import { createFileRoute } from '@tanstack/react-router';
import { useQuery } from '@tanstack/react-query';
import { api } from '~/lib/orpc';

export const Route = createFileRoute('/')({
  component: HomePage,
});

function HomePage() {
  const ping = useQuery(api.ping.queryOptions());

  return (
    <section className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Day 1 ping</h1>
        <p className="text-muted-foreground">
          End-to-end smoke test: React → oRPC → Hono on Bun. Replaced by real procedures next.
        </p>
      </div>

      <div className="rounded-lg border bg-card p-4 text-card-foreground">
        {ping.isPending && <p>Pinging…</p>}
        {ping.isError && (
          <p className="text-destructive">Error: {ping.error.message}</p>
        )}
        {ping.data && (
          <pre className="text-sm text-muted-foreground">
            {JSON.stringify(ping.data, null, 2)}
          </pre>
        )}
      </div>
    </section>
  );
}
