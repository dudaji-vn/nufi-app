import { useState } from 'react';
import type { FileRow } from '../../api';
import { Button } from '../../ui/button';
import { Input } from '../../ui/input';
import { Modal } from '../../ui/modal';

export function RenameModal({ open, row, onClose, onSave }: { open: boolean; row: FileRow; onClose: () => void; onSave: (name: string) => void }) {
  const [name, setName] = useState(row.name);
  const submit = () => name.trim() && onSave(name.trim());
  return (
    <Modal
      open={open}
      title="Rename"
      onClose={onClose}
      actions={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={!name.trim()} onClick={submit}>
            Save Changes
          </Button>
        </>
      }
    >
      <form onSubmit={(e) => { e.preventDefault(); submit(); }}>
        <Input aria-label="Name" value={name} autoFocus onChange={(e) => setName(e.target.value)} />
      </form>
    </Modal>
  );
}
