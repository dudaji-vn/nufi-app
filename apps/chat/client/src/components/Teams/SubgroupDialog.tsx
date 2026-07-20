import React, { useState, useEffect } from 'react';
import {
  OGDialog,
  OGDialogTrigger,
  OGDialogTemplate,
  Button,
  Label,
  Input,
  Spinner,
  useToastContext,
} from '@librechat/client';
import type { TSubgroup } from 'librechat-data-provider';
import { useCreateSubgroupMutation, useUpdateSubgroupMutation } from '~/data-provider';
import { useLocalize } from '~/hooks';

interface SubgroupDialogProps {
  teamId: string;
  subgroup?: TSubgroup;
  children: React.ReactNode;
}

export default function SubgroupDialog({ teamId, subgroup, children }: SubgroupDialogProps) {
  const localize = useLocalize();
  const { showToast } = useToastContext();

  const [open, setOpen] = useState(false);
  const [name, setName] = useState(subgroup?.name ?? '');
  const [description, setDescription] = useState(subgroup?.description ?? '');

  useEffect(() => {
    if (open) {
      setName(subgroup?.name ?? '');
      setDescription(subgroup?.description ?? '');
    }
  }, [open, subgroup]);

  const isEdit = subgroup != null;

  const { mutate: createSubgroup, isLoading: isCreating } = useCreateSubgroupMutation(teamId, {
    onSuccess: () => {
      showToast({ message: localize('com_ui_team_group_created'), status: 'success' });
      setOpen(false);
    },
    onError: (error: Error) => {
      showToast({ message: error.message || localize('com_ui_error'), status: 'error' });
    },
  });

  const { mutate: updateSubgroup, isLoading: isUpdating } = useUpdateSubgroupMutation(teamId, {
    onSuccess: () => {
      showToast({ message: localize('com_ui_team_group_updated'), status: 'success' });
      setOpen(false);
    },
    onError: (error: Error) => {
      showToast({ message: error.message || localize('com_ui_error'), status: 'error' });
    },
  });

  const isLoading = isCreating || isUpdating;

  const handleSave = () => {
    if (!name.trim()) {
      showToast({ message: localize('com_ui_field_required'), status: 'error' });
      return;
    }
    if (isEdit) {
      updateSubgroup({ sgId: subgroup._id, name: name.trim(), description: description.trim() });
    } else {
      createSubgroup({ name: name.trim(), description: description.trim() });
    }
  };

  const handleNameKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && name.trim()) {
      e.preventDefault();
      handleSave();
    }
  };

  const title = isEdit ? localize('com_ui_team_rename_group') : localize('com_ui_team_new_group');

  return (
    <OGDialog open={open} onOpenChange={setOpen}>
      <OGDialogTrigger asChild>{children}</OGDialogTrigger>
      <OGDialogTemplate
        title={title}
        showCloseButton={false}
        className="w-11/12 md:max-w-lg"
        main={
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="group-name" className="text-sm font-medium text-text-primary">
                {localize('com_ui_team_group_name')}
              </Label>
              <Input
                id="group-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                onKeyDown={handleNameKeyDown}
                placeholder={localize('com_ui_team_group_name')}
                className="w-full"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="group-description" className="text-sm font-medium text-text-primary">
                {localize('com_ui_team_description')}
              </Label>
              <textarea
                id="group-description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder={localize('com_ui_team_description')}
                className="min-h-[80px] w-full resize-none rounded-lg border border-border-light bg-transparent px-3 py-2 text-sm text-text-primary focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-border-heavy"
                rows={3}
              />
            </div>
          </div>
        }
        buttons={
          <Button
            type="button"
            variant="submit"
            onClick={handleSave}
            disabled={isLoading || !name.trim()}
            className="text-white"
            aria-label={title}
          >
            {isLoading ? (
              <Spinner className="size-4" />
            ) : (
              localize(isEdit ? 'com_ui_save' : 'com_ui_create')
            )}
          </Button>
        }
      />
    </OGDialog>
  );
}
