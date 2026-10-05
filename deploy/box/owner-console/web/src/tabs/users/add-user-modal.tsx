import { useState } from 'react';
import { useAddUser, type UserOs } from '../../api';
import { Button } from '../../ui/button';
import { Modal } from '../../ui/modal';
import { useToast } from '../../ui/toast';

const OSES: { id: UserOs; label: string }[] = [
  { id: 'macos', label: 'macOS' },
  { id: 'windows', label: 'Windows' },
  { id: 'linux', label: 'Linux' },
];

export function AddUserModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [name, setName] = useState('');
  const [os, setOs] = useState<UserOs>('macos');
  const add = useAddUser();
  const toast = useToast();
  const valid = name.trim().length > 0;

  const close = () => {
    setName('');
    setOs('macos');
    onClose();
  };
  const submit = () => {
    if (!valid) return;
    add.mutate(
      { name: name.trim(), os },
      {
        onSuccess: () => {
          toast.push('User added', 'ok');
          close();
        },
        onError: (e) => toast.push((e as { error?: string }).error ?? 'Could not add user', 'bad'),
      },
    );
  };

  return (
    <Modal
      open={open}
      title="Add User"
      onClose={close}
      actions={
        <>
          <Button variant="secondary" onClick={close}>
            Cancel
          </Button>
          <Button data-testid="add-user-submit" disabled={!valid || add.isPending} onClick={submit}>
            Add
          </Button>
        </>
      }
    >
      <form
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
        style={{ display: 'grid', gap: 12 }}
      >
        <label style={{ display: 'grid', gap: 4 }}>
          Name
          <input value={name} onChange={(e) => setName(e.target.value)} autoFocus />
        </label>
        <label style={{ display: 'grid', gap: 4 }}>
          OS
          <select value={os} onChange={(e) => setOs(e.target.value as UserOs)}>
            {OSES.map((o) => (
              <option key={o.id} value={o.id}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
      </form>
    </Modal>
  );
}
