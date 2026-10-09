import { useRef, useState } from 'react';
import { useUi } from '../store';
import { Breadcrumb } from './files/breadcrumb';
import { useDeleteFile, useFiles, useMkdir, useRename, useSetAccess, useStatus, type FileRow } from '../api';
import { AccessModal } from './files/access-modal';
import { DeleteDialog } from './files/delete-dialog';
import { NewFolderModal } from './files/new-folder-modal';
import { RenameModal } from './files/rename-modal';
import { Button } from '../ui/button';
import { IconPlus, IconSearch, IconUpload } from '../ui/icons';
import { FileTable, formatSize, type FileAction } from './files/file-table';
import { FilesHelp } from './files/files-help';
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
      <div className="files-bar">
        {depts.length > 1 && (
          <select
            className="ui-select"
            aria-label="Department"
            value={dept ?? ''}
            onChange={(e) => { setPicked(e.target.value); setFilePath(''); }}
          >
            {depts.map((d) => (
              <option key={d} value={d}>{d}</option>
            ))}
          </select>
        )}
        <span className="field-search">
          <span className="field-search__icon"><IconSearch size={16} /></span>
          <input
            type="search"
            className="ui-input"
            aria-label="Search files"
            placeholder="Search for file"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </span>
        <Button variant="secondary" className="btn-ico" data-testid="upload-file" disabled={!dept} onClick={() => input.current?.click()}>
          <IconUpload size={16} /> Upload
        </Button>
        <Button variant="secondary" className="btn-ico" disabled={!dept} onClick={() => setModal({ kind: 'newFolder' })}>
          <IconPlus size={16} /> New Folder
        </Button>
        <FilesHelp />
        <input ref={input} type="file" hidden multiple aria-label="File to upload" onChange={(e) => send(e.target.files)} />
      </div>

      <Breadcrumb path={filePath} onNavigate={setFilePath} />

      <div
        data-testid="drop-zone"
        className={`files-drop${over ? ' files-drop--over' : ''}`}
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
      >
        {over && <div className="files-drop__hint">Drop files to upload</div>}
        {body}
      </div>

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
