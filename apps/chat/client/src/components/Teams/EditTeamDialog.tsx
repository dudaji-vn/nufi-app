import React, { useEffect, useState } from 'react';
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
import type { TUpdateTeamRequest } from 'librechat-data-provider';
import { useUpdateTeamMutation } from '~/data-provider';
import { useLocalize } from '~/hooks';

interface EditTeamDialogProps {
  teamId: string;
  initialName: string;
  initialDescription?: string;
  children: React.ReactNode;
}

export default function EditTeamDialog({
  teamId,
  initialName,
  initialDescription,
  children,
}: EditTeamDialogProps) {
  const localize = useLocalize();
  const { showToast } = useToastContext();

  const [open, setOpen] = useState(false);
  const [name, setName] = useState(initialName);
  const [description, setDescription] = useState(initialDescription ?? '');

  useEffect(() => {
    if (open) {
      setName(initialName);
      setDescription(initialDescription ?? '');
    }
  }, [open, initialName, initialDescription]);

  const { mutate: updateTeam, isLoading } = useUpdateTeamMutation({
    onSuccess: () => {
      showToast({ message: localize('com_ui_team_updated'), status: 'success' });
      setOpen(false);
    },
    onError: (error: Error) => {
      showToast({ message: error.message || localize('com_ui_error'), status: 'error' });
    },
  });

  const handleSave = () => {
    if (!name.trim()) {
      showToast({ message: localize('com_ui_field_required'), status: 'error' });
      return;
    }
    const payload: TUpdateTeamRequest & { teamId: string } = {
      teamId,
      name: name.trim(),
      description: description.trim(),
    };
    updateTeam(payload);
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && e.ctrlKey) {
      handleSave();
    }
  };

  return (
    <OGDialog open={open} onOpenChange={setOpen}>
      <OGDialogTrigger asChild>{children}</OGDialogTrigger>
      <OGDialogTemplate
        title={localize('com_ui_edit_team')}
        showCloseButton={false}
        className="w-11/12 md:max-w-lg"
        main={
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="edit-team-name" className="text-sm font-medium text-text-primary">
                {localize('com_ui_team_name')}
              </Label>
              <Input
                id="edit-team-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                onKeyDown={handleKeyPress}
                placeholder={localize('com_ui_team_name')}
                className="w-full"
                aria-label={localize('com_ui_team_name')}
              />
            </div>
            <div className="space-y-2">
              <Label
                htmlFor="edit-team-description"
                className="text-sm font-medium text-text-primary"
              >
                {localize('com_ui_team_description')}
              </Label>
              <textarea
                id="edit-team-description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                onKeyDown={handleKeyPress}
                placeholder={localize('com_ui_team_description')}
                className="min-h-[100px] w-full resize-none rounded-lg border border-border-light bg-transparent px-3 py-2 text-sm text-text-primary focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-border-heavy"
                rows={4}
                aria-label={localize('com_ui_team_description')}
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
            aria-label={localize('com_ui_edit_team')}
          >
            {isLoading ? <Spinner className="size-4" /> : localize('com_ui_save')}
          </Button>
        }
      />
    </OGDialog>
  );
}
