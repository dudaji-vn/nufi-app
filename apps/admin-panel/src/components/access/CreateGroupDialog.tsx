import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import type { AdminUserSearchResult } from '@librechat/data-schemas';
import type * as t from '@/types';
import { Input, Label, Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui';
import { FormDialog, SelectedMemberList, UserSearchInline } from '@/components/shared';
import { addGroupMemberFn, createGroupFn } from '@/server';
import { useLocalize } from '@/hooks';
import { cn } from '@/utils';

export function CreateGroupDialog({ open, onClose }: t.CreateGroupDialogProps) {
  const localize = useLocalize();
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<t.CreateGroupTab>('details');
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [selectedUsers, setSelectedUsers] = useState<AdminUserSearchResult[]>([]);
  const [error, setError] = useState('');

  const resetAndClose = () => {
    setName('');
    setDescription('');
    setSelectedUsers([]);
    setError('');
    setActiveTab('details');
    onClose();
  };

  const mutation = useMutation({
    mutationFn: async () => {
      const { group } = await createGroupFn({ data: { name, description } });
      for (const user of selectedUsers) {
        await addGroupMemberFn({ data: { groupId: group.id, userId: user.id } });
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['groups'] });
      queryClient.invalidateQueries({ queryKey: ['groupMembers'] });
      queryClient.invalidateQueries({ queryKey: ['availableScopes'] });
      queryClient.invalidateQueries({ queryKey: ['groupAssignments'] });
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
      title={localize('com_access_create_group')}
      submitLabel={localize('com_access_create_group')}
      submitDisabled={!name.trim()}
      saving={mutation.isPending}
      error={error}
      size="lg"
      onSubmit={doSubmit}
      onClose={resetAndClose}
    >
      <Tabs
        value={activeTab}
        onValueChange={(v) => setActiveTab(v as t.CreateGroupTab)}
        aria-label={localize('com_access_create_group')}
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
              <Label htmlFor="create-group-name">{localize('com_access_col_name')}</Label>
              <Input
                id="create-group-name"
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={localize('com_access_group_name_placeholder')}
                autoFocus
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="create-group-description">
                {localize('com_config_field_description')}
              </Label>
              <Input
                id="create-group-description"
                type="text"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder={localize('com_access_group_desc_placeholder')}
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
            <UserSearchInline
              existingIds={selectedUsers.map((u) => u.id)}
              onAdd={addUser}
              listboxId="create-group-member-results"
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
