import type { Types, ClientSession } from 'mongoose';
import type { IGroup, TeamRole } from '@librechat/data-schemas';

export type { TeamRole };

export const RANK: Record<TeamRole, number> = { owner: 3, admin: 2, member: 1 };

export function hasMinRole(role: TeamRole | null, min: TeamRole): boolean {
  if (!role) {
    return false;
  }
  return RANK[role] >= RANK[min];
}

export interface TeamAccessDeps {
  getTeamRole: (params: {
    groupId: string | Types.ObjectId;
    userId: string | Types.ObjectId;
  }) => Promise<TeamRole | null>;
  findGroupById: (
    groupId: string | Types.ObjectId,
    projection?: Record<string, 0 | 1>,
    session?: ClientSession,
  ) => Promise<IGroup | null>;
}

/** Resolves team access for a caller, returning the team and effective role or a typed error result. */
export async function resolveTeamAccess(
  deps: TeamAccessDeps,
  groupId: string,
  callerId: string,
  minRole: TeamRole,
): Promise<{ ok: true; team: IGroup; role: TeamRole } | { ok: false; status: 404 | 403 }> {
  const [team, role] = await Promise.all([
    deps.findGroupById(groupId),
    deps.getTeamRole({ groupId, userId: callerId }),
  ]);

  if (!team || team.kind !== 'team' || !role) {
    return { ok: false, status: 404 };
  }

  if (!hasMinRole(role, minRole)) {
    return { ok: false, status: 403 };
  }

  return { ok: true, team, role };
}
