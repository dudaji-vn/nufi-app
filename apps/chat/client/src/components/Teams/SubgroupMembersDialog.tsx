import React from 'react';
import { UserMinus, UserPlus } from 'lucide-react';
import {
  Button,
  Spinner,
  useToastContext,
  OGDialog,
  OGDialogContent,
  OGDialogHeader,
  OGDialogTitle,
} from '@librechat/client';
import type { TTeamMember } from 'librechat-data-provider';
import {
  useSubgroupQuery,
  useTeamQuery,
  useAddSubgroupMemberMutation,
  useRemoveSubgroupMemberMutation,
} from '~/data-provider';
import { useLocalize } from '~/hooks';

function MemberInitialsAvatar({ name, email }: { name: string; email: string }) {
  const initials = (name || email || '?').slice(0, 2).toUpperCase();
  return (
    <div
      className="flex size-8 shrink-0 items-center justify-center rounded-full bg-surface-tertiary text-xs font-semibold text-text-secondary"
      aria-hidden="true"
    >
      {initials}
    </div>
  );
}

interface MemberPickerProps {
  teamId: string;
  sgId: string;
  currentMemberIds: Set<string>;
}

function MemberPicker({ teamId, sgId, currentMemberIds }: MemberPickerProps) {
  const localize = useLocalize();
  const { showToast } = useToastContext();
  const { data: teamData } = useTeamQuery(teamId);
  const teamMembers: TTeamMember[] = teamData?.members ?? [];

  const { mutate: addMember, isLoading } = useAddSubgroupMemberMutation(teamId, {
    onSuccess: () => {
      showToast({ message: localize('com_ui_team_member_added'), status: 'success' });
    },
    onError: (error: Error) => {
      showToast({ message: error.message || localize('com_ui_error'), status: 'error' });
    },
  });

  const available = teamMembers.filter((m) => !currentMemberIds.has(m.userId));

  if (available.length === 0) {
    return (
      <p className="py-4 text-center text-sm text-text-secondary">
        {localize('com_ui_team_no_members_to_add')}
      </p>
    );
  }

  return (
    <ul className="flex max-h-60 flex-col gap-1 overflow-y-auto py-2">
      {available.map((member) => {
        const displayName = member.name || member.email;
        return (
          <li
            key={member.userId}
            className="flex items-center justify-between gap-3 rounded-lg px-3 py-2 hover:bg-surface-hover"
          >
            <div className="flex min-w-0 flex-1 items-center gap-3">
              {member.avatar != null && member.avatar !== '' ? (
                <img
                  src={member.avatar}
                  alt={displayName}
                  className="size-8 shrink-0 rounded-full object-cover"
                />
              ) : (
                <MemberInitialsAvatar name={member.name} email={member.email} />
              )}
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-text-primary">{displayName}</p>
                {member.name !== '' && member.name != null && (
                  <p className="truncate text-xs text-text-secondary">{member.email}</p>
                )}
              </div>
            </div>
            <Button
              variant="outline"
              size="sm"
              disabled={isLoading}
              onClick={() => addMember({ sgId, userId: member.userId })}
              aria-label={`${localize('com_ui_team_add_to_group')}: ${displayName}`}
            >
              {isLoading ? (
                <Spinner className="size-3.5" />
              ) : (
                <UserPlus className="size-3.5" aria-hidden="true" />
              )}
            </Button>
          </li>
        );
      })}
    </ul>
  );
}

interface SubgroupMembersDialogProps {
  teamId: string;
  sgId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export default function SubgroupMembersDialog({
  teamId,
  sgId,
  open,
  onOpenChange,
}: SubgroupMembersDialogProps) {
  const localize = useLocalize();
  const { showToast } = useToastContext();
  const { data, isLoading } = useSubgroupQuery(teamId, sgId, { enabled: open });

  const members = data?.members ?? [];
  const currentMemberIds = new Set(members.map((m) => m.userId));

  const { mutate: removeMember, isLoading: isRemoving } = useRemoveSubgroupMemberMutation(teamId, {
    onSuccess: () => {
      showToast({ message: localize('com_ui_team_member_removed'), status: 'success' });
    },
    onError: (error: Error) => {
      showToast({ message: error.message || localize('com_ui_error'), status: 'error' });
    },
  });

  return (
    <OGDialog open={open} onOpenChange={onOpenChange}>
      <OGDialogContent className="w-11/12 md:max-w-lg">
        <OGDialogHeader>
          <OGDialogTitle>{localize('com_ui_team_manage_members')}</OGDialogTitle>
        </OGDialogHeader>

        {isLoading ? (
          <div className="flex items-center justify-center py-8">
            <Spinner className="text-text-secondary" aria-label={localize('com_ui_loading')} />
          </div>
        ) : (
          <div className="flex flex-col gap-4">
            {members.length > 0 && (
              <div>
                <p className="mb-2 text-xs font-medium uppercase tracking-wide text-text-secondary">
                  {localize('com_ui_team_members')}
                </p>
                <ul className="flex flex-col gap-1">
                  {members.map((member) => {
                    const displayName = member.name || member.email;
                    return (
                      <li
                        key={member.userId}
                        className="flex items-center justify-between gap-3 rounded-lg border border-border-light bg-surface-primary px-3.5 py-2.5"
                      >
                        <div className="flex min-w-0 flex-1 items-center gap-3">
                          {member.avatar != null && member.avatar !== '' ? (
                            <img
                              src={member.avatar}
                              alt={displayName}
                              className="size-8 shrink-0 rounded-full object-cover"
                            />
                          ) : (
                            <MemberInitialsAvatar name={member.name} email={member.email} />
                          )}
                          <div className="min-w-0">
                            <p className="truncate text-sm font-medium text-text-primary">
                              {displayName}
                            </p>
                            {member.name !== '' && member.name != null && (
                              <p className="truncate text-xs text-text-secondary">{member.email}</p>
                            )}
                          </div>
                        </div>
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={isRemoving}
                          onClick={() => removeMember({ sgId, userId: member.userId })}
                          aria-label={localize('com_ui_team_remove_member')}
                        >
                          {isRemoving ? (
                            <Spinner className="size-3.5" />
                          ) : (
                            <UserMinus className="size-3.5" aria-hidden="true" />
                          )}
                        </Button>
                      </li>
                    );
                  })}
                </ul>
              </div>
            )}

            <div>
              <p className="mb-1 text-xs font-medium uppercase tracking-wide text-text-secondary">
                {localize('com_ui_team_add_to_group')}
              </p>
              <MemberPicker teamId={teamId} sgId={sgId} currentMemberIds={currentMemberIds} />
            </div>
          </div>
        )}
      </OGDialogContent>
    </OGDialog>
  );
}
