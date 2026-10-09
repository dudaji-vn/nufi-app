import { useEffect, useState } from 'react';
import { useApplyConfig, useConfig } from '../../api';
import { Button } from '../../ui/button';
import { Input } from '../../ui/input';
import { Modal } from '../../ui/modal';
import { useToast } from '../../ui/toast';

// The Config modal: edit the model endpoint the box talks to (AI Base Location +
// Model Name) and apply it live. These live in litellm/config.yaml — the ONE box
// config file that is not .env — so the change is applied by re-creating the AI
// gateway, no box secret involved. Settings that live only in .env (sign-up,
// departments, …) are changed on the box itself, not here.
export function ConfigModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { data, isPending } = useConfig();
  const apply = useApplyConfig();
  const toast = useToast();
  const [aiBaseUrl, setAiBaseUrl] = useState('');
  const [aiModel, setAiModel] = useState('');

  // Load the current values when the modal opens (or they arrive).
  useEffect(() => {
    if (open && data) {
      setAiBaseUrl(data.aiBaseUrl);
      setAiModel(data.aiModel);
    }
  }, [open, data]);

  const save = () => {
    apply.mutate(
      { aiBaseUrl: aiBaseUrl.trim(), aiModel: aiModel.trim() },
      {
        onSuccess: (r) => {
          toast.push(r.ok ? 'Model updated — AI gateway restarting' : 'Saved, but the restart reported an error', r.ok ? 'ok' : 'bad');
          onClose();
        },
        onError: (e) => toast.push((e as { error?: string }).error ?? 'Could not apply config', 'bad'),
      },
    );
  };

  return (
    <Modal
      open={open}
      title="Config"
      onClose={onClose}
      actions={
        <>
          <Button variant="secondary" data-testid="config-cancel" onClick={onClose} disabled={apply.isPending}>
            Cancel
          </Button>
          <Button data-testid="config-save" onClick={save} disabled={apply.isPending || isPending}>
            {apply.isPending ? 'Saving…' : 'Save and Restart Service'}
          </Button>
        </>
      }
    >
      <div className="config-form">
        <label className="config-field">
          <span>AI Base Location</span>
          <Input
            data-testid="config-base"
            value={aiBaseUrl}
            onChange={(e) => setAiBaseUrl(e.target.value)}
            placeholder="http://192.168.100:8080/v1"
            spellCheck={false}
            autoComplete="off"
          />
        </label>
        <label className="config-field">
          <span>Model Name</span>
          <Input
            data-testid="config-model"
            value={aiModel}
            onChange={(e) => setAiModel(e.target.value)}
            placeholder="llama-3-70b-instruct"
            spellCheck={false}
            autoComplete="off"
          />
        </label>
        <p className="config-note">
          Saving restarts the AI gateway (a few seconds); current chats reconnect. Sign-up and departments are set on the box
          itself, not here.
        </p>
      </div>
    </Modal>
  );
}
