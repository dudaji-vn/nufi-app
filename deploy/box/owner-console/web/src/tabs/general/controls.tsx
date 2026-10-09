import { useState } from 'react';
import { useControl, type ControlAction } from '../../api';
import { Button } from '../../ui/button';
import { Modal } from '../../ui/modal';
import { ContextMenu } from '../../ui/context-menu';
import { IconChat, IconGear, IconLogout, IconMore, IconPower, IconRestart, IconSparkles, IconStop } from '../../ui/icons';
import { useToast } from '../../ui/toast';
import { ConfigModal } from './config';

// The whole-box target understood by POST /api/control.
export const BOX = '__box__';

const PAST: Record<ControlAction, string> = { start: 'started', restart: 'restarted', stop: 'stopped' };
const TITLE: Record<'restart' | 'stop', string> = { restart: 'Restart Service?', stop: 'Stop Service?' };
const BODY: Record<'restart' | 'stop', string> = {
  restart:
    'It will take about 1–2 minutes to restart AI models. All current running processes will be cancelled. Are you sure to restart service?',
  stop: 'This action will disconnect all users and stop all currently running processes. Are you sure to stop service?',
};

export function Controls({ active }: { active: boolean }) {
  const [confirm, setConfirm] = useState<'restart' | 'stop' | null>(null);
  const [configOpen, setConfigOpen] = useState(false);
  const control = useControl();
  const toast = useToast();

  const fire = (action: ControlAction) => {
    control.mutate(
      { action, service: BOX },
      {
        onSuccess: (r) => (r.ok ? toast.push(`Service ${PAST[action]}`, 'ok') : toast.push(`Could not ${action} service`, 'bad')),
        onError: (e) => toast.push((e as { error?: string }).error ?? `Could not ${action} service`, 'bad'),
      },
    );
  };

  // Overflow menu: restart ONE service (not the whole box), and sign out.
  const restartOne = (service: string, label: string) =>
    control.mutate(
      { action: 'restart', service },
      {
        onSuccess: (r) => toast.push(r.ok ? `${label} restarted` : `Could not restart ${label}`, r.ok ? 'ok' : 'bad'),
        onError: (e) => toast.push((e as { error?: string }).error ?? `Could not restart ${label}`, 'bad'),
      },
    );
  const signOut = () => {
    fetch('/logout', { method: 'POST', credentials: 'same-origin' }).finally(() => window.location.assign('/login'));
  };
  const menuItems = [
    { label: 'Restart chat', icon: <IconChat size={15} />, onSelect: () => restartOne('librechat', 'Chat') },
    { label: 'Restart AI gateway', icon: <IconSparkles size={15} />, onSelect: () => restartOne('litellm-proxy', 'AI gateway') },
    { label: 'Sign out', icon: <IconLogout size={15} />, danger: true, onSelect: signOut },
  ];

  return (
    <div className="gen-controls" data-testid="controls">
      <span className="status-pill">
        <span className="status-pill__label">Status:</span>
        <span className={`status-pill__val status-pill__val--${active ? 'ok' : 'bad'}`} data-testid="status-pill">
          {active ? 'Active' : 'Degraded'}
        </span>
        <span className={`dot dot--${active ? 'ok' : 'bad'}`} aria-hidden="true" />
      </span>
      <Button className="btn-ico" data-testid="control-start" disabled={control.isPending || active} onClick={() => fire('start')}>
        <IconPower size={16} /> Start Service
      </Button>
      <Button className="btn-ico" data-testid="control-restart" disabled={control.isPending} onClick={() => setConfirm('restart')}>
        <IconRestart size={16} /> Restart Service
      </Button>
      <Button variant="danger" className="btn-ico" data-testid="control-stop" disabled={control.isPending} onClick={() => setConfirm('stop')}>
        <IconStop size={16} /> Stop Service
      </Button>
      <Button variant="secondary" className="btn-ico" data-testid="control-config" onClick={() => setConfigOpen(true)}>
        <IconGear size={16} /> Config
      </Button>
      <ContextMenu items={menuItems}>
        <Button variant="secondary" className="btn-ico btn-ico--square" data-testid="control-more" aria-label="More actions">
          <IconMore size={16} />
        </Button>
      </ContextMenu>
      <ConfigModal open={configOpen} onClose={() => setConfigOpen(false)} />
      <Modal
        open={confirm !== null}
        title={confirm ? TITLE[confirm] : ''}
        onClose={() => setConfirm(null)}
        actions={
          <>
            <Button variant="secondary" data-testid="confirm-cancel" onClick={() => setConfirm(null)}>
              Cancel
            </Button>
            <Button
              variant={confirm === 'stop' ? 'danger' : 'primary'}
              data-testid="confirm-ok"
              onClick={() => {
                if (confirm) fire(confirm);
                setConfirm(null);
              }}
            >
              {confirm === 'stop' ? 'Stop' : 'Restart'}
            </Button>
          </>
        }
      >
        {confirm && <p>{BODY[confirm]}</p>}
      </Modal>
    </div>
  );
}
