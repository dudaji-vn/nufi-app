jest.mock('@librechat/data-schemas', () => ({
  logger: { error: jest.fn() },
}));

jest.mock('~/server/services/PermissionService', () => ({
  checkPermission: jest.fn(),
  getResourcePermissionsMap: jest.fn(),
  findAccessibleResources: jest.fn(),
}));

jest.mock('~/models', () => ({
  getAgent: jest.fn(),
  getFiles: jest.fn(),
}));

jest.mock('mongoose', () => {
  const actual = jest.requireActual('mongoose');
  return {
    ...actual,
    Types: {
      ObjectId: {
        isValid: (id) =>
          id != null && typeof id.toString === 'function' && id.toString().length > 0,
      },
    },
  };
});

const { logger } = require('@librechat/data-schemas');
const { Constants, PermissionBits, ResourceType } = require('librechat-data-provider');
const {
  checkPermission,
  getResourcePermissionsMap,
  findAccessibleResources,
} = require('~/server/services/PermissionService');
const { getAgent, getFiles } = require('~/models');
const {
  filterFilesByAgentAccess,
  hasAccessToFilesViaAgent,
  getTeamSharedFileIds,
} = require('./permissions');

const AUTHOR_ID = 'author-user-id';
const USER_ID = 'viewer-user-id';
const AGENT_ID = 'agent_test-abc123';
const AGENT_MONGO_ID = 'mongo-agent-id';

function makeFile(file_id, user, _id) {
  return { _id: _id ?? file_id, file_id, user, filename: `${file_id}.txt` };
}

function makeAgent(overrides = {}) {
  return {
    _id: AGENT_MONGO_ID,
    id: AGENT_ID,
    author: AUTHOR_ID,
    tool_resources: {
      file_search: { file_ids: ['attached-1', 'attached-2'] },
      execute_code: { file_ids: ['attached-3'] },
    },
    ...overrides,
  };
}

beforeEach(() => {
  jest.clearAllMocks();
  getFiles.mockResolvedValue([
    makeFile('attached-1', AUTHOR_ID),
    makeFile('attached-2', AUTHOR_ID),
    makeFile('attached-3', AUTHOR_ID),
    makeFile('not-attached', AUTHOR_ID),
  ]);
  // Default: no direct ACL grants
  getResourcePermissionsMap.mockResolvedValue(new Map());
});

