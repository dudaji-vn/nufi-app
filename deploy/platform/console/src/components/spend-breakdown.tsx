import { formatUsd } from '@/lib/format';

type Props = {
  chat: number;
  issuedKeys: number;
};

export function SpendBreakdown({ chat, issuedKeys }: Props) {
  const total = chat + issuedKeys;
  const chatPct = total > 0 ? (chat / total) * 100 : 0;
  const keysPct = total > 0 ? (issuedKeys / total) * 100 : 0;

  return (
    <div className="rounded-lg border bg-card p-5 text-card-foreground">
      <h3 className="mb-3 text-sm font-medium">Where it goes</h3>

      {total === 0 ? (
        <p className="py-4 text-center text-sm text-muted-foreground">
          You haven’t used anything yet this period.
        </p>
      ) : (
        <>
          <div className="mb-4 flex h-2.5 w-full overflow-hidden rounded-full bg-muted">
            <div className="bg-primary" style={{ width: `${chatPct}%` }} />
            <div className="bg-blue-500" style={{ width: `${keysPct}%` }} />
          </div>

          <div className="space-y-2 text-sm">
            <Row colorClass="bg-primary" label="Chat conversations" value={chat} pct={chatPct} />
            <Row
              colorClass="bg-blue-500"
              label="Direct API calls"
              value={issuedKeys}
              pct={keysPct}
            />
          </div>
        </>
      )}
    </div>
  );
}

function Row({
  colorClass,
  label,
  value,
  pct,
}: {
  colorClass: string;
  label: string;
  value: number;
  pct: number;
}) {
  return (
    <div className="flex items-center gap-3">
      <span className={`size-2.5 rounded-full ${colorClass}`} aria-hidden />
      <span className="flex-1 text-muted-foreground">{label}</span>
      <span className="font-mono">{formatUsd(value)}</span>
      <span className="w-12 text-right text-xs text-muted-foreground">{pct.toFixed(0)}%</span>
    </div>
  );
}
