import { createFileRoute } from '@tanstack/react-router';
import { DashboardPage } from '@/components/dashboard';

export const Route = createFileRoute('/_app/')({
  head: () => ({
    meta: [{ title: 'Dashboard | NuFi Admin Panel' }],
  }),
  component: DashboardRoute,
});

function DashboardRoute() {
  return <DashboardPage />;
}
