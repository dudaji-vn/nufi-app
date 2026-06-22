import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, Users, Trash2 } from 'lucide-react';
import {
  Button,
  Spinner,
  Tabs,
  TabsList,
  TabsTrigger,
  TabsContent,
  OGDialog,
  OGDialogTrigger,
  OGDialogTemplate,
  useToastContext,
} from '@librechat/client';
import type { TeamRole } from 'librechat-data-provider';
import type { TranslationKeys } from '~/hooks';
import { useTeamQuery, useDeleteTeamMutation } from '~/data-provider';
import { useLocalize, useAuthContext } from '~/hooks';
import MembersTab from './MembersTab';
import InvitesTab from './InvitesTab';
import KnowledgeTab from './KnowledgeTab';
import SharedTab from './SharedTab';
import GroupsTab from './GroupsTab';

const roleLabelKey: Record<TeamRole, TranslationKeys> = {
  owner: 'com_ui_role_owner',
  admin: 'com_ui_role_admin',
  member: 'com_ui_role_member',
};

interface TeamDetailProps {
  teamId: string;
}

function DeleteTeamButton({ teamId }: { teamId: string }) {
  const localize = useLocalize();
  const navigate = useNavigate();
  const { showToast } = useToastContext();
  const [open, setOpen] = useState(false);

  const { mutate: deleteTeam, isLoading } = useDeleteTeamMutation({
    onSuccess: () => {
      showToast({ message: localize('com_ui_team_deleted'), status: 'success' });
      setOpen(false);
      navigate('/teams');
    },
    onError: (error: Error) => {
      showToast({ message: error.message || localize('com_ui_error'), status: 'error' });
    },
  });

  return (
    <OGDialog open={open} onOpenChange={setOpen}>
      <OGDialogTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          className="gap-1.5 text-text-secondary hover:text-red-500"
          aria-label={localize('com_ui_team_delete')}
        >
          <Trash2 className="size-4" aria-hidden="true" />
          <span className="hidden sm:inline">{localize('com_ui_team_delete')}</span>
        </Button>
      </OGDialogTrigger>
      <OGDialogTemplate
        title={localize('com_ui_team_delete')}
        showCloseButton={false}
        className="w-11/12 md:max-w-md"
        main={
          <p className="text-sm text-text-secondary">{localize('com_ui_team_delete_confirm')}</p>
        }
        buttons={
          <Button
            type="button"
            variant="destructive"
            onClick={() => deleteTeam(teamId)}
            disabled={isLoading}
            aria-label={localize('com_ui_confirm')}
          >
            {isLoading ? <Spinner className="size-4" /> : localize('com_ui_delete')}
          </Button>
        }
      />
    </OGDialog>
  );
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
        {!isLoading && callerRole === 'owner' && (
          <div className="ml-auto">
            <DeleteTeamButton teamId={teamId} />
          </div>
        )}
      </div>

      {!isLoading && (
        <Tabs defaultValue="members" className="w-full">
          <TabsList className="mb-4 gap-1 rounded-lg">
            <TabsTrigger value="members" className="rounded-lg">
              {localize('com_ui_team_members')}
            </TabsTrigger>
            <TabsTrigger value="invites" className="rounded-lg">
              {localize('com_ui_team_invites')}
            </TabsTrigger>
            <TabsTrigger value="knowledge" className="rounded-lg">
              {localize('com_ui_team_knowledge')}
            </TabsTrigger>
            <TabsTrigger value="shared" className="rounded-lg">
              {localize('com_ui_team_shared')}
            </TabsTrigger>
            {callerRole !== 'member' && (
              <TabsTrigger value="groups" className="rounded-lg">
                {localize('com_ui_team_groups')}
              </TabsTrigger>
            )}
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
          {callerRole !== 'member' && (
            <TabsContent value="groups">
              <GroupsTab teamId={teamId} callerRole={callerRole} />
            </TabsContent>
          )}
        </Tabs>
      )}
    </div>
  );
}
