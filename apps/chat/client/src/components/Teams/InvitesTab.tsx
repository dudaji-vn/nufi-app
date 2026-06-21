import { Mail } from 'lucide-react';
import { Button, Spinner, useToastContext } from '@librechat/client';
import type { TTeamInvite, TeamRole } from 'librechat-data-provider';
import type { TranslationKeys } from '~/hooks';
import { useTeamInvitesQuery, useRevokeInviteMutation } from '~/data-provider';
import { useLocalize } from '~/hooks';

const inviteRoleLabelKey: Record<TTeamInvite['role'], TranslationKeys> = {
  admin: 'com_ui_role_admin',
  member: 'com_ui_role_member',
};

interface InviteRowProps {
  invite: TTeamInvite;
  teamId: string;
}

function InviteRow({ invite, teamId }: InviteRowProps) {
  const localize = useLocalize();
  const { showToast } = useToastContext();

  const { mutate: revokeInvite, isLoading } = useRevokeInviteMutation({
    onSuccess: () => {
      showToast({ message: localize('com_ui_team_revoke_invite'), status: 'success' });
    },
    onError: (error: Error) => {
      showToast({ message: error.message || localize('com_ui_error'), status: 'error' });
    },
  });

  return (
    <li className="flex items-center justify-between gap-3 rounded-lg border border-border-light bg-surface-primary px-4 py-3">
      <div className="flex min-w-0 flex-1 items-center gap-3">
        <div className="flex size-8 shrink-0 items-center justify-center rounded-full bg-surface-tertiary">
          <Mail className="size-4 text-text-secondary" aria-hidden="true" />
        </div>
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-text-primary">{invite.email}</p>
          <span className="text-xs text-text-secondary">
            {localize(inviteRoleLabelKey[invite.role])}
          </span>
        </div>
      </div>
      <Button
        variant="outline"
        size="sm"
        disabled={isLoading}
        onClick={() => revokeInvite({ teamId, inviteId: invite._id })}
        aria-label={localize('com_ui_team_revoke_invite')}
      >
        {isLoading ? <Spinner className="size-3.5" /> : localize('com_ui_revoke')}
      </Button>
    </li>
  );
}

interface InvitesTabProps {
  teamId: string;
  callerRole: TeamRole;
}

export default function InvitesTab({ teamId, callerRole }: InvitesTabProps) {
  const localize = useLocalize();
  const canManage = callerRole === 'owner' || callerRole === 'admin';
  const { data, isLoading } = useTeamInvitesQuery(teamId, { enabled: canManage });

  if (!canManage) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-border-light py-12 text-center">
        <p className="text-sm text-text-secondary">{localize('com_ui_team_invites_no_access')}</p>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Spinner className="text-text-secondary" aria-label={localize('com_ui_loading')} />
      </div>
    );
  }

  const invites = data?.invites ?? [];

  if (invites.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-border-light py-12 text-center">
        <Mail className="size-8 text-text-tertiary" aria-hidden="true" />
        <p className="text-sm text-text-secondary">{localize('com_ui_team_no_invites')}</p>
      </div>
    );
  }

  return (
    <section aria-label={localize('com_ui_pending_invites')} className="flex flex-col gap-3">
      <ul className="flex flex-col gap-2">
        {invites.map((invite) => (
          <InviteRow key={invite._id} invite={invite} teamId={teamId} />
        ))}
      </ul>
    </section>
  );
}
