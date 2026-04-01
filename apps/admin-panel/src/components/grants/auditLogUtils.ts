import type * as t from '@/types';

export const ACTION_FILTER_LABELS: Record<t.ActionFilter, string> = {
  all: 'com_audit_filter_all',
  grant_assigned: 'com_audit_filter_assigned',
  grant_removed: 'com_audit_filter_removed',
};

export function formatTimestamp(iso: string): string {
  try {
    return new Intl.DateTimeFormat(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    }).format(new Date(iso));
  } catch {
    return iso;
  }
}

export function capabilityLabel(cap: string, localize: (key: string) => string): string {
  const key = `com_cap_${cap.replace(/:/g, '_')}`;
  const label = localize(key);
  return label !== key ? label : cap;
}
