import { createTeamKnowledgeHandlers } from './knowledge';
import type { TeamKnowledgeHandlersDeps } from './knowledge';
import type { IGroup, IMongoFile, IAclEntry, TeamRole } from '@librechat/data-schemas';
import { Types } from 'mongoose';
import { PrincipalType } from 'librechat-data-provider';

type FileTarget =
  | { type: 'team' }
  | { type: 'subgroup'; id: string; name: string };

function makeSubgroup(id: string, parentTeamId: string): IGroup {
  return {
    _id: new Types.ObjectId(id),
    name: 'Sub-group Alpha',
    kind: 'team_subgroup',
    parentTeamId: new Types.ObjectId(parentTeamId),
    members: [],
    memberIds: [],
  } as unknown as IGroup;
}

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
    getSubgroupById: jest.fn().mockResolvedValue(null),
    getTeamSubgroups: jest.fn().mockResolvedValue([]),
    getUserTeamPrincipals: jest.fn().mockResolvedValue([]),
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
        getTeamSubgroups: jest.fn().mockResolvedValue([]),
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
        getTeamSubgroups: jest.fn().mockResolvedValue([]),
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

    it('counts sub-group grants toward per-team total cap', async () => {
      const callerId = makeId();
      const sgId = makeId();
      const team = makeTeam(teamId);
      const file = makeFile(callerId);
      const subgroup = makeSubgroup(sgId, teamId);
      const existingSubgroupEntry = makeAclEntry(new Types.ObjectId());
      const deps = makeDeps({
        findGroupById: jest.fn().mockResolvedValue(team),
        findFileById: jest.fn().mockResolvedValue(file),
        getTeamSubgroups: jest.fn().mockResolvedValue([subgroup]),
        // Team principal has 0 grants; sub-group has 1 — total = 1 = limit → reject
        findEntriesByPrincipal: jest
          .fn()
          .mockResolvedValueOnce([])
          .mockResolvedValueOnce([existingSubgroupEntry]),
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

    it('grants to sub-group principal when valid targetSubgroupId provided', async () => {
      const callerId = makeId();
      const sgId = makeId();
      const team = makeTeam(teamId);
      const file = makeFile(callerId);
      const subgroup = makeSubgroup(sgId, teamId);
      const deps = makeDeps({
        findGroupById: jest.fn().mockResolvedValue(team),
        findFileById: jest.fn().mockResolvedValue(file),
        getSubgroupById: jest.fn().mockResolvedValue(subgroup),
      });
      const { add } = createTeamKnowledgeHandlers(deps);
      const req = makeReq({ id: teamId }, { fileId: file.file_id, targetSubgroupId: sgId }, callerId);
      const res = makeRes();

      await add(req as unknown as import('~/types/http').ServerRequest, res);

      expect(res.status).toHaveBeenCalledWith(201);
      const call = (deps.grantPermission as jest.Mock).mock.calls[0][0];
      expect(call.principalId).toBe(sgId);
    });

    it('returns 404 when targetSubgroupId belongs to a different team', async () => {
      const callerId = makeId();
      const sgId = makeId();
      const otherTeamId = makeId();
      const team = makeTeam(teamId);
      const file = makeFile(callerId);
      const subgroup = makeSubgroup(sgId, otherTeamId);
      const deps = makeDeps({
        findGroupById: jest.fn().mockResolvedValue(team),
        findFileById: jest.fn().mockResolvedValue(file),
        getSubgroupById: jest.fn().mockResolvedValue(subgroup),
      });
      const { add } = createTeamKnowledgeHandlers(deps);
      const req = makeReq({ id: teamId }, { fileId: file.file_id, targetSubgroupId: sgId }, callerId);
      const res = makeRes();

      await add(req as unknown as import('~/types/http').ServerRequest, res);

      expect(res.status).toHaveBeenCalledWith(404);
      expect(deps.grantPermission).not.toHaveBeenCalled();
    });

    it('returns 404 when targetSubgroupId does not exist', async () => {
      const callerId = makeId();
      const team = makeTeam(teamId);
      const file = makeFile(callerId);
      const deps = makeDeps({
        findGroupById: jest.fn().mockResolvedValue(team),
        findFileById: jest.fn().mockResolvedValue(file),
        getSubgroupById: jest.fn().mockResolvedValue(null),
      });
      const { add } = createTeamKnowledgeHandlers(deps);
      const req = makeReq({ id: teamId }, { fileId: file.file_id, targetSubgroupId: makeId() }, callerId);
      const res = makeRes();

      await add(req as unknown as import('~/types/http').ServerRequest, res);

      expect(res.status).toHaveBeenCalledWith(404);
      expect(deps.grantPermission).not.toHaveBeenCalled();
    });
  });

  describe('list (GET /:id/knowledge)', () => {
    it('returns file list for a member', async () => {
      const callerId = makeId();
      const team = makeTeam(teamId);
      const file = makeFile(callerId);
      const teamObjId = new Types.ObjectId(teamId);
      const entry: IAclEntry = {
        ...makeAclEntry(file._id as Types.ObjectId),
        principalId: teamObjId,
      };
      const deps = makeDeps({
        findGroupById: jest.fn().mockResolvedValue(team),
        getTeamRole: jest.fn().mockResolvedValue('member' as TeamRole),
        getUserTeamPrincipals: jest.fn().mockResolvedValue([teamId]),
        getTeamSubgroups: jest.fn().mockResolvedValue([]),
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
        getUserTeamPrincipals: jest.fn().mockResolvedValue([teamId]),
      });
      const { list } = createTeamKnowledgeHandlers(deps);
      const req = makeReq({ id: teamId }, {}, callerId);
      const res = makeRes();

      await list(req as unknown as import('~/types/http').ServerRequest, res);

      expect(res.status).toHaveBeenCalledWith(200);
      expect((res.json as jest.Mock).mock.calls[0][0]).toEqual({ files: [] });
    });

    describe('access matrix — caller-scoped with target annotation', () => {
      const ownerId = makeId();
      const m1Id = makeId();
      const m2Id = makeId();
      const sgAId = makeId();
      const sgBId = makeId();

      function makeSubgroupA(): IGroup {
        return {
          _id: new Types.ObjectId(sgAId),
          name: 'Sub-group A',
          kind: 'team_subgroup',
          parentTeamId: new Types.ObjectId(teamId),
          members: [],
          memberIds: [],
        } as unknown as IGroup;
      }

      function makeSubgroupB(): IGroup {
        return {
          _id: new Types.ObjectId(sgBId),
          name: 'Sub-group B',
          kind: 'team_subgroup',
          parentTeamId: new Types.ObjectId(teamId),
          members: [],
          memberIds: [],
        } as unknown as IGroup;
      }

      function makeTeamFile(userId: string): IMongoFile {
        return makeFile(userId, { file_id: `f-team-${userId}`, filename: 'f-team.pdf' });
      }
      function makeFileA(userId: string): IMongoFile {
        return makeFile(userId, { file_id: `f-A-${userId}`, filename: 'f-A.pdf' });
      }
      function makeFileB(userId: string): IMongoFile {
        return makeFile(userId, { file_id: `f-B-${userId}`, filename: 'f-B.pdf' });
      }

      function makeAclEntryForPrincipal(
        resourceId: Types.ObjectId,
        principalId: Types.ObjectId,
      ): IAclEntry {
        return {
          _id: new Types.ObjectId(),
          principalType: PrincipalType.GROUP,
          principalId,
          resourceType: 'file',
          resourceId,
          permBits: 1,
          grantedBy: new Types.ObjectId(),
          grantedAt: new Date(),
        } as unknown as IAclEntry;
      }

      it('member m1 (in sub-group A) sees F-team and F-A but NOT F-B, each with correct target', async () => {
        const team = makeTeam(teamId);
        const sgA = makeSubgroupA();
        const sgB = makeSubgroupB();
        const fTeam = makeTeamFile(ownerId);
        const fA = makeFileA(ownerId);
        const fB = makeFileB(ownerId);

        const teamObjId = new Types.ObjectId(teamId);
        const sgAObjId = new Types.ObjectId(sgAId);
        const sgBObjId = new Types.ObjectId(sgBId);

        const entryTeam = makeAclEntryForPrincipal(fTeam._id as Types.ObjectId, teamObjId);
        const entryA = makeAclEntryForPrincipal(fA._id as Types.ObjectId, sgAObjId);

        const deps = makeDeps({
          findGroupById: jest.fn().mockResolvedValue(team),
          getTeamRole: jest.fn().mockResolvedValue('member' as TeamRole),
          getUserTeamPrincipals: jest.fn().mockResolvedValue([teamId, sgAId]),
          getTeamSubgroups: jest.fn().mockResolvedValue([sgA, sgB]),
          findEntriesByPrincipal: jest
            .fn()
            .mockResolvedValueOnce([entryTeam])
            .mockResolvedValueOnce([entryA]),
          getFiles: jest.fn().mockImplementation(({ _id }: { _id: { $in: Types.ObjectId[] } }) => {
            const allFiles = [fTeam, fA, fB];
            return Promise.resolve(
              allFiles.filter((f) =>
                _id.$in.some((id: Types.ObjectId) => id.equals(f._id as Types.ObjectId)),
              ),
            );
          }),
        });

        const { list } = createTeamKnowledgeHandlers(deps);
        const req = makeReq({ id: teamId }, {}, m1Id);
        const res = makeRes();

        await list(req as unknown as import('~/types/http').ServerRequest, res);

        expect(res.status).toHaveBeenCalledWith(200);
        const body = (res.json as jest.Mock).mock.calls[0][0];
        const fileIds = body.files.map((f: { file_id: string }) => f.file_id);
        expect(fileIds).toContain(fTeam.file_id);
        expect(fileIds).toContain(fA.file_id);
        expect(fileIds).not.toContain(fB.file_id);

        const fTeamEntry = body.files.find((f: { file_id: string }) => f.file_id === fTeam.file_id);
        const fAEntry = body.files.find((f: { file_id: string }) => f.file_id === fA.file_id);
        expect(fTeamEntry.target).toEqual({ type: 'team' });
        expect(fAEntry.target).toEqual({ type: 'subgroup', id: sgAId, name: 'Sub-group A' });
      });

      it('member m2 (in sub-group B) sees F-team and F-B but NOT F-A, each with correct target', async () => {
        const team = makeTeam(teamId);
        const sgA = makeSubgroupA();
        const sgB = makeSubgroupB();
        const fTeam = makeTeamFile(ownerId);
        const fA = makeFileA(ownerId);
        const fB = makeFileB(ownerId);

        const teamObjId = new Types.ObjectId(teamId);
        const sgBObjId = new Types.ObjectId(sgBId);

        const entryTeam = makeAclEntryForPrincipal(fTeam._id as Types.ObjectId, teamObjId);
        const entryB = makeAclEntryForPrincipal(fB._id as Types.ObjectId, sgBObjId);

        const deps = makeDeps({
          findGroupById: jest.fn().mockResolvedValue(team),
          getTeamRole: jest.fn().mockResolvedValue('member' as TeamRole),
          getUserTeamPrincipals: jest.fn().mockResolvedValue([teamId, sgBId]),
          getTeamSubgroups: jest.fn().mockResolvedValue([sgA, sgB]),
          findEntriesByPrincipal: jest
            .fn()
            .mockResolvedValueOnce([entryTeam])
            .mockResolvedValueOnce([entryB]),
          getFiles: jest.fn().mockImplementation(({ _id }: { _id: { $in: Types.ObjectId[] } }) => {
            const allFiles = [fTeam, fA, fB];
            return Promise.resolve(
              allFiles.filter((f) =>
                _id.$in.some((id: Types.ObjectId) => id.equals(f._id as Types.ObjectId)),
              ),
            );
          }),
        });

        const { list } = createTeamKnowledgeHandlers(deps);
        const req = makeReq({ id: teamId }, {}, m2Id);
        const res = makeRes();

        await list(req as unknown as import('~/types/http').ServerRequest, res);

        expect(res.status).toHaveBeenCalledWith(200);
        const body = (res.json as jest.Mock).mock.calls[0][0];
        const fileIds = body.files.map((f: { file_id: string }) => f.file_id);
        expect(fileIds).toContain(fTeam.file_id);
        expect(fileIds).toContain(fB.file_id);
        expect(fileIds).not.toContain(fA.file_id);

        const fTeamEntry = body.files.find((f: { file_id: string }) => f.file_id === fTeam.file_id);
        const fBEntry = body.files.find((f: { file_id: string }) => f.file_id === fB.file_id);
        expect(fTeamEntry.target).toEqual({ type: 'team' });
        expect(fBEntry.target).toEqual({ type: 'subgroup', id: sgBId, name: 'Sub-group B' });
      });

      it('owner sees all three files (F-team, F-A, F-B) with correct per-grant target annotation', async () => {
        const team = makeTeam(teamId);
        const sgA = makeSubgroupA();
        const sgB = makeSubgroupB();
        const fTeam = makeTeamFile(ownerId);
        const fA = makeFileA(ownerId);
        const fB = makeFileB(ownerId);

        const teamObjId = new Types.ObjectId(teamId);
        const sgAObjId = new Types.ObjectId(sgAId);
        const sgBObjId = new Types.ObjectId(sgBId);

        const entryTeam = makeAclEntryForPrincipal(fTeam._id as Types.ObjectId, teamObjId);
        const entryA = makeAclEntryForPrincipal(fA._id as Types.ObjectId, sgAObjId);
        const entryB = makeAclEntryForPrincipal(fB._id as Types.ObjectId, sgBObjId);

        const deps = makeDeps({
          findGroupById: jest.fn().mockResolvedValue(team),
          getTeamRole: jest.fn().mockResolvedValue('owner' as TeamRole),
          getTeamSubgroups: jest.fn().mockResolvedValue([sgA, sgB]),
          findEntriesByPrincipal: jest
            .fn()
            .mockResolvedValueOnce([entryTeam])
            .mockResolvedValueOnce([entryA])
            .mockResolvedValueOnce([entryB]),
          getFiles: jest.fn().mockImplementation(({ _id }: { _id: { $in: Types.ObjectId[] } }) => {
            const allFiles = [fTeam, fA, fB];
            return Promise.resolve(
              allFiles.filter((f) =>
                _id.$in.some((id: Types.ObjectId) => id.equals(f._id as Types.ObjectId)),
              ),
            );
          }),
        });

        const { list } = createTeamKnowledgeHandlers(deps);
        const req = makeReq({ id: teamId }, {}, ownerId);
        const res = makeRes();

        await list(req as unknown as import('~/types/http').ServerRequest, res);

        expect(res.status).toHaveBeenCalledWith(200);
        const body = (res.json as jest.Mock).mock.calls[0][0];
        const fileIds = body.files.map((f: { file_id: string }) => f.file_id);
        expect(fileIds).toContain(fTeam.file_id);
        expect(fileIds).toContain(fA.file_id);
        expect(fileIds).toContain(fB.file_id);

        const fTeamEntry = body.files.find((f: { file_id: string }) => f.file_id === fTeam.file_id);
        const fAEntry = body.files.find((f: { file_id: string }) => f.file_id === fA.file_id);
        const fBEntry = body.files.find((f: { file_id: string }) => f.file_id === fB.file_id);
        expect(fTeamEntry.target).toEqual({ type: 'team' });
        expect(fAEntry.target).toEqual({ type: 'subgroup', id: sgAId, name: 'Sub-group A' });
        expect(fBEntry.target).toEqual({ type: 'subgroup', id: sgBId, name: 'Sub-group B' });
      });

      it('resource granted to both team and sub-group A appears as two rows', async () => {
        const team = makeTeam(teamId);
        const sgA = makeSubgroupA();
        const sgB = makeSubgroupB();
        const fShared = makeTeamFile(ownerId);

        const teamObjId = new Types.ObjectId(teamId);
        const sgAObjId = new Types.ObjectId(sgAId);

        const entryTeam = makeAclEntryForPrincipal(fShared._id as Types.ObjectId, teamObjId);
        const entryA = makeAclEntryForPrincipal(fShared._id as Types.ObjectId, sgAObjId);

        const deps = makeDeps({
          findGroupById: jest.fn().mockResolvedValue(team),
          getTeamRole: jest.fn().mockResolvedValue('owner' as TeamRole),
          getTeamSubgroups: jest.fn().mockResolvedValue([sgA, sgB]),
          findEntriesByPrincipal: jest
            .fn()
            .mockResolvedValueOnce([entryTeam])
            .mockResolvedValueOnce([entryA])
            .mockResolvedValueOnce([]),
          getFiles: jest.fn().mockResolvedValue([fShared]),
        });

        const { list } = createTeamKnowledgeHandlers(deps);
        const req = makeReq({ id: teamId }, {}, ownerId);
        const res = makeRes();

        await list(req as unknown as import('~/types/http').ServerRequest, res);

        expect(res.status).toHaveBeenCalledWith(200);
        const body = (res.json as jest.Mock).mock.calls[0][0];
        expect(body.files).toHaveLength(2);
        const targets = body.files.map((f: { target: FileTarget }) => f.target);
        expect(targets).toContainEqual({ type: 'team' });
        expect(targets).toContainEqual({ type: 'subgroup', id: sgAId, name: 'Sub-group A' });
      });
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

    it('revokes from sub-group principal when valid targetSubgroupId in query', async () => {
      const callerId = makeId();
      const sgId = makeId();
      const team = makeTeam(teamId);
      const file = makeFile(callerId);
      const subgroup = makeSubgroup(sgId, teamId);
      const deps = makeDeps({
        findGroupById: jest.fn().mockResolvedValue(team),
        findFileById: jest.fn().mockResolvedValue(file),
        getSubgroupById: jest.fn().mockResolvedValue(subgroup),
      });
      const { remove } = createTeamKnowledgeHandlers(deps);
      const req = {
        params: { id: teamId, fileId: file.file_id },
        body: {},
        query: { targetSubgroupId: sgId },
        user: { id: callerId },
      };
      const res = makeRes();

      await remove(req as unknown as import('~/types/http').ServerRequest, res);

      expect(res.status).toHaveBeenCalledWith(200);
      expect(deps.revokePermission).toHaveBeenCalledWith(
        PrincipalType.GROUP,
        sgId,
        'file',
        file._id,
      );
    });

    it('returns 404 when targetSubgroupId in query does not belong to this team', async () => {
      const callerId = makeId();
      const sgId = makeId();
      const otherTeamId = makeId();
      const team = makeTeam(teamId);
      const file = makeFile(callerId);
      const subgroup = makeSubgroup(sgId, otherTeamId);
      const deps = makeDeps({
        findGroupById: jest.fn().mockResolvedValue(team),
        findFileById: jest.fn().mockResolvedValue(file),
        getSubgroupById: jest.fn().mockResolvedValue(subgroup),
      });
      const { remove } = createTeamKnowledgeHandlers(deps);
      const req = {
        params: { id: teamId, fileId: file.file_id },
        body: {},
        query: { targetSubgroupId: sgId },
        user: { id: callerId },
      };
      const res = makeRes();

      await remove(req as unknown as import('~/types/http').ServerRequest, res);

      expect(res.status).toHaveBeenCalledWith(404);
      expect(deps.revokePermission).not.toHaveBeenCalled();
    });

    it('returns 404 when targetSubgroupId in query does not exist (null from db)', async () => {
      const callerId = makeId();
      const team = makeTeam(teamId);
      const file = makeFile(callerId);
      const deps = makeDeps({
        findGroupById: jest.fn().mockResolvedValue(team),
        findFileById: jest.fn().mockResolvedValue(file),
        getSubgroupById: jest.fn().mockResolvedValue(null),
      });
      const { remove } = createTeamKnowledgeHandlers(deps);
      const req = {
        params: { id: teamId, fileId: file.file_id },
        body: {},
        query: { targetSubgroupId: makeId() },
        user: { id: callerId },
      };
      const res = makeRes();

      await remove(req as unknown as import('~/types/http').ServerRequest, res);

      expect(res.status).toHaveBeenCalledWith(404);
      expect(deps.revokePermission).not.toHaveBeenCalled();
    });
  });
});
