import { useRef, useState } from 'react';
import { useUi } from '../store';
import { Breadcrumb } from './files/breadcrumb';
import { useDeleteFile, useFiles, useMkdir, useRename, useSetAccess, useStatus, type FileRow } from '../api';
import { AccessModal } from './files/access-modal';
import { DeleteDialog } from './files/delete-dialog';
import { NewFolderModal } from './files/new-folder-modal';
import { RenameModal } from './files/rename-modal';
import { Button } from '../ui/button';
import { IconSearch } from '../ui/icons';
import { FileTable, formatSize, type FileAction } from './files/file-table';
import { useToast } from '../ui/toast';
import { UploadPanel, useUploader } from './files/upload-panel';

const errText = (e: unknown, fallback: string) => (e as { error?: string }).error ?? fallback;

export { formatSize };

const muted = { color: 'var(--gray-1)' } as const;

export function Files() {
  const status = useStatus();
  const depts = (status.data?.box.departments as string[] | undefined) ?? [];
  const [picked, setPicked] = useState<string>();
  const dept = picked && depts.includes(picked) ? picked : depts[0];
  const filePath = useUi((s) => s.filePath);
  const setFilePath = useUi((s) => s.setFilePath);
  const { data, isPending, error } = useFiles(dept, filePath);
  const uploader = useUploader(dept, filePath);
  const toast = useToast();
  const setAccess = useSetAccess(dept, filePath);
  const rename = useRename(dept, filePath);
  const deleteFile = useDeleteFile(dept, filePath);
  const mkdir = useMkdir(dept, filePath);
  const [modal, setModal] = useState<{ kind: 'access' | 'rename' | 'delete' | 'newFolder'; row?: FileRow } | null>(null);
  const [query, setQuery] = useState('');
  const [over, setOver] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  const send = (list: FileList | null | undefined) => {
    if (list && list.length) uploader.enqueue(Array.from(list));
    if (input.current) input.current.value = '';
  };

  const rel = (name: string) => (filePath ? `${filePath}/${name}` : name);
  const href = (name: string) =>
    `/api/files/${encodeURIComponent(dept ?? '')}/${rel(name).split('/').map(encodeURIComponent).join('/')}`;
  const open = (row: FileRow) => {
    setQuery('');
    setFilePath(rel(row.name));
  };
  const close = () => setModal(null);
  const run = (mutation: { mutate: (v: never, o: { onSuccess: () => void; onError: (e: unknown) => void }) => void }, v: unknown, ok: string) =>
    mutation.mutate(v as never, {
      onSuccess: () => {
        toast.push(ok, 'ok');
        close();
      },
      onError: (e) => toast.push(errText(e, 'Action failed'), 'bad'),
    });
  const onAction = (action: FileAction, row: FileRow) => {
    if (action === 'download') {
      const a = document.createElement('a');
      a.href = href(row.name);
      a.download = row.name;
      a.click();
    } else setModal({ kind: action, row });
  };

  let body;
  if (!dept) body = <p style={muted}>No departments configured.</p>;
  else if (isPending) body = <p role="status">Loading…</p>;
  else if (error) body = <p role="alert">Could not load files: {errText(error, 'unknown error')}</p>;
  else {
    body = <FileTable rows={data} search={query} onOpen={open} onAction={onAction} />;
  }

  return (
    <div data-testid="files">
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', marginBottom: 16 }}>
        <select className="ui-select" aria-label="Department" value={dept ?? ''} disabled={depts.length === 0} onChange={(e) => {
            setPicked(e.target.value);
            setFilePath('');
          }}>
          {depts.map((d) => (
            <option key={d} value={d}>
              {d}
            </option>
          ))}
        </select>
        <span className="field-search">
          <span className="field-search__icon"><IconSearch size={16} /></span>
          <input
            type="search"
            className="ui-input"
            aria-label="Search files"
            placeholder="Search by name"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </span>
        <Button data-testid="upload-file" disabled={!dept} onClick={() => input.current?.click()}>
          Upload
        </Button>
        <Button variant="secondary" disabled={!dept} onClick={() => setModal({ kind: 'newFolder' })}>
          New Folder
        </Button>
        <input ref={input} type="file" hidden multiple aria-label="File to upload" onChange={(e) => send(e.target.files)} />
      </div>

      <Breadcrumb path={filePath} onNavigate={setFilePath} />

      <div
        data-testid="drop-zone"
        onDragOver={(e) => {
          e.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setOver(false);
          if (dept) send(e.dataTransfer.files);
        }}
        style={{
          border: `2px dashed ${over ? 'var(--navy-2)' : 'var(--gray-3)'}`,
          borderRadius: 8,
          padding: 16,
          marginBottom: 16,
          textAlign: 'center',
          color: 'var(--gray-1)',
        }}
      >
        Drag and drop files here to upload
      </div>

      {body}

      {uploader.items.length > 0 && (
        <UploadPanel items={uploader.items} onCancel={uploader.cancel} onCancelAll={uploader.cancelAll} onDismiss={uploader.clear} />
      )}

      {modal?.kind === 'access' && modal.row && (
        <AccessModal key={modal.row.name} open row={modal.row} onClose={close} onSave={(access) => run(setAccess, { itemPath: rel(modal.row!.name), access }, 'Accessibility updated')} />
      )}
      {modal?.kind === 'rename' && modal.row && (
        <RenameModal key={modal.row.name} open row={modal.row} onClose={close} onSave={(newName) => run(rename, { itemPath: rel(modal.row!.name), newName }, 'Renamed')} />
      )}
      {modal?.kind === 'delete' && modal.row && (
        <DeleteDialog open row={modal.row} onClose={close} onConfirm={() => run(deleteFile, rel(modal.row!.name), `Deleted ${modal.row!.name}`)} />
      )}
      {modal?.kind === 'newFolder' && <NewFolderModal open onClose={close} onCreate={(name) => run(mkdir, name, 'Folder created')} />}
    </div>
  );
}
