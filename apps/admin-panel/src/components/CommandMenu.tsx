import { useRouter } from '@tanstack/react-router';
import { useCallback, useState } from 'react';
import { HelpCircle, Home, Lock, Monitor, Moon, Settings, Sun, Users } from 'lucide-react';
import type * as t from '@/types';
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@/components/ui';
import { CONFIG_TABS } from './configuration/configMeta';
import { useSearchIndex, useLocalize } from '@/hooks';
import { useTheme } from '@/contexts/ThemeContext';

export function CommandMenu({ open, onOpenChange }: t.CommandMenuProps) {
  const localize = useLocalize();
  const router = useRouter();
  const { setTheme } = useTheme();
  const { items: configSections } = useSearchIndex(localize, open);

  const [search, setSearch] = useState('');

  const close = useCallback(() => onOpenChange(false), [onOpenChange]);

  const navigateTo = useCallback(
    (path: string, search?: Record<string, string>) => {
      close();
      router.navigate({ to: path, search });
    },
    [close, router],
  );

  const selectTheme = useCallback(
    (value: 'system' | 'light' | 'dark') => {
      setTheme(value);
      close();
    },
    [setTheme, close],
  );

  return (
    <CommandDialog open={open} onOpenChange={onOpenChange}>
      <CommandInput
        value={search}
        onValueChange={setSearch}
        placeholder={localize('com_cmdk_placeholder')}
      />
      <CommandList>
        <CommandEmpty>{localize('com_cmdk_no_results')}</CommandEmpty>

        <CommandGroup heading={localize('com_cmdk_group_navigation')}>
          <CommandItem onSelect={() => navigateTo('/')}>
            <Home className="h-4 w-4 text-muted-foreground" />
            <span>{localize('com_nav_dashboard')}</span>
          </CommandItem>
          <CommandItem onSelect={() => navigateTo('/configuration')}>
            <Settings className="h-4 w-4 text-muted-foreground" />
            <span>{localize('com_nav_configuration')}</span>
          </CommandItem>
          <CommandItem onSelect={() => navigateTo('/access')}>
            <Users className="h-4 w-4 text-muted-foreground" />
            <span>{localize('com_nav_access')}</span>
          </CommandItem>
          <CommandItem onSelect={() => navigateTo('/grants')}>
            <Lock className="h-4 w-4 text-muted-foreground" />
            <span>{localize('com_nav_grants')}</span>
          </CommandItem>
          <CommandItem onSelect={() => navigateTo('/help')}>
            <HelpCircle className="h-4 w-4 text-muted-foreground" />
            <span>{localize('com_nav_help')}</span>
          </CommandItem>
        </CommandGroup>

        <CommandGroup heading={localize('com_cmdk_group_tabs')}>
          {CONFIG_TABS.map((tab) => (
            <CommandItem
              key={`config-tab-${tab.id}`}
              keywords={['configuration', 'config', tab.id]}
              onSelect={() => navigateTo('/configuration', { tab: tab.id })}
            >
              <Settings className="h-4 w-4 text-muted-foreground" />
              <span>{localize(tab.labelKey)}</span>
            </CommandItem>
          ))}
          <CommandItem
            keywords={['access', 'groups', 'permissions']}
            onSelect={() => navigateTo('/access', { tab: 'groups' })}
          >
            <Users className="h-4 w-4 text-muted-foreground" />
            <span>{localize('com_access_tab_groups')}</span>
          </CommandItem>
          <CommandItem
            keywords={['access', 'roles', 'permissions']}
            onSelect={() => navigateTo('/access', { tab: 'roles' })}
          >
            <Users className="h-4 w-4 text-muted-foreground" />
            <span>{localize('com_access_tab_roles')}</span>
          </CommandItem>
        </CommandGroup>

        {configSections.length > 0 && (
          <CommandGroup heading={localize('com_cmdk_group_sections')}>
            {configSections.map((item) => (
              <CommandItem
                key={item.id}
                value={item.label}
                keywords={item.keywords}
                onSelect={() => item.tab && navigateTo('/configuration', { tab: item.tab })}
              >
                <Settings className="h-4 w-4 text-muted-foreground" />
                <span>{item.label}</span>
              </CommandItem>
            ))}
          </CommandGroup>
        )}

        <CommandGroup heading={localize('com_cmdk_group_actions')}>
          <CommandItem
            keywords={['theme', 'light', 'mode', 'appearance']}
            onSelect={() => selectTheme('light')}
          >
            <Sun className="h-4 w-4 text-muted-foreground" />
            <span>
              {localize('com_cmdk_set_theme', { theme: localize('com_nav_theme_light') })}
            </span>
          </CommandItem>
          <CommandItem
            keywords={['theme', 'dark', 'mode', 'appearance']}
            onSelect={() => selectTheme('dark')}
          >
            <Moon className="h-4 w-4 text-muted-foreground" />
            <span>
              {localize('com_cmdk_set_theme', { theme: localize('com_nav_theme_dark') })}
            </span>
          </CommandItem>
          <CommandItem
            keywords={['theme', 'system', 'auto', 'mode', 'appearance']}
            onSelect={() => selectTheme('system')}
          >
            <Monitor className="h-4 w-4 text-muted-foreground" />
            <span>
              {localize('com_cmdk_set_theme', { theme: localize('com_nav_theme_system') })}
            </span>
          </CommandItem>
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  );
}
