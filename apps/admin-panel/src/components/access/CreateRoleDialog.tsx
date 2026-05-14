import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import type { AdminUserSearchResult } from '@librechat/data-schemas';
import type * as t from '@/types';
import { Input, Label, Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui';
import { FormDialog, SelectedMemberList, UserSearchInline } from '@/components/shared';
import { addRoleMemberFn, createRoleFn, updateRolePermissionsFn } from '@/server';
import { RolePermissionsPanel } from './RolePermissionsPanel';
import { defaultPermissions } from '@/constants';
import { useLocalize } from '@/hooks';
import { cn } from '@/utils';

export function CreateRoleDialog({ open, onClose }: t.CreateRoleDialogProps) {
  const localize = useLocalize();
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<t.CreateRoleTab>('details');
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [permissions, setPermissions] = useState<t.RolePermissions>(defaultPermissions);
  const [selectedUsers, setSelectedUsers] = useState<AdminUserSearchResult[]>([]);
  const [error, setError] = useState('');

  const resetAndClose = () => {
    setName('');
    setDescription('');
    setPermissions(defaultPermissions());
    setSelectedUsers([]);
    setError('');
    setActiveTab('details');
    onClose();
  };

  const mutation = useMutation({
    mutationFn: async () => {
      const { role } = await createRoleFn({ data: { name, description } });
      await updateRolePermissionsFn({ data: { id: role.id, permissions } });
      for (const user of selectedUsers) {
        await addRoleMemberFn({ data: { roleId: role.id, userId: user.id } });
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['roles'] });
      queryClient.invalidateQueries({ queryKey: ['roleMembers'] });
      queryClient.invalidateQueries({ queryKey: ['availableScopes'] });
      queryClient.invalidateQueries({ queryKey: ['roleAssignments'] });
      resetAndClose();
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

  const addUser = (user: AdminUserSearchResult) => {
    setSelectedUsers((prev) => {
      if (prev.some((u) => u.id === user.id)) return prev;
      return [...prev, user];
    });
  };

  const removeUser = (userId: string) => {
    setSelectedUsers((prev) => prev.filter((u) => u.id !== userId));
  };

  return (
    <FormDialog
      open={open}
      title={localize('com_access_create_role')}
      submitLabel={localize('com_access_create_role')}
      submitDisabled={!name.trim()}
      saving={mutation.isPending}
      error={error}
      size="lg"
      onSubmit={doSubmit}
      onClose={resetAndClose}
    >
      <Tabs
        value={activeTab}
        onValueChange={(v) => setActiveTab(v as t.CreateRoleTab)}
        aria-label={localize('com_access_create_role')}
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
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="create-role-name">{localize('com_access_col_name')}</Label>
              <Input
                id="create-role-name"
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={localize('com_access_role_name_placeholder')}
                autoFocus
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="create-role-description">
                {localize('com_config_field_description')}
              </Label>
              <Input
                id="create-role-description"
                type="text"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder={localize('com_access_role_desc_placeholder')}
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
            <RolePermissionsPanel
              permissions={permissions}
              onChange={setPermissions}
              disabled={mutation.isPending}
            />
          </div>
        </TabsContent>
        <TabsContent
          value="members"
          forceMount
          tabIndex={-1}
          className={cn(activeTab !== 'members' && 'hidden')}
        >
          <div className="flex flex-col gap-4 pt-3">
            <UserSearchInline
              existingIds={selectedUsers.map((u) => u.id)}
              onAdd={addUser}
              listboxId="create-role-member-results"
              disabled={mutation.isPending}
            />
            <SelectedMemberList
              users={selectedUsers}
              onRemove={removeUser}
              disabled={mutation.isPending}
            />
          </div>
        </TabsContent>
      </Tabs>
    </FormDialog>
  );
}
