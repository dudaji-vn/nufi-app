import type * as t from '@/types';
import {
  Button,
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui';
import { getScopeTypeConfig } from '@/constants';
import { useLocalize } from '@/hooks';

export function DeleteProfileValueModal({
  scope,
  fieldLabel,
  saving,
  onConfirm,
  onCancel,
}: t.DeleteProfileValueModalProps) {
  const localize = useLocalize();
  const scopeConfig = scope ? getScopeTypeConfig(scope.principalType) : null;
  const ScopeIcon = scopeConfig?.icon;

  return (
    <Dialog
      open={!!scope}
      onOpenChange={(isOpen) => {
        if (!isOpen) onCancel();
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{localize('com_scope_confirm_remove')}</DialogTitle>
        </DialogHeader>
        {scope && (
          <>
            <div className="flex items-center gap-2">
              {ScopeIcon && scopeConfig && (
                <ScopeIcon
                  aria-hidden="true"
                  className="h-4 w-4"
                  style={{ color: scopeConfig.color }}
                />
              )}
              <span className="text-sm text-foreground">{fieldLabel}</span>
              <span className="text-xs text-muted-foreground">{scope.name}</span>
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={onCancel} disabled={saving}>
                {localize('com_ui_cancel')}
              </Button>
              <Button
                type="button"
                variant="destructive"
                onClick={() => onConfirm(scope)}
                disabled={saving}
              >
                {localize('com_scope_confirm_yes')}
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
