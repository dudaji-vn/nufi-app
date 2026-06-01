import { createFileRoute, Outlet, useRouter, Link, redirect } from '@tanstack/react-router';
import { AlertTriangle } from 'lucide-react';
import type { ErrorComponentProps } from '@tanstack/react-router';
import { useCapabilities, useCommandMenu, useLocalize, useSidebar } from '@/hooks';
import { CommandMenu } from '@/components/CommandMenu';
import { AccessDenied } from '@/components/shared';
import { SystemCapabilities } from '@/constants';
import { Button } from '@/components/ui';
import { Sidebar } from '@/components/Sidebar';
import { verifyAdminTokenFn } from '@/server';
import { Header } from '@/components/Header';

const ROUTE_TITLE_KEYS: Record<string, string> = {
  '/': 'com_dash_title',
  '/configuration': 'com_config_title',
  '/users': 'com_users_title',
  '/access': 'com_access_title',
  '/grants': 'com_grants_title',
  '/audit-log': 'com_audit_title',
  '/help': 'com_help_title',
};

export const Route = createFileRoute('/_app')({
  beforeLoad: async ({ location }) => {
    const result = await verifyAdminTokenFn();

    if (!result.valid) {
      throw redirect({
        to: '/login',
        search: { redirect: location.pathname },
      });
    }

    return { user: result.user };
  },
  component: AppLayout,
  errorComponent: AppError,
  notFoundComponent: AppNotFound,
});

function AppLayout() {
  const { user } = Route.useRouteContext();
  const { hasCapability, isLoading, isError } = useCapabilities();
  const router = useRouter();
  const localize = useLocalize();
  const { open, setOpen } = useCommandMenu();
  const { collapsed, toggle } = useSidebar();
  const pathname = router.state.location.pathname;

  if (!isLoading && !isError && !hasCapability(SystemCapabilities.ACCESS_ADMIN)) {
    return <AccessDenied />;
  }

  const matchedKey = Object.keys(ROUTE_TITLE_KEYS).find((route) =>
    route === '/' ? pathname === '/' : pathname.startsWith(route),
  );
  const title = matchedKey ? localize(ROUTE_TITLE_KEYS[matchedKey]) : undefined;

  return (
    <div className="flex h-screen overflow-hidden bg-background text-foreground">
      <Sidebar user={user} collapsed={collapsed} onToggle={toggle} />
      <div className="flex min-w-0 flex-1 flex-col">
        <Header title={title} onSearchClick={() => setOpen(true)} />
        <main className="flex min-h-0 flex-1 flex-col overflow-auto">
          <Outlet />
        </main>
      </div>
      <CommandMenu open={open} onOpenChange={setOpen} />
    </div>
  );
}

function AppError({ error }: ErrorComponentProps) {
  if (import.meta.env.DEV) console.error(error);
  const localize = useLocalize();
  return (
    <div
      role="alert"
      className="flex min-h-screen items-center justify-center bg-background p-6 text-foreground"
    >
      <div className="flex max-w-sm flex-col items-center gap-4 text-center">
        <div className="flex h-14 w-14 items-center justify-center rounded-full bg-destructive/10 text-destructive">
          <AlertTriangle className="h-6 w-6" />
        </div>
        <h2 className="text-lg font-semibold text-foreground">
          {localize('com_error_page_title')}
        </h2>
        <p className="text-sm text-muted-foreground">{localize('com_error_page_desc')}</p>
        <Button asChild variant="outline" size="sm">
          <Link to="/">{localize('com_nav_go_home')}</Link>
        </Button>
      </div>
    </div>
  );
}

function AppNotFound() {
  const localize = useLocalize();
  return (
    <div
      role="alert"
      className="flex min-h-screen items-center justify-center bg-background p-6 text-foreground"
    >
      <div className="flex max-w-sm flex-col items-center gap-4 text-center">
        <span className="text-5xl font-bold text-muted-foreground">404</span>
        <h2 className="text-lg font-semibold text-foreground">
          {localize('com_error_not_found_title')}
        </h2>
        <p className="text-sm text-muted-foreground">{localize('com_error_not_found_desc')}</p>
        <Button asChild variant="outline" size="sm">
          <Link to="/">{localize('com_nav_go_home')}</Link>
        </Button>
      </div>
    </div>
  );
}
