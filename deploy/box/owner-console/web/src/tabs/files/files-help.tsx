import { useEffect, useRef, useState } from 'react';
import { IconHelp } from '../../ui/icons';

// The "?" guide next to Upload (Figma): a short popover explaining how File
// Sharing works — uploading, accessibility, and folders.
export function FilesHelp() {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => root.current && !root.current.contains(e.target as Node) && setOpen(false);
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false);
    window.addEventListener('mousedown', onDown);
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('mousedown', onDown);
      window.removeEventListener('keydown', onKey);
    };
  }, [open]);

  return (
    <div className="help" ref={root}>
      <button type="button" className="help-btn" data-testid="files-help" aria-label="How file sharing works" onClick={() => setOpen((o) => !o)}>
        <IconHelp size={18} />
      </button>
      {open && (
        <div className="help-panel" role="menu" data-testid="files-help-panel">
          <div className="help-sec">
            <div className="help-sec__title">Upload files</div>
            <p className="help-sec__desc">Click Upload, or drag &amp; drop files onto the list. Files are shared within the selected department.</p>
          </div>
          <div className="help-sec">
            <div className="help-sec__title">Public vs Private</div>
            <p className="help-sec__desc">Public — anyone in the department can open it. Private — only you. Change it from a file's ⋮ menu → Accessibility.</p>
          </div>
          <div className="help-sec">
            <div className="help-sec__title">Folders</div>
            <p className="help-sec__desc">Use New Folder to organise files; open a folder to upload inside it.</p>
          </div>
        </div>
      )}
    </div>
  );
}
