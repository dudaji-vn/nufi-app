import { formatUsd } from '~/lib/format';

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
      <div className="mb-3 flex items-baseline justify-between">
        <h3 className="text-sm font-medium">Spend breakdown</h3>
        <span className="text-xs text-muted-foreground">{formatUsd(total)} total</span>
      </div>

      {total === 0 ? (
        <p className="py-4 text-center text-sm text-muted-foreground">
          No usage yet this period.
        </p>
      ) : (
        <>
          <div className="mb-4 flex h-2.5 w-full overflow-hidden rounded-full bg-muted">
            <div
              className="bg-primary"
              style={{ width: `${chatPct}%` }}
              aria-label={`Chat ${chatPct.toFixed(1)}%`}
            />
            <div
              className="bg-blue-500"
              style={{ width: `${keysPct}%` }}
              aria-label={`Issued keys ${keysPct.toFixed(1)}%`}
            />
          </div>

          <div className="space-y-2 text-sm">
            <Row colorClass="bg-primary" label="Chat (LibreChat)" value={chat} pct={chatPct} />
            <Row colorClass="bg-blue-500" label="Issued API keys" value={issuedKeys} pct={keysPct} />
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
      <span className="w-12 text-right text-xs text-muted-foreground">{pct.toFixed(1)}%</span>
    </div>
  );
}
