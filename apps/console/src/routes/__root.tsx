import type { QueryClient } from '@tanstack/react-query';
import { createRootRouteWithContext, Link, Outlet, useRouterState } from '@tanstack/react-router';
import { ThemeToggle } from '@/components/theme-toggle';
import { Toaster } from '@/components/ui/sonner';

export const Route = createRootRouteWithContext<{ queryClient: QueryClient }>()({
  component: RootLayout,
});

function RootLayout() {
  // The chooser is served at agents.nufi.me, a different door from the
  // console. Wrapping it in the console's header and nav would tell a visitor
  // they had landed somewhere they did not ask for.
  const bare = useRouterState({ select: (s) => s.location.pathname === '/choose' });

  if (bare) {
    return (
      <div className="min-h-dvh bg-background text-foreground">
        <Outlet />
        <Toaster richColors position="bottom-right" />
      </div>
    );
  }

  return (
    <div className="min-h-dvh bg-background text-foreground">
      <header className="border-b">
        <div className="mx-auto flex h-14 max-w-5xl items-center gap-4 px-4 sm:gap-6 sm:px-6">
          <Link to="/" className="flex items-center gap-2">
            <img src="/nufi-logo.svg" alt="NUFI" className="h-5 w-auto" />
            <span className="font-semibold tracking-tight">NUFI Console</span>
          </Link>
          <nav className="flex flex-1 items-center gap-3 text-sm sm:gap-4">
            <NavLink to="/">Profile</NavLink>
            <NavLink to="/usage">Usage</NavLink>
            <NavLink to="/keys">API keys</NavLink>
          </nav>
          <ThemeToggle />
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-6 sm:px-6 sm:py-8">
        <Outlet />
      </main>
      <Toaster richColors position="bottom-right" />
    </div>
  );
}

function NavLink({ to, children }: { to: string; children: React.ReactNode }) {
  return (
    <Link
      to={to}
      className="text-muted-foreground transition-colors hover:text-foreground"
      activeProps={{ className: 'text-foreground font-medium' }}
    >
      {children}
    </Link>
  );
}
