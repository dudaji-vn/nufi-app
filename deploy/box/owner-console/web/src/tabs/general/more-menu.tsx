import { useEffect, useRef, useState } from 'react';
import { useStatus } from '../../api';
import { Button } from '../../ui/button';
import { IconMore, IconRestart } from '../../ui/icons';
import { useToast } from '../../ui/toast';

// The overflow (⋮) menu next to Config (Figma): a small panel, not a list —
// Allow remote work (toggle), Data & Back up (last-backup + refresh), App Update
// (current version + check). Backend wiring for backup/update/remote is not in
// yet, so those actions are informational for now; the toggle reflects whether
// the box is on a mesh (remote-reachable).
export function MoreMenu() {
  const [open, setOpen] = useState(false);
  const { data } = useStatus();
  const mesh = (data?.box?.mesh as { joined?: boolean } | undefined) ?? {};
  const [remote, setRemote] = useState<boolean>(!!mesh.joined);
  const root = useRef<HTMLDivElement>(null);
  const toast = useToast();

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
    <div className="more" ref={root}>
      <Button
        variant="secondary"
        className="btn-ico btn-ico--square"
        data-testid="control-more"
        aria-label="More actions"
        onClick={() => setOpen((o) => !o)}
      >
        <IconMore size={16} />
      </Button>
      {open && (
        <div className="more-panel" role="menu" data-testid="more-panel">
          <div className="more-row">
            <div className="more-text">
              <div className="more-title">
                Allow remote work {remote && <span className="more-pill">Enabled</span>}
              </div>
            </div>
            <label className="switch" aria-label="Allow remote work">
              <input
                type="checkbox"
                checked={remote}
                onChange={(e) => {
                  setRemote(e.target.checked);
                  toast.push(e.target.checked ? 'Remote work enabled' : 'Remote work disabled', 'ok');
                }}
              />
              <span className="switch-track" />
            </label>
          </div>

          <div className="more-row">
            <div className="more-text">
              <div className="more-title">Data &amp; Back up</div>
              <div className="more-sub">No backup yet</div>
            </div>
            <button type="button" className="icon-btn" aria-label="Back up now" onClick={() => toast.push('Backup started', 'ok')}>
              <IconRestart size={16} />
            </button>
          </div>

          <div className="more-row">
            <div className="more-text">
              <div className="more-title">App Update</div>
              <div className="more-sub">Current v1.0.0</div>
            </div>
            <Button size="sm" onClick={() => toast.push("You're on the latest version", 'ok')}>
              Check for Update
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
