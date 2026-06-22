import React, { useState } from 'react';
import { Users, Pencil, Trash2, UserCog, Plus } from 'lucide-react';
import {
  Button,
  Spinner,
  useToastContext,
  OGDialog,
  OGDialogTrigger,
  OGDialogTemplate,
} from '@librechat/client';
import type { TSubgroup, TeamRole } from 'librechat-data-provider';
import { useSubgroupsQuery, useDeleteSubgroupMutation } from '~/data-provider';
import { useLocalize } from '~/hooks';
import SubgroupDialog from './SubgroupDialog';
import SubgroupMembersDialog from './SubgroupMembersDialog';

interface SubgroupCardProps {
  subgroup: TSubgroup;
  teamId: string;
  canManage: boolean;
}

function SubgroupCard({ subgroup, teamId, canManage }: SubgroupCardProps) {
  const localize = useLocalize();
  const { showToast } = useToastContext();
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [membersOpen, setMembersOpen] = useState(false);

  const { mutate: deleteSubgroup, isLoading: isDeleting } = useDeleteSubgroupMutation(teamId, {
    onSuccess: () => {
      showToast({ message: localize('com_ui_team_group_deleted'), status: 'success' });
      setDeleteOpen(false);
    },
    onError: (error: Error) => {
      showToast({ message: error.message || localize('com_ui_error'), status: 'error' });
    },
  });

  return (
    <li className="flex items-center justify-between gap-3 rounded-lg border border-border-light bg-surface-primary px-3.5 py-2.5">
      <div className="flex min-w-0 flex-1 items-center gap-3">
        <div className="flex size-8 shrink-0 items-center justify-center rounded-full bg-surface-tertiary">
          <Users className="size-4 text-text-secondary" aria-hidden="true" />
        </div>
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-text-primary">{subgroup.name}</p>
          {subgroup.description != null && subgroup.description !== '' && (
            <p className="truncate text-xs text-text-secondary">{subgroup.description}</p>
          )}
        </div>
      </div>

      <div className="flex shrink-0 items-center gap-2">
        <span className="rounded-full bg-surface-tertiary px-2 py-0.5 text-xs font-medium text-text-secondary">
          {localize('com_ui_members_count').replace('{{0}}', String(subgroup.memberCount))}
        </span>

        {canManage && (
          <>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setMembersOpen(true)}
              aria-label={localize('com_ui_team_manage_members')}
            >
              <UserCog className="size-3.5" aria-hidden="true" />
            </Button>

            <SubgroupDialog teamId={teamId} subgroup={subgroup}>
              <Button variant="outline" size="sm" aria-label={localize('com_ui_team_rename_group')}>
                <Pencil className="size-3.5" aria-hidden="true" />
              </Button>
            </SubgroupDialog>

            <OGDialog open={deleteOpen} onOpenChange={setDeleteOpen}>
              <OGDialogTrigger asChild>
                <Button
                  variant="outline"
                  size="sm"
                  aria-label={localize('com_ui_team_delete_group')}
                >
                  <Trash2 className="size-3.5" aria-hidden="true" />
                </Button>
              </OGDialogTrigger>
              <OGDialogTemplate
                title={localize('com_ui_team_delete_group')}
                showCloseButton={false}
                className="w-11/12 md:max-w-md"
                main={
                  <p className="text-sm text-text-secondary">
                    {localize('com_ui_team_delete_group_confirm')}
                  </p>
                }
                buttons={
                  <Button
                    type="button"
                    variant="destructive"
                    onClick={() => deleteSubgroup(subgroup._id)}
                    disabled={isDeleting}
                    aria-label={localize('com_ui_confirm')}
                  >
                    {isDeleting ? <Spinner className="size-4" /> : localize('com_ui_delete')}
                  </Button>
                }
              />
            </OGDialog>

            <SubgroupMembersDialog
              teamId={teamId}
              sgId={subgroup._id}
              open={membersOpen}
              onOpenChange={setMembersOpen}
            />
          </>
        )}
      </div>
    </li>
  );
}

interface GroupsTabProps {
  teamId: string;
  callerRole: TeamRole;
}

export default function GroupsTab({ teamId, callerRole }: GroupsTabProps) {
  const localize = useLocalize();
  const { data, isLoading } = useSubgroupsQuery(teamId);
  const canManage = callerRole !== 'member';
  const subgroups: TSubgroup[] = data?.subgroups ?? [];

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Spinner className="text-text-secondary" aria-label={localize('com_ui_loading')} />
      </div>
    );
  }

  return (
    <section aria-label={localize('com_ui_team_groups')} className="flex flex-col gap-4">
      {canManage && (
        <div className="flex justify-end">
          <SubgroupDialog teamId={teamId}>
            <Button
              variant="submit"
              className="gap-1.5 text-white"
              aria-label={localize('com_ui_team_new_group')}
            >
              <Plus className="size-4" aria-hidden="true" />
              {localize('com_ui_team_new_group')}
            </Button>
          </SubgroupDialog>
        </div>
      )}

      {subgroups.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-border-light py-12 text-center">
          <Users className="size-8 text-text-tertiary" aria-hidden="true" />
          <p className="text-sm text-text-secondary">{localize('com_ui_team_no_groups')}</p>
        </div>
      ) : (
        <ul className="flex flex-col gap-2">
          {subgroups.map((sg) => (
            <SubgroupCard key={sg._id} subgroup={sg} teamId={teamId} canManage={canManage} />
          ))}
        </ul>
      )}
    </section>
  );
}
