import { createFileRoute } from '@tanstack/react-router';
import { AccessDenied, PermissionsUnavailable } from '@/components/shared';
import { AuditLogPage } from '@/components/auditLog';
import { SystemCapabilities } from '@/constants';
import { useCapabilities } from '@/hooks';

export const Route = createFileRoute('/_app/audit-log')({
  head: () => ({
    meta: [{ title: 'Audit Log | NUFI Admin Panel' }],
  }),
  component: AuditLogRoute,
});

function AuditLogRoute() {
  const { hasCapability, isLoading, isError } = useCapabilities();

  if (isLoading) return null;
  if (isError) return <PermissionsUnavailable />;
  if (!hasCapability(SystemCapabilities.ACCESS_ADMIN)) {
    return <AccessDenied />;
  }

  return <AuditLogPage />;
}
