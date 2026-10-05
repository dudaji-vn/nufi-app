import { useState } from 'react';
import { Button } from '../../ui/button';
import { Input } from '../../ui/input';
import { Modal } from '../../ui/modal';

export function NewFolderModal({ open, onClose, onCreate }: { open: boolean; onClose: () => void; onCreate: (name: string) => void }) {
  const [name, setName] = useState('');
  const submit = () => name.trim() && onCreate(name.trim());
  return (
    <Modal
      open={open}
      title="New Folder"
      onClose={onClose}
      actions={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={!name.trim()} onClick={submit}>
            Create
          </Button>
        </>
      }
    >
      <form onSubmit={(e) => { e.preventDefault(); submit(); }}>
        <Input aria-label="Folder name" placeholder="Folder name" value={name} autoFocus onChange={(e) => setName(e.target.value)} />
      </form>
    </Modal>
  );
}
