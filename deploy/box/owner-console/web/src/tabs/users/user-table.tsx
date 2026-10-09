import { useEffect, useState } from 'react';
import { connectorUrl, inviteLink, type UserRow } from '../../api';
import { Badge, type BadgeTone } from '../../ui/badge';
import { IconCopy, IconDownload, IconRestart, IconTrash } from '../../ui/icons';
// (Button no longer used here: row actions are compact icon buttons.)
import { Table, type Col } from '../../ui/table';
import { useToast } from '../../ui/toast';

const TONE: Record<UserRow['activation'], BadgeTone> = { activated: 'ok', pending: 'warn', expired: 'bad' };
const LABEL: Record<UserRow['activation'], string> = { activated: 'Activated', pending: 'Pending', expired: 'Expired' };
const OS_LABEL: Record<UserRow['os'], string> = { macos: 'macOS', windows: 'Windows', linux: 'Linux' };

/** Time left until `expiresAt`, relative to `now` (ms). "Expires in MM:SS" (or
 * "Expires in Nd Nh" when far off), else "Expired". Pure. */
export function remaining(expiresAt: string, now: number): string {
  const s = Math.floor((Date.parse(expiresAt) - now) / 1000);
  if (!(s > 0)) return 'Expired';
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  const ss = s % 60;
  const pad = (n: number) => String(n).padStart(2, '0');
  if (d > 0) return `Expires in ${d}d ${h}h`;
  if (h > 0) return `Expires in ${h}h ${pad(m)}m`;
  return `Expires in ${pad(m)}:${pad(ss)}`;
}

function useNow(): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  return now;
}

const ColFilter = ({ label, value, onChange, options }: { label: string; value: string; onChange: (v: string) => void; options: { value: string; label: string }[] }) => (
  <span className="col-head">
    {label}
    <span className="col-filter">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M4 6h16M7 12h10M10 18h4" /></svg>
      <select aria-label={`Filter by ${label}`} value={value} onChange={(e) => onChange(e.target.value)}>
        {options.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
    </span>
  </span>
);

export function UserTable({
  rows,
  selected,
  osFilter,
  actFilter,
  onOsFilter,
  onActFilter,
  onToggle,
  onRegenerate,
  onDelete,
}: {
  rows: UserRow[];
  selected: Set<string>;
  osFilter: string;
  actFilter: string;
  onOsFilter: (v: string) => void;
  onActFilter: (v: string) => void;
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
    {
      key: 'os',
      label: 'Operating System',
      header: (
        <ColFilter
          label="Operating System"
          value={osFilter}
          onChange={onOsFilter}
          options={[
            { value: 'all', label: 'All' },
            { value: 'macos', label: 'macOS' },
            { value: 'windows', label: 'Windows' },
            { value: 'linux', label: 'Linux' },
          ]}
        />
      ),
      render: (u) => OS_LABEL[u.os],
    },
    {
      key: 'activation',
      label: 'Activation',
      header: (
        <ColFilter
          label="Activation"
          value={actFilter}
          onChange={onActFilter}
          options={[
            { value: 'all', label: 'All' },
            { value: 'pending', label: 'Pending' },
            { value: 'activated', label: 'Activated' },
            { value: 'expired', label: 'Expired' },
          ]}
        />
      ),
      render: (u) => (
        <span data-testid={`activation-${u.id}`} style={{ display: 'contents' }}>
          <Badge tone={TONE[u.activation]}>{LABEL[u.activation]}</Badge>
        </span>
      ),
    },
    {
      key: 'token',
      label: 'Access Key',
      render: (u) => {
        // Public = a downloadable join file to send; Private (default) = a LAN link.
        if (u.addingMethod === 'public') {
          return (
            <a href={connectorUrl(u)} download data-testid={`joinfile-${u.id}`} className="join-file-btn">
              Download join file <IconDownload size={16} />
            </a>
          );
        }
        const label = u.expiresAt ? remaining(u.expiresAt, now) : '';
        const expired = label === 'Expired';
        return (
          <span style={{ display: 'inline-flex', gap: 10, alignItems: 'center' }}>
            <a href={inviteLink(u.token)} title={inviteLink(u.token)} target="_blank" rel="noopener" className="access-link">
              {inviteLink(u.token)}
            </a>
            {label && (
              <span
                data-testid={`countdown-${u.id}`}
                style={{ color: expired ? 'var(--bad)' : 'var(--ok)', fontSize: 'var(--fs-sm)', fontWeight: 600, whiteSpace: 'nowrap' }}
              >
                {label}
              </span>
            )}
            <button type="button" className="icon-btn" data-testid={`copy-${u.id}`} aria-label={`Copy link for ${u.name}`} title="Copy link" onClick={() => copy(u)}>
              <IconCopy size={16} />
            </button>
          </span>
        );
      },
    },
    {
      key: 'actions',
      label: 'Actions',
      render: (u) => (
        <span style={{ display: 'inline-flex', gap: 6 }}>
          <button type="button" className="icon-btn" data-testid={`regenerate-${u.id}`} aria-label={`Regenerate link for ${u.name}`} title="Regenerate link" onClick={() => onRegenerate(u)}>
            <IconRestart size={16} />
          </button>
          <a href={connectorUrl(u)} download data-testid={`download-${u.id}`} className="icon-btn" aria-label={`Download join file for ${u.name}`} title="Download join file">
            <IconDownload size={16} />
          </a>
          <button type="button" className="icon-btn icon-btn--danger" data-testid={`delete-${u.id}`} aria-label={`Delete ${u.name}`} title="Delete" onClick={() => onDelete(u)}>
            <IconTrash size={16} />
          </button>
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
