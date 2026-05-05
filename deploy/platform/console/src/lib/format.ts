/** Show only first 3 + last 4 chars of a key-like identifier. */
export function maskKey(value: string | null | undefined): string {
  if (!value) return '—';
  if (value.length <= 8) return value;
  return `${value.slice(0, 3)}…${value.slice(-4)}`;
}

export function formatUsd(n: number | null | undefined): string {
  if (n === null || n === undefined) return '—';
  if (n === 0) return '$0.00';
  if (n < 0.01) return `$${n.toFixed(4)}`;
  if (n < 1) return `$${n.toFixed(3)}`;
  return `$${n.toFixed(2)}`;
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
}

export function formatRelative(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  const diffSec = (Date.now() - d.getTime()) / 1000;
  if (diffSec < 60) return 'just now';
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)} min ago`;
  if (diffSec < 86400) return `${Math.floor(diffSec / 3600)} hr ago`;
  if (diffSec < 604800) return `${Math.floor(diffSec / 86400)} d ago`;
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

/** "Mon", "Tue", … from an ISO date string (YYYY-MM-DD treated as UTC). */
export function dayLabel(isoDate: string): string {
  const d = new Date(`${isoDate}T00:00:00Z`);
  return d.toLocaleDateString(undefined, { weekday: 'short' });
}

export function pctSpent(spend: number, max: number | null): number {
  if (!max || max <= 0) return 0;
  return Math.min(100, Math.round((spend / max) * 100));
}

/** Prettier number formatting for limits (10000 → "10K", 100000 → "100K"). */
export function compactNumber(n: number | null | undefined): string {
  if (n === null || n === undefined) return '∞';
  return new Intl.NumberFormat(undefined, { notation: 'compact', maximumFractionDigits: 1 }).format(
    n,
  );
}
