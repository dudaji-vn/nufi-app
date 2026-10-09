import { useEffect, useRef, useState } from 'react';
import { useRemoteWork, useRemoteWorkStatus, useStatus } from '../../api';
import { Button } from '../../ui/button';
import { IconCopy, IconMore } from '../../ui/icons';
import { useToast } from '../../ui/toast';

// The overflow (⋮) menu next to Config (Figma): Allow remote work, Data &
// Back up, App Update. These three are box-admin operations run with
// `nufi-box` on the box host — by design the hardened web console does NOT
// execute host commands (its sidecar only runs allowlisted `docker compose`
// ops). So the menu REFLECTS real state (mesh membership from /api/status) and
// hands the owner the exact command to run on the box, copied to the clipboard
// — not a fake success.
function host(url: string): string {
  try {
    return new URL(url).hostname;
  } catch {
    return url;
  }
}

export function MoreMenu() {
  const [open, setOpen] = useState(false);
  const { data } = useStatus();
  const mesh = (data?.box?.mesh as { joined?: boolean; serverUrl?: string; host?: string } | undefined) ?? {};
  const remoteWork = useRemoteWork();
  const remoteStatus = useRemoteWorkStatus();
  const root = useRef<HTMLDivElement>(null);
  const toast = useToast();

  // The toggle reflects whether the mesh (tailscale) container is actually
  // running — read live from the box (remoteStatus), NOT .env's mesh.joined,
  // which stays set after a stop. `on` is optimistic so the switch flips
  // instantly; the live read confirms it.
  const live = remoteStatus.data?.on;
  const [on, setOn] = useState(live ?? !!mesh.joined);
  useEffect(() => {
    if (live !== undefined) setOn(live);
  }, [live]);
  const joined = on;

  const toggleRemote = (next: boolean) => {
    setOn(next);
    remoteWork.mutate(next, {
      onSuccess: (r) => (r.ok ? toast.push(next ? 'Remote work enabled' : 'Remote work disabled', 'ok') : toast.push('The box did not report success', 'bad')),
      onError: (e) => {
        setOn(!next);
        toast.push((e as { error?: string }).error ?? 'Could not change remote work', 'bad');
      },
    });
  };

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

  // Copy a `nufi-box …` command for the owner to run on the box, and say so.
  const copyCmd = (cmd: string) => {
    navigator.clipboard.writeText(cmd).then(
      () => toast.push(`Copied — run “${cmd}” on the box`, 'ok'),
      () => toast.push(`Run “${cmd}” on the box`, 'neutral'),
    );
  };

  return (
    <div className="more" ref={root}>
      <Button variant="secondary" className="btn-ico btn-ico--square" data-testid="control-more" aria-label="More actions" onClick={() => setOpen((o) => !o)}>
        <IconMore size={16} />
      </Button>
      {open && (
        <div className="more-panel" role="menu" data-testid="more-panel">
          <div className="more-row">
            <div className="more-text">
              <div className="more-title">
                Allow remote work {joined && <span className="more-pill">Enabled</span>}
              </div>
              <div className="more-sub">{joined ? `On the mesh via ${host(mesh.serverUrl ?? '')}` : 'LAN-only — not on a mesh'}</div>
            </div>
            <label className="switch" aria-label="Allow remote work">
              <input
                type="checkbox"
                data-testid="remote-work-toggle"
                checked={joined}
                disabled={remoteWork.isPending}
                onChange={(e) => toggleRemote(e.target.checked)}
              />
              <span className="switch-track" />
            </label>
          </div>

          <div className="more-row">
            <div className="more-text">
              <div className="more-title">Data &amp; Back up</div>
              <div className="more-sub">Back up this box's data from its command line</div>
            </div>
            <button type="button" className="icon-btn" data-testid="more-backup" aria-label="Copy the backup command" onClick={() => copyCmd('nufi-box backup')}>
              <IconCopy size={16} />
            </button>
          </div>

          <div className="more-row">
            <div className="more-text">
              <div className="more-title">App Update</div>
              <div className="more-sub">Upgrade the box to the latest release</div>
            </div>
            <Button size="sm" data-testid="more-update" onClick={() => copyCmd('nufi-box update')}>
              Check for Update
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
