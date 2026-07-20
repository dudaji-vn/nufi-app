import { useNavigate, useParams, useLocation, Link, Navigate } from 'react-router-dom';
import { Check, X, Users } from 'lucide-react';
import { Button, Spinner, useToastContext } from '@librechat/client';
import type { TTeamInvite } from 'librechat-data-provider';
import type { TranslationKeys } from '~/hooks';
import {
  useMyTeamInvitesQuery,
  useAcceptInviteMutation,
  useDeclineInviteMutation,
} from '~/data-provider';
import { useAuthContext } from '~/hooks/AuthContext';
import { useLocalize } from '~/hooks';

const inviteRoleLabelKey: Record<TTeamInvite['role'], TranslationKeys> = {
  admin: 'com_ui_role_admin',
  member: 'com_ui_role_member',
};

function InviteCard({ invite, token }: { invite: TTeamInvite; token: string }) {
  const localize = useLocalize();
  const { showToast } = useToastContext();
  const navigate = useNavigate();

  const { mutate: acceptInvite, isLoading: isAccepting } = useAcceptInviteMutation({
    onSuccess: (result) => {
      showToast({ message: localize('com_ui_invite_accepted'), status: 'success' });
      navigate('/teams/' + result.team._id);
    },
    onError: (error: Error) => {
      showToast({ message: error.message || localize('com_ui_error'), status: 'error' });
    },
  });

  const { mutate: declineInvite, isLoading: isDeclining } = useDeclineInviteMutation({
    onSuccess: () => {
      showToast({ message: localize('com_ui_invite_declined'), status: 'success' });
      navigate('/teams');
    },
    onError: (error: Error) => {
      showToast({ message: error.message || localize('com_ui_error'), status: 'error' });
    },
  });

  const isPending = isAccepting || isDeclining;

  return (
    <div className="flex flex-col items-center gap-6 text-center">
      <div className="flex h-16 w-16 items-center justify-center rounded-full bg-surface-tertiary">
        <Users className="h-8 w-8 text-text-primary" aria-hidden="true" />
      </div>
      <div className="space-y-2">
        <p className="text-sm text-text-secondary">{localize('com_ui_team_invite_to')}</p>
        <h1 className="text-2xl font-bold text-text-primary">{invite.teamName ?? invite.email}</h1>
        <p className="text-sm text-text-secondary">
          {localize('com_ui_team_invite_as')}{' '}
          <span className="font-medium text-text-primary">
            {localize(inviteRoleLabelKey[invite.role])}
          </span>
        </p>
      </div>
      <div className="flex w-full flex-col gap-3">
        <Button
          variant="submit"
          disabled={isPending}
          onClick={() => acceptInvite(token)}
          className="w-full gap-2"
          aria-label={localize('com_ui_team_invite_accept')}
        >
          {isAccepting ? (
            <Spinner className="h-4 w-4" />
          ) : (
            <Check className="h-4 w-4" aria-hidden="true" />
          )}
          {localize('com_ui_team_invite_accept')}
        </Button>
        <Button
          variant="outline"
          disabled={isPending}
          onClick={() => declineInvite(token)}
          className="w-full gap-2"
          aria-label={localize('com_ui_team_invite_decline')}
        >
          {isDeclining ? (
            <Spinner className="h-4 w-4" />
          ) : (
            <X className="h-4 w-4" aria-hidden="true" />
          )}
          {localize('com_ui_team_invite_decline')}
        </Button>
      </div>
    </div>
  );
}

function NotFoundCard() {
  const localize = useLocalize();
  return (
    <div className="flex flex-col items-center gap-6 text-center">
      <div className="flex h-16 w-16 items-center justify-center rounded-full bg-surface-tertiary">
        <Users className="h-8 w-8 text-text-secondary" aria-hidden="true" />
      </div>
      <p className="text-base text-text-secondary">{localize('com_ui_team_invite_not_found')}</p>
      <Button variant="outline" asChild>
        <Link to="/teams">{localize('com_ui_team_back_to_teams')}</Link>
      </Button>
    </div>
  );
}

function InvitePageContent({ token }: { token: string }) {
  const { data, isLoading } = useMyTeamInvitesQuery();
  const invite = data?.invites.find((inv) => inv.token === token);

  return (
    <div className="flex min-h-screen items-center justify-center bg-surface-primary p-4">
      <div className="w-full max-w-md rounded-2xl border border-border-light bg-surface-secondary p-8 shadow-lg">
        {isLoading && (
          <div className="flex flex-col items-center gap-4">
            <Spinner className="h-8 w-8 text-text-secondary" />
          </div>
        )}
        {!isLoading && invite && <InviteCard invite={invite} token={token} />}
        {!isLoading && !invite && <NotFoundCard />}
      </div>
    </div>
  );
}

export default function TeamInviteRoute() {
  const { token } = useParams<{ token: string }>();
  const location = useLocation();
  const { isAuthenticated } = useAuthContext();

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ redirect_to: location.pathname }} replace />;
  }

  return <InvitePageContent token={token ?? ''} />;
}
