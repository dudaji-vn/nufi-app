import { createFileRoute, useNavigate } from '@tanstack/react-router';
import { useQuery } from '@tanstack/react-query';
import { useEffect } from 'react';
import { Plus } from 'lucide-react';
import { api, isUnauthorized } from '@/lib/orpc';
import { useUi } from '@/stores/ui';
import { Button } from '@/components/ui/button';
import { KeyTable, KeyTableSkeleton } from '@/components/key-table';
import { KeysSummary } from '@/components/keys-summary';
import { KeysEmptyState } from '@/components/keys-empty-state';
import { KeyGenerateModal } from '@/components/key-generate-modal';
import { KeyRevealOnceModal } from '@/components/key-reveal-once-modal';

export const Route = createFileRoute('/keys')({
  component: KeysPage,
});

function KeysPage() {
  const keys = useQuery(api.keys.list.queryOptions());
  const setGenerateOpen = useUi((s) => s.setGenerateOpen);
  const navigate = useNavigate();

  useEffect(() => {
    if (keys.isError && isUnauthorized(keys.error)) {
      navigate({ to: '/unauthorized' });
    }
  }, [keys.isError, keys.error, navigate]);

  const hasKeys = (keys.data?.length ?? 0) > 0;

  return (
    <section className="space-y-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">API keys</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Each key has its own budget and rate limits. Use them to call the API from your code.
          </p>
        </div>
        {hasKeys && (
          <Button onClick={() => setGenerateOpen(true)} className="gap-2">
            <Plus className="size-4" />
            Generate Key
          </Button>
        )}
      </header>

      {keys.isPending && <KeyTableSkeleton />}

      {keys.isError && !isUnauthorized(keys.error) && (
        <p className="text-sm text-destructive">Error: {keys.error.message}</p>
      )}

      {keys.data && !hasKeys && (
        <KeysEmptyState onGenerate={() => setGenerateOpen(true)} />
      )}

      {keys.data && hasKeys && (
        <>
          <KeysSummary keys={keys.data} />
          <KeyTable rows={keys.data} />
        </>
      )}

      <KeyGenerateModal />
      <KeyRevealOnceModal />
    </section>
  );
}
