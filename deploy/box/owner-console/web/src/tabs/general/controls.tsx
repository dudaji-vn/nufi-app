import { useState } from 'react';
import { useControl, type ControlAction } from '../../api';
import { Badge } from '../../ui/badge';
import { Button } from '../../ui/button';
import { Modal } from '../../ui/modal';
import { useToast } from '../../ui/toast';

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

  return (
    <div data-testid="controls" style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', marginBottom: 16 }}>
      <span style={{ display: 'inline-flex', gap: 8, alignItems: 'center', marginRight: 'auto' }}>
        Status:
        <Badge tone={active ? 'ok' : 'bad'}>
          <span data-testid="status-pill">{active ? 'Active' : 'Degraded'}</span>
        </Badge>
      </span>
      <Button data-testid="control-start" disabled={control.isPending} onClick={() => fire('start')}>
        Start Service
      </Button>
      <Button variant="secondary" data-testid="control-restart" disabled={control.isPending} onClick={() => setConfirm('restart')}>
        Restart Service
      </Button>
      <Button variant="danger" data-testid="control-stop" disabled={control.isPending} onClick={() => setConfirm('stop')}>
        Stop Service
      </Button>
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
