// import { Tabs } from '@clickhouse/click-ui';
import type * as t from '@/types';
import { GrantManagementTab } from './GrantManagementTab';
// import { AuditLogTab } from './AuditLogTab';
import { useLocalize } from '@/hooks';

export function GrantsPage({
  activeTab: _activeTab,
  onTabChange: _onTabChange,
}: t.GrantsPageProps) {
  const localize = useLocalize();

  return (
    <div
      role="region"
      aria-label={localize('com_grants_title')}
      className="flex min-h-0 flex-1 flex-col gap-6 overflow-hidden px-6 pt-6"
    >
      {/* TODO: restore audit-log tab when backend is ready */}
      {/* <Tabs value={activeTab} onValueChange={onTabChange} ariaLabel={localize('com_grants_title')}>
        <Tabs.TriggersList>
          <Tabs.Trigger value="management">{localize('com_grants_tab_management')}</Tabs.Trigger>
          <Tabs.Trigger value="audit-log">{localize('com_grants_tab_audit_log')}</Tabs.Trigger>
        </Tabs.TriggersList>

        <Tabs.Content value="management" tabIndex={-1} />
        <Tabs.Content value="audit-log" tabIndex={-1} />
      </Tabs> */}

      <GrantManagementTab />
    </div>
  );
}
