import { useRef, useState } from 'react';
import { exportUsersCsv, exportUsersZip, useDeleteUser, useImportUsers, useRegenerate, useUsers, type UserRow } from '../api';
import { Button } from '../ui/button';
import { Modal } from '../ui/modal';
import { Select } from '../ui/select';
import { useToast } from '../ui/toast';
import { IconClose, IconDownload, IconPlus, IconSearch, IconTrash, IconUpload } from '../ui/icons';
import { AddUserModal } from './users/add-user-modal';
import { HelpMenu } from './users/help-menu';
import { UserTable } from './users/user-table';

const PAGE_SIZES = [
  { value: '10', label: '10 items/row' },
  { value: '25', label: '25 items/row' },
  { value: '50', label: '50 items/row' },
  { value: '100', label: '100 items/row' },
];
const errText = (e: unknown, fallback: string) => (e as { error?: string }).error ?? fallback;

export function Users() {
  const { data, isPending, error } = useUsers();
  const del = useDeleteUser();
  const regen = useRegenerate();
  const imp = useImportUsers();
  const toast = useToast();
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(10);
  const [osFilter, setOsFilter] = useState('all');
  const [actFilter, setActFilter] = useState('all');
  const [methodFilter, setMethodFilter] = useState('all');
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [adding, setAdding] = useState(false);
  const [deleting, setDeleting] = useState<UserRow | null>(null);
  const [bulkDeleting, setBulkDeleting] = useState(false);
  const file = useRef<HTMLInputElement>(null);

  if (isPending) return <p role="status">Loading…</p>;
  if (error) return <p role="alert">Could not load users: {errText(error, 'unknown error')}</p>;

  const q = query.trim().toLowerCase();
  let filtered = q ? data.filter((u) => u.name.toLowerCase().includes(q)) : data;
  if (osFilter !== 'all') filtered = filtered.filter((u) => u.os === osFilter);
  if (actFilter !== 'all') filtered = filtered.filter((u) => u.activation === actFilter);
  // Legacy users have no addingMethod — they render (and filter) as 'private'.
  if (methodFilter !== 'all') filtered = filtered.filter((u) => (u.addingMethod ?? 'private') === methodFilter);
  const pages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const cur = Math.min(page, pages - 1);
  const visible = filtered.slice(cur * pageSize, (cur + 1) * pageSize);
  const selectedRows = data.filter((u) => selected.has(u.id));

  const toggle = (id: string) =>
    setSelected((s) => {
      const n = new Set(s);
      if (!n.delete(id)) n.add(id);
      return n;
    });

  // Select-all acts on the rows currently visible (this page, after filters).
  const allVisibleSelected = visible.length > 0 && visible.every((u) => selected.has(u.id));
  const toggleAll = () =>
    setSelected((s) => {
      const n = new Set(s);
      if (allVisibleSelected) visible.forEach((u) => n.delete(u.id));
      else visible.forEach((u) => n.add(u.id));
      return n;
    });

  // Export .zip carries the join FILES — only Public users have one; Private
  // users use a LAN link (covered by Export .CSV), so they are excluded.
  const exportZip = () => {
    const pub = selectedRows.filter((u) => (u.addingMethod ?? 'private') === 'public');
    if (!pub.length) {
      toast.push('No public users selected — private users use a link (Export .CSV)', 'warn');
      return;
    }
    exportUsersZip(pub).catch((e) => toast.push(errText(e, 'Export failed'), 'bad'));
  };

  const doBulkDelete = async () => {
    const ids = [...selected];
    setBulkDeleting(false);
    setSelected(new Set());
    let ok = 0;
    let fail = 0;
    for (const id of ids) {
      try {
        await del.mutateAsync(id);
        ok++;
      } catch {
        fail++;
      }
    }
    toast.push(`Deleted ${ok} user${ok === 1 ? '' : 's'}${fail ? `, ${fail} failed` : ''}`, fail ? 'warn' : 'ok');
  };

  const onUpload = (f: File | undefined) => {
    if (!f) return;
    imp.mutate(f, {
      onSuccess: (r) => toast.push(`Imported ${r.added} user${r.added === 1 ? '' : 's'}${r.skipped ? `, skipped ${r.skipped}` : ''}`, r.skipped ? 'warn' : 'ok'),
      onError: (e) => toast.push(errText(e, 'Import failed'), 'bad'),
    });
    if (file.current) file.current.value = '';
  };

  return (
    <div data-testid="users">
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', marginBottom: 16 }}>
        <span className="field-search">
          <span className="field-search__icon"><IconSearch size={16} /></span>
          <input
            type="search"
            className="ui-input"
            aria-label="Search users"
            placeholder="Search for user"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setPage(0);
            }}
          />
        </span>
        <Button className="btn-ico" data-testid="add-user" onClick={() => setAdding(true)}>
          <IconPlus size={16} /> Add User
        </Button>
        <Button variant="secondary" className="btn-ico" data-testid="upload-csv" disabled={imp.isPending} onClick={() => file.current?.click()}>
          <IconUpload size={16} /> Upload CSV
        </Button>
        <input ref={file} type="file" accept=".csv,text/csv" hidden aria-label="CSV file" onChange={(e) => onUpload(e.target.files?.[0])} />
        <HelpMenu />
      </div>

      {selected.size > 0 && (
        <div data-testid="bulk-bar" className="bulk-bar">
          <span className="bulk-count">Selected: {selected.size}</span>
          <span className="bulk-actions">
            <Button variant="secondary" className="btn-ico" data-testid="export-csv" onClick={() => exportUsersCsv([...selected]).catch((e) => toast.push(errText(e, 'Export failed'), 'bad'))}>
              <IconDownload size={16} /> Export .CSV
            </Button>
            <Button variant="secondary" className="btn-ico" data-testid="export-zip" onClick={exportZip}>
              <IconDownload size={16} /> Export .zip
            </Button>
            <Button variant="danger" className="btn-ico" data-testid="bulk-delete" disabled={del.isPending} onClick={() => setBulkDeleting(true)}>
              <IconTrash size={16} /> Delete
            </Button>
            <button type="button" className="btn-deselect" data-testid="deselect" onClick={() => setSelected(new Set())}>
              <IconClose size={16} /> Deselect
            </button>
          </span>
        </div>
      )}

      <UserTable
        rows={visible}
        selected={selected}
        allSelected={allVisibleSelected}
        onToggleAll={toggleAll}
        osFilter={osFilter}
        actFilter={actFilter}
        methodFilter={methodFilter}
        onOsFilter={(v) => { setOsFilter(v); setPage(0); }}
        onActFilter={(v) => { setActFilter(v); setPage(0); }}
        onMethodFilter={(v) => { setMethodFilter(v); setPage(0); }}
        onToggle={toggle}
        onRegenerate={(u) =>
          regen.mutate(u.id, {
            onSuccess: () => toast.push(`New link for ${u.name}`, 'ok'),
            onError: (e) => toast.push(errText(e, 'Could not regenerate'), 'bad'),
          })
        }
        onDelete={setDeleting}
      />

      <div className="table-foot">
        <span className="page-size">
          <Select
            value={String(pageSize)}
            onChange={(v) => {
              setPageSize(Number(v));
              setPage(0);
            }}
            options={PAGE_SIZES}
          />
        </span>
        <span className="pager">
          <button type="button" className="icon-btn" data-testid="prev-page" aria-label="Previous page" disabled={cur === 0} onClick={() => setPage(cur - 1)}>
            ←
          </button>
          <span className="pager-label">
            Page {cur + 1} of {pages}
          </span>
          <button type="button" className="icon-btn" data-testid="next-page" aria-label="Next page" disabled={cur >= pages - 1} onClick={() => setPage(cur + 1)}>
            →
          </button>
        </span>
      </div>

      <AddUserModal open={adding} onClose={() => setAdding(false)} />
      <Modal
        open={deleting !== null}
        title="Delete User?"
        onClose={() => setDeleting(null)}
        actions={
          <>
            <Button variant="secondary" onClick={() => setDeleting(null)}>
              Cancel
            </Button>
            <Button
              variant="danger"
              data-testid="delete-confirm"
              onClick={() => {
                const u = deleting;
                setDeleting(null);
                if (!u) return;
                setSelected((s) => {
                  const n = new Set(s);
                  n.delete(u.id);
                  return n;
                });
                del.mutate(u.id, {
                  onSuccess: () => toast.push(`${u.name} deleted`, 'ok'),
                  onError: (e) => toast.push(errText(e, 'Could not delete'), 'bad'),
                });
              }}
            >
              Delete
            </Button>
          </>
        }
      >
        {deleting && <p>{deleting.name} will lose access and their invite link stops working.</p>}
      </Modal>
      <Modal
        open={bulkDeleting}
        title="Delete Users?"
        onClose={() => setBulkDeleting(false)}
        actions={
          <>
            <Button variant="secondary" onClick={() => setBulkDeleting(false)}>
              Cancel
            </Button>
            <Button variant="danger" data-testid="bulk-delete-confirm" onClick={doBulkDelete}>
              Delete {selected.size}
            </Button>
          </>
        }
      >
        <p>{selected.size} user{selected.size === 1 ? '' : 's'} will lose access and their invite links stop working.</p>
      </Modal>
    </div>
  );
}
