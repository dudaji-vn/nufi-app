import { createTeamKnowledgeHandlers } from './knowledge';
import type { TeamKnowledgeHandlersDeps } from './knowledge';
import type { IGroup, IMongoFile, IAclEntry, TeamRole } from '@librechat/data-schemas';
import { Types } from 'mongoose';
import { PrincipalType } from 'librechat-data-provider';

function makeId() {
  return new Types.ObjectId().toString();
}

function makeTeam(id: string): IGroup {
  return {
    _id: new Types.ObjectId(id),
    name: 'Test Team',
    kind: 'team',
    members: [],
    memberIds: [],
  } as unknown as IGroup;
}

function makeFile(userId: string, overrides: Partial<IMongoFile> = {}): IMongoFile {
  return {
    _id: new Types.ObjectId(),
    file_id: 'file-string-id-001',
    filename: 'test.pdf',
    bytes: 1024,
    type: 'application/pdf',
    embedded: true,
    user: new Types.ObjectId(userId),
    createdAt: new Date(),
    object: 'file',
    filepath: '/uploads/test.pdf',
    source: 'local',
    usage: 0,
    ...overrides,
  } as unknown as IMongoFile;
}

function makeAclEntry(resourceId: Types.ObjectId): IAclEntry {
  return {
    _id: new Types.ObjectId(),
    principalType: PrincipalType.GROUP,
    principalId: new Types.ObjectId(),
    resourceType: 'file',
    resourceId,
    permBits: 1,
    grantedBy: new Types.ObjectId(),
    grantedAt: new Date(),
  } as unknown as IAclEntry;
}

function makeDeps(overrides: Partial<TeamKnowledgeHandlersDeps> = {}): TeamKnowledgeHandlersDeps {
  return {
    getTeamRole: jest.fn().mockResolvedValue('owner' as TeamRole),
    findGroupById: jest.fn().mockResolvedValue(null),
    findFileById: jest.fn().mockResolvedValue(null),
    getFiles: jest.fn().mockResolvedValue([]),
    findEntriesByPrincipal: jest.fn().mockResolvedValue([]),
    revokePermission: jest.fn().mockResolvedValue({}),
    grantPermission: jest.fn().mockResolvedValue({}),
    ...overrides,
  };
}

function makeReq(params: Record<string, string>, body = {}, userId?: string) {
  return {
    params,
    body,
    user: { id: userId ?? makeId() },
  };
}

function makeRes() {
  const res = {
    status: jest.fn().mockReturnThis(),
    json: jest.fn().mockReturnThis(),
  };
  return res as unknown as import('express').Response;
}

