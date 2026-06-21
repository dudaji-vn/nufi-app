import { Check, X, Mail } from 'lucide-react';
import { Button, Spinner, useToastContext } from '@librechat/client';
import type { TTeamInvite } from 'librechat-data-provider';
import type { TranslationKeys } from '~/hooks';
import {
  useMyTeamInvitesQuery,
  useAcceptInviteMutation,
  useDeclineInviteMutation,
} from '~/data-provider';
import { useLocalize } from '~/hooks';

const inviteRoleLabelKey: Record<TTeamInvite['role'], TranslationKeys> = {
  admin: 'com_ui_role_admin',
  member: 'com_ui_role_member',
};

function InviteRow({ invite }: { invite: TTeamInvite }) {
  const localize = useLocalize();
  const { showToast } = useToastContext();
  const { mutate: acceptInvite, isLoading: isAccepting } = useAcceptInviteMutation({
    onSuccess: () => {
      showToast({ message: localize('com_ui_invite_accepted'), status: 'success' });
    },
    onError: (error: Error) => {
      showToast({ message: error.message || localize('com_ui_error'), status: 'error' });
    },
  });
  const { mutate: declineInvite, isLoading: isDeclining } = useDeclineInviteMutation({
    onSuccess: () => {
      showToast({ message: localize('com_ui_invite_declined'), status: 'success' });
    },
    onError: (error: Error) => {
      showToast({ message: error.message || localize('com_ui_error'), status: 'error' });
    },
  });

  const isPending = isAccepting || isDeclining;
  const hasToken = invite.token != null && invite.token !== '';

  return (
    <li className="flex items-center justify-between gap-3 rounded-lg border border-border-light bg-surface-primary px-4 py-3">
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-text-primary">
          {invite.teamName ?? invite.email}
        </p>
        <span className="text-xs text-text-secondary">
          {localize(inviteRoleLabelKey[invite.role])}
        </span>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <Button
          variant="submit"
          disabled={isPending || !hasToken}
          onClick={() => hasToken && acceptInvite(invite.token as string)}
          className="gap-1.5 text-white"
          aria-label={localize('com_ui_accept')}
        >
          {isAccepting ? (
            <Spinner className="size-4" />
          ) : (
            <Check className="size-4" aria-hidden={true} />
          )}
          {localize('com_ui_accept')}
        </Button>
        <Button
          variant="outline"
          disabled={isPending || !hasToken}
          onClick={() => hasToken && declineInvite(invite.token as string)}
          className="gap-1.5"
          aria-label={localize('com_ui_decline')}
        >
          {isDeclining ? (
            <Spinner className="size-4" />
          ) : (
            <X className="size-4" aria-hidden={true} />
          )}
          {localize('com_ui_decline')}
        </Button>
      </div>
    </li>
  );
}

export default function MyInvitesInbox() {
  const localize = useLocalize();
  const { data, isLoading } = useMyTeamInvitesQuery();

  const invites = data?.invites ?? [];

  if (isLoading) {
    return null;
  }

  if (invites.length === 0) {
    return null;
  }

  return (
    <section aria-label={localize('com_ui_my_invitations')} className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <Mail className="size-4 text-text-secondary" aria-hidden={true} />
        <h2 className="text-base font-semibold text-text-primary">
          {localize('com_ui_my_invitations')}
        </h2>
      </div>
      <ul className="flex flex-col gap-2">
        {invites.map((invite) => (
          <InviteRow key={invite._id} invite={invite} />
        ))}
      </ul>
    </section>
  );
}
