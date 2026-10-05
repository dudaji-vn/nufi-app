import { useRef, useState } from 'react';
import { useFiles, useStatus, useUpload, type FileRow } from '../api';
import { Button } from '../ui/button';
import { Table, type Col } from '../ui/table';
import { useToast } from '../ui/toast';

const errText = (e: unknown, fallback: string) => (e as { error?: string }).error ?? fallback;

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

const fmtDate = (s: string) => (Number.isNaN(Date.parse(s)) ? '—' : new Date(s).toLocaleString());
const muted = { color: 'var(--gray-1)' } as const;

export function Files() {
  const status = useStatus();
  const depts = (status.data?.box.departments as string[] | undefined) ?? [];
  const [picked, setPicked] = useState<string>();
  const dept = picked && depts.includes(picked) ? picked : depts[0];
  const { data, isPending, error } = useFiles(dept);
  const upload = useUpload(dept);
  const toast = useToast();
  const [query, setQuery] = useState('');
  const [over, setOver] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  const send = (file: File | undefined) => {
    if (!file) return;
    upload.mutate(file, {
      onSuccess: () => toast.push(`Uploaded ${file.name}`, 'ok'),
      onError: (e) => toast.push(errText(e, 'Upload failed'), 'bad'),
    });
    if (input.current) input.current.value = '';
  };

  const href = (name: string) => `/api/files/${encodeURIComponent(dept ?? '')}/${encodeURIComponent(name)}`;
  const columns: Col<FileRow>[] = [
    { key: 'name', label: 'Name', render: (r) => (r.kind === 'file' ? <a href={href(r.name)}>{r.name}</a> : r.name) },
    { key: 'kind', label: 'Kind' },
    { key: 'size', label: 'Size', render: (r) => (r.kind === 'file' ? formatSize(r.size) : '—') },
    { key: 'uploadedAt', label: 'Uploaded', render: (r) => fmtDate(r.uploadedAt) },
    { key: 'modifiedAt', label: 'Modified', render: (r) => fmtDate(r.modifiedAt) },
    { key: 'owner', label: 'Owner (not yet available)', render: () => <span aria-disabled="true" style={muted}>—</span> },
    { key: 'access', label: 'Accessibility (not yet available)', render: () => <span aria-disabled="true" style={muted}>—</span> },
  ];

  let body;
  if (!dept) body = <p style={muted}>No departments configured.</p>;
  else if (isPending) body = <p role="status">Loading…</p>;
  else if (error) body = <p role="alert">Could not load files: {errText(error, 'unknown error')}</p>;
  else {
    const q = query.trim().toLowerCase();
    const rows = q ? data.filter((r) => r.name.toLowerCase().includes(q)) : data;
    body = (
      <Table
        columns={columns}
        rows={rows}
        rowKey={(r) => r.name}
        rowTestId={(r) => `file-row-${r.name}`}
        empty={data.length === 0 ? 'Your uploaded files will be listed here' : 'No files match your search'}
      />
    );
  }

  return (
    <div data-testid="files">
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', marginBottom: 16 }}>
        <select aria-label="Department" value={dept ?? ''} disabled={depts.length === 0} onChange={(e) => setPicked(e.target.value)}>
          {depts.map((d) => (
            <option key={d} value={d}>
              {d}
            </option>
          ))}
        </select>
        <input
          type="search"
          aria-label="Search files"
          placeholder="Search by name"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          style={{ flex: 1, minWidth: 160 }}
        />
        <Button data-testid="upload-file" disabled={!dept || upload.isPending} onClick={() => input.current?.click()}>
          Upload
        </Button>
        <input ref={input} type="file" hidden aria-label="File to upload" onChange={(e) => send(e.target.files?.[0])} />
      </div>

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
          if (dept) send(e.dataTransfer.files[0]);
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
        Drag and drop a file here to upload
      </div>

      {body}
    </div>
  );
}
