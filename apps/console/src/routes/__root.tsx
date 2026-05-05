import type { QueryClient } from '@tanstack/react-query';
import { createRootRouteWithContext, Link, Outlet } from '@tanstack/react-router';
import { ThemeToggle } from '@/components/theme-toggle';
import { Toaster } from '@/components/ui/sonner';

export const Route = createRootRouteWithContext<{ queryClient: QueryClient }>()({
  component: RootLayout,
});

function RootLayout() {
  return (
    <div className="min-h-dvh bg-background text-foreground">
      <header className="border-b">
        <div className="mx-auto flex h-14 max-w-5xl items-center gap-4 px-4 sm:gap-6 sm:px-6">
          <span className="font-semibold tracking-tight">NPUOps Console</span>
          <nav className="flex flex-1 items-center gap-3 text-sm sm:gap-4">
            <NavLink to="/">Profile</NavLink>
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
