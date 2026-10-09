import { useState } from 'react';
import type { FileRow } from '../../api';
import { Avatar } from '../../ui/avatar';
import { ColFilter, SortHeader } from '../../ui/col-filter';
import { ContextMenu } from '../../ui/context-menu';
import '../../ui/ui.css';
import './file-table.css';

// Accessibility shown as an icon + label (Figma), not a coloured badge.
const AccessCell = ({ access }: { access: FileRow['access'] }) =>
  access === 'public' ? (
    <span className="access-cell">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M17 21v-2a4 4 0 0 0-3-3.87M9 21v-2a4 4 0 0 1 3-3.87M12 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6z" />
      </svg>
      Public
    </span>
  ) : (
    <span className="access-cell access-cell--private">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <rect x="5" y="11" width="14" height="10" rx="2" /><path d="M8 11V7a4 4 0 0 1 8 0v4" />
      </svg>
      Private
    </span>
  );

export type SortKey = 'name' | 'size' | 'uploadedAt' | 'modifiedAt';
export type SortDir = 'asc' | 'desc';
export type Filters = { owner: 'all' | 'admin'; access: 'all' | FileRow['access']; kind: 'all' | 'file' | 'dir' };
export type FileAction = 'access' | 'rename' | 'download' | 'delete';

export const noFilters: Filters = { owner: 'all', access: 'all', kind: 'all' };

