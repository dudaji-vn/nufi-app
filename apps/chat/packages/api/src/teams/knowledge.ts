import { logger, isValidObjectIdString } from '@librechat/data-schemas';
import { ResourceType, AccessRoleIds, PrincipalType } from 'librechat-data-provider';
import { Types } from 'mongoose';
import type { IGroup, IMongoFile, IAclEntry, TeamRole } from '@librechat/data-schemas';
import type { Response } from 'express';
import type { ServerRequest } from '~/types/http';
import { resolveTeamAccess, hasMinRole } from './access';
import { resolveShareTarget } from './target';

type FileTarget = { type: 'team' } | { type: 'subgroup'; id: string; name: string };

type AnnotatedFileInfo = Pick<
  IMongoFile,
  'file_id' | 'filename' | 'bytes' | 'type' | 'embedded' | 'createdAt'
> & { target: FileTarget };

interface TeamIdParams {
  id: string;
}

interface KnowledgeFileParams extends TeamIdParams {
  fileId: string;
}

type SafeFileInfo = Pick<
  IMongoFile,
  'file_id' | 'filename' | 'bytes' | 'type' | 'embedded' | 'createdAt'
>;

export interface TeamKnowledgeHandlersDeps {
  getTeamRole: (params: {
    groupId: string | Types.ObjectId;
    userId: string | Types.ObjectId;
  }) => Promise<TeamRole | null>;
  findGroupById: (
    groupId: string | Types.ObjectId,
    projection?: Record<string, 0 | 1>,
  ) => Promise<IGroup | null>;
  findFileById: (file_id: string) => Promise<IMongoFile | null>;
  getFiles: (filter: Record<string, unknown>) => Promise<IMongoFile[] | null>;
  findEntriesByPrincipal: (
    principalType: string,
    principalId: string | Types.ObjectId,
    resourceType?: string,
  ) => Promise<IAclEntry[]>;
  revokePermission: (
    principalType: string,
    principalId: string | Types.ObjectId,
    resourceType: string,
    resourceId: string | Types.ObjectId,
  ) => Promise<unknown>;
  grantPermission: (params: {
    principalType: string;
    principalId: string | Types.ObjectId;
    resourceType: string;
    resourceId: string | Types.ObjectId;
    accessRoleId: string;
    grantedBy: string | Types.ObjectId;
  }) => Promise<unknown>;
  getSubgroupById: (id: string) => Promise<IGroup | null>;
  getTeamSubgroups: (parentTeamId: string | Types.ObjectId) => Promise<IGroup[]>;
  getUserTeamPrincipals: (params: { userId: string; teamId: string }) => Promise<string[]>;
}

function toSafeFile(file: IMongoFile): SafeFileInfo {
  return {
    file_id: file.file_id,
    filename: file.filename,
    bytes: file.bytes,
    type: file.type,
    embedded: file.embedded,
    createdAt: file.createdAt,
  };
}

