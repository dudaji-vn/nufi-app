import { useState } from 'react';
import type { Access, FileRow } from '../../api';
import { Button } from '../../ui/button';
import { Modal } from '../../ui/modal';
import { Radio } from '../../ui/radio';

export function AccessModal({ open, row, onClose, onSave }: { open: boolean; row: FileRow; onClose: () => void; onSave: (a: Access) => void }) {
  const [value, setValue] = useState<string>(row.access);
  return (
    <Modal
      open={open}
      title={`Accessibility ${row.name}`}
      onClose={onClose}
      actions={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={() => onSave(value as Access)}>Save Changes</Button>
        </>
      }
    >
      <Radio name="access" value="public" checked={value === 'public'} onChange={setValue} label="Public" hint="Every user can use all files of this folder on their NuFi Chat" />
      <Radio name="access" value="private" checked={value === 'private'} onChange={setValue} label="Private" hint="Only admin can use all files of this folder on their NuFi Chat" />
      <Radio name="access" value="specific" checked={false} onChange={() => {}} disabled label="Specific Users" hint="Only selected users can use all files of this folder on their NuFi Chat (coming soon)" />
    </Modal>
  );
}
