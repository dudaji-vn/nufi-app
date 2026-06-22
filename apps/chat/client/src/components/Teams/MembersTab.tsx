import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { UserMinus, UserPlus, ArrowRightLeft } from 'lucide-react';
import {
  Button,
  Spinner,
  useToastContext,
  OGDialog,
  OGDialogTrigger,
  OGDialogTemplate,
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from '@librechat/client';
import type { TTeamMember, TeamRole } from 'librechat-data-provider';
import type { TranslationKeys } from '~/hooks';
import {
  useRemoveMemberMutation,
  useChangeMemberRoleMutation,
  useTransferOwnershipMutation,
} from '~/data-provider';
import { useLocalize } from '~/hooks';
import InviteByEmailDialog from './InviteByEmailDialog';

const roleLabelKey: Record<TeamRole, TranslationKeys> = {
  owner: 'com_ui_role_owner',
  admin: 'com_ui_role_admin',
  member: 'com_ui_role_member',
};

interface MemberRowProps {
  member: TTeamMember;
  teamId: string;
  callerRole: TeamRole;
  callerId: string;
}

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

function MemberRow({ member, teamId, callerRole, callerId }: MemberRowProps) {
  const localize = useLocalize();
  const { showToast } = useToastContext();
  const navigate = useNavigate();
  const [removeOpen, setRemoveOpen] = useState(false);
  const [transferOpen, setTransferOpen] = useState(false);

  const isSelf = member.userId === callerId;
  const isOwner = callerRole === 'owner';
  const isAdmin = callerRole === 'admin';
  const canManage = isOwner || isAdmin;

  const { mutate: removeMember, isLoading: isRemoving } = useRemoveMemberMutation({
    onSuccess: () => {
      showToast({
        message: isSelf ? localize('com_ui_team_leave') : localize('com_ui_team_remove_member'),
        status: 'success',
      });
      setRemoveOpen(false);
      if (isSelf) {
        navigate('/teams');
      }
    },
    onError: (error: Error) => {
      showToast({ message: error.message || localize('com_ui_error'), status: 'error' });
    },
  });

  const { mutate: changeRole, isLoading: isChangingRole } = useChangeMemberRoleMutation({
    onSuccess: () => {
      showToast({ message: localize('com_ui_team_change_role'), status: 'success' });
    },
    onError: (error: Error) => {
      showToast({ message: error.message || localize('com_ui_error'), status: 'error' });
    },
  });

  const { mutate: transferOwnership, isLoading: isTransferring } = useTransferOwnershipMutation({
    onSuccess: () => {
      showToast({ message: localize('com_ui_team_transfer_ownership'), status: 'success' });
      setTransferOpen(false);
    },
    onError: (error: Error) => {
      showToast({ message: error.message || localize('com_ui_error'), status: 'error' });
    },
  });

  const canChangeRole = canManage && !isSelf && member.role !== 'owner';
  const canRemove = (canManage && !isSelf && member.role !== 'owner') || (isSelf && !isOwner);
  const canTransfer = isOwner && !isSelf && member.role !== 'owner';

  const isPending = isRemoving || isChangingRole || isTransferring;
  const displayName = member.name || member.email;

  return (
    <li className="flex items-center justify-between gap-3 rounded-lg border border-border-light bg-surface-primary px-3.5 py-2.5">
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
      <div className="flex shrink-0 items-center gap-2">
        <span className="rounded-full bg-surface-tertiary px-2 py-0.5 text-xs font-medium text-text-secondary">
          {localize(roleLabelKey[member.role])}
        </span>

        {canChangeRole && (
          <Select
            value={member.role as 'admin' | 'member'}
            onValueChange={(v) =>
              changeRole({ teamId, userId: member.userId, role: v as 'admin' | 'member' })
            }
            disabled={isPending}
          >
            <SelectTrigger
              className="h-7 w-[90px] text-xs"
              aria-label={localize('com_ui_team_change_role')}
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="admin">{localize('com_ui_role_admin')}</SelectItem>
              <SelectItem value="member">{localize('com_ui_role_member')}</SelectItem>
            </SelectContent>
          </Select>
        )}

        {canTransfer && (
          <OGDialog open={transferOpen} onOpenChange={setTransferOpen}>
            <OGDialogTrigger asChild>
              <Button
                variant="outline"
                size="sm"
                disabled={isPending}
                aria-label={localize('com_ui_team_transfer_ownership')}
              >
                <ArrowRightLeft className="size-3.5" aria-hidden="true" />
              </Button>
            </OGDialogTrigger>
            <OGDialogTemplate
              title={localize('com_ui_team_transfer_ownership')}
              showCloseButton={false}
              className="w-11/12 md:max-w-md"
              main={
                <p className="text-sm text-text-secondary">
                  {localize('com_ui_team_transfer_confirm')}
                </p>
              }
              buttons={
                <Button
                  type="button"
                  variant="destructive"
                  onClick={() => transferOwnership({ teamId, newOwnerId: member.userId })}
                  disabled={isTransferring}
                  aria-label={localize('com_ui_confirm')}
                >
                  {isTransferring ? <Spinner className="size-4" /> : localize('com_ui_confirm')}
                </Button>
              }
            />
          </OGDialog>
        )}

        {canRemove && (
          <OGDialog open={removeOpen} onOpenChange={setRemoveOpen}>
            <OGDialogTrigger asChild>
              <Button
                variant="outline"
                size="sm"
                disabled={isPending}
                aria-label={
                  isSelf ? localize('com_ui_team_leave') : localize('com_ui_team_remove_member')
                }
              >
                <UserMinus className="size-3.5" aria-hidden="true" />
              </Button>
            </OGDialogTrigger>
            <OGDialogTemplate
              title={isSelf ? localize('com_ui_team_leave') : localize('com_ui_team_remove_member')}
              showCloseButton={false}
              className="w-11/12 md:max-w-md"
              main={
                <p className="text-sm text-text-secondary">
                  {isSelf
                    ? localize('com_ui_team_leave_confirm')
                    : localize('com_ui_team_remove_confirm')}
                </p>
              }
              buttons={
                <Button
                  type="button"
                  variant="destructive"
                  onClick={() => removeMember({ teamId, userId: member.userId })}
                  disabled={isRemoving}
                  aria-label={localize('com_ui_confirm')}
                >
                  {isRemoving ? <Spinner className="size-4" /> : localize('com_ui_confirm')}
                </Button>
              }
            />
          </OGDialog>
        )}
      </div>
    </li>
  );
}

interface MembersTabProps {
  teamId: string;
  members: TTeamMember[];
  callerRole: TeamRole;
  callerId: string;
}

export default function MembersTab({ teamId, members, callerRole, callerId }: MembersTabProps) {
  const localize = useLocalize();
  const canInvite = callerRole === 'owner' || callerRole === 'admin';

  return (
    <section aria-label={localize('com_ui_team_members')} className="flex flex-col gap-4">
      {canInvite && (
        <div className="flex justify-end">
          <InviteByEmailDialog teamId={teamId}>
            <Button
              variant="submit"
              className="gap-1.5 text-white"
              aria-label={localize('com_ui_team_invite_member')}
            >
              <UserPlus className="size-4" aria-hidden="true" />
              {localize('com_ui_team_invite_member')}
            </Button>
          </InviteByEmailDialog>
        </div>
      )}
      <ul className="flex flex-col gap-2">
        {members.map((member) => (
          <MemberRow
            key={member.userId}
            member={member}
            teamId={teamId}
            callerRole={callerRole}
            callerId={callerId}
          />
        ))}
      </ul>
    </section>
  );
}
