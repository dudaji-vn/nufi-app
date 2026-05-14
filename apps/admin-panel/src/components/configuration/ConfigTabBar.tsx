import type * as t from '@/types';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui';
import { useLocalize } from '@/hooks';
import { cn } from '@/utils';

export function ConfigTabBar({
  tabs,
  activeTab,
  onTabChange,
  tabCounts,
  children,
}: t.ConfigTabBarProps) {
  const localize = useLocalize();

  return (
    <Tabs value={activeTab} onValueChange={onTabChange} aria-label={localize('com_nav_configuration')}>
      <TabsList>
        {tabs.map((tab) => {
          const count = tabCounts?.[tab.id];
          return (
            <TabsTrigger key={tab.id} value={tab.id}>
              <span className="flex items-center gap-1.5">
                {localize(tab.labelKey)}
                {count !== undefined && (
                  <span
                    className={cn(
                      'config-tab-count',
                      count > 0 ? 'config-tab-count-active' : 'config-tab-count-zero',
                    )}
                  >
                    {count}
                  </span>
                )}
              </span>
            </TabsTrigger>
          );
        })}
      </TabsList>
      {children}
    </Tabs>
  );
}
