import { formatRelative, formatUsd } from '@/lib/format';
import { Badge } from './ui/badge';
import { Skeleton } from './ui/skeleton';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from './ui/table';

type Row = {
  startTime: string;
  model: string | null;
  spend: number;
  keyAlias: string | null;
  via: 'chat' | 'key';
};

type Props = {
  rows: Row[];
  pending?: boolean;
};

export function RecentRequestsTable({ rows, pending }: Props) {
  if (pending) {
    return (
      <div className="rounded-lg border bg-card p-5">
        <Skeleton className="h-4 w-32" />
        <Skeleton className="mt-4 h-48 w-full" />
      </div>
    );
  }

  if (rows.length === 0) {
    return (
      <div className="rounded-lg border bg-card p-5">
        <h3 className="text-sm font-medium">Recent requests</h3>
        <p className="mt-3 text-sm text-muted-foreground">
          No requests yet — usage will appear here as you chat or call the API.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-lg border bg-card text-card-foreground">
      <div className="border-b p-5 pb-3">
        <h3 className="text-sm font-medium">Recent requests</h3>
        <p className="mt-0.5 text-xs text-muted-foreground">
          Last {rows.length} request{rows.length === 1 ? '' : 's'} (most recent first)
        </p>
      </div>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-[28%]">When</TableHead>
            <TableHead>Model</TableHead>
            <TableHead>Source</TableHead>
            <TableHead className="text-right">Cost</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row) => (
            <TableRow key={`${row.startTime}-${row.model ?? 'na'}`}>
              <TableCell className="text-muted-foreground">
                {formatRelative(row.startTime)}
              </TableCell>
              <TableCell className="font-mono text-xs">{row.model ?? '—'}</TableCell>
              <TableCell>
                {row.via === 'key' ? (
                  <Badge variant="secondary">{row.keyAlias ?? 'key'}</Badge>
                ) : (
                  <Badge variant="outline">chat</Badge>
                )}
              </TableCell>
              <TableCell className="text-right font-mono tabular-nums">
                {formatUsd(row.spend)}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
