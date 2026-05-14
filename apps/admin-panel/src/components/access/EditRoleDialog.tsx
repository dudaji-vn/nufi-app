import { useState, useEffect, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient, keepPreviousData } from '@tanstack/react-query';
import type { AdminMember, AdminUserSearchResult } from '@librechat/data-schemas';
import type * as t from '@/types';
import {
  Badge,
  Button,
  Input,
  Label,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '@/components/ui';
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
  addRoleMemberFn,
  removeRoleMemberFn,
  roleQueryOptions,
  roleMembersQueryOptions,
  updateRoleFn,
  updateRolePermissionsFn,
  MEMBERS_PAGE_SIZE,
} from '@/server';
import { RolePermissionsPanel } from './RolePermissionsPanel';
import { useLocalize } from '@/hooks';
import { cn } from '@/utils';

type EditRoleTab = 'details' | 'permissions' | 'members';

export function EditRoleDialog({ role, canManage, onClose }: t.EditRoleDialogProps) {
  const localize = useLocalize();
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<EditRoleTab>('details');
  const [name, setName] = useState(role?.name ?? '');
  const [description, setDescription] = useState(role?.description ?? '');
  const [permissions, setPermissions] = useState<t.RolePermissions | null>(null);
  const [error, setError] = useState('');

  const [page, setPage] = useState(1);
  const [pendingAdditions, setPendingAdditions] = useState<AdminUserSearchResult[]>([]);
  const [pendingRemovals, setPendingRemovals] = useState<AdminMember[]>([]);

  const roleDetail = useQuery({
    ...roleQueryOptions(role?.id ?? ''),
    enabled: !!role,
  });

  useEffect(() => {
    if (roleDetail.data && permissions === null) {
      setPermissions(roleDetail.data.permissions);
    }
  }, [roleDetail.data, permissions]);

  const membersQuery = useQuery({
    ...roleMembersQueryOptions(role?.id ?? '', page),
    placeholderData: keepPreviousData,
    enabled: !!role,
  });

  const members = membersQuery.data?.members ?? [];
  const total = membersQuery.data?.total ?? 0;
  const totalPages = Math.ceil(total / MEMBERS_PAGE_SIZE);
  const removalIds = new Set(pendingRemovals.map((m) => m.userId));
  const existingIds = [...members.map((m) => m.userId), ...pendingAdditions.map((u) => u.id)];

  const detailsDirty = name !== role?.name || description !== role?.description;
  const permissionsDirty =
    permissions !== null &&
    JSON.stringify(permissions) !== JSON.stringify(roleDetail.data?.permissions);
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

  const updateMutation = useMutation({
    mutationFn: async (): Promise<string> => {
      if (!role) return '';
      let roleId = role.id;
      if (detailsDirty) {
        const result = await updateRoleFn({ data: { id: role.id, name, description } });
        roleId = result.role.id;
      }
      if (permissionsDirty && permissions) {
        try {
          await updateRolePermissionsFn({ data: { id: roleId, permissions } });
        } catch (err) {
          if (detailsDirty) {
            throw new Error(
              localize('com_access_details_saved_permissions_failed', {
                error: (err as Error).message,
              }),
            );
          }
          throw err;
        }
      }
      const memberResults = await Promise.allSettled([
        ...pendingAdditions.map((user) =>
          addRoleMemberFn({ data: { roleId, userId: user.id } }),
        ),
        ...pendingRemovals.map((member) =>
          removeRoleMemberFn({ data: { roleId, userId: member.userId } }),
        ),
      ]);
      const failures = memberResults.filter(
        (r): r is PromiseRejectedResult => r.status === 'rejected',
      );
      if (failures.length > 0) {
        const parts: string[] = [];
        if (detailsDirty) parts.push(localize('com_access_details_saved'));
        if (permissionsDirty) parts.push(localize('com_access_permissions_saved'));
        parts.push(localize('com_access_member_ops_failed', { count: failures.length }));
        throw new Error(parts.join(', '));
      }
      return roleId;
    },
    onSuccess: (newRoleId) => {
      queryClient.invalidateQueries({ queryKey: ['roles'] });
      queryClient.invalidateQueries({ queryKey: ['role', role?.id] });
      if (newRoleId !== role?.id) {
        queryClient.invalidateQueries({ queryKey: ['role', newRoleId] });
      }
      queryClient.invalidateQueries({ queryKey: ['roleAssignments'] });
      queryClient.invalidateQueries({ queryKey: ['roleMembers', role?.id] });
      if (newRoleId !== role?.id) {
        queryClient.invalidateQueries({ queryKey: ['roleMembers', newRoleId] });
      }
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
    updateMutation.mutate();
  };

  return (
    <FormDialog
      open={!!role}
      title={localize('com_access_edit_role')}
      submitLabel={localize('com_ui_save')}
      submitDisabled={
        !canManage ||
        !name.trim() ||
        (permissionsDirty && permissions === null) ||
        (!detailsDirty && !permissionsDirty && !membersDirty)
      }
      saving={updateMutation.isPending}
      error={error}
      size="lg"
      onSubmit={doSubmit}
      onClose={onClose}
    >
      <Tabs
        value={activeTab}
        onValueChange={(v) => setActiveTab(v as EditRoleTab)}
        aria-label={localize('com_access_edit_role')}
      >
        <TabsList>
          <TabsTrigger value="details">{localize('com_access_tab_details')}</TabsTrigger>
          <TabsTrigger value="permissions">{localize('com_access_tab_permissions')}</TabsTrigger>
          <TabsTrigger value="members">{localize('com_access_tab_members')}</TabsTrigger>
        </TabsList>
        <TabsContent
          value="details"
          forceMount
          tabIndex={-1}
          className={cn(activeTab !== 'details' && 'hidden')}
        >
          <div className="flex flex-col gap-5 pt-3">
            {role?.isSystemRole && (
              <Badge variant="secondary" className="w-fit">
                {localize('com_access_system_role')}
              </Badge>
            )}
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="edit-role-name">{localize('com_access_col_name')}</Label>
              <Input
                id="edit-role-name"
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={localize('com_access_role_name_placeholder')}
                disabled={role?.isSystemRole || !canManage}
                readOnly={!canManage}
                autoFocus
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="edit-role-description">
                {localize('com_config_field_description')}
              </Label>
              <Input
                id="edit-role-description"
                type="text"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder={localize('com_access_role_desc_placeholder')}
                disabled={!canManage}
                readOnly={!canManage}
              />
            </div>
          </div>
        </TabsContent>
        <TabsContent
          value="permissions"
          forceMount
          tabIndex={-1}
          className={cn(activeTab !== 'permissions' && 'hidden')}
        >
          <div className="pt-3">
            {(() => {
              if (roleDetail.isLoading) {
                return <LoadingState className="flex items-center justify-center py-8" />;
              }
              if (roleDetail.isError || !permissions) {
                return (
                  <div className="flex flex-col items-center justify-center gap-3 py-8 text-center text-sm text-muted-foreground">
                    <p>{localize('com_access_permissions_load_error')}</p>
                    {roleDetail.isError && (
                      <Button type="button" variant="outline" onClick={() => roleDetail.refetch()}>
                        {localize('com_ui_retry')}
                      </Button>
                    )}
                  </div>
                );
              }
              return (
                <RolePermissionsPanel
                  permissions={permissions}
                  onChange={setPermissions}
                  disabled={!canManage || updateMutation.isPending}
                />
              );
            })()}
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
                listboxId="edit-role-member-search"
                disabled={updateMutation.isPending}
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
                  disabled={updateMutation.isPending}
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
                  disabled={updateMutation.isPending}
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
