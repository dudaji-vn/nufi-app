import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
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
import type { TCreateTeamRequest } from 'librechat-data-provider';
import { useCreateTeamMutation } from '~/data-provider';
import { useLocalize } from '~/hooks';

interface CreateTeamDialogProps {
  children: React.ReactNode;
}

export default function CreateTeamDialog({ children }: CreateTeamDialogProps) {
  const localize = useLocalize();
  const navigate = useNavigate();
  const { showToast } = useToastContext();

  const [open, setOpen] = useState(false);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');

  const { mutate: createTeam, isLoading } = useCreateTeamMutation({
    onSuccess: ({ team }) => {
      showToast({ message: localize('com_ui_team_created'), status: 'success' });
      setOpen(false);
      setName('');
      setDescription('');
      navigate(`/teams/${team._id}`);
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

    const payload: TCreateTeamRequest = { name: name.trim() };
    if (description.trim()) {
      payload.description = description.trim();
    }
    createTeam(payload);
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
        title={localize('com_ui_create_team')}
        showCloseButton={false}
        className="w-11/12 md:max-w-lg"
        main={
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="team-name" className="text-sm font-medium text-text-primary">
                {localize('com_ui_team_name')}
              </Label>
              <Input
                id="team-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                onKeyDown={handleKeyPress}
                placeholder={localize('com_ui_team_name')}
                className="w-full"
                aria-label={localize('com_ui_team_name')}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="team-description" className="text-sm font-medium text-text-primary">
                {localize('com_ui_team_description')}
              </Label>
              <textarea
                id="team-description"
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
            aria-label={localize('com_ui_create_team')}
          >
            {isLoading ? <Spinner className="size-4" /> : localize('com_ui_create')}
          </Button>
        }
      />
    </OGDialog>
  );
}
