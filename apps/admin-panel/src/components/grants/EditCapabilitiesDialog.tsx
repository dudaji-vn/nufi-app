import { PrincipalType } from 'librechat-data-provider';
import { useCallback, useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { AdminSystemGrant } from '@librechat/data-schemas';
import type * as t from '@/types';
import {
  Button,
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui';
import { grantCapabilityFn, principalGrantsQueryOptions, revokeCapabilityFn } from '@/server';
import { getScopeTypeConfig, SystemCapabilities } from '@/constants';
import { CapabilityPanel } from './CapabilityPanel';
import { LoadingState } from '@/components/shared';
import { useLocalize } from '@/hooks';
import { cn } from '@/utils';

function grantsToRecord(grants: AdminSystemGrant[]): Record<string, boolean> {
  const record: Record<string, boolean> = {};
  for (const cap of Object.values(SystemCapabilities)) {
    record[cap] = false;
  }
  for (const g of grants) {
    record[g.capability] = true;
  }
  return record;
}

export function EditCapabilitiesDialog({
  principalType,
  principalId,
  principalName,
  onClose,
}: t.EditCapabilitiesDialogProps) {
  const localize = useLocalize();
  const queryClient = useQueryClient();
  const open = principalType != null && principalId != null;

  const { data: grants = [], isLoading } = useQuery({
    ...principalGrantsQueryOptions(principalType ?? PrincipalType.ROLE, principalId ?? ''),
    enabled: open,
  });

  const [capabilities, setCapabilities] = useState<Record<string, boolean>>({});
  const [baseline, setBaseline] = useState<Record<string, boolean>>({});
  const [error, setError] = useState('');

  useEffect(() => {
    if (open && !isLoading) {
      const record = grantsToRecord(grants);
      setCapabilities(record);
      setBaseline(record);
      setError('');
    }
  }, [open, isLoading, grants]);

  const saveMutation = useMutation({
    mutationFn: async () => {
      if (!principalType || !principalId) return;
      const toGrant: string[] = [];
      const toRevoke: string[] = [];
      for (const [cap, enabled] of Object.entries(capabilities)) {
        if (enabled && !baseline[cap]) toGrant.push(cap);
        if (!enabled && baseline[cap]) toRevoke.push(cap);
      }
      const shared = { principalType, principalId };
      for (const cap of toGrant) {
        await grantCapabilityFn({ data: { ...shared, capability: cap } });
      }
      for (const cap of toRevoke) {
        await revokeCapabilityFn({ data: { ...shared, capability: cap } });
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['systemGrants'] });
      queryClient.invalidateQueries({ queryKey: ['effectiveCapabilities'] });
      queryClient.invalidateQueries({ queryKey: ['auditLog'] });
      onClose();
    },
    onError: (err: Error) => setError(err.message),
  });

  const hasChanges = Object.keys(capabilities).some((cap) => capabilities[cap] !== baseline[cap]);

  const handleSave = useCallback(() => {
    setError('');
    saveMutation.mutate();
  }, [saveMutation]);

  const dialogTitle = principalType
    ? `${localize('com_cap_edit_title', { name: principalName })}`
    : '';
  const principalConfig = principalType ? getScopeTypeConfig(principalType) : null;
  const PrincipalIcon = principalConfig?.icon;

  return (
    <Dialog
      open={open}
      onOpenChange={(isOpen) => {
        if (!isOpen) onClose();
      }}
    >
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{dialogTitle}</DialogTitle>
        </DialogHeader>
        {isLoading ? (
          <LoadingState />
        ) : (
          <>
            {principalConfig && PrincipalIcon && (
              <div className="flex items-center gap-2">
                <span
                  className={cn(
                    'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium',
                    principalConfig.badgeClass,
                  )}
                >
                  <PrincipalIcon className="h-3 w-3" />
                  {localize(principalConfig.labelKey)}
                </span>
                <span className="text-sm font-medium text-foreground">{principalName}</span>
              </div>
            )}
            <CapabilityPanel
              capabilities={capabilities}
              onChange={setCapabilities}
              disabled={saveMutation.isPending}
            />
            {error && (
              <p role="alert" className="text-sm text-destructive">
                {error}
              </p>
            )}
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={onClose}
                disabled={saveMutation.isPending}
              >
                {localize('com_ui_cancel')}
              </Button>
              <Button
                type="button"
                onClick={handleSave}
                disabled={!hasChanges || saveMutation.isPending}
              >
                {saveMutation.isPending ? localize('com_ui_loading') : localize('com_ui_save')}
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
