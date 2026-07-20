import type * as t from '@/types';
import {
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui';
import { useLocalize } from '@/hooks';

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  confirmType = 'danger',
  saving,
  error,
  onConfirm,
  onCancel,
}: t.ConfirmDialogProps) {
  const localize = useLocalize();
  const confirmVariant = confirmType === 'danger' ? 'destructive' : 'default';

  return (
    <Dialog
      open={open}
      onOpenChange={(isOpen) => {
        if (!isOpen) onCancel();
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          {description && <DialogDescription>{description}</DialogDescription>}
        </DialogHeader>

        {error && (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}

        <DialogFooter>
          <Button type="button" variant="outline" onClick={onCancel} disabled={saving}>
            {localize('com_ui_cancel')}
          </Button>
          <Button type="button" variant={confirmVariant} onClick={onConfirm} disabled={saving}>
            {confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
