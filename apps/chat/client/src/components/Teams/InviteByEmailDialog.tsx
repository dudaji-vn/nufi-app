import React, { useState } from 'react';
import {
  OGDialog,
  OGDialogTrigger,
  OGDialogTemplate,
  Button,
  Label,
  Input,
  Spinner,
  useToastContext,
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from '@librechat/client';
import type { TranslationKeys } from '~/hooks';
import { useCreateInviteMutation } from '~/data-provider';
import { getResponseErrorMessage } from '~/utils';
import { useLocalize } from '~/hooks';

interface InviteByEmailDialogProps {
  teamId: string;
  children: React.ReactNode;
}

const roleOptions: Array<{ value: 'admin' | 'member'; labelKey: TranslationKeys }> = [
  { value: 'member', labelKey: 'com_ui_role_member' },
  { value: 'admin', labelKey: 'com_ui_role_admin' },
];

export default function InviteByEmailDialog({ teamId, children }: InviteByEmailDialogProps) {
  const localize = useLocalize();
  const { showToast } = useToastContext();

  const [open, setOpen] = useState(false);
  const [email, setEmail] = useState('');
  const [role, setRole] = useState<'admin' | 'member'>('member');

  const { mutate: createInvite, isLoading } = useCreateInviteMutation({
    onSuccess: () => {
      showToast({ message: localize('com_ui_team_invite_sent'), status: 'success' });
      setOpen(false);
      setEmail('');
      setRole('member');
    },
    onError: (error: Error) => {
      showToast({
        message: getResponseErrorMessage(error) || localize('com_ui_error'),
        status: 'error',
      });
    },
  });

  const handleSend = () => {
    if (!email.trim()) {
      showToast({ message: localize('com_ui_field_required'), status: 'error' });
      return;
    }
    createInvite({ teamId, email: email.trim(), role });
  };

  return (
    <OGDialog open={open} onOpenChange={setOpen}>
      <OGDialogTrigger asChild>{children}</OGDialogTrigger>
      <OGDialogTemplate
        title={localize('com_ui_team_invite_member')}
        showCloseButton={false}
        className="w-11/12 md:max-w-md"
        main={
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="invite-email" className="text-sm font-medium text-text-primary">
                {localize('com_ui_team_invite_email')}
              </Label>
              <Input
                id="invite-email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder={localize('com_ui_team_invite_email_placeholder')}
                className="w-full"
                aria-label={localize('com_ui_team_invite_email')}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="invite-role" className="text-sm font-medium text-text-primary">
                {localize('com_ui_team_invite_role')}
              </Label>
              <Select value={role} onValueChange={(v) => setRole(v as 'admin' | 'member')}>
                <SelectTrigger
                  id="invite-role"
                  className="w-full"
                  aria-label={localize('com_ui_team_invite_role')}
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="z-[200]">
                  {roleOptions.map((opt) => (
                    <SelectItem key={opt.value} value={opt.value}>
                      {localize(opt.labelKey)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
        }
        buttons={
          <Button
            type="button"
            variant="submit"
            onClick={handleSend}
            disabled={isLoading || !email.trim()}
            className="text-white"
            aria-label={localize('com_ui_team_invite_member')}
          >
            {isLoading ? <Spinner className="size-4" /> : localize('com_ui_team_invite_member')}
          </Button>
        }
      />
    </OGDialog>
  );
}
