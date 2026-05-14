import { useState, useMemo } from 'react';
import { Lock, Plus, Trash2, User as UserIcon, Users as UsersGroupIcon } from 'lucide-react';
import { PrincipalType, SystemRoles } from 'librechat-data-provider';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import type { TUser } from 'librechat-data-provider';
import type * as t from '@/types';
import {
  availableScopesOptions,
  deleteUserFn,
  groupAssignmentsQueryOptions,
  roleAssignmentsQueryOptions,
  usersQueryOptions,
} from '@/server';
import {
  Avatar,
  EmptyState,
  KebabMenu,
  LoadingState,
  ScreenReaderAnnouncer,
  SearchInput,
} from '@/components/shared';
import { useAnnouncement, useCapabilities, useLocalize } from '@/hooks';
import { CreateUserDialog } from './CreateUserDialog';
import { UserDetailDialog } from './UserDetailDialog';
import { ConfirmDialog } from '@/components/access';
import { SystemCapabilities } from '@/constants';
import { cn } from '@/utils';

const ROLE_FILTER_LABELS: Record<t.RoleFilter, string> = {
  all: 'com_ui_all',
  admin: 'com_users_admins',
  user: 'com_nav_users',
};

export function UsersPage() {
  const localize = useLocalize();
  const queryClient = useQueryClient();
  const { hasCapability } = useCapabilities();
  const canManage = hasCapability(SystemCapabilities.MANAGE_USERS);
  const canManageRoles = hasCapability(SystemCapabilities.MANAGE_ROLES);
  const canManageGroups = hasCapability(SystemCapabilities.MANAGE_GROUPS);
  const canAssignConfigs = hasCapability(SystemCapabilities.ASSIGN_CONFIGS);
  const [search, setSearch] = useState('');
  const [roleFilter, setRoleFilter] = useState<t.RoleFilter>('all');
  const [createOpen, setCreateOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<TUser | null>(null);
  const [detailUser, setDetailUser] = useState<TUser | null>(null);
  const { message: announcement, announce } = useAnnouncement();

  const { data: users = [], isLoading } = useQuery(usersQueryOptions);
  const { data: roleAssignments = {} } = useQuery(roleAssignmentsQueryOptions);
  const { data: groupAssignments = {} } = useQuery(groupAssignmentsQueryOptions);
  const { data: allScopes = [] } = useQuery(availableScopesOptions);

  const userProfileSet = useMemo(() => {
    const set = new Set<string>();
    for (const s of allScopes) {
      if (s.principalType === PrincipalType.USER) set.add(s.principalId);
    }
    return set;
  }, [allScopes]);

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteUserFn({ data: { id } }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] });
      queryClient.invalidateQueries({ queryKey: ['roleAssignments'] });
      queryClient.invalidateQueries({ queryKey: ['groupAssignments'] });
      queryClient.invalidateQueries({ queryKey: ['roleMembers'] });
      queryClient.invalidateQueries({ queryKey: ['groupMembers'] });
      queryClient.invalidateQueries({ queryKey: ['availableScopes'] });
      setDeleteTarget(null);
    },
  });

  const applyFilters = (list: TUser[], q: string, role: t.RoleFilter) =>
    list.filter((u) => {
      if (role === 'admin' && u.role !== SystemRoles.ADMIN) return false;
      if (role === 'user' && u.role !== SystemRoles.USER) return false;
      if (q) {
        const lower = q.toLowerCase();
        return u.name.toLowerCase().includes(lower) || u.email.toLowerCase().includes(lower);
      }
      return true;
    });

  const filtered = applyFilters(users, search, roleFilter);

  const handleSearchChange = (value: string) => {
    setSearch(value);
    const count = applyFilters(users, value, roleFilter).length;
    announce(localize('com_a11y_results_found', { count }));
  };

  const handleRoleFilter = (role: t.RoleFilter) => {
    setRoleFilter(role);
    const count = applyFilters(users, search, role).length;
    announce(localize('com_a11y_filter_changed', { count }));
  };

  if (isLoading) {
    return <LoadingState />;
  }

  return (
    <div
      role="region"
      aria-label={localize('com_nav_users')}
      className="flex flex-1 flex-col gap-6 overflow-auto p-6"
    >
      <section aria-label={localize('com_users_list')}>
        <div className="mb-3 flex flex-wrap items-center gap-3">
          <SearchInput
            value={search}
            onChange={handleSearchChange}
            placeholder={localize('com_users_search')}
            className="relative flex-1"
          />

          <div className="flex gap-1" role="group" aria-label={localize('com_users_role_filter')}>
            {(['all', 'admin', 'user'] as t.RoleFilter[]).map((role) => (
              <button
                key={role}
                type="button"
                aria-pressed={roleFilter === role}
                onClick={() => handleRoleFilter(role)}
                className={cn(
                  'rounded-md px-3 py-1.5 text-xs font-medium transition-colors',
                  roleFilter === role
                    ? 'bg-accent text-foreground'
                    : 'text-muted-foreground hover:bg-accent hover:text-foreground',
                )}
              >
                {localize(ROLE_FILTER_LABELS[role])}
              </button>
            ))}
          </div>

          <button
            type="button"
            onClick={() => setCreateOpen(true)}
            disabled={!canManage}
            aria-disabled={!canManage || undefined}
            title={
              !canManage
                ? localize('com_cap_no_permission', { cap: SystemCapabilities.MANAGE_USERS })
                : undefined
            }
            className="flex shrink-0 items-center gap-1.5 rounded-lg border border-border bg-transparent px-3 py-1.5 text-sm text-foreground transition-colors hover:bg-accent disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Plus aria-hidden="true" className="h-3.5 w-3.5" />
            {localize('com_users_add')}
          </button>
        </div>

        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-border bg-muted">
                <th scope="col" className="px-4 py-2.5 font-medium text-muted-foreground">
                  {localize('com_users_col_user')}
                </th>
                <th scope="col" className="px-4 py-2.5 font-medium text-muted-foreground">
                  {localize('com_users_col_role')}
                </th>
                <th scope="col" className="px-4 py-2.5 font-medium text-muted-foreground">
                  {localize('com_users_col_joined')}
                </th>
                <th scope="col" className="px-4 py-2.5 font-medium text-muted-foreground">
                  <span className="sr-only">{localize('com_ui_actions')}</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((user, i) => (
                <UserRow
                  key={user.id}
                  user={user}
                  roles={roleAssignments[user.id] ?? []}
                  groups={groupAssignments[user.id] ?? []}
                  hasUserProfile={userProfileSet.has(user.id)}
                  isLast={i === filtered.length - 1}
                  onViewDetails={() => setDetailUser(user)}
                  onDelete={() => setDeleteTarget(user)}
                  canManage={canManage}
                />
              ))}
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={4}>
                    <EmptyState message={localize('com_users_empty')} />
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <p className="mt-2 text-xs text-muted-foreground">
          {localize('com_users_showing')} {filtered.length} {localize('com_ui_of')} {users.length}{' '}
          {localize('com_nav_users').toLowerCase()}
        </p>
      </section>

      <CreateUserDialog open={createOpen} onClose={() => setCreateOpen(false)} />

      <UserDetailDialog
        user={detailUser}
        onClose={() => setDetailUser(null)}
        canManageRoles={canManageRoles}
        canManageGroups={canManageGroups}
        canAssignConfigs={canAssignConfigs}
      />

      <ConfirmDialog
        open={!!deleteTarget}
        title={localize('com_users_delete_title')}
        description={localize('com_users_delete_desc', { name: deleteTarget?.name ?? '' })}
        confirmLabel={localize('com_ui_delete')}
        saving={deleteMutation.isPending}
        onConfirm={() => {
          if (deleteTarget) deleteMutation.mutate(deleteTarget.id);
        }}
        onCancel={() => setDeleteTarget(null)}
      />

      <ScreenReaderAnnouncer message={announcement} />
    </div>
  );
}

