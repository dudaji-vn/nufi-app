jest.mock('@librechat/data-schemas', () => ({
  logger: { error: jest.fn() },
}));

jest.mock('@librechat/agents/langchain/tools', () => ({
  tool: jest.fn(() => ({})),
}));

jest.mock('@librechat/api', () => ({
  generateShortLivedToken: jest.fn(() => 'mock-token'),
}));

jest.mock('~/server/services/Files/permissions', () => ({
  filterFilesByAgentAccess: jest.fn(),
  getTeamSharedFileIds: jest.fn(),
}));

jest.mock('~/models', () => ({
  getFiles: jest.fn(),
}));

const { logger } = require('@librechat/data-schemas');
const {
  filterFilesByAgentAccess,
  getTeamSharedFileIds,
} = require('~/server/services/Files/permissions');
const { getFiles } = require('~/models');
const { primeFiles } = require('./fileSearch');

const USER_ID = 'user-abc';
const AGENT_ID = 'agent_test-123';
const AGENT_FILE_ID = 'agent-file-1';
const TEAM_FILE_ID = 'team-file-shared';

function makeReq(overrides = {}) {
  return { user: { id: USER_ID, role: 'USER' }, ...overrides };
}

function makeToolResources(fileIds = []) {
  return { file_search: { file_ids: fileIds } };
}

beforeEach(() => {
  jest.clearAllMocks();
  filterFilesByAgentAccess.mockImplementation(({ files }) => Promise.resolve(files));
  getTeamSharedFileIds.mockResolvedValue([]);
  getFiles.mockResolvedValue([]);
});

describe('primeFiles — team file union', () => {
  it('includes team-shared file_ids in the candidate set passed to getFiles', async () => {
    getTeamSharedFileIds.mockResolvedValue([TEAM_FILE_ID]);
    getFiles.mockResolvedValue([
      { file_id: AGENT_FILE_ID, filename: 'agent.txt' },
      { file_id: TEAM_FILE_ID, filename: 'team.txt' },
    ]);

    await primeFiles({
      req: makeReq(),
      tool_resources: makeToolResources([AGENT_FILE_ID]),
      agentId: AGENT_ID,
    });

    expect(getFiles).toHaveBeenCalledWith(
      { file_id: { $in: expect.arrayContaining([AGENT_FILE_ID, TEAM_FILE_ID]) } },
      null,
      { text: 0 },
    );
  });

  it('deduplicates file_ids when team returns an id already in agent tool_resources', async () => {
    getTeamSharedFileIds.mockResolvedValue([AGENT_FILE_ID]);
    getFiles.mockResolvedValue([{ file_id: AGENT_FILE_ID, filename: 'agent.txt' }]);

    await primeFiles({
      req: makeReq(),
      tool_resources: makeToolResources([AGENT_FILE_ID]),
      agentId: AGENT_ID,
    });

    const calledWith = getFiles.mock.calls[0][0];
    const ids = calledWith.file_id.$in;
    expect(ids.filter((id) => id === AGENT_FILE_ID)).toHaveLength(1);
  });

  it('falls back to agent file_ids only when getTeamSharedFileIds throws', async () => {
    getTeamSharedFileIds.mockRejectedValue(new Error('ACL service down'));
    getFiles.mockResolvedValue([{ file_id: AGENT_FILE_ID, filename: 'agent.txt' }]);

    await primeFiles({
      req: makeReq(),
      tool_resources: makeToolResources([AGENT_FILE_ID]),
      agentId: AGENT_ID,
    });

    expect(logger.error).toHaveBeenCalledWith(
      expect.stringContaining('[primeFiles]'),
      expect.any(Error),
    );
    const calledWith = getFiles.mock.calls[0][0];
    expect(calledWith.file_id.$in).toEqual([AGENT_FILE_ID]);
  });

  it('skips getTeamSharedFileIds when req.user.id is absent', async () => {
    getFiles.mockResolvedValue([{ file_id: AGENT_FILE_ID, filename: 'agent.txt' }]);

    await primeFiles({
      req: { user: {} },
      tool_resources: makeToolResources([AGENT_FILE_ID]),
      agentId: AGENT_ID,
    });

    expect(getTeamSharedFileIds).not.toHaveBeenCalled();
    const calledWith = getFiles.mock.calls[0][0];
    expect(calledWith.file_id.$in).toEqual([AGENT_FILE_ID]);
  });

  it('returns both agent and team files in the output when filterFilesByAgentAccess passes them', async () => {
    const agentFile = { file_id: AGENT_FILE_ID, filename: 'agent.txt' };
    const teamFile = { file_id: TEAM_FILE_ID, filename: 'team.txt' };

    getTeamSharedFileIds.mockResolvedValue([TEAM_FILE_ID]);
    getFiles.mockResolvedValue([agentFile, teamFile]);
    filterFilesByAgentAccess.mockResolvedValue([agentFile, teamFile]);

    const { files } = await primeFiles({
      req: makeReq(),
      tool_resources: makeToolResources([AGENT_FILE_ID]),
      agentId: AGENT_ID,
    });

    const ids = files.map((f) => f.file_id);
    expect(ids).toContain(AGENT_FILE_ID);
    expect(ids).toContain(TEAM_FILE_ID);
  });
});
