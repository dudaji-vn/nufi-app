import { useState } from 'react';
import { Link, useRouter } from '@tanstack/react-router';
import {
  ChevronLeft,
  ChevronRight,
  Home,
  LifeBuoy,
  LogOut,
  Settings,
  ShieldCheck,
  Users as UsersIcon,
} from 'lucide-react';
import type * as t from '@/types';
import {
  Avatar,
  AvatarFallback,
  Button,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui';
import { useCapabilities, useLocalize } from '@/hooks';
import nufiLogo from '@/assets/nufi-logo.svg';
import { SettingsDialog } from './SettingsDialog';
import { SystemCapabilities } from '@/constants';
import { getInitials, cn } from '@/utils';
import { adminLogoutFn } from '@/server';

const navItems: t.NavItem[] = [
  { labelKey: 'com_nav_dashboard', path: '/', icon: Home },
  {
    labelKey: 'com_nav_configuration',
    path: '/configuration',
    icon: Settings,
    capability: SystemCapabilities.READ_CONFIGS,
  },
  {
    labelKey: 'com_nav_access',
    path: '/access',
    icon: UsersIcon,
    capability: [SystemCapabilities.READ_ROLES, SystemCapabilities.READ_GROUPS],
  },
  { labelKey: 'com_nav_grants', path: '/grants', icon: ShieldCheck },
  { labelKey: 'com_nav_help', path: '/help', icon: LifeBuoy },
];

function getUserInitials(user?: { name?: string; email?: string } | null): string {
  if (user?.name) return getInitials(user.name);
  if (user?.email) return user.email[0].toUpperCase();
  return '';
}

export function Sidebar({ user, collapsed, onToggle }: t.SidebarProps) {
  const localize = useLocalize();
  const router = useRouter();
  const { hasCapability } = useCapabilities();
  const currentPath = router.state.location.pathname;
  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);

  const visibleItems = navItems.filter((item) => {
    if (!item.capability) return true;
    if (Array.isArray(item.capability)) return item.capability.some((c) => hasCapability(c));
    return hasCapability(item.capability);
  });

  const isActive = (path: string) =>
    path === '/' ? currentPath === '/' : currentPath.startsWith(path);

  const handleLogout = async () => {
    setIsLoggingOut(true);
    try {
      await adminLogoutFn();
      await router.invalidate();
      router.navigate({ to: '/login', search: { redirect: '/' } });
    } catch (error) {
      console.error('Logout error:', error);
    } finally {
      setIsLoggingOut(false);
    }
  };

  const initials = getUserInitials(user);

  return (
    <TooltipProvider delayDuration={150}>
      <aside
        aria-label={localize('com_a11y_admin_panel')}
        className={cn(
          'sticky top-0 z-(--z-floating) flex h-screen shrink-0 flex-col overflow-hidden border-r border-sidebar-border bg-sidebar text-sidebar-foreground transition-[width] duration-200',
          collapsed ? 'w-14' : 'w-64',
        )}
      >
        <div
          className={cn(
            'flex h-16 shrink-0 items-center border-b border-sidebar-border',
            collapsed ? 'justify-center px-2' : 'px-3',
          )}
        >
          <div className="flex min-w-0 items-center gap-2.5">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-white shadow-sm">
              <img src={nufiLogo} alt={localize('com_a11y_logo_alt')} className="h-7 w-7" />
            </div>
            {!collapsed && (
              <span className="truncate text-sm font-semibold tracking-tight text-foreground">
                {localize('com_auth_title')}
              </span>
            )}
          </div>
        </div>

        <nav
          className={cn('flex-1 overflow-y-auto py-3', collapsed ? 'px-2' : 'px-3')}
          role="navigation"
        >
          <div className="flex flex-col gap-1">
            {visibleItems.map((item) => {
              const Icon = item.icon;
              const active = isActive(item.path);
              const label = localize(item.labelKey);
              const link = (
                <Link
                  key={item.path}
                  to={item.path}
                  aria-current={active ? 'page' : undefined}
                  aria-label={collapsed ? label : undefined}
                  className={cn(
                    'group relative flex h-10 items-center text-sm no-underline transition-colors duration-150',
                    collapsed ? 'w-10 justify-center rounded-md' : 'gap-3 rounded-r-md pr-3 pl-4',
                    active &&
                      'bg-sidebar-accent font-medium text-primary before:absolute before:inset-y-0 before:left-0 before:w-0.75 before:bg-primary',
                    !active &&
                      'font-normal text-sidebar-foreground hover:bg-sidebar-accent/50 hover:text-sidebar-accent-foreground',
                    !active && !collapsed && 'rounded-l-md',
                    active && collapsed && 'before:hidden',
                  )}
                >
                  <Icon
                    aria-hidden="true"
                    className={cn(
                      'h-4.5 w-4.5 shrink-0 transition-colors',
                      active ? 'text-primary' : 'text-sidebar-foreground group-hover:text-sidebar-accent-foreground',
                    )}
                  />
                  {!collapsed && <span className="truncate text-sm">{label}</span>}
                </Link>
              );
              if (!collapsed) return link;
              return (
                <Tooltip key={item.path}>
                  <TooltipTrigger asChild>{link}</TooltipTrigger>
                  <TooltipContent side="right">{label}</TooltipContent>
                </Tooltip>
              );
            })}
          </div>
        </nav>

        {initials && (
          <div className="flex shrink-0 items-center gap-2.5 border-t border-sidebar-border px-2 py-3">
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button
                  type="button"
                  className="flex h-9 w-9 shrink-0 cursor-pointer items-center justify-center rounded-full bg-sidebar-accent/60 transition-colors hover:bg-sidebar-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sidebar-ring"
                  aria-label={`${localize('com_nav_user_menu')}, ${user?.name || user?.email || ''}`}
                  title={user?.name || user?.email || ''}
                >
                  <Avatar className="h-9 w-9">
                    <AvatarFallback className="bg-transparent text-xs font-medium text-sidebar-foreground">
                      {initials}
                    </AvatarFallback>
                  </Avatar>
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start" side="top" className="min-w-56">
                {user && (
                  <div className="px-2 py-2">
                    <div className="text-sm font-medium leading-tight text-foreground">
                      {user.name || ''}
                    </div>
                    {user.email && (
                      <div className="mt-0.5 text-xs leading-tight text-muted-foreground">
                        {user.email}
                      </div>
                    )}
                  </div>
                )}
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={() => setSettingsOpen(true)}>
                  <Settings className="h-4 w-4" />
                  {localize('com_ui_settings')}
                </DropdownMenuItem>
                <DropdownMenuItem onClick={handleLogout} disabled={isLoggingOut}>
                  <LogOut className="h-4 w-4" />
                  {isLoggingOut ? localize('com_ui_signing_out') : localize('com_ui_sign_out')}
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
            {!collapsed && user && (
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm leading-tight font-medium text-foreground">
                  {user.name || ''}
                </div>
                {user.email && (
                  <div className="truncate text-xs leading-tight text-muted-foreground">
                    {user.email}
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={onToggle}
          aria-label={localize(collapsed ? 'com_nav_expand_sidebar' : 'com_nav_collapse_sidebar')}
          title={localize(collapsed ? 'com_nav_expand_sidebar' : 'com_nav_collapse_sidebar')}
          className="w-full shrink-0 justify-center rounded-none border-t border-sidebar-border bg-transparent py-6 text-muted-foreground hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground"
        >
          {collapsed ? (
            <ChevronRight className="h-4 w-4" />
          ) : (
            <ChevronLeft className="h-4 w-4" />
          )}
        </Button>
      </aside>

      <SettingsDialog open={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </TooltipProvider>
  );
}