describe('filterFilesByAgentAccess', () => {
  describe('early returns (no DB calls)', () => {
    it('should return files unfiltered for ephemeral agentId', async () => {
      const files = [makeFile('f1', 'other-user')];
      const result = await filterFilesByAgentAccess({
        files,
        userId: USER_ID,
        agentId: Constants.EPHEMERAL_AGENT_ID,
      });

      expect(result).toBe(files);
      expect(getAgent).not.toHaveBeenCalled();
    });

    it('should return files unfiltered for non-agent_ prefixed agentId', async () => {
      const files = [makeFile('f1', 'other-user')];
      const result = await filterFilesByAgentAccess({
        files,
        userId: USER_ID,
        agentId: 'custom-memory-id',
      });

      expect(result).toBe(files);
      expect(getAgent).not.toHaveBeenCalled();
    });

    it('should return files when userId is missing', async () => {
      const files = [makeFile('f1', 'someone')];
      const result = await filterFilesByAgentAccess({
        files,
        userId: undefined,
        agentId: AGENT_ID,
      });

      expect(result).toBe(files);
      expect(getAgent).not.toHaveBeenCalled();
    });

    it('should return files when agentId is missing', async () => {
      const files = [makeFile('f1', 'someone')];
      const result = await filterFilesByAgentAccess({
        files,
        userId: USER_ID,
        agentId: undefined,
      });

      expect(result).toBe(files);
      expect(getAgent).not.toHaveBeenCalled();
    });

    it('should return empty array when files is empty', async () => {
      const result = await filterFilesByAgentAccess({
        files: [],
        userId: USER_ID,
        agentId: AGENT_ID,
      });

      expect(result).toEqual([]);
      expect(getAgent).not.toHaveBeenCalled();
    });

    it('should return undefined when files is nullish', async () => {
      const result = await filterFilesByAgentAccess({
        files: null,
        userId: USER_ID,
        agentId: AGENT_ID,
      });

      expect(result).toBeNull();
      expect(getAgent).not.toHaveBeenCalled();
    });
  });

  describe('all files owned by userId', () => {
    it('should return all files without calling getAgent', async () => {
      const files = [makeFile('f1', USER_ID), makeFile('f2', USER_ID)];
      const result = await filterFilesByAgentAccess({
        files,
        userId: USER_ID,
        agentId: AGENT_ID,
      });

      expect(result).toEqual(files);
      expect(getAgent).not.toHaveBeenCalled();
    });
  });

  describe('mixed owned and non-owned files', () => {
    const ownedFile = makeFile('owned-1', USER_ID);
    const sharedFile = makeFile('attached-1', AUTHOR_ID);
    const unattachedFile = makeFile('not-attached', AUTHOR_ID);

    it('should return owned + accessible non-owned files when user has VIEW', async () => {
      getAgent.mockResolvedValue(makeAgent());
      checkPermission.mockResolvedValue(true);

      const result = await filterFilesByAgentAccess({
        files: [ownedFile, sharedFile, unattachedFile],
        userId: USER_ID,
        role: 'USER',
        agentId: AGENT_ID,
      });

      expect(result).toHaveLength(2);
      expect(result.map((f) => f.file_id)).toContain('owned-1');
      expect(result.map((f) => f.file_id)).toContain('attached-1');
      expect(result.map((f) => f.file_id)).not.toContain('not-attached');
    });

    it('should not return a file referenced from an agent that is not authored by the file owner', async () => {
      getAgent.mockResolvedValue(makeAgent({ author: USER_ID }));
      checkPermission.mockResolvedValue(true);

      const result = await filterFilesByAgentAccess({
        files: [sharedFile],
        userId: USER_ID,
        role: 'USER',
        agentId: AGENT_ID,
      });

      expect(result).toEqual([]);
    });

    it('should return only owned files when user lacks VIEW permission', async () => {
      getAgent.mockResolvedValue(makeAgent());
      checkPermission.mockResolvedValue(false);

      const result = await filterFilesByAgentAccess({
        files: [ownedFile, sharedFile],
        userId: USER_ID,
        role: 'USER',
        agentId: AGENT_ID,
      });

      expect(result).toEqual([ownedFile]);
    });

    it('should return only owned files when agent is not found', async () => {
      getAgent.mockResolvedValue(null);

      const result = await filterFilesByAgentAccess({
        files: [ownedFile, sharedFile],
        userId: USER_ID,
        agentId: AGENT_ID,
      });

      expect(result).toEqual([ownedFile]);
    });

    it('should return only owned files on DB error (fail-closed)', async () => {
      getAgent.mockRejectedValue(new Error('DB connection lost'));

      const result = await filterFilesByAgentAccess({
        files: [ownedFile, sharedFile],
        userId: USER_ID,
        agentId: AGENT_ID,
      });

      expect(result).toEqual([ownedFile]);
      expect(logger.error).toHaveBeenCalled();
    });
  });

  describe('file with no user field', () => {
    it('should exclude the file even when attached to the agent', async () => {
      const noUserFile = makeFile('attached-1', undefined);
      getAgent.mockResolvedValue(makeAgent());
      checkPermission.mockResolvedValue(true);

      const result = await filterFilesByAgentAccess({
        files: [noUserFile],
        userId: USER_ID,
        role: 'USER',
        agentId: AGENT_ID,
      });

      expect(getAgent).toHaveBeenCalled();
      expect(result).toEqual([]);
    });

    it('should exclude file with no user field when not attached to agent', async () => {
      const noUserFile = makeFile('not-attached', null);
      getAgent.mockResolvedValue(makeAgent());
      checkPermission.mockResolvedValue(true);

      const result = await filterFilesByAgentAccess({
        files: [noUserFile],
        userId: USER_ID,
        role: 'USER',
        agentId: AGENT_ID,
      });

      expect(result).toEqual([]);
    });
  });

  describe('no owned files (all non-owned)', () => {
    const file1 = makeFile('attached-1', AUTHOR_ID);
    const file2 = makeFile('not-attached', AUTHOR_ID);

    it('should return only attached files when user has VIEW', async () => {
      getAgent.mockResolvedValue(makeAgent());
      checkPermission.mockResolvedValue(true);

      const result = await filterFilesByAgentAccess({
        files: [file1, file2],
        userId: USER_ID,
        role: 'USER',
        agentId: AGENT_ID,
      });

      expect(result).toEqual([file1]);
    });

    it('should return empty array when no VIEW permission', async () => {
      getAgent.mockResolvedValue(makeAgent());
      checkPermission.mockResolvedValue(false);

      const result = await filterFilesByAgentAccess({
        files: [file1, file2],
        userId: USER_ID,
        agentId: AGENT_ID,
      });

      expect(result).toEqual([]);
    });

    it('should return empty array when agent not found', async () => {
      getAgent.mockResolvedValue(null);

      const result = await filterFilesByAgentAccess({
        files: [file1],
        userId: USER_ID,
        agentId: AGENT_ID,
      });

      expect(result).toEqual([]);
    });
  });

  describe('FILE ACL VIEW fallback (D15)', () => {
    const ACL_FILE_ID = 'acl-granted-file';
    const ACL_MONGO_ID = 'mongo-acl-file-id';
    const NO_GRANT_FILE_ID = 'no-grant-file';
    const NO_GRANT_MONGO_ID = 'mongo-no-grant-id';

    it('returns a file the user has a direct FILE ACL VIEW grant on even when not owned and not agent-attached', async () => {
      const aclFile = makeFile(ACL_FILE_ID, AUTHOR_ID, ACL_MONGO_ID);
      const noGrantFile = makeFile(NO_GRANT_FILE_ID, AUTHOR_ID, NO_GRANT_MONGO_ID);

      getAgent.mockResolvedValue(makeAgent());
      // No agent VIEW permission — agent path returns false for both
      checkPermission.mockResolvedValue(false);
      // FILE ACL: aclFile has VIEW bits, noGrantFile has none
      getResourcePermissionsMap.mockResolvedValue(new Map([[ACL_MONGO_ID, PermissionBits.VIEW]]));

      const result = await filterFilesByAgentAccess({
        files: [aclFile, noGrantFile],
        userId: USER_ID,
        role: 'USER',
        agentId: AGENT_ID,
      });

      expect(result).toHaveLength(1);
      expect(result[0].file_id).toBe(ACL_FILE_ID);
      expect(getResourcePermissionsMap).toHaveBeenCalledWith(
        expect.objectContaining({
          userId: USER_ID,
          role: 'USER',
          resourceType: ResourceType.FILE,
        }),
      );
    });

    it('does not return a file that has no grant, is not owned, and is not agent-attached', async () => {
      const noGrantFile = makeFile(NO_GRANT_FILE_ID, AUTHOR_ID, NO_GRANT_MONGO_ID);

      getAgent.mockResolvedValue(makeAgent());
      checkPermission.mockResolvedValue(false);
      // No entries in permissions map
      getResourcePermissionsMap.mockResolvedValue(new Map());

      const result = await filterFilesByAgentAccess({
        files: [noGrantFile],
        userId: USER_ID,
        role: 'USER',
        agentId: AGENT_ID,
      });

      expect(result).toEqual([]);
    });

    it('includes owned + agent-accessible + ACL-granted files additively', async () => {
      const ownedFile = makeFile('owned-1', USER_ID, 'mongo-owned-1');
      const agentFile = makeFile('attached-1', AUTHOR_ID, 'mongo-attached-1');
      const aclFile = makeFile(ACL_FILE_ID, AUTHOR_ID, ACL_MONGO_ID);

      getAgent.mockResolvedValue(makeAgent());
      checkPermission.mockResolvedValue(true);
      getResourcePermissionsMap.mockResolvedValue(new Map([[ACL_MONGO_ID, PermissionBits.VIEW]]));

      const result = await filterFilesByAgentAccess({
        files: [ownedFile, agentFile, aclFile],
        userId: USER_ID,
        role: 'USER',
        agentId: AGENT_ID,
      });

      const ids = result.map((f) => f.file_id);
      expect(ids).toContain('owned-1');
      expect(ids).toContain('attached-1');
      expect(ids).toContain(ACL_FILE_ID);
      expect(result).toHaveLength(3);
    });

    it('falls back gracefully (excludes ACL files) when getResourcePermissionsMap throws', async () => {
      const aclFile = makeFile(ACL_FILE_ID, AUTHOR_ID, ACL_MONGO_ID);

      getAgent.mockResolvedValue(makeAgent());
      checkPermission.mockResolvedValue(false);
      getResourcePermissionsMap.mockRejectedValue(new Error('DB error'));

      const result = await filterFilesByAgentAccess({
        files: [aclFile],
        userId: USER_ID,
        role: 'USER',
        agentId: AGENT_ID,
      });

      expect(result).toEqual([]);
      expect(logger.error).toHaveBeenCalledWith(
        '[filterFilesByAgentAccess] Error checking FILE ACL:',
        expect.any(Error),
      );
    });
  });
});

