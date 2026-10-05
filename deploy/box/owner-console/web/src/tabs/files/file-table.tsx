import { useState } from 'react';
import type { FileRow } from '../../api';
import { Avatar } from '../../ui/avatar';
import { Badge } from '../../ui/badge';
import { ContextMenu } from '../../ui/context-menu';
import '../../ui/ui.css';
import './file-table.css';

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

  const header = (key: SortKey, label: string) => (
    <th scope="col" aria-sort={sort.key === key ? (sort.dir === 'asc' ? 'ascending' : 'descending') : 'none'}>
      <button
        type="button"
        className="file-table__sort"
        onClick={() => setSort((s) => (s.key === key ? { key, dir: s.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: 'asc' }))}
      >
        {label}
        {sort.key === key && <span aria-hidden="true"> {sort.dir === 'asc' ? '▲' : '▼'}</span>}
      </button>
    </th>
  );

  return (
    <table className="ui-table">
      <thead>
        <tr>
          {header('name', 'Name')}
          <th scope="col">
            Owner
            <select
              aria-label="Filter by owner"
              className="file-table__filter"
              value={filters.owner}
              onChange={(e) => setFilters({ ...filters, owner: e.target.value as Filters['owner'] })}
            >
              <option value="all">All</option>
              <option value="admin">Admin</option>
            </select>
          </th>
          <th scope="col">
            Accessibility
            <select
              aria-label="Filter by accessibility"
              className="file-table__filter"
              value={filters.access}
              onChange={(e) => setFilters({ ...filters, access: e.target.value as Filters['access'] })}
            >
              <option value="all">All</option>
              <option value="public">Public</option>
              <option value="private">Private</option>
            </select>
          </th>
          <th scope="col">
            Kind
            <select
              aria-label="Filter by kind"
              className="file-table__filter"
              value={filters.kind}
              onChange={(e) => setFilters({ ...filters, kind: e.target.value as Filters['kind'] })}
            >
              <option value="all">All</option>
              <option value="file">File</option>
              <option value="dir">Folder</option>
            </select>
          </th>
          {header('size', 'Size')}
          {header('uploadedAt', 'Date uploaded')}
          {header('modifiedAt', 'Date modified')}
          <th scope="col" aria-label="Actions" />
        </tr>
      </thead>
      <tbody>
        {visible.length === 0 ? (
          <tr>
            <td className="ui-table__empty" colSpan={8}>
              {rows.length === 0 ? empty : 'No files match your search'}
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
                  <Badge tone={r.access === 'public' ? 'ok' : 'neutral'}>{r.access === 'public' ? 'Public' : 'Private'}</Badge>
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
