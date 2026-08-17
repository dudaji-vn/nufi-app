import { useMutation, useQuery } from '@tanstack/react-query';
import { createFileRoute } from '@tanstack/react-router';
import { AlertTriangle, Check, ShieldCheck } from 'lucide-react';
import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { api, isUnauthorized } from '@/lib/orpc';

/**
 * Consent screen for handing a gateway key to another NUFI app.
 *
 * Opened as a popup by NUFI Agents. The chat cookie arrives with this top-level
 * navigation, so the console knows who the visitor is; this page asks whether
 * they want a key minted for the app that opened it, and delivers the answer
 * back through `postMessage`.
 *
 * The destination comes from the server's reply, never from the query string —
 * the query string is what an attacker controls.
 */

type ConnectSearch = { origin: string; state: string; workspace: string };

export const Route = createFileRoute('/connect')({
  validateSearch: (search: Record<string, unknown>): ConnectSearch => ({
    origin: typeof search.origin === 'string' ? search.origin : '',
    state: typeof search.state === 'string' ? search.state : '',
    workspace: typeof search.workspace === 'string' ? search.workspace : '',
  }),
  component: ConnectPage,
});

const CHAT_URL = import.meta.env.VITE_LIBRECHAT_URL ?? 'http://localhost:3080';

function ConnectPage() {
  const { origin, state, workspace } = Route.useSearch();
  const [done, setDone] = useState(false);

  /**
   * No opener means no way to deliver the key. Refuse before asking for consent
   * rather than minting a credential that would go nowhere and linger.
   */
  const hasOpener = typeof window !== 'undefined' && window.opener != null;

  const begin = useQuery({
    ...api.connect.begin.queryOptions({ input: { origin, workspaceId: workspace } }),
    enabled: hasOpener && origin !== '' && workspace !== '' && state !== '',
    retry: false,
  });

  const approve = useMutation({
    ...api.connect.approve.mutationOptions(),
    onSuccess: (result) => {
      window.opener?.postMessage(
        { source: 'nufi-console', type: 'nufi.connect.key', state, key: result.key },
        result.origin,
      );
      setDone(true);
      // Give the opener a moment to receive the message before the window goes.
      setTimeout(() => window.close(), 1200);
    },
  });

  if (done) {
    return (
      <Panel icon={<Check className="size-5 text-primary" />} title="Connected">
        <p>Your key has been sent to NUFI Agents. You can close this window.</p>
      </Panel>
    );
  }

  if (!hasOpener) {
    return (
      <Panel icon={<AlertTriangle className="size-5" />} title="Open this from NUFI Agents">
        <p>
          This page issues a key to an app that opened it. Nothing opened this one, so there is
          nowhere to send a key. Start from Settings → NUFI in the Agents app.
        </p>
      </Panel>
    );
  }

  if (!origin || !workspace || !state) {
    return (
      <Panel icon={<AlertTriangle className="size-5" />} title="Incomplete request">
        <p>
          This link is missing information the Agents app should have supplied. Try again from
          Settings → NUFI.
        </p>
      </Panel>
    );
  }

  if (begin.isPending) {
    return (
      <Panel title="Checking your session…">
        <p className="text-muted-foreground">One moment.</p>
      </Panel>
    );
  }

  if (begin.isError && isUnauthorized(begin.error)) {
    return (
      <Panel icon={<AlertTriangle className="size-5" />} title="Sign in required">
        <p>
          The console reuses your chat session. Sign in there, then come back to this window and try
          again.
        </p>
        <div className="flex gap-2">
          <a
            href={CHAT_URL}
            target="_blank"
            rel="noreferrer"
            className="inline-flex h-10 items-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/90"
          >
            Open chat
          </a>
          <Button variant="outline" onClick={() => begin.refetch()}>
            I have signed in
          </Button>
        </div>
      </Panel>
    );
  }

  if (begin.isError) {
    return (
      <Panel icon={<AlertTriangle className="size-5" />} title="Could not check this request">
        <p>{begin.error instanceof Error ? begin.error.message : 'Unknown error.'}</p>
      </Panel>
    );
  }

  if (!begin.data.ok) {
    return begin.data.reason === 'disabled' ? (
      <Panel icon={<AlertTriangle className="size-5" />} title="Not enabled on this console">
        <p>
          Handing keys to other NUFI apps is switched off here. An administrator turns it on by
          listing the Agents address in <code className="font-mono">AGENTS_ALLOWED_ORIGINS</code>.
        </p>
      </Panel>
    ) : (
      <Panel icon={<AlertTriangle className="size-5" />} title="This site cannot request a key">
        <p>
          <span className="font-mono break-all">{origin}</span> is not on this console’s list of
          approved apps, so no key will be issued to it. If that is your own Agents install, ask an
          administrator to add it.
        </p>
      </Panel>
    );
  }

  const { terms, replaces, email, alias } = begin.data;

  return (
    <Panel
      icon={<ShieldCheck className="size-5 text-primary" />}
      title="Give NUFI Agents a gateway key"
    >
      <p>
        <span className="font-mono break-all">{begin.data.origin}</span> is asking for a key that
        lets it call NUFI models as {email ? <strong>{email}</strong> : 'you'}. Everything it spends
        counts against your budget.
      </p>

      <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-1.5 rounded-lg border p-4 text-sm">
        <dt className="text-muted-foreground">Key name</dt>
        <dd className="font-mono">{alias}</dd>
        <dt className="text-muted-foreground">Budget</dt>
        <dd>
          ${terms.maxBudget} per {terms.budgetDuration}
        </dd>
        <dt className="text-muted-foreground">Rate limit</dt>
        <dd>
          {terms.tpmLimit.toLocaleString()} tokens/min · {terms.rpmLimit.toLocaleString()} req/min
        </dd>
        <dt className="text-muted-foreground">Expires</dt>
        <dd>{terms.duration === 'never' ? 'never' : `in ${terms.duration}`}</dd>
      </dl>

      {replaces > 0 && (
        <p className="text-sm text-muted-foreground">
          This replaces the key already issued to this workspace. Anything still using the old one
          stops working.
        </p>
      )}

      {approve.isError && (
        <p className="text-sm text-destructive">
          {approve.error instanceof Error ? approve.error.message : 'Could not issue the key.'}
        </p>
      )}

      <div className="flex gap-2">
        <Button
          onClick={() => approve.mutate({ origin, workspaceId: workspace })}
          disabled={approve.isPending}
        >
          {approve.isPending ? 'Issuing…' : 'Approve'}
        </Button>
        <Button variant="outline" onClick={() => window.close()} disabled={approve.isPending}>
          Cancel
        </Button>
      </div>
    </Panel>
  );
}

function Panel({
  icon,
  title,
  children,
}: {
  icon?: React.ReactNode;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="mx-auto max-w-xl space-y-4">
      <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
        {icon}
        {title}
      </h1>
      <div className="space-y-4 text-sm leading-relaxed">{children}</div>
    </section>
  );
}
