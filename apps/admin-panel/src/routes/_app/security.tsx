import { createFileRoute } from '@tanstack/react-router';
import { AccessDenied, PermissionsUnavailable } from '@/components/shared';
import { SecurityPage } from '@/components/security';
import { SystemCapabilities } from '@/constants';
import { useCapabilities } from '@/hooks';

export const Route = createFileRoute('/_app/security')({
  head: () => ({
    meta: [{ title: 'Security events | NUFI Admin Panel' }],
  }),
  component: SecurityRoute,
});

function SecurityRoute() {
  const { hasCapability, isLoading, isError } = useCapabilities();

  if (isLoading) return null;
  if (isError) return <PermissionsUnavailable />;
  if (!hasCapability(SystemCapabilities.ACCESS_ADMIN)) {
    return <AccessDenied />;
  }

  return <SecurityPage />;
}