function UserRow({
  user,
  roles,
  groups,
  hasUserProfile,
  isLast,
  onViewDetails,
  onDelete,
  canManage,
}: t.UserRowProps) {
  const localize = useLocalize();

  const kebabItems: t.KebabMenuItem[] = [
    { label: localize('com_users_view_details'), icon: UserIcon, onClick: onViewDetails },
    ...(canManage
      ? [
          {
            label: localize('com_ui_delete'),
            icon: Trash2,
            danger: true,
            onClick: onDelete,
          } as t.KebabMenuItem,
        ]
      : []),
  ];

  return (
    <tr
      className={cn(
        'cursor-pointer bg-card transition-colors hover:bg-accent',
        !isLast && 'border-b border-border',
      )}
      onClick={onViewDetails}
    >
      <td className="px-4 py-3">
        <div className="flex items-center gap-3">
          <Avatar name={user.name} />
          <div className="flex flex-col gap-1">
            <div className="flex flex-col">
              <span className="font-medium text-foreground">{user.name}</span>
              <span className="text-xs text-muted-foreground">{user.email}</span>
            </div>
            {/* Role/group pills are user data returned by the API -- not gated by
                READ_ROLES/READ_GROUPS. The backend controls what data is included
                in the users response; the frontend renders what it receives. */}
            <div className="flex flex-wrap gap-1">
              {roles.map((r) => (
                <span
                  key={r.id}
                  className="badge-role inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium"
                >
                  <Lock aria-hidden="true" className="h-3 w-3" />
                  {r.name}
                </span>
              ))}
              {groups.map((g) => (
                <span
                  key={g.id}
                  className="badge-group inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium"
                >
                  <UsersGroupIcon aria-hidden="true" className="h-3 w-3" />
                  {g.name}
                </span>
              ))}
              {hasUserProfile && (
                <span
                  className="badge-profile inline-flex items-center rounded-full p-1"
                  title={localize('com_users_user_profile', { name: user.name })}
                  aria-label={localize('com_users_user_profile', { name: user.name })}
                >
                  <UserIcon aria-hidden="true" className="h-3 w-3" />
                </span>
              )}
            </div>
          </div>
        </div>
      </td>
      <td className="px-4 py-3">
        <span
          className={cn(
            'inline-block rounded-full px-2 py-0.5 text-xs font-medium',
            user.role === SystemRoles.ADMIN
              ? 'badge-admin'
              : 'bg-muted text-muted-foreground',
          )}
        >
          {user.role}
        </span>
      </td>
      <td className="px-4 py-3 text-muted-foreground">
        {new Date(user.createdAt).toLocaleDateString()}
      </td>
      <td className="px-4 py-3">
        <span onClick={(e) => e.stopPropagation()}>
          <KebabMenu items={kebabItems} ariaLabel={`${localize('com_ui_actions')} ${user.name}`} />
        </span>
      </td>
    </tr>
  );
}