export function createTeamKnowledgeHandlers(deps: TeamKnowledgeHandlersDeps) {
  const {
    findFileById,
    getFiles,
    findEntriesByPrincipal,
    revokePermission,
    grantPermission,
    getTeamSubgroups,
    getUserTeamPrincipals,
  } = deps;

  async function add(req: ServerRequest, res: Response) {
    try {
      const { id } = req.params as TeamIdParams;
      if (!isValidObjectIdString(id)) {
        return res.status(400).json({ error: 'Invalid team ID format' });
      }

      const callerId = req.user?.id as string;
      const access = await resolveTeamAccess(deps, id, callerId, 'admin');
      if (!access.ok) {
        const error = access.status === 403 ? 'Forbidden' : 'Team not found';
        return res.status(access.status).json({ error });
      }

      const { fileId, targetSubgroupId } = req.body as {
        fileId?: string;
        targetSubgroupId?: string;
      };
      if (!fileId || typeof fileId !== 'string' || !fileId.trim()) {
        return res.status(400).json({ error: 'fileId is required' });
      }

      const target = await resolveShareTarget(deps, id, targetSubgroupId);
      if (!target.ok) {
        return res.status(target.status).json({ error: 'Sub-group not found' });
      }

      const file = await findFileById(fileId.trim());
      if (!file) {
        return res.status(404).json({ error: 'File not found' });
      }

      if (file.user.toString() !== callerId) {
        return res.status(403).json({ error: 'Forbidden: you do not own this file' });
      }

      if (file.expiresAt) {
        return res.status(409).json({ error: 'File must be saved (not temporary) before sharing' });
      }

      const maxKnowledgeFilesPerTeam = req.config?.config?.teams?.maxKnowledgeFilesPerTeam;
      if (maxKnowledgeFilesPerTeam !== undefined) {
        // Per-team TOTAL: count FILE grants across the team principal and all its sub-groups.
        const subgroups = await getTeamSubgroups(id);
        const subgroupIds = subgroups.map((sg) => sg._id.toString());
        const principalIds = [id, ...subgroupIds];
        const counts = await Promise.all(
          principalIds.map((pid) =>
            findEntriesByPrincipal(PrincipalType.GROUP, pid, ResourceType.FILE),
          ),
        );
        const total = counts.reduce((sum, entries) => sum + entries.length, 0);
        if (total >= maxKnowledgeFilesPerTeam) {
          return res.status(403).json({ error: 'Team knowledge limit reached' });
        }
      }

      await grantPermission({
        principalType: PrincipalType.GROUP,
        principalId: target.principalId,
        resourceType: ResourceType.FILE,
        resourceId: file._id as Types.ObjectId,
        accessRoleId: AccessRoleIds.FILE_VIEWER,
        grantedBy: callerId,
      });

      return res.status(201).json({ success: true, fileId: file.file_id });
    } catch (error) {
      logger.error('[knowledge] add error:', error);
      return res.status(500).json({ error: 'Failed to share file with team' });
    }
  }

  async function list(req: ServerRequest, res: Response) {
    try {
      const { id } = req.params as TeamIdParams;
      if (!isValidObjectIdString(id)) {
        return res.status(400).json({ error: 'Invalid team ID format' });
      }

      const callerId = req.user?.id as string;
      const access = await resolveTeamAccess(deps, id, callerId, 'member');
      if (!access.ok) {
        const error = access.status === 403 ? 'Forbidden' : 'Team not found';
        return res.status(access.status).json({ error });
      }

      const isAdmin = hasMinRole(access.role, 'admin');

      const subgroups = await getTeamSubgroups(id);
      const principalIds = isAdmin
        ? [id, ...subgroups.map((sg) => sg._id.toString())]
        : await getUserTeamPrincipals({ userId: callerId, teamId: id });

      const subgroupNameById = new Map(
        subgroups.map((sg) => [sg._id.toString(), sg.name]),
      );

      const entriesPerPrincipal = await Promise.all(
        principalIds.map((pid) =>
          findEntriesByPrincipal(PrincipalType.GROUP, pid, ResourceType.FILE).then((entries) =>
            entries.map((e) => ({ entry: e, principalId: pid })),
          ),
        ),
      );

      const taggedEntries = entriesPerPrincipal.flat();

      if (!taggedEntries.length) {
        return res.status(200).json({ files: [] });
      }

      const resourceIds = taggedEntries.map((t) => t.entry.resourceId);
      const files = await getFiles({ _id: { $in: resourceIds } });

      const fileById = new Map(
        (files ?? []).map((f) => [(f._id as Types.ObjectId).toString(), f]),
      );

      const annotatedFiles: AnnotatedFileInfo[] = [];
      for (const { entry, principalId } of taggedEntries) {
        const file = fileById.get((entry.resourceId as Types.ObjectId).toString());
        if (!file) {
          continue;
        }
        const target: FileTarget =
          principalId === id // team principal is the route :id
            ? { type: 'team' }
            : {
                type: 'subgroup',
                id: principalId,
                name: subgroupNameById.get(principalId) ?? principalId,
              };
        annotatedFiles.push({ ...toSafeFile(file), target });
      }

      return res.status(200).json({ files: annotatedFiles });
    } catch (error) {
      logger.error('[knowledge] list error:', error);
      return res.status(500).json({ error: 'Failed to list team knowledge files' });
    }
  }

  async function remove(req: ServerRequest, res: Response) {
    try {
      const { id, fileId } = req.params as KnowledgeFileParams;
      if (!isValidObjectIdString(id)) {
        return res.status(400).json({ error: 'Invalid team ID format' });
      }

      const callerId = req.user?.id as string;
      const access = await resolveTeamAccess(deps, id, callerId, 'admin');
      if (!access.ok) {
        const error = access.status === 403 ? 'Forbidden' : 'Team not found';
        return res.status(access.status).json({ error });
      }

      const { targetSubgroupId } = (req.query ?? {}) as { targetSubgroupId?: string };
      const target = await resolveShareTarget(deps, id, targetSubgroupId);
      if (!target.ok) {
        return res.status(target.status).json({ error: 'Sub-group not found' });
      }

      const file = await findFileById(fileId);
      if (!file) {
        return res.status(404).json({ error: 'File not found' });
      }

      await revokePermission(
        PrincipalType.GROUP,
        target.principalId,
        ResourceType.FILE,
        file._id as Types.ObjectId,
      );

      return res.status(200).json({ success: true });
    } catch (error) {
      logger.error('[knowledge] remove error:', error);
      return res.status(500).json({ error: 'Failed to remove file from team knowledge' });
    }
  }

  return { add, list, remove };
}
