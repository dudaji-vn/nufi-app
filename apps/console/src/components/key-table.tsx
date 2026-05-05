import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { api } from '@/lib/orpc';
import { compactNumber, formatDate, formatUsd, maskKey, pctSpent } from '@/lib/format';
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
import { ConfirmDialog } from './confirm-dialog';

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
      onError: (err) => toast.error(`Revoke failed: ${err.message}`),
    }),
  );

  return (
    <>
      <div className="overflow-hidden rounded-lg border bg-card">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Usage</TableHead>
              <TableHead className="hidden md:table-cell">Limits</TableHead>
              <TableHead className="hidden lg:table-cell">Created</TableHead>
              <TableHead className="hidden lg:table-cell">Expires</TableHead>
              <TableHead className="w-12"></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((k) => {
              const pct = pctSpent(k.spend, k.maxBudget);
              const tone =
                pct >= 90 ? 'bg-destructive' : pct >= 70 ? 'bg-amber-500' : 'bg-primary';
              return (
                <TableRow key={k.token}>
                  <TableCell>
                    <div className="flex flex-col">
                      <span className="font-medium">{k.alias ?? <span className="text-muted-foreground">(unnamed)</span>}</span>
                      <span className="font-mono text-[11px] text-muted-foreground">
                        {maskKey(k.token)}
                      </span>
                    </div>
                  </TableCell>
                  <TableCell>
                    <div className="flex flex-col gap-1.5">
                      <span className="text-sm tabular-nums">
                        <span className="font-mono">{formatUsd(k.spend)}</span>
                        {k.maxBudget !== null && (
                          <span className="text-muted-foreground">
                            {' '}of <span className="font-mono">{formatUsd(k.maxBudget)}</span>
                            {k.budgetDuration && <> · {k.budgetDuration}</>}
                          </span>
                        )}
                      </span>
                      {k.maxBudget !== null && k.maxBudget > 0 && (
                        <div className="h-1 w-32 overflow-hidden rounded-full bg-muted">
                          <div className={`h-full ${tone}`} style={{ width: `${pct}%` }} />
                        </div>
                      )}
                    </div>
                  </TableCell>
                  <TableCell className="hidden md:table-cell">
                    <div className="flex flex-col gap-0.5 text-xs">
                      <span>
                        <Badge variant="secondary" className="font-mono">{compactNumber(k.tpmLimit)}</Badge>
                        <span className="ml-1 text-muted-foreground">tok/min</span>
                      </span>
                      <span>
                        <Badge variant="secondary" className="font-mono">{compactNumber(k.rpmLimit)}</Badge>
                        <span className="ml-1 text-muted-foreground">req/min</span>
                      </span>
                    </div>
                  </TableCell>
                  <TableCell className="hidden lg:table-cell text-xs text-muted-foreground">{formatDate(k.createdAt)}</TableCell>
                  <TableCell className="hidden lg:table-cell text-xs text-muted-foreground">
                    {k.expires ? formatDate(k.expires) : <span className="italic">never</span>}
                  </TableCell>
                  <TableCell>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => setPendingRevoke(k)}
                      aria-label="Revoke key"
                    >
                      <Trash2 className="size-4 text-muted-foreground transition-colors group-hover:text-destructive" />
                    </Button>
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>

      <ConfirmDialog
        open={pendingRevoke !== null}
        onOpenChange={(o) => !o && setPendingRevoke(null)}
        title={`Revoke "${pendingRevoke?.alias ?? 'this key'}"?`}
        description="This is immediate and irreversible. Anything using this key will start receiving 401 errors."
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
    <div className="overflow-hidden rounded-lg border bg-card">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Name</TableHead>
            <TableHead>Usage</TableHead>
            <TableHead className="hidden md:table-cell">Limits</TableHead>
            <TableHead className="hidden lg:table-cell">Created</TableHead>
            <TableHead className="hidden lg:table-cell">Expires</TableHead>
            <TableHead className="w-12"></TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {Array.from({ length: 3 }).map((_, i) => (
            <TableRow key={i}>
              <TableCell>
                <Skeleton className="h-4 w-24" />
                <Skeleton className="mt-1 h-3 w-20" />
              </TableCell>
              <TableCell>
                <Skeleton className="h-4 w-32" />
                <Skeleton className="mt-1 h-1 w-32" />
              </TableCell>
              <TableCell className="hidden md:table-cell"><Skeleton className="h-4 w-16" /></TableCell>
              <TableCell className="hidden lg:table-cell"><Skeleton className="h-4 w-16" /></TableCell>
              <TableCell className="hidden lg:table-cell"><Skeleton className="h-4 w-16" /></TableCell>
              <TableCell><Skeleton className="size-8 rounded-md" /></TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
