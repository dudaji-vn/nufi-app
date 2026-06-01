/** Full set of audit actions surfaced in the dedicated audit-log page filter. */
export const AUDIT_ACTIONS = [
  'admin_login',
  'user_created',
  'user_updated',
  'user_deleted',
  'role_created',
  'role_updated',
  'role_deleted',
  'group_created',
  'group_updated',
  'group_deleted',
  'grant_assigned',
  'grant_removed',
  'config_updated',
  'config_deleted',
] as const;

/** Format an ISO timestamp for display, falling back to the raw string. */
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

/** Turn an action key like `user_created` into a readable label `User created`. */
export function humanizeAction(action: string): string {
  if (!action) return '';
  const spaced = action.replace(/_/g, ' ');
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

/** Pick a badge tone from the action's verb so the table scans quickly. */
export function actionBadgeClass(action: string): string {
  if (/(_created|_assigned|login)$/.test(action)) {
    return 'badge-success';
  }
  if (/(_deleted|_removed)$/.test(action)) {
    return 'badge-danger';
  }
  return 'bg-muted text-muted-foreground';
}
