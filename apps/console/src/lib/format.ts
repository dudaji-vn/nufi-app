/** Show only first 3 + last 4 chars of a key-like identifier. */
export function maskKey(value: string | null | undefined): string {
  if (!value) return '—';
  if (value.length <= 8) return value;
  return `${value.slice(0, 3)}…${value.slice(-4)}`;
}

export function formatUsd(n: number | null | undefined): string {
  if (n === null || n === undefined) return '—';
  return `$${n.toFixed(n < 1 ? 4 : 2)}`;
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
}

export function pctSpent(spend: number, max: number | null): number {
  if (!max || max <= 0) return 0;
  return Math.min(100, Math.round((spend / max) * 100));
}
