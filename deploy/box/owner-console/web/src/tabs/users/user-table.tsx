import { useEffect, useState } from 'react';
import { connectorUrl, inviteLink, type UserRow } from '../../api';
import { Badge, type BadgeTone } from '../../ui/badge';
import { Button } from '../../ui/button';
import { Table, type Col } from '../../ui/table';
import { useToast } from '../../ui/toast';

const TONE: Record<UserRow['activation'], BadgeTone> = { activated: 'ok', pending: 'warn', expired: 'bad' };
const LABEL: Record<UserRow['activation'], string> = { activated: 'Activated', pending: 'Pending', expired: 'Expired' };
const OS_LABEL: Record<UserRow['os'], string> = { macos: 'macOS', windows: 'Windows', linux: 'Linux' };

/** Human-readable time left until `expiresAt`, relative to `now` (ms). Pure. */
export function remaining(expiresAt: string, now: number): string {
  const s = Math.floor((Date.parse(expiresAt) - now) / 1000);
  if (!(s > 0)) return 'Expired';
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s % 60}s`;
  return `${s}s`;
}

function useNow(): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  return now;
}

export function UserTable({
  rows,
  selected,
  onToggle,
  onRegenerate,
  onDelete,
}: {
  rows: UserRow[];
  selected: Set<string>;
  onToggle: (id: string) => void;
  onRegenerate: (u: UserRow) => void;
  onDelete: (u: UserRow) => void;
}) {
  const now = useNow();
  const toast = useToast();

  const copy = (u: UserRow) => {
    navigator.clipboard.writeText(inviteLink(u.token)).then(
      () => toast.push('Invite link copied', 'ok'),
      () => toast.push('Could not copy link', 'bad'),
    );
  };

  const columns: Col<UserRow>[] = [
    {
      key: 'select',
      label: '',
      render: (u) => (
        <input type="checkbox" aria-label={`Select ${u.name}`} checked={selected.has(u.id)} onChange={() => onToggle(u.id)} />
      ),
    },
    { key: 'name', label: 'Name' },
    { key: 'os', label: 'OS', render: (u) => OS_LABEL[u.os] },
    {
      key: 'activation',
      label: 'Activation',
      render: (u) => (
        <span data-testid={`activation-${u.id}`} style={{ display: 'contents' }}>
          <Badge tone={TONE[u.activation]}>{LABEL[u.activation]}</Badge>
        </span>
      ),
    },
    {
      key: 'token',
      label: 'Access Key',
      render: (u) => (
        <span style={{ display: 'inline-flex', gap: 8, alignItems: 'center' }}>
          <code
            title={inviteLink(u.token)}
            style={{ fontFamily: 'var(--mono)', maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', display: 'inline-block' }}
          >
            {inviteLink(u.token)}
          </code>
          <Button variant="ghost" size="sm" data-testid={`copy-${u.id}`} aria-label={`Copy link for ${u.name}`} onClick={() => copy(u)}>
            Copy
          </Button>
          {u.expiresAt && (
            <span data-testid={`countdown-${u.id}`} style={{ color: 'var(--gray-1)', fontSize: 'var(--fs-sm)' }}>
              {remaining(u.expiresAt, now)}
            </span>
          )}
        </span>
      ),
    },
    {
      key: 'actions',
      label: 'Actions',
      render: (u) => (
        <span style={{ display: 'inline-flex', gap: 4 }}>
          <Button variant="secondary" size="sm" data-testid={`regenerate-${u.id}`} onClick={() => onRegenerate(u)}>
            Regenerate
          </Button>
          <a href={connectorUrl(u)} download data-testid={`download-${u.id}`} className="ui-btn ui-btn--secondary ui-btn--sm">
            Download
          </a>
          <Button variant="danger" size="sm" data-testid={`delete-${u.id}`} onClick={() => onDelete(u)}>
            Delete
          </Button>
        </span>
      ),
    },
  ];

  return (
    <Table
      columns={columns}
      rows={rows}
      rowKey={(u) => u.id}
      empty="No users"
      rowTestId={(u) => `user-row-${u.id}`}
    />
  );
}
