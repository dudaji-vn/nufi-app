import { useParams, useNavigate, Navigate } from 'react-router-dom';
import { ArrowLeft, Users } from 'lucide-react';
import { Button, Spinner } from '@librechat/client';
import { PermissionTypes, Permissions, SystemRoles } from 'librechat-data-provider';
import { useTeamQuery, useGetRole } from '~/data-provider';
import { useLocalize, useHasAccess } from '~/hooks';
import MyInvitesInbox from '~/components/Teams/MyInvitesInbox';
import TeamsList from '~/components/Teams/TeamsList';

function TeamDetailHeader({ teamId }: { teamId: string }) {
  const localize = useLocalize();
  const navigate = useNavigate();
  const { data, isLoading } = useTeamQuery(teamId);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center gap-3">
        <Button
          variant="outline"
          size="sm"
          onClick={() => navigate('/teams')}
          aria-label={localize('com_ui_teams')}
        >
          <ArrowLeft className="size-4" aria-hidden={true} />
        </Button>
        <div className="flex items-center gap-3">
          <div className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-surface-tertiary text-text-secondary">
            <Users className="size-5" aria-hidden={true} />
          </div>
          {isLoading ? (
            <Spinner className="text-text-secondary" aria-label={localize('com_ui_loading')} />
          ) : (
            <h1 className="text-xl font-semibold text-text-primary">{data?.team.name}</h1>
          )}
        </div>
      </div>
      <div className="rounded-xl border border-dashed border-border-light p-6 text-sm text-text-secondary">
        {localize('com_ui_teams_tabs_coming_soon')}
      </div>
    </div>
  );
}

export default function TeamsView() {
  const localize = useLocalize();
  const { teamId } = useParams<{ teamId?: string }>();

  /** Wait for the role to load before deciding access, so a direct navigation
   * or page reload to /teams doesn't redirect away while permissions resolve. */
  const { isFetched: roleFetched } = useGetRole(SystemRoles.USER);
  const hasAccess = useHasAccess({
    permissionType: PermissionTypes.TEAMS,
    permission: Permissions.USE,
  });

  if (!roleFetched) {
    return (
      <div className="flex h-full w-full items-center justify-center bg-presentation">
        <Spinner className="text-text-secondary" aria-label={localize('com_ui_loading')} />
      </div>
    );
  }

  if (!hasAccess) {
    return <Navigate to="/c/new" replace />;
  }

  return (
    <div className="flex h-full w-full flex-col overflow-y-auto bg-presentation">
      <div className="mx-auto w-full max-w-5xl px-4 py-6 sm:px-6">
        {teamId != null ? (
          <TeamDetailHeader teamId={teamId} />
        ) : (
          <div className="flex flex-col gap-8">
            <MyInvitesInbox />
            <TeamsList />
          </div>
        )}
      </div>
    </div>
  );
}
