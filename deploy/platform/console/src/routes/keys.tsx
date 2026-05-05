import { createFileRoute, useNavigate } from '@tanstack/react-router';
import { useQuery } from '@tanstack/react-query';
import { useEffect } from 'react';
import { Plus } from 'lucide-react';
import { api, isUnauthorized } from '~/lib/orpc';
import { useUi } from '~/stores/ui';
import { Button } from '~/components/ui/button';
import { KeyTable } from '~/components/KeyTable';
import { KeyGenerateModal } from '~/components/KeyGenerateModal';
import { KeyRevealOnceModal } from '~/components/KeyRevealOnceModal';

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

  return (
    <section className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">API keys</h1>
          <p className="text-muted-foreground">
            Self-issue keys with budgets and rate limits. Use them directly against the LiteLLM proxy.
          </p>
        </div>
        <Button onClick={() => setGenerateOpen(true)} className="gap-2">
          <Plus className="size-4" />
          Generate Key
        </Button>
      </div>

      {keys.isPending && <p className="text-sm text-muted-foreground">Loading keys…</p>}
      {keys.isError && !isUnauthorized(keys.error) && (
        <p className="text-sm text-destructive">Error: {keys.error.message}</p>
      )}
      {keys.data && <KeyTable rows={keys.data} />}

      <KeyGenerateModal />
      <KeyRevealOnceModal />
    </section>
  );
}
