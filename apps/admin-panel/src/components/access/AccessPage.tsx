import { useState } from 'react';
import type * as t from '@/types';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui';
import { CreateGroupDialog } from './CreateGroupDialog';
import { CreateRoleDialog } from './CreateRoleDialog';
import { GroupsTab } from './GroupsTab';
import { useLocalize } from '@/hooks';
import { RolesTab } from './RolesTab';

export function AccessPage({
  activeTab,
  onTabChange,
  canReadRoles,
  canReadGroups,
}: t.AccessPageProps) {
  const localize = useLocalize();
  const [createGroupOpen, setCreateGroupOpen] = useState(false);
  const [createRoleOpen, setCreateRoleOpen] = useState(false);

  return (
    <div
      role="region"
      aria-label={localize('com_nav_access')}
      className="flex min-h-0 flex-1 flex-col gap-6 overflow-hidden px-6 pt-6"
    >
      {canReadRoles && canReadGroups && (
        <Tabs value={activeTab} onValueChange={onTabChange} aria-label={localize('com_nav_access')}>
          <TabsList>
            <TabsTrigger value="roles">{localize('com_access_tab_roles')}</TabsTrigger>
            <TabsTrigger value="groups">{localize('com_access_tab_groups')}</TabsTrigger>
          </TabsList>
        </Tabs>
      )}

      <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
        {activeTab === 'groups' && canReadGroups && (
          <GroupsTab onCreateGroup={() => setCreateGroupOpen(true)} />
        )}

        {activeTab === 'roles' && canReadRoles && (
          <RolesTab onCreateRole={() => setCreateRoleOpen(true)} />
        )}
      </div>

      <CreateGroupDialog open={createGroupOpen} onClose={() => setCreateGroupOpen(false)} />
      <CreateRoleDialog open={createRoleOpen} onClose={() => setCreateRoleOpen(false)} />
    </div>
  );
}
