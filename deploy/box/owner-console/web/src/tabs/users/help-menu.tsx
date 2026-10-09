import { useEffect, useRef, useState } from 'react';
import { IconDownload, IconHelp } from '../../ui/icons';

// The "?" guide next to Upload CSV (Figma): a small panel explaining the bulk
// operations — add many users from a CSV (with a downloadable template), and
// the two export formats. The Template button hands the owner the exact two
// columns POST /api/users/import accepts (name,os), with a few examples.
const TEMPLATE = 'name,os\nAlice Tran,windows\nMinh Nguyen,macos\nLan Pham,linux\n';

export function HelpMenu() {
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

  const downloadTemplate = () => {
    const url = URL.createObjectURL(new Blob([TEMPLATE], { type: 'text/csv' }));
    const a = document.createElement('a');
    a.href = url;
    a.download = 'nufi-users-template.csv';
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="help" ref={root}>
      <button
        type="button"
        className="help-btn"
        data-testid="help-menu"
        aria-label="How to bulk add and export users"
        onClick={() => setOpen((o) => !o)}
      >
        <IconHelp size={18} />
      </button>
      {open && (
        <div className="help-panel" role="menu" data-testid="help-panel">
          <div className="help-sec">
            <div className="help-sec__head">
              <div className="help-sec__title">Bulk add users by upload CSV</div>
              <button type="button" className="help-tmpl" data-testid="download-template" onClick={downloadTemplate}>
                <IconDownload size={16} /> Template
              </button>
            </div>
            <p className="help-sec__desc">Download the template below, add user details, and upload the .csv file.</p>
          </div>
          <div className="help-sec">
            <div className="help-sec__title">Export CSV</div>
            <p className="help-sec__desc">Select users from the list to export their local invitation links.</p>
          </div>
          <div className="help-sec">
            <div className="help-sec__title">Export ZIP</div>
            <p className="help-sec__desc">Select users from the list to export their .join remote access files.</p>
          </div>
        </div>
      )}
    </div>
  );
}
