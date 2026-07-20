import { useContext, useMemo } from 'react';
import { PermissionTypes, Permissions } from 'librechat-data-provider';
import { useHasAccess, AuthContext } from '~/hooks';
import useUIMode from '~/hooks/useUIMode';

/**
 * Hook to determine if the Agent Marketplace should be shown.
 * Consolidates the logic for checking:
 * - Auth readiness (avoid race conditions)
 * - Access to Agents permission
 * - Access to Marketplace permission
 * - UI mode (Marketplace is an Advanced-only surface)
 *
 * @returns Whether the Agent Marketplace should be displayed
 */
export default function useShowMarketplace(): boolean {
  const { isAdvanced } = useUIMode();
  const authContext = useContext(AuthContext);

  const hasAccessToAgents = useHasAccess({
    permissionType: PermissionTypes.AGENTS,
    permission: Permissions.USE,
  });

  const hasAccessToMarketplace = useHasAccess({
    permissionType: PermissionTypes.MARKETPLACE,
    permission: Permissions.USE,
  });

  // Check if auth is ready (avoid race conditions)
  const authReady = useMemo(
    () =>
      authContext?.isAuthenticated !== undefined &&
      (authContext?.isAuthenticated === false || authContext?.user !== undefined),
    [authContext?.isAuthenticated, authContext?.user],
  );

  // Show agent marketplace when marketplace permission is enabled, auth is ready, and user has access to agents
  // Marketplace is an Advanced-only surface, so Basic mode always hides it.
  return authReady && hasAccessToAgents && hasAccessToMarketplace && isAdvanced;
}
