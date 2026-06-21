import { logger, isValidObjectIdString } from '@librechat/data-schemas';
import { ResourceType, AccessRoleIds, PrincipalType } from 'librechat-data-provider';
import { Types } from 'mongoose';
import type { IGroup, IMongoFile, IAclEntry, TeamRole } from '@librechat/data-schemas';
import type { Response } from 'express';
import type { ServerRequest } from '~/types/http';
import { resolveTeamAccess } from './access';

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
  const { findFileById, getFiles, findEntriesByPrincipal, revokePermission, grantPermission } =
    deps;

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

      const { fileId } = req.body as { fileId?: string };
      if (!fileId || typeof fileId !== 'string' || !fileId.trim()) {
        return res.status(400).json({ error: 'fileId is required' });
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

      await grantPermission({
        principalType: PrincipalType.GROUP,
        principalId: id,
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

      const groupObjectId = new Types.ObjectId(id);
      const entries = await findEntriesByPrincipal(
        PrincipalType.GROUP,
        groupObjectId,
        ResourceType.FILE,
      );

      if (!entries.length) {
        return res.status(200).json({ files: [] });
      }

      const resourceIds = entries.map((e) => e.resourceId);
      const files = await getFiles({ _id: { $in: resourceIds } });

      const safeFiles: SafeFileInfo[] = (files ?? []).map(toSafeFile);

      return res.status(200).json({ files: safeFiles });
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

      const file = await findFileById(fileId);
      if (!file) {
        return res.status(404).json({ error: 'File not found' });
      }

      await revokePermission(
        PrincipalType.GROUP,
        id,
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
