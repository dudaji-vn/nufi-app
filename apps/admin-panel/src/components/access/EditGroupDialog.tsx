import { useState, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient, keepPreviousData } from '@tanstack/react-query';
import type { AdminMember, AdminUserSearchResult } from '@librechat/data-schemas';
import type * as t from '@/types';
import { Input, Label, Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui';
import {
  Avatar,
  FormDialog,
  LoadingState,
  Pagination,
  SelectedMemberList,
  TrashButton,
  UserSearchInline,
} from '@/components/shared';
import {
  addGroupMemberFn,
  groupMembersQueryOptions,
  removeGroupMemberFn,
  updateGroupFn,
  MEMBERS_PAGE_SIZE,
} from '@/server';
import { useLocalize } from '@/hooks';
import { cn } from '@/utils';

type EditGroupTab = 'details' | 'members';

export function EditGroupDialog({ group, canManage, onClose }: t.EditGroupDialogProps) {
  const localize = useLocalize();
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<EditGroupTab>('details');
  const [name, setName] = useState(group?.name ?? '');
  const [description, setDescription] = useState(group?.description ?? '');
  const [error, setError] = useState('');

  const [page, setPage] = useState(1);
  const [pendingAdditions, setPendingAdditions] = useState<AdminUserSearchResult[]>([]);
  const [pendingRemovals, setPendingRemovals] = useState<AdminMember[]>([]);

  const membersQuery = useQuery({
    ...groupMembersQueryOptions(group?.id ?? '', page),
    placeholderData: keepPreviousData,
    enabled: !!group,
  });

  const members = membersQuery.data?.members ?? [];
  const total = membersQuery.data?.total ?? 0;
  const totalPages = Math.ceil(total / MEMBERS_PAGE_SIZE);
  const removalIds = new Set(pendingRemovals.map((m) => m.userId));
  const existingIds = [...members.map((m) => m.userId), ...pendingAdditions.map((u) => u.id)];

  const detailsDirty = name !== group?.name || description !== group?.description;
  const membersDirty = pendingAdditions.length > 0 || pendingRemovals.length > 0;

  const addUser = (user: AdminUserSearchResult) => {
    setPendingAdditions((prev) => {
      if (prev.some((u) => u.id === user.id)) return prev;
      return [...prev, user];
    });
  };

  const removePendingUser = (userId: string) => {
    setPendingAdditions((prev) => prev.filter((u) => u.id !== userId));
  };

  const stageRemoval = useCallback((member: AdminMember) => {
    setPendingRemovals((prev) => {
      if (prev.some((m) => m.userId === member.userId)) return prev;
      return [...prev, member];
    });
  }, []);

  const unstageRemoval = (userId: string) => {
    setPendingRemovals((prev) => prev.filter((m) => m.userId !== userId));
  };

  const mutation = useMutation({
    mutationFn: async () => {
      if (!group) return;
      if (detailsDirty) {
        await updateGroupFn({ data: { id: group.id, name, description } });
      }
      const memberResults = await Promise.allSettled([
        ...pendingAdditions.map((user) =>
          addGroupMemberFn({ data: { groupId: group.id, userId: user.id } }),
        ),
        ...pendingRemovals.map((member) =>
          removeGroupMemberFn({ data: { groupId: group.id, userId: member.userId } }),
        ),
      ]);
      const failures = memberResults.filter(
        (r): r is PromiseRejectedResult => r.status === 'rejected',
      );
      if (failures.length > 0) {
        const parts: string[] = [];
        if (detailsDirty) parts.push(localize('com_access_details_saved'));
        parts.push(localize('com_access_member_ops_failed', { count: failures.length }));
        throw new Error(parts.join(', '));
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['groups'] });
      queryClient.invalidateQueries({ queryKey: ['groupAssignments'] });
      queryClient.invalidateQueries({ queryKey: ['groupMembers', group?.id] });
      onClose();
    },
    onError: (err: Error) => setError(err.message),
  });

  const doSubmit = () => {
    setError('');
    if (!name.trim()) {
      setError(localize('com_access_name_required'));
      setActiveTab('details');
      return;
    }
    mutation.mutate();
  };

  return (
    <FormDialog
      open={!!group}
      title={localize('com_access_edit_group')}
      submitLabel={localize('com_ui_save')}
      submitDisabled={!canManage || !name.trim() || (!detailsDirty && !membersDirty)}
      saving={mutation.isPending}
      error={error}
      size="lg"
      onSubmit={doSubmit}
      onClose={onClose}
    >
      <Tabs
        value={activeTab}
        onValueChange={(v) => setActiveTab(v as EditGroupTab)}
        aria-label={localize('com_access_edit_group')}
      >
        <TabsList>
          <TabsTrigger value="details">{localize('com_access_tab_details')}</TabsTrigger>
          <TabsTrigger value="members">{localize('com_access_tab_members')}</TabsTrigger>
        </TabsList>
        <TabsContent
          value="details"
          forceMount
          tabIndex={-1}
          className={cn(activeTab !== 'details' && 'hidden')}
        >
          <div className="flex flex-col gap-5 pt-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="edit-group-name">{localize('com_access_col_name')}</Label>
              <Input
                id="edit-group-name"
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={localize('com_access_group_name_placeholder')}
                disabled={!canManage}
                readOnly={!canManage}
                autoFocus
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="edit-group-description">
                {localize('com_config_field_description')}
              </Label>
              <Input
                id="edit-group-description"
                type="text"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder={localize('com_access_group_desc_placeholder')}
                disabled={!canManage}
                readOnly={!canManage}
              />
            </div>
          </div>
        </TabsContent>
        <TabsContent
          value="members"
          forceMount
          tabIndex={-1}
          className={cn(activeTab !== 'members' && 'hidden')}
        >
          <div className="flex flex-col gap-4 pt-3">
            {canManage && (
              <UserSearchInline
                existingIds={existingIds}
                onAdd={addUser}
                listboxId="edit-group-member-search"
                disabled={mutation.isPending}
              />
            )}
            {pendingAdditions.length > 0 && (
              <div className="flex flex-col gap-1">
                <span className="text-xs font-medium text-muted-foreground">
                  {localize('com_access_pending_additions', { count: pendingAdditions.length })}
                </span>
                <SelectedMemberList
                  users={pendingAdditions}
                  onRemove={removePendingUser}
                  disabled={mutation.isPending}
                />
              </div>
            )}
            {pendingRemovals.length > 0 && (
              <div className="flex flex-col gap-1">
                <span className="text-xs font-medium text-muted-foreground">
                  {localize('com_access_pending_removals', { count: pendingRemovals.length })}
                </span>
                <SelectedMemberList
                  users={pendingRemovals.map((m) => ({
                    id: m.userId,
                    name: m.name,
                    email: m.email,
                    avatarUrl: m.avatarUrl,
                  }))}
                  onRemove={unstageRemoval}
                  disabled={mutation.isPending}
                />
              </div>
            )}
            <MemberList
              members={members}
              loading={membersQuery.isLoading}
              error={membersQuery.isError}
              fetching={membersQuery.isFetching}
              removalIds={removalIds}
              onRemove={stageRemoval}
              canManage={canManage}
              total={total}
              currentPage={page}
              totalPages={totalPages}
              onPageChange={setPage}
            />
          </div>
        </TabsContent>
      </Tabs>
    </FormDialog>
  );
}