describe('hasAccessToFilesViaAgent', () => {
  describe('agent not found', () => {
    it('should return all-false map', async () => {
      getAgent.mockResolvedValue(null);

      const result = await hasAccessToFilesViaAgent({
        userId: USER_ID,
        fileIds: ['f1', 'f2'],
        agentId: AGENT_ID,
      });

      expect(result.get('f1')).toBe(false);
      expect(result.get('f2')).toBe(false);
    });
  });

  describe('author path', () => {
    it('should grant access to attached files for the agent author', async () => {
      getAgent.mockResolvedValue(makeAgent());

      const result = await hasAccessToFilesViaAgent({
        userId: AUTHOR_ID,
        fileIds: ['attached-1', 'not-attached'],
        agentId: AGENT_ID,
      });

      expect(result.get('attached-1')).toBe(true);
      expect(result.get('not-attached')).toBe(false);
      expect(checkPermission).not.toHaveBeenCalled();
    });

    it('should deny attached files not owned by the agent author', async () => {
      getAgent.mockResolvedValue(makeAgent({ author: USER_ID }));
      getFiles.mockResolvedValue([makeFile('attached-1', AUTHOR_ID)]);

      const result = await hasAccessToFilesViaAgent({
        userId: USER_ID,
        fileIds: ['attached-1'],
        agentId: AGENT_ID,
      });

      expect(result.get('attached-1')).toBe(false);
    });
  });

  describe('VIEW permission path', () => {
    it('should grant access to attached files for viewer with VIEW permission', async () => {
      getAgent.mockResolvedValue(makeAgent());
      checkPermission.mockResolvedValue(true);

      const result = await hasAccessToFilesViaAgent({
        userId: USER_ID,
        role: 'USER',
        fileIds: ['attached-1', 'attached-3', 'not-attached'],
        agentId: AGENT_ID,
      });

      expect(result.get('attached-1')).toBe(true);
      expect(result.get('attached-3')).toBe(true);
      expect(result.get('not-attached')).toBe(false);

      expect(checkPermission).toHaveBeenCalledWith({
        userId: USER_ID,
        role: 'USER',
        resourceType: ResourceType.AGENT,
        resourceId: AGENT_MONGO_ID,
        requiredPermission: PermissionBits.VIEW,
      });
    });

    it('should deny all when VIEW permission is missing', async () => {
      getAgent.mockResolvedValue(makeAgent());
      checkPermission.mockResolvedValue(false);

      const result = await hasAccessToFilesViaAgent({
        userId: USER_ID,
        fileIds: ['attached-1'],
        agentId: AGENT_ID,
      });

      expect(result.get('attached-1')).toBe(false);
    });
  });

  describe('delete path (EDIT permission required)', () => {
    it('should grant access when both VIEW and EDIT pass', async () => {
      getAgent.mockResolvedValue(makeAgent());
      checkPermission.mockResolvedValueOnce(true).mockResolvedValueOnce(true);

      const result = await hasAccessToFilesViaAgent({
        userId: USER_ID,
        fileIds: ['attached-1'],
        agentId: AGENT_ID,
        isDelete: true,
      });

      expect(result.get('attached-1')).toBe(true);
      expect(checkPermission).toHaveBeenCalledTimes(2);
      expect(checkPermission).toHaveBeenLastCalledWith(
        expect.objectContaining({ requiredPermission: PermissionBits.EDIT }),
      );
    });

    it('should deny all when VIEW passes but EDIT fails', async () => {
      getAgent.mockResolvedValue(makeAgent());
      checkPermission.mockResolvedValueOnce(true).mockResolvedValueOnce(false);

      const result = await hasAccessToFilesViaAgent({
        userId: USER_ID,
        fileIds: ['attached-1'],
        agentId: AGENT_ID,
        isDelete: true,
      });

      expect(result.get('attached-1')).toBe(false);
    });
  });

  describe('error handling', () => {
    it('should return all-false map on DB error (fail-closed)', async () => {
      getAgent.mockRejectedValue(new Error('connection refused'));

      const result = await hasAccessToFilesViaAgent({
        userId: USER_ID,
        fileIds: ['f1', 'f2'],
        agentId: AGENT_ID,
      });

      expect(result.get('f1')).toBe(false);
      expect(result.get('f2')).toBe(false);
      expect(logger.error).toHaveBeenCalledWith(
        '[hasAccessToFilesViaAgent] Error checking file access:',
        expect.any(Error),
      );
    });
  });

  describe('agent with no tool_resources', () => {
    it('should deny all files even for the author', async () => {
      getAgent.mockResolvedValue(makeAgent({ tool_resources: undefined }));

      const result = await hasAccessToFilesViaAgent({
        userId: AUTHOR_ID,
        fileIds: ['f1'],
        agentId: AGENT_ID,
      });

      expect(result.get('f1')).toBe(false);
    });
  });
});

