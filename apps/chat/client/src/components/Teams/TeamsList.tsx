import { useNavigate } from 'react-router-dom';
import { Plus, Users } from 'lucide-react';
import { Button, Spinner } from '@librechat/client';
import type { TTeam, TeamRole } from 'librechat-data-provider';
import type { TranslationKeys } from '~/hooks';
import { useTeamsQuery } from '~/data-provider';
import { useLocalize, useAuthContext } from '~/hooks';
import CreateTeamDialog from './CreateTeamDialog';

const roleLabelKey: Record<TeamRole, TranslationKeys> = {
  owner: 'com_ui_role_owner',
  admin: 'com_ui_role_admin',
  member: 'com_ui_role_member',
};

function TeamCard({ team, userId }: { team: TTeam; userId?: string }) {
  const localize = useLocalize();
  const navigate = useNavigate();

  const memberCount = team.members?.length ?? 0;
  const myRole = team.members?.find((member) => member.userId === userId)?.role;

  return (
    <button
      type="button"
      onClick={() => navigate(`/teams/${team._id}`)}
      aria-label={team.name}
      className="flex w-full flex-col gap-3 rounded-xl border border-border-light bg-surface-primary p-4 text-left transition-colors hover:border-border-heavy hover:bg-surface-secondary"
    >
      <div className="flex items-center gap-3">
        <div className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-surface-tertiary text-text-secondary">
          <Users className="size-5" aria-hidden={true} />
        </div>
        <div className="min-w-0 flex-1">
          <h3 className="truncate text-sm font-semibold text-text-primary">{team.name}</h3>
          {team.description != null && team.description !== '' && (
            <p className="truncate text-xs text-text-secondary">{team.description}</p>
          )}
        </div>
      </div>
      <div className="flex items-center justify-between">
        <span className="text-xs text-text-secondary">
          {localize('com_ui_members_count', { 0: memberCount })}
        </span>
        {myRole != null && (
          <span className="rounded-full bg-surface-tertiary px-2 py-0.5 text-xs font-medium text-text-secondary">
            {localize(roleLabelKey[myRole])}
          </span>
        )}
      </div>
    </button>
  );
}

export default function TeamsList() {
  const localize = useLocalize();
  const { user } = useAuthContext();
  const { data, isLoading } = useTeamsQuery();

  const teams = data?.teams ?? [];

  const renderContent = () => {
    if (isLoading) {
      return (
        <div className="flex items-center justify-center py-12">
          <Spinner className="text-text-secondary" aria-label={localize('com_ui_loading')} />
        </div>
      );
    }

    if (teams.length === 0) {
      return (
        <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-border-light py-12 text-center">
          <Users className="size-8 text-text-tertiary" aria-hidden={true} />
          <p className="text-sm text-text-secondary">{localize('com_ui_no_teams_yet')}</p>
        </div>
      );
    }

    return (
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {teams.map((team) => (
          <TeamCard key={team._id} team={team} userId={user?.id} />
        ))}
      </div>
    );
  };

  return (
    <section aria-label={localize('com_ui_teams')} className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-text-primary">{localize('com_ui_teams')}</h2>
        <CreateTeamDialog>
          <Button
            variant="submit"
            className="gap-1.5 text-white"
            aria-label={localize('com_ui_create_team')}
          >
            <Plus className="size-4" aria-hidden={true} />
            {localize('com_ui_create_team')}
          </Button>
        </CreateTeamDialog>
      </div>

      {renderContent()}
    </section>
  );
}
