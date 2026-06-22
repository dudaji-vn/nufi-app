import { isValidObjectIdString } from '@librechat/data-schemas';
import type { IGroup } from '@librechat/data-schemas';

export interface ResolveShareTargetDeps {
  getSubgroupById: (id: string) => Promise<IGroup | null>;
}

/**
 * Resolves the ACL principal for a share/unshare operation.
 *
 * - No `targetSubgroupId` → grant/revoke to the whole team (`teamId`).
 * - Malformed `targetSubgroupId` (not a valid ObjectId) → 400, no DB call.
 * - Valid `targetSubgroupId` that belongs to this team → grant/revoke to the sub-group.
 * - Non-existent or cross-team `targetSubgroupId` → 404.
 */
export async function resolveShareTarget(
  deps: ResolveShareTargetDeps,
  teamId: string,
  targetSubgroupId?: string,
): Promise<{ ok: true; principalId: string } | { ok: false; status: 400 | 404 }> {
  if (!targetSubgroupId) {
    return { ok: true, principalId: teamId };
  }

  if (!isValidObjectIdString(targetSubgroupId)) {
    return { ok: false, status: 400 };
  }

  const sg = await deps.getSubgroupById(targetSubgroupId);
  if (!sg || sg.parentTeamId?.toString() !== teamId) {
    return { ok: false, status: 404 };
  }

  return { ok: true, principalId: targetSubgroupId };
}
