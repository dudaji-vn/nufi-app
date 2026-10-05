import { useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Button } from '../../ui/button';
import './upload-panel.css';

export type UploadStatus = 'uploading' | 'done' | 'error' | 'cancelled';
export type UploadItem = { id: number; name: string; progress: number; status: UploadStatus; error?: string };

let nextId = 1;

// Queue of multipart uploads into one folder. XHR (not fetch) for real progress.
export function useUploader(dept: string | undefined, path: string) {
  const qc = useQueryClient();
  const [items, setItems] = useState<UploadItem[]>([]);
  const xhrs = useRef(new Map<number, XMLHttpRequest>());

  const patch = useCallback((id: number, p: Partial<UploadItem>) => setItems((cur) => cur.map((i) => (i.id === id ? { ...i, ...p } : i))), []);

  const enqueue = useCallback(
    (files: File[]) => {
      if (!dept) return;
      const target = path;
      for (const file of files) {
        const id = nextId++;
        setItems((cur) => [...cur, { id, name: file.name, progress: 0, status: 'uploading' }]);
        const xhr = new XMLHttpRequest();
        xhrs.current.set(id, xhr);
        xhr.open('POST', `/api/files?dept=${encodeURIComponent(dept)}&path=${encodeURIComponent(target)}`);
        xhr.withCredentials = true;
        xhr.upload.onprogress = (e) => {
          if (e.lengthComputable) patch(id, { progress: e.loaded / e.total });
        };
        xhr.onload = () => {
          xhrs.current.delete(id);
          if (xhr.status === 401) window.location.assign('/login');
          if (xhr.status >= 200 && xhr.status < 300) {
            patch(id, { progress: 1, status: 'done' });
            void qc.invalidateQueries({ queryKey: ['files', dept, target] });
          } else {
            let msg = `HTTP ${xhr.status}`;
            try {
              msg = (JSON.parse(xhr.responseText) as { error?: string }).error ?? msg;
            } catch {
              /* keep fallback */
            }
            patch(id, { status: 'error', error: msg });
          }
        };
        xhr.onerror = () => {
          xhrs.current.delete(id);
          patch(id, { status: 'error', error: 'Network error' });
        };
        const form = new FormData();
        form.append('file', file);
        xhr.send(form);
      }
    },
    [dept, path, qc, patch],
  );

  const cancel = useCallback(
    (id: number) => {
      xhrs.current.get(id)?.abort();
      xhrs.current.delete(id);
      patch(id, { status: 'cancelled' });
    },
    [patch],
  );

  const cancelAll = useCallback(() => {
    for (const [id, x] of xhrs.current) {
      x.abort();
      patch(id, { status: 'cancelled' });
    }
    xhrs.current.clear();
  }, [patch]);

  const clear = useCallback(() => setItems((cur) => cur.filter((i) => i.status === 'uploading')), []);

  useEffect(() => {
    const live = xhrs.current;
    return () => {
      for (const x of live.values()) x.abort();
      live.clear();
    };
  }, []);

  return { items, enqueue, cancel, cancelAll, clear };
}

type Props = { items: UploadItem[]; onCancel: (id: number) => void; onCancelAll: () => void; onDismiss: () => void };

export function UploadPanel({ items, onCancel, onCancelAll, onDismiss }: Props) {
  const [collapsed, setCollapsed] = useState(false);
  const done = items.filter((i) => i.status === 'done').length;
  const active = items.some((i) => i.status === 'uploading');
  return (
    <section className="upload-panel" aria-label="Uploads" data-testid="upload-panel">
      <div className="upload-panel__head">
        <span>
          Uploading ({done}/{items.length} items)
        </span>
        <span>
          <button type="button" className="upload-panel__btn" aria-label={collapsed ? 'Expand' : 'Collapse'} onClick={() => setCollapsed((c) => !c)}>
            {collapsed ? '▴' : '▾'}
          </button>
          {!active && (
            <button type="button" className="upload-panel__btn" aria-label="Dismiss" onClick={onDismiss}>
              ✕
            </button>
          )}
        </span>
      </div>
      {!collapsed && (
        <>
          <ul className="upload-panel__list">
            {items.map((i) => (
              <li key={i.id} className="upload-panel__row" data-testid="upload-row" data-status={i.status}>
                <span className="upload-panel__name">{i.name}</span>
                {i.status === 'done' ? (
                  <span aria-label="Done" style={{ color: 'var(--ok)' }}>✓</span>
                ) : i.status === 'uploading' ? (
                  <button type="button" className="upload-panel__btn" aria-label={`Cancel ${i.name}`} onClick={() => onCancel(i.id)}>
                    ✕
                  </button>
                ) : (
                  <span style={{ color: 'var(--gray-1)' }}>{i.status === 'cancelled' ? 'Cancelled' : 'Failed'}</span>
                )}
                <div className="upload-panel__bar" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(i.progress * 100)}>
                  <div className="upload-panel__fill" style={{ width: `${Math.round(i.progress * 100)}%` }} />
                </div>
                {i.error && <span className="upload-panel__err">{i.error}</span>}
              </li>
            ))}
          </ul>
          {active && (
            <div className="upload-panel__foot">
              <Button variant="ghost" size="sm" onClick={onCancelAll}>
                Cancel all
              </Button>
            </div>
          )}
        </>
      )}
    </section>
  );
}
