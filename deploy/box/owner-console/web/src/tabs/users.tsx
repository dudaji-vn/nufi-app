import { useRef, useState } from 'react';
import { exportUsersCsv, useDeleteUser, useImportUsers, useRegenerate, useUsers, type UserRow } from '../api';
import { Button } from '../ui/button';
import { Modal } from '../ui/modal';
import { useToast } from '../ui/toast';
import { IconPlus, IconSearch, IconUpload } from '../ui/icons';
import { AddUserModal } from './users/add-user-modal';
import { UserTable } from './users/user-table';

const PAGE_SIZE = 10;
const errText = (e: unknown, fallback: string) => (e as { error?: string }).error ?? fallback;

export function Users() {
  const { data, isPending, error } = useUsers();
  const del = useDeleteUser();
  const regen = useRegenerate();
  const imp = useImportUsers();
  const toast = useToast();
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(0);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [adding, setAdding] = useState(false);
  const [deleting, setDeleting] = useState<UserRow | null>(null);
  const file = useRef<HTMLInputElement>(null);

  if (isPending) return <p role="status">Loading…</p>;
  if (error) return <p role="alert">Could not load users: {errText(error, 'unknown error')}</p>;

  const q = query.trim().toLowerCase();
  const filtered = q ? data.filter((u) => u.name.toLowerCase().includes(q)) : data;
  const pages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const cur = Math.min(page, pages - 1);
  const visible = filtered.slice(cur * PAGE_SIZE, (cur + 1) * PAGE_SIZE);

  const toggle = (id: string) =>
    setSelected((s) => {
      const n = new Set(s);
      if (!n.delete(id)) n.add(id);
      return n;
    });

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
      </div>

      {selected.size > 0 && (
        <div data-testid="bulk-bar" style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 12 }}>
          <span>{selected.size} selected</span>
          <Button
            variant="secondary"
            size="sm"
            data-testid="export-csv"
            onClick={() => exportUsersCsv([...selected]).catch((e) => toast.push(errText(e, 'Export failed'), 'bad'))}
          >
            Export CSV
          </Button>
          <Button variant="ghost" size="sm" onClick={() => setSelected(new Set())}>
            Clear
          </Button>
        </div>
      )}

      <UserTable
        rows={visible}
        selected={selected}
        onToggle={toggle}
        onRegenerate={(u) =>
          regen.mutate(u.id, {
            onSuccess: () => toast.push(`New link for ${u.name}`, 'ok'),
            onError: (e) => toast.push(errText(e, 'Could not regenerate'), 'bad'),
          })
        }
        onDelete={setDeleting}
      />

      <div style={{ display: 'flex', gap: 8, alignItems: 'center', justifyContent: 'flex-end', marginTop: 12 }}>
        <span style={{ color: 'var(--gray-1)', fontSize: 'var(--fs-sm)' }}>
          Page {cur + 1} of {pages} · {filtered.length} user{filtered.length === 1 ? '' : 's'}
        </span>
        <Button variant="secondary" size="sm" data-testid="prev-page" disabled={cur === 0} onClick={() => setPage(cur - 1)}>
          Previous
        </Button>
        <Button variant="secondary" size="sm" data-testid="next-page" disabled={cur >= pages - 1} onClick={() => setPage(cur + 1)}>
          Next
        </Button>
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
    </div>
  );
}
