import { useMemo } from 'react';
import { Link } from '@tanstack/react-router';
import { LifeBuoy, Settings, ShieldCheck, Users as UsersIcon } from 'lucide-react';
import type * as t from '@/types';
import { Card } from '@/components/ui';
import { useCapabilities, useLocalize } from '@/hooks';
import { SystemCapabilities } from '@/constants';

const QUICK_LINKS: (t.NavItem & { descKey: string })[] = [
  {
    labelKey: 'com_nav_configuration',
    path: '/configuration',
    icon: Settings,
    descKey: 'com_dash_config_desc',
    capability: SystemCapabilities.READ_CONFIGS,
  },
  {
    labelKey: 'com_nav_access',
    path: '/access',
    icon: UsersIcon,
    descKey: 'com_dash_access_desc',
    capability: [SystemCapabilities.READ_ROLES, SystemCapabilities.READ_GROUPS],
  },
  {
    labelKey: 'com_nav_grants',
    path: '/grants',
    icon: ShieldCheck,
    descKey: 'com_dash_grants_desc',
  },
  {
    labelKey: 'com_nav_help',
    path: '/help',
    icon: LifeBuoy,
    descKey: 'com_dash_help_desc',
  },
];

export function DashboardPage() {
  const localize = useLocalize();
  const { hasCapability } = useCapabilities();

  const isMac =
    typeof navigator !== 'undefined' && /Mac|iPod|iPhone|iPad/.test(navigator.userAgent);

  const visibleLinks = useMemo(
    () =>
      QUICK_LINKS.filter((link) => {
        if (!link.capability) return true;
        if (Array.isArray(link.capability)) return link.capability.some((c) => hasCapability(c));
        return hasCapability(link.capability);
      }),
    [hasCapability],
  );

  return (
    <div
      role="region"
      aria-label={localize('com_nav_dashboard')}
      className="flex flex-1 flex-col gap-8 overflow-auto p-6"
    >
      <section aria-label={localize('com_dash_quick_links')}>
        <h3 className="mb-3 text-sm font-medium text-muted-foreground">
          {localize('com_dash_quick_links')}
        </h3>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {visibleLinks.map((link) => {
            const Icon = link.icon;
            return (
              <Link
                key={link.path}
                to={link.path}
                className="group flex items-start gap-3 rounded-lg border border-border bg-card p-4 no-underline shadow-sm transition-colors hover:border-ring/40 hover:bg-accent/40"
              >
                <span
                  aria-hidden="true"
                  className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary transition-colors group-hover:bg-primary/15"
                >
                  <Icon className="h-4.5 w-4.5" />
                </span>
                <div className="flex flex-col gap-0.5">
                  <span className="text-sm font-medium text-foreground">
                    {localize(link.labelKey)}
                  </span>
                  <span className="text-xs text-muted-foreground">{localize(link.descKey)}</span>
                </div>
              </Link>
            );
          })}
        </div>
      </section>

      <Card
        role="region"
        aria-label={localize('com_dash_nav_tips')}
        className="p-5"
      >
        <h3 className="mb-3 text-sm font-medium text-foreground">
          {localize('com_dash_nav_tips')}
        </h3>
        <ul className="flex flex-col gap-3 text-sm text-muted-foreground">
          <li className="flex items-center gap-3">
            <kbd className="shrink-0 rounded border border-border bg-muted px-1.5 py-0.5 font-mono text-xs font-medium text-foreground">
              {isMac ? '⌘B' : 'Ctrl+B'}
            </kbd>
            <span>{localize('com_dash_tip_sidebar')}</span>
          </li>
          <li className="flex items-center gap-3">
            <kbd className="shrink-0 rounded border border-border bg-muted px-1.5 py-0.5 font-mono text-xs font-medium text-foreground">
              {isMac ? '⌘K' : 'Ctrl+K'}
            </kbd>
            <span>{localize('com_dash_tip_cmdk')}</span>
          </li>
        </ul>
      </Card>
    </div>
  );
}