describe('getTeamSharedFileIds', () => {
  const TEAM_FILE_ID = 'team-file-123';
  const TEAM_MONGO_ID = 'mongo-team-file-id';

  beforeEach(() => {
    jest.clearAllMocks();
    findAccessibleResources.mockResolvedValue([]);
    getFiles.mockResolvedValue([]);
  });

  it('returns file_ids for embedded files the user has VIEW access to via FILE ACL', async () => {
    findAccessibleResources.mockResolvedValue([TEAM_MONGO_ID]);
    getFiles.mockResolvedValue([{ file_id: TEAM_FILE_ID }]);

    const result = await getTeamSharedFileIds(USER_ID, 'USER');

    expect(findAccessibleResources).toHaveBeenCalledWith({
      userId: USER_ID,
      role: 'USER',
      resourceType: ResourceType.FILE,
      requiredPermissions: PermissionBits.VIEW,
    });
    expect(getFiles).toHaveBeenCalledWith({ _id: { $in: [TEAM_MONGO_ID] }, embedded: true }, null, {
      file_id: 1,
    });
    expect(result).toEqual([TEAM_FILE_ID]);
  });

  it('excludes granted but non-embedded files (embedded:true filter in the query)', async () => {
    findAccessibleResources.mockResolvedValue([TEAM_MONGO_ID]);
    // getFiles with embedded:true returns nothing — simulates a non-embedded file being excluded
    getFiles.mockResolvedValue([]);

    const result = await getTeamSharedFileIds(USER_ID, 'USER');

    expect(getFiles).toHaveBeenCalledWith({ _id: { $in: [TEAM_MONGO_ID] }, embedded: true }, null, {
      file_id: 1,
    });
    expect(result).toEqual([]);
  });

  it('returns [] when the user has no ACL grants', async () => {
    findAccessibleResources.mockResolvedValue([]);

    const result = await getTeamSharedFileIds(USER_ID, 'USER');

    expect(getFiles).not.toHaveBeenCalled();
    expect(result).toEqual([]);
  });

  it('returns [] when findAccessibleResources returns an empty array (no grants)', async () => {
    findAccessibleResources.mockResolvedValue([]);

    const result = await getTeamSharedFileIds('other-user', undefined);

    expect(result).toEqual([]);
  });
});
