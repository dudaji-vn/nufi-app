import { useState } from 'react';
import { useControl, type ControlAction } from '../../api';
import { Button } from '../../ui/button';
import { Modal } from '../../ui/modal';
import { useToast } from '../../ui/toast';

// Mirrors the backend allowlist (src/exec.ts SERVICES).
export const SERVICES = ['librechat', 'litellm-proxy', 'rag_api', 'ollama', 'caddy', 'mongodb', 'postgres', 'studio'];

const PAST: Record<ControlAction, string> = { start: 'started', restart: 'restarted', stop: 'stopped' };
const TITLE: Record<'restart' | 'stop', string> = { restart: 'Restart Service?', stop: 'Stop Service?' };
const BODY: Record<'restart' | 'stop', string> = {
  restart:
    'It will take about 1–2 minutes to restart AI models. All current running processes will be cancelled. Are you sure to restart service?',
  stop: 'All current running processes will be cancelled. Are you sure to stop service?',
};

export function Controls() {
  const [service, setService] = useState(SERVICES[0]);
  const [confirm, setConfirm] = useState<'restart' | 'stop' | null>(null);
  const control = useControl();
  const toast = useToast();

  const fire = (action: ControlAction) => {
    control.mutate(
      { action, service },
      {
        onSuccess: (r) => (r.ok ? toast.push(`${service} ${PAST[action]}`, 'ok') : toast.push(`Could not ${action} ${service}`, 'bad')),
        onError: (e) => toast.push((e as { error?: string }).error ?? `Could not ${action} ${service}`, 'bad'),
      },
    );
  };

  return (
    <div data-testid="controls" style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', marginBottom: 16 }}>
      <select aria-label="Service" data-testid="control-service" value={service} onChange={(e) => setService(e.target.value)}>
        {SERVICES.map((s) => (
          <option key={s} value={s}>
            {s}
          </option>
        ))}
      </select>
      <Button data-testid="control-start" disabled={control.isPending} onClick={() => fire('start')}>
        Start
      </Button>
      <Button variant="secondary" data-testid="control-restart" disabled={control.isPending} onClick={() => setConfirm('restart')}>
        Restart
      </Button>
      <Button variant="danger" data-testid="control-stop" disabled={control.isPending} onClick={() => setConfirm('stop')}>
        Stop
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