export function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ['KB', 'MB', 'GB', 'TB'];
  let v = bytes / 1024;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v.toFixed(1)} ${units[i]}`;
}

const time = (s: string) => {
  const t = Date.parse(s);
  return Number.isNaN(t) ? 0 : t;
};
const fmtDate = (s: string) => (Number.isNaN(Date.parse(s)) ? '—' : new Date(s).toLocaleString());

export function kindLabel(row: FileRow): string {
  if (row.kind === 'dir') return 'Folder';
  const dot = row.name.lastIndexOf('.');
  return dot > 0 && dot < row.name.length - 1 ? `${row.name.slice(dot + 1).toUpperCase()} file` : 'File';
}

/** Folders always sort before files; `key`/`dir` order within each group. */
export function sortRows(rows: FileRow[], key: SortKey, dir: SortDir): FileRow[] {
  const sign = dir === 'asc' ? 1 : -1;
  const cmp = (a: FileRow, b: FileRow) => {
    if (key === 'name') return a.name.localeCompare(b.name, undefined, { numeric: true, sensitivity: 'base' });
    if (key === 'size') return a.size - b.size;
    return time(a[key]) - time(b[key]);
  };
  return [...rows].sort((a, b) => (a.kind === b.kind ? sign * cmp(a, b) : a.kind === 'dir' ? -1 : 1));
}

export function filterRows(rows: FileRow[], f: Filters): FileRow[] {
  return rows.filter((r) => (f.access === 'all' || r.access === f.access) && (f.kind === 'all' || r.kind === f.kind));
}

const Icon = ({ dir }: { dir: boolean }) => (
  <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true" className="file-table__icon">
    {dir ? (
      <path d="M1.5 3.5h4l1.5 1.5h7.5v7.5h-13z" fill="currentColor" />
    ) : (
      <path d="M3.5 1.5h6l3 3v10h-9z" fill="none" stroke="currentColor" strokeWidth="1.2" />
    )}
  </svg>
);

export function FileTable({
  rows,
  search,
  onOpen,
  onAction,
  empty = 'Your uploaded files will be listed here',
}: {
  rows: FileRow[];
  search: string;
  onOpen: (row: FileRow) => void;
  onAction: (action: FileAction, row: FileRow) => void;
  empty?: string;
}) {
  const [sort, setSort] = useState<{ key: SortKey; dir: SortDir }>({ key: 'name', dir: 'asc' });
  const [filters, setFilters] = useState<Filters>(noFilters);

  const q = search.trim().toLowerCase();
  const visible = sortRows(
    filterRows(rows, filters).filter((r) => !q || r.name.toLowerCase().includes(q)),
    sort.key,
    sort.dir,
  );

  const toggle = (key: SortKey) =>
    setSort((s) => (s.key === key ? { key, dir: s.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: 'asc' }));
  const sortTh = (key: SortKey, label: string) => (
    <th scope="col" aria-sort={sort.key === key ? (sort.dir === 'asc' ? 'ascending' : 'descending') : 'none'}>
      <SortHeader label={label} active={sort.key === key} dir={sort.dir} onToggle={() => toggle(key)} />
    </th>
  );

  return (
    <table className="ui-table">
      <thead>
        <tr>
          {sortTh('name', 'Name')}
          <th scope="col">
            <ColFilter label="Owner" value={filters.owner} onChange={(v) => setFilters({ ...filters, owner: v as Filters['owner'] })} options={[{ value: 'all', label: 'All' }, { value: 'admin', label: 'Admin' }]} />
          </th>
          <th scope="col">
            <ColFilter label="Accessibility" value={filters.access} onChange={(v) => setFilters({ ...filters, access: v as Filters['access'] })} options={[{ value: 'all', label: 'All' }, { value: 'public', label: 'Public' }, { value: 'private', label: 'Private' }]} />
          </th>
          <th scope="col">
            <ColFilter label="Kind" value={filters.kind} onChange={(v) => setFilters({ ...filters, kind: v as Filters['kind'] })} options={[{ value: 'all', label: 'All' }, { value: 'file', label: 'File' }, { value: 'dir', label: 'Folder' }]} />
          </th>
          {sortTh('size', 'Size')}
          {sortTh('uploadedAt', 'Date uploaded')}
          {sortTh('modifiedAt', 'Date modified')}
          <th scope="col" aria-label="Actions" />
        </tr>
      </thead>
      <tbody>
        {visible.length === 0 ? (
          <tr>
            <td className="ui-table__empty" colSpan={8}>
              {rows.length === 0 ? (
                <div className="files-empty">
                  <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z" />
                  </svg>
                  <div className="files-empty__title">{empty}</div>
                  <div className="files-empty__hint">Click “Upload” or drag &amp; drop your file here to upload it</div>
                </div>
              ) : (
                'No files match your search'
              )}
            </td>
          </tr>
        ) : (
          visible.map((r) => (
            <tr key={r.name} data-testid={`file-row-${r.name}`}>
              <td>
                <span className="file-table__name">
                  <Icon dir={r.kind === 'dir'} />
                  {r.kind === 'dir' ? (
                    <button type="button" className="file-table__link" onClick={() => onOpen(r)}>
                      {r.name}
                    </button>
                  ) : (
                    r.name
                  )}
                </span>
              </td>
              <td>
                <span className="file-table__name">
                  <Avatar name="Admin" size="sm" /> Admin
                </span>
              </td>
              <td>
                <span data-testid={`access-badge-${r.name}`}>
                  <AccessCell access={r.access} />
                </span>
              </td>
              <td>{kindLabel(r)}</td>
              <td>{r.kind === 'file' ? formatSize(r.size) : '—'}</td>
              <td>{fmtDate(r.uploadedAt)}</td>
              <td>{fmtDate(r.modifiedAt)}</td>
              <td>
                <ContextMenu
                  items={[
                    { label: 'Accessibility', onSelect: () => onAction('access', r) },
                    { label: 'Create Agent', disabled: true, onSelect: () => {} },
                    { label: 'Rename', onSelect: () => onAction('rename', r) },
                    ...(r.kind === 'file' ? [{ label: 'Download', onSelect: () => onAction('download', r) }] : []),
                    { label: 'Delete', danger: true, onSelect: () => onAction('delete', r) },
                  ]}
                >
                  <button type="button" className="file-table__more" aria-label={`Actions for ${r.name}`}>
                    ⋮
                  </button>
                </ContextMenu>
              </td>
            </tr>
          ))
        )}
      </tbody>
    </table>
  );
}