describe('createTeamKnowledgeHandlers', () => {
  const teamId = makeId();

  describe('add (POST /:id/knowledge)', () => {
    it('grants file permission and returns 201 on success', async () => {
      const callerId = makeId();
      const team = makeTeam(teamId);
      const file = makeFile(callerId);
      const deps = makeDeps({
        findGroupById: jest.fn().mockResolvedValue(team),
        findFileById: jest.fn().mockResolvedValue(file),
      });
      const { add } = createTeamKnowledgeHandlers(deps);
      const req = makeReq({ id: teamId }, { fileId: file.file_id }, callerId);
      const res = makeRes();

      await add(req as unknown as import('~/types/http').ServerRequest, res);

      expect(res.status).toHaveBeenCalledWith(201);
      expect(deps.grantPermission).toHaveBeenCalled();
      const call = (deps.grantPermission as jest.Mock).mock.calls[0][0];
      expect(call.principalType).toBe('group');
      expect(call.accessRoleId).toBe('file_viewer');
    });

    it('returns 404 when team not found', async () => {
      const callerId = makeId();
      const deps = makeDeps({
        findGroupById: jest.fn().mockResolvedValue(null),
      });
      const { add } = createTeamKnowledgeHandlers(deps);
      const req = makeReq({ id: teamId }, { fileId: 'some-file' }, callerId);
      const res = makeRes();

      await add(req as unknown as import('~/types/http').ServerRequest, res);

      expect(res.status).toHaveBeenCalledWith(404);
    });

    it('returns 403 when caller is only a member (not admin)', async () => {
      const callerId = makeId();
      const team = makeTeam(teamId);
      const deps = makeDeps({
        findGroupById: jest.fn().mockResolvedValue(team),
        getTeamRole: jest.fn().mockResolvedValue('member' as TeamRole),
      });
      const { add } = createTeamKnowledgeHandlers(deps);
      const req = makeReq({ id: teamId }, { fileId: 'some-file' }, callerId);
      const res = makeRes();

      await add(req as unknown as import('~/types/http').ServerRequest, res);

      expect(res.status).toHaveBeenCalledWith(403);
    });

    it('returns 404 when file not found', async () => {
      const callerId = makeId();
      const team = makeTeam(teamId);
      const deps = makeDeps({
        findGroupById: jest.fn().mockResolvedValue(team),
        findFileById: jest.fn().mockResolvedValue(null),
      });
      const { add } = createTeamKnowledgeHandlers(deps);
      const req = makeReq({ id: teamId }, { fileId: 'no-such-file' }, callerId);
      const res = makeRes();

      await add(req as unknown as import('~/types/http').ServerRequest, res);

      expect(res.status).toHaveBeenCalledWith(404);
    });

    it('returns 403 when caller does not own the file', async () => {
      const callerId = makeId();
      const ownerId = makeId();
      const team = makeTeam(teamId);
      const file = makeFile(ownerId);
      const deps = makeDeps({
        findGroupById: jest.fn().mockResolvedValue(team),
        findFileById: jest.fn().mockResolvedValue(file),
      });
      const { add } = createTeamKnowledgeHandlers(deps);
      const req = makeReq({ id: teamId }, { fileId: file.file_id }, callerId);
      const res = makeRes();

      await add(req as unknown as import('~/types/http').ServerRequest, res);

      expect(res.status).toHaveBeenCalledWith(403);
      expect((res.json as jest.Mock).mock.calls[0][0]).toMatchObject({
        error: expect.stringContaining('own'),
      });
    });

    it('returns 409 when file has expiresAt set (temporary file)', async () => {
      const callerId = makeId();
      const team = makeTeam(teamId);
      const file = makeFile(callerId, { expiresAt: new Date(Date.now() + 3600_000) });
      const deps = makeDeps({
        findGroupById: jest.fn().mockResolvedValue(team),
        findFileById: jest.fn().mockResolvedValue(file),
      });
      const { add } = createTeamKnowledgeHandlers(deps);
      const req = makeReq({ id: teamId }, { fileId: file.file_id }, callerId);
      const res = makeRes();

      await add(req as unknown as import('~/types/http').ServerRequest, res);

      expect(res.status).toHaveBeenCalledWith(409);
      expect((res.json as jest.Mock).mock.calls[0][0]).toMatchObject({
        error: 'File must be saved (not temporary) before sharing',
      });
    });

    it('returns 403 when maxKnowledgeFilesPerTeam is configured and team is at limit', async () => {
      const callerId = makeId();
      const team = makeTeam(teamId);
      const file = makeFile(callerId);
      const existingEntry = makeAclEntry(new Types.ObjectId());
      const deps = makeDeps({
        findGroupById: jest.fn().mockResolvedValue(team),
        findFileById: jest.fn().mockResolvedValue(file),
        findEntriesByPrincipal: jest.fn().mockResolvedValue([existingEntry]),
      });
      const { add } = createTeamKnowledgeHandlers(deps);
      const req = makeReq({ id: teamId }, { fileId: file.file_id }, callerId);
      (req as unknown as Record<string, unknown>).config = {
        config: { teams: { maxKnowledgeFilesPerTeam: 1 } },
      };
      const res = makeRes();

      await add(req as unknown as import('~/types/http').ServerRequest, res);

      expect(res.status).toHaveBeenCalledWith(403);
      expect((res.json as jest.Mock).mock.calls[0][0]).toMatchObject({
        error: 'Team knowledge limit reached',
      });
      expect(deps.grantPermission).not.toHaveBeenCalled();
    });

    it('proceeds when maxKnowledgeFilesPerTeam is configured and team is below limit', async () => {
      const callerId = makeId();
      const team = makeTeam(teamId);
      const file = makeFile(callerId);
      const deps = makeDeps({
        findGroupById: jest.fn().mockResolvedValue(team),
        findFileById: jest.fn().mockResolvedValue(file),
        findEntriesByPrincipal: jest.fn().mockResolvedValue([]),
      });
      const { add } = createTeamKnowledgeHandlers(deps);
      const req = makeReq({ id: teamId }, { fileId: file.file_id }, callerId);
      (req as unknown as Record<string, unknown>).config = {
        config: { teams: { maxKnowledgeFilesPerTeam: 5 } },
      };
      const res = makeRes();

      await add(req as unknown as import('~/types/http').ServerRequest, res);

      expect(res.status).toHaveBeenCalledWith(201);
      expect(deps.grantPermission).toHaveBeenCalled();
    });

    it('proceeds when maxKnowledgeFilesPerTeam is not configured (unlimited)', async () => {
      const callerId = makeId();
      const team = makeTeam(teamId);
      const file = makeFile(callerId);
      const deps = makeDeps({
        findGroupById: jest.fn().mockResolvedValue(team),
        findFileById: jest.fn().mockResolvedValue(file),
      });
      const { add } = createTeamKnowledgeHandlers(deps);
      const req = makeReq({ id: teamId }, { fileId: file.file_id }, callerId);
      const res = makeRes();

      await add(req as unknown as import('~/types/http').ServerRequest, res);

      expect(res.status).toHaveBeenCalledWith(201);
    });
  });

  describe('list (GET /:id/knowledge)', () => {
    it('returns file list for a member', async () => {
      const callerId = makeId();
      const team = makeTeam(teamId);
      const file = makeFile(callerId);
      const entry = makeAclEntry(file._id as Types.ObjectId);
      const deps = makeDeps({
        findGroupById: jest.fn().mockResolvedValue(team),
        getTeamRole: jest.fn().mockResolvedValue('member' as TeamRole),
        findEntriesByPrincipal: jest.fn().mockResolvedValue([entry]),
        getFiles: jest.fn().mockResolvedValue([file]),
      });
      const { list } = createTeamKnowledgeHandlers(deps);
      const req = makeReq({ id: teamId }, {}, callerId);
      const res = makeRes();

      await list(req as unknown as import('~/types/http').ServerRequest, res);

      expect(res.status).toHaveBeenCalledWith(200);
      const body = (res.json as jest.Mock).mock.calls[0][0];
      expect(body.files).toHaveLength(1);
      expect(body.files[0]).toHaveProperty('file_id', file.file_id);
      expect(body.files[0]).not.toHaveProperty('user');
      expect(body.files[0]).not.toHaveProperty('filepath');
    });

    it('returns 404 for non-member', async () => {
      const callerId = makeId();
      const deps = makeDeps({
        findGroupById: jest.fn().mockResolvedValue(null),
        getTeamRole: jest.fn().mockResolvedValue(null),
      });
      const { list } = createTeamKnowledgeHandlers(deps);
      const req = makeReq({ id: teamId }, {}, callerId);
      const res = makeRes();

      await list(req as unknown as import('~/types/http').ServerRequest, res);

      expect(res.status).toHaveBeenCalledWith(404);
    });

    it('returns empty array when no ACL entries exist', async () => {
      const callerId = makeId();
      const team = makeTeam(teamId);
      const deps = makeDeps({
        findGroupById: jest.fn().mockResolvedValue(team),
        getTeamRole: jest.fn().mockResolvedValue('member' as TeamRole),
        findEntriesByPrincipal: jest.fn().mockResolvedValue([]),
      });
      const { list } = createTeamKnowledgeHandlers(deps);
      const req = makeReq({ id: teamId }, {}, callerId);
      const res = makeRes();

      await list(req as unknown as import('~/types/http').ServerRequest, res);

      expect(res.status).toHaveBeenCalledWith(200);
      expect((res.json as jest.Mock).mock.calls[0][0]).toEqual({ files: [] });
    });
  });

  describe('remove (DELETE /:id/knowledge/:fileId)', () => {
    it('revokes team grant and returns 200', async () => {
      const callerId = makeId();
      const team = makeTeam(teamId);
      const file = makeFile(callerId);
      const deps = makeDeps({
        findGroupById: jest.fn().mockResolvedValue(team),
        findFileById: jest.fn().mockResolvedValue(file),
      });
      const { remove } = createTeamKnowledgeHandlers(deps);
      const req = makeReq({ id: teamId, fileId: file.file_id }, {}, callerId);
      const res = makeRes();

      await remove(req as unknown as import('~/types/http').ServerRequest, res);

      expect(res.status).toHaveBeenCalledWith(200);
      expect(deps.revokePermission).toHaveBeenCalledWith(
        PrincipalType.GROUP,
        teamId,
        'file',
        file._id,
      );
    });

    it('returns 404 when file not found', async () => {
      const callerId = makeId();
      const team = makeTeam(teamId);
      const deps = makeDeps({
        findGroupById: jest.fn().mockResolvedValue(team),
        findFileById: jest.fn().mockResolvedValue(null),
      });
      const { remove } = createTeamKnowledgeHandlers(deps);
      const req = makeReq({ id: teamId, fileId: 'no-file' }, {}, callerId);
      const res = makeRes();

      await remove(req as unknown as import('~/types/http').ServerRequest, res);

      expect(res.status).toHaveBeenCalledWith(404);
    });

    it('returns 403 when caller is only a member (not admin)', async () => {
      const callerId = makeId();
      const team = makeTeam(teamId);
      const deps = makeDeps({
        findGroupById: jest.fn().mockResolvedValue(team),
        getTeamRole: jest.fn().mockResolvedValue('member' as TeamRole),
      });
      const { remove } = createTeamKnowledgeHandlers(deps);
      const req = makeReq({ id: teamId, fileId: 'some-file' }, {}, callerId);
      const res = makeRes();

      await remove(req as unknown as import('~/types/http').ServerRequest, res);

      expect(res.status).toHaveBeenCalledWith(403);
    });

    it('returns 404 when team not found', async () => {
      const callerId = makeId();
      const deps = makeDeps({
        findGroupById: jest.fn().mockResolvedValue(null),
        getTeamRole: jest.fn().mockResolvedValue(null),
      });
      const { remove } = createTeamKnowledgeHandlers(deps);
      const req = makeReq({ id: teamId, fileId: 'some-file' }, {}, callerId);
      const res = makeRes();

      await remove(req as unknown as import('~/types/http').ServerRequest, res);

      expect(res.status).toHaveBeenCalledWith(404);
    });
  });
});
