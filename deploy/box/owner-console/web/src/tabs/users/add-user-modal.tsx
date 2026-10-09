import { useState } from 'react';
import { connectorUrl, useAddUser, type UserOs } from '../../api';
import { Button } from '../../ui/button';
import { Input } from '../../ui/input';
import { Select } from '../../ui/select';
import { Modal } from '../../ui/modal';
import { useToast } from '../../ui/toast';

type Method = 'private' | 'public';

const OS_OPTS = [
  { value: 'macos', label: 'macOS' },
  { value: 'windows', label: 'Windows' },
  { value: 'linux', label: 'Linux' },
];
const METHOD_OPTS = [
  { value: 'private', label: 'Private — local LAN link (recommended)' },
  { value: 'public', label: 'Public — downloadable join file' },
];

export function AddUserModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [name, setName] = useState('');
  const [os, setOs] = useState<UserOs>('macos');
  const [method, setMethod] = useState<Method>('private');
  const add = useAddUser();
  const toast = useToast();
  const valid = name.trim().length > 0;

  const close = () => {
    setName('');
    setOs('macos');
    setMethod('private');
    onClose();
  };
  const submit = () => {
    if (!valid) return;
    add.mutate(
      { name: name.trim(), os, method },
      {
        onSuccess: (u) => {
          toast.push('User added', 'ok');
          // Public = hand the owner the join file to send; Private = the link in the table.
          if (method === 'public') {
            const a = document.createElement('a');
            a.href = connectorUrl(u);
            a.download = '';
            document.body.appendChild(a);
            a.click();
            a.remove();
          }
          close();
        },
        onError: (e) => toast.push((e as { error?: string }).error ?? 'Could not add user', 'bad'),
      },
    );
  };

  return (
    <Modal
      open={open}
      title="Add user"
      onClose={close}
      actions={
        <>
          <Button variant="secondary" onClick={close}>
            Cancel
          </Button>
          <Button data-testid="add-user-submit" disabled={!valid || add.isPending} onClick={submit}>
            Add User
          </Button>
        </>
      }
    >
      <div className="form-grid">
        <p className="form-intro">Add a user to your air-gapped NuFi. There are two methods:</p>
        <ul className="form-methods">
          <li>
            <b>Public</b> — a join file you send to the user to install on their machine. Your data may be at risk if the file
            leaks.
          </li>
          <li>
            <b>Private</b> — a local link to download the join file; only a user on the same LAN can open it, for maximum
            security. <b>(Recommended)</b>
          </li>
        </ul>
        <label className="form-field">
          <span className="form-label">
            User Name <i className="req">*</i>
          </span>
          <Input data-testid="add-user-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Enter user name" autoFocus />
        </label>
        <label className="form-field">
          <span className="form-label">
            OS <i className="req">*</i>
          </span>
          <Select value={os} onChange={(v) => setOs(v as UserOs)} options={OS_OPTS} />
        </label>
        <label className="form-field">
          <span className="form-label">
            Adding method <i className="req">*</i>
          </span>
          <Select value={method} onChange={(v) => setMethod(v as Method)} options={METHOD_OPTS} />
        </label>
      </div>
    </Modal>
  );
}
