import type { IGroup } from '@librechat/data-schemas';

export interface ResolveShareTargetDeps {
  getSubgroupById: (id: string) => Promise<IGroup | null>;
}

/**
 * Resolves the ACL principal for a share/unshare operation.
 *
 * - No `targetSubgroupId` → grant/revoke to the whole team (`teamId`).
 * - Valid `targetSubgroupId` that belongs to this team → grant/revoke to the sub-group.
 * - Invalid / missing / cross-team `targetSubgroupId` → 404.
 */
export async function resolveShareTarget(
  deps: ResolveShareTargetDeps,
  teamId: string,
  targetSubgroupId?: string,
): Promise<{ ok: true; principalId: string } | { ok: false; status: 400 | 404 }> {
  if (!targetSubgroupId) {
    return { ok: true, principalId: teamId };
  }

  const sg = await deps.getSubgroupById(targetSubgroupId);
  if (!sg || sg.parentTeamId?.toString() !== teamId) {
    return { ok: false, status: 404 };
  }

  return { ok: true, principalId: targetSubgroupId };
}
