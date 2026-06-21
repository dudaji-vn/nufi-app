import { useParams, Navigate } from 'react-router-dom';
import { Spinner } from '@librechat/client';
import { PermissionTypes, Permissions, SystemRoles } from 'librechat-data-provider';
import { useGetRole } from '~/data-provider';
import { useLocalize, useHasAccess } from '~/hooks';
import TeamDetail from '~/components/Teams/TeamDetail';
import MyInvitesInbox from '~/components/Teams/MyInvitesInbox';
import TeamsList from '~/components/Teams/TeamsList';

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
          <TeamDetail teamId={teamId} />
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
