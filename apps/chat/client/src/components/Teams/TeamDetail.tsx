import { useNavigate } from 'react-router-dom';
import { ArrowLeft, Users } from 'lucide-react';
import { Button, Spinner, Tabs, TabsList, TabsTrigger, TabsContent } from '@librechat/client';
import type { TeamRole } from 'librechat-data-provider';
import type { TranslationKeys } from '~/hooks';
import { useTeamQuery } from '~/data-provider';
import { useLocalize, useAuthContext } from '~/hooks';
import MembersTab from './MembersTab';
import InvitesTab from './InvitesTab';
import KnowledgeTab from './KnowledgeTab';
import SharedTab from './SharedTab';

const roleLabelKey: Record<TeamRole, TranslationKeys> = {
  owner: 'com_ui_role_owner',
  admin: 'com_ui_role_admin',
  member: 'com_ui_role_member',
};

interface TeamDetailProps {
  teamId: string;
}

export default function TeamDetail({ teamId }: TeamDetailProps) {
  const localize = useLocalize();
  const navigate = useNavigate();
  const { user } = useAuthContext();
  const { data, isLoading } = useTeamQuery(teamId);

  const members = data?.members ?? [];
  const callerRole: TeamRole = members.find((m) => m.userId === user?.id)?.role ?? 'member';

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center gap-3">
        <Button
          variant="outline"
          size="sm"
          onClick={() => navigate('/teams')}
          aria-label={localize('com_ui_teams')}
        >
          <ArrowLeft className="size-4" aria-hidden="true" />
        </Button>
        <div className="flex items-center gap-3">
          <div className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-surface-tertiary text-text-secondary">
            <Users className="size-5" aria-hidden="true" />
          </div>
          {isLoading ? (
            <Spinner className="text-text-secondary" aria-label={localize('com_ui_loading')} />
          ) : (
            <div className="flex items-center gap-2">
              <h1 className="text-xl font-semibold text-text-primary">{data?.team.name}</h1>
              <span className="rounded-full bg-surface-tertiary px-2 py-0.5 text-xs font-medium text-text-secondary">
                {localize(roleLabelKey[callerRole])}
              </span>
            </div>
          )}
        </div>
      </div>

      {!isLoading && (
        <Tabs defaultValue="members" className="w-full">
          <TabsList className="mb-4 gap-1">
            <TabsTrigger value="members">{localize('com_ui_team_members')}</TabsTrigger>
            <TabsTrigger value="invites">{localize('com_ui_team_invites')}</TabsTrigger>
            <TabsTrigger value="knowledge">{localize('com_ui_team_knowledge')}</TabsTrigger>
            <TabsTrigger value="shared">{localize('com_ui_team_shared')}</TabsTrigger>
          </TabsList>
          <TabsContent value="members">
            <MembersTab
              teamId={teamId}
              members={members}
              callerRole={callerRole}
              callerId={user?.id ?? ''}
            />
          </TabsContent>
          <TabsContent value="invites">
            <InvitesTab teamId={teamId} callerRole={callerRole} />
          </TabsContent>
          <TabsContent value="knowledge">
            <KnowledgeTab teamId={teamId} callerRole={callerRole} />
          </TabsContent>
          <TabsContent value="shared">
            <SharedTab teamId={teamId} callerRole={callerRole} />
          </TabsContent>
        </Tabs>
      )}
    </div>
  );
}
