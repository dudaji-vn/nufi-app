import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { api } from '~/lib/orpc';
import { formatDate, formatUsd, maskKey, pctSpent } from '~/lib/format';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { Skeleton } from './ui/skeleton';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from './ui/table';
import { ConfirmDialog } from './ConfirmDialog';

type KeyRow = {
  alias: string | null;
  token: string;
  maxBudget: number | null;
  spend: number;
  budgetDuration: string | null;
  tpmLimit: number | null;
  rpmLimit: number | null;
  createdAt: string | null;
  expires: string | null;
};

export function KeyTable({ rows }: { rows: KeyRow[] }) {
  const qc = useQueryClient();
  const [pendingRevoke, setPendingRevoke] = useState<KeyRow | null>(null);

  const remove = useMutation(
    api.keys.remove.mutationOptions({
      onSuccess: () => {
        toast.success(`Key "${pendingRevoke?.alias ?? pendingRevoke?.token}" revoked`);
        setPendingRevoke(null);
        qc.invalidateQueries({ queryKey: api.keys.list.queryKey() });
      },
      onError: (err) => {
        toast.error(`Revoke failed: ${err.message}`);
      },
    }),
  );

  if (rows.length === 0) {
    return (
      <div className="rounded-lg border bg-card p-8 text-center text-card-foreground">
        <p className="text-sm text-muted-foreground">
          No keys yet. Click <span className="font-medium">Generate Key</span> to create your first one.
        </p>
      </div>
    );
  }

  return (
    <>
      <div className="rounded-lg border bg-card">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Alias</TableHead>
              <TableHead>Key</TableHead>
              <TableHead>Budget</TableHead>
              <TableHead>Limits</TableHead>
              <TableHead>Created</TableHead>
              <TableHead>Expires</TableHead>
              <TableHead className="w-12"></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((k) => (
              <TableRow key={k.token}>
                <TableCell className="font-medium">{k.alias ?? '—'}</TableCell>
                <TableCell className="font-mono text-xs text-muted-foreground">{maskKey(k.token)}</TableCell>
                <TableCell>
                  <div className="flex flex-col gap-1">
                    <span className="text-sm">
                      {formatUsd(k.spend)} / {formatUsd(k.maxBudget)}
                      {k.budgetDuration && (
                        <span className="text-muted-foreground"> · {k.budgetDuration}</span>
                      )}
                    </span>
                    {k.maxBudget !== null && k.maxBudget > 0 && (
                      <div className="h-1 w-24 overflow-hidden rounded-full bg-muted">
                        <div
                          className="h-full bg-primary"
                          style={{ width: `${pctSpent(k.spend, k.maxBudget)}%` }}
                        />
                      </div>
                    )}
                  </div>
                </TableCell>
                <TableCell className="text-xs">
                  <div className="flex flex-col">
                    <span>
                      <Badge variant="secondary">{k.tpmLimit ?? '∞'}</Badge> tpm
                    </span>
                    <span>
                      <Badge variant="secondary">{k.rpmLimit ?? '∞'}</Badge> rpm
                    </span>
                  </div>
                </TableCell>
                <TableCell className="text-sm text-muted-foreground">{formatDate(k.createdAt)}</TableCell>
                <TableCell className="text-sm text-muted-foreground">{formatDate(k.expires)}</TableCell>
                <TableCell>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => setPendingRevoke(k)}
                    aria-label="Revoke key"
                  >
                    <Trash2 className="size-4 text-destructive" />
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      <ConfirmDialog
        open={pendingRevoke !== null}
        onOpenChange={(o) => !o && setPendingRevoke(null)}
        title={`Revoke "${pendingRevoke?.alias ?? 'this key'}"?`}
        description="This action is immediate and irreversible. Any service using this key will start receiving 401s."
        confirmLabel="Revoke"
        destructive
        pending={remove.isPending}
        onConfirm={() => pendingRevoke && remove.mutate({ token: pendingRevoke.token })}
      />
    </>
  );
}

export function KeyTableSkeleton() {
  return (
    <div className="rounded-lg border bg-card">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Alias</TableHead>
            <TableHead>Key</TableHead>
            <TableHead>Budget</TableHead>
            <TableHead>Limits</TableHead>
            <TableHead>Created</TableHead>
            <TableHead>Expires</TableHead>
            <TableHead className="w-12"></TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {Array.from({ length: 3 }).map((_, i) => (
            <TableRow key={i}>
              <TableCell><Skeleton className="h-4 w-24" /></TableCell>
              <TableCell><Skeleton className="h-4 w-20" /></TableCell>
              <TableCell><Skeleton className="h-4 w-32" /></TableCell>
              <TableCell><Skeleton className="h-4 w-16" /></TableCell>
              <TableCell><Skeleton className="h-4 w-16" /></TableCell>
              <TableCell><Skeleton className="h-4 w-16" /></TableCell>
              <TableCell><Skeleton className="size-8 rounded-md" /></TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
