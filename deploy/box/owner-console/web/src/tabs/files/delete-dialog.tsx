import type { FileRow } from '../../api';
import { Button } from '../../ui/button';
import { Modal } from '../../ui/modal';

export function DeleteDialog({ open, row, onClose, onConfirm }: { open: boolean; row: FileRow; onClose: () => void; onConfirm: () => void }) {
  const dir = row.kind === 'dir';
  return (
    <Modal
      open={open}
      title={dir ? `Delete folder "${row.name}"` : `Delete ${row.name}?`}
      onClose={onClose}
      actions={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="danger" onClick={onConfirm}>
            Delete
          </Button>
        </>
      }
    >
      <p style={{ margin: 0 }}>
        {dir
          ? 'This action is permanent and can not be undone. All files of this folder will also be deleted. No one can use these file of this folder on NuFi anymore. Are you sure to delete it?'
          : 'This action is permanent and can not be undone.'}
      </p>
    </Modal>
  );
}
