import { Plus } from 'lucide-react';
import { useCallback, useState } from 'react';
import { PrincipalType } from 'librechat-data-provider';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import type * as t from '@/types';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui';
import { FieldProfilePopover } from './FieldProfilePopover';
import { fieldProfileValuesOptions } from '@/server';
import { getScopeTypeConfig } from '@/constants';
import { useLocalize } from '@/hooks';

export function ProfileIndicator({
  fieldPath,
  fieldLabel,
  fieldSchema,
  profileTypes,
  permissions,
  onProfileChange,
  baseValue,
  onBaseValueChange,
}: t.ProfileIndicatorProps) {
  const localize = useLocalize();
  const queryClient = useQueryClient();
  const [dialogOpen, setDialogOpen] = useState(false);

  const hasProfiles = profileTypes && profileTypes.length > 0;

  const { data: profileValues = [] } = useQuery({
    ...fieldProfileValuesOptions(fieldPath),
    enabled: dialogOpen,
  }) as { data: t.FieldProfileValue[] };

  const handleClose = useCallback(() => {
    setDialogOpen(false);
  }, []);

  const handleProfileChange = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ['fieldProfileValues', fieldPath] });
    onProfileChange?.();
  }, [queryClient, fieldPath, onProfileChange]);

  if (!hasProfiles) return null;

  const uniqueTypes = hasProfiles ? [...new Set(profileTypes)] : [];

  return (
    <>
      <button
        type="button"
        className="profile-indicator-btn"
        aria-label={`${localize('com_scope_field_profiles')}: ${fieldLabel}`}
        aria-haspopup="dialog"
        aria-expanded={dialogOpen}
        onClick={() => setDialogOpen(true)}
      >
        {uniqueTypes.length > 0 ? (
          uniqueTypes.map((type) => {
            const config = getScopeTypeConfig(type as PrincipalType);
            const TypeIcon = config.icon;
            return (
              <span
                key={type}
                aria-hidden="true"
                className="inline-flex shrink-0 items-center justify-center"
                style={{ color: config.color, width: 18, height: 18 }}
                title={localize(config.labelKey)}
              >
                <TypeIcon className="h-4 w-4" />
              </span>
            );
          })
        ) : (
          <span
            aria-hidden="true"
            className="inline-flex shrink-0 items-center justify-center text-muted-foreground"
            style={{ width: 18, height: 18 }}
            title={localize('com_scope_add_profile_value')}
          >
            <Plus className="h-4 w-4" />
          </span>
        )}
      </button>

      <Dialog
        open={dialogOpen}
        onOpenChange={(isOpen) => {
          if (!isOpen) handleClose();
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{localize('com_scope_cascade_title')}</DialogTitle>
          </DialogHeader>
          <FieldProfilePopover
            fieldPath={fieldPath}
            fieldLabel={fieldLabel}
            fieldSchema={fieldSchema}
            profileValues={profileValues}
            permissions={permissions}
            onProfileChange={handleProfileChange}
            baseValue={baseValue}
            onBaseValueChange={onBaseValueChange}
          />
        </DialogContent>
      </Dialog>
    </>
  );
}
