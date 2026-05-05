import { Activity, Gauge } from 'lucide-react';
import { compactNumber } from '~/lib/format';

type Props = {
  tpmLimit: number | null;
  rpmLimit: number | null;
};

export function LimitsBar({ tpmLimit, rpmLimit }: Props) {
  return (
    <div className="rounded-lg border bg-card p-5 text-card-foreground">
      <h3 className="mb-3 text-sm font-medium">Per-minute limits</h3>
      <div className="grid grid-cols-2 gap-4">
        <div className="flex items-center gap-3">
          <div className="rounded-md bg-muted p-2">
            <Activity className="size-4 text-muted-foreground" />
          </div>
          <div>
            <p className="font-mono text-lg font-semibold tracking-tight">
              {compactNumber(tpmLimit)}
            </p>
            <p className="text-xs text-muted-foreground">tokens / minute</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <div className="rounded-md bg-muted p-2">
            <Gauge className="size-4 text-muted-foreground" />
          </div>
          <div>
            <p className="font-mono text-lg font-semibold tracking-tight">
              {compactNumber(rpmLimit)}
            </p>
            <p className="text-xs text-muted-foreground">requests / minute</p>
          </div>
        </div>
      </div>
    </div>
  );
}
