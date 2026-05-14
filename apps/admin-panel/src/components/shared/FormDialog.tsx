import type * as t from '@/types';
import {
  Button,
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui';
import { useLocalize } from '@/hooks';
import { cn } from '@/utils';

const sizeClasses: Record<NonNullable<t.FormDialogProps['size']>, string> = {
  sm: '',
  lg: 'sm:max-w-2xl',
};

export function FormDialog({
  open,
  title,
  submitLabel,
  submitDisabled,
  saving,
  error,
  size = 'sm',
  onSubmit,
  onClose,
  children,
}: t.FormDialogProps) {
  const localize = useLocalize();

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit();
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(isOpen) => {
        if (!isOpen) onClose();
      }}
    >
      <DialogContent className={cn(sizeClasses[size])}>
        <DialogHeader className="shrink-0">
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="flex min-h-0 flex-1 flex-col gap-5">
          <div className="flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto pr-1">
            {children}
            {error && (
              <p role="alert" className="text-sm text-destructive">
                {error}
              </p>
            )}
          </div>
          <DialogFooter className="shrink-0">
            <Button type="button" variant="outline" onClick={onClose} disabled={saving}>
              {localize('com_ui_cancel')}
            </Button>
            <Button type="submit" disabled={submitDisabled || saving}>
              {submitLabel}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