interface MemberListProps {
  members: AdminMember[];
  loading: boolean;
  error: boolean;
  fetching: boolean;
  removalIds: Set<string>;
  onRemove: (member: AdminMember) => void;
  canManage: boolean;
  total: number;
  currentPage: number;
  totalPages: number;
  onPageChange: (page: number) => void;
}

function MemberList({
  members,
  loading,
  error,
  fetching,
  removalIds,
  onRemove,
  canManage,
  total,
  currentPage,
  totalPages,
  onPageChange,
}: MemberListProps) {
  const localize = useLocalize();

  if (loading) {
    return (
      <LoadingState className="flex items-center justify-center gap-2 py-6 text-sm text-muted-foreground" />
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center py-6 text-sm text-destructive">
        {localize('com_error_load_members')}
      </div>
    );
  }

  if (members.length === 0 && total === 0) {
    return (
      <div className="flex items-center justify-center py-6 text-sm text-muted-foreground">
        {localize('com_access_no_members')}
      </div>
    );
  }

  return (
    <div className="flex flex-col">
      <span className="mb-2 text-xs font-medium text-muted-foreground">
        {localize('com_access_member_count', { count: total })}
      </span>
      <div
        className={cn(
          'max-h-64 overflow-auto rounded-lg border border-border',
          fetching && 'opacity-60 transition-opacity',
        )}
      >
        {members.map((member, i) => {
          const staged = removalIds.has(member.userId);
          return (
            <div
              key={member.userId}
              className={cn(
                'flex items-center justify-between px-3 py-2',
                i < members.length - 1 && 'border-b border-border',
                staged && 'opacity-40',
              )}
            >
              <div className="flex items-center gap-3">
                <Avatar name={member.name} />
                <div className="flex flex-col">
                  <span
                    className={cn(
                      'text-sm font-medium text-foreground',
                      staged && 'line-through',
                    )}
                  >
                    {member.name}
                  </span>
                  <span className="text-xs text-muted-foreground">{member.email}</span>
                </div>
              </div>
              {canManage && !staged && (
                <TrashButton
                  onClick={() => onRemove(member)}
                  ariaLabel={`${localize('com_access_remove_member')} ${member.name}`}
                />
              )}
            </div>
          );
        })}
      </div>
      <Pagination currentPage={currentPage} totalPages={totalPages} onPageChange={onPageChange} />
    </div>
  );
}
